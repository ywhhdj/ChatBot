//! 有界流：无 GIL 的 mpsc + 背压 + 暂停/恢复/取消。
//!
//! R10：
//! * 结束判定用 `AtomicBool`，**不用 sentinel 占槽位** ——
//!   sentinel 会和数据抢容量，drain 时还容易把未消费数据冲掉（之前踩过）。
//! * 容量有界，producer 在满时阻塞（背压），避免内存膨胀。

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use pyo3::prelude::*;

use crate::error::CoreError;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamState {
    Open,
    Paused,
    Closed,
}

pub struct StreamInner {
    queue: VecDeque<Vec<u8>>, // 以序列化后的字节承载，避免泛型跨 FFI
    capacity: usize,
    state: StreamState,
    producer_done: bool,
    error: Option<String>,
}

/// 一个流通道。producer 端与 consumer 端共享 `Arc<Stream>`。
pub struct Stream {
    inner: Mutex<StreamInner>,
    cv: Condvar,
    /// 结束标志，与队列容量解耦（R10）
    done: AtomicBool,
    cancelled: AtomicBool,
}

impl Stream {
    pub fn new(capacity: usize) -> Arc<Self> {
        Arc::new(Self {
            inner: Mutex::new(StreamInner {
                queue: VecDeque::new(),
                capacity: capacity.max(1),
                state: StreamState::Open,
                producer_done: false,
                error: None,
            }),
            cv: Condvar::new(),
            done: AtomicBool::new(false),
            cancelled: AtomicBool::new(false),
        })
    }

    /// producer 推一条。队列满则阻塞（背压），可超时。
    pub fn push(&self, bytes: Vec<u8>, timeout: Option<Duration>) -> Result<(), CoreError> {
        let deadline = timeout.map(|t| Instant::now() + t);
        let mut g = self.inner.lock().unwrap();
        loop {
            if self.cancelled.load(Ordering::SeqCst) {
                return Err(CoreError::Cancelled("stream".into()));
            }
            if g.state == StreamState::Closed {
                return Err(CoreError::Cancelled("stream closed".into()));
            }
            if g.queue.len() < g.capacity {
                g.queue.push_back(bytes);
                self.cv.notify_all();
                return Ok(());
            }
            if let Some(dl) = deadline {
                let remain = dl.saturating_duration_since(Instant::now());
                if remain.is_zero() {
                    return Err(CoreError::Timeout("stream push".into()));
                }
                let (ng, _t) = self.cv.wait_timeout(g, remain.min(Duration::from_millis(100))).unwrap();
                g = ng;
            } else {
                let (ng, _t) = self.cv.wait_timeout(g, Duration::from_millis(100)).unwrap();
                g = ng;
            }
        }
    }

    /// consumer 取一条。`Ok(None)` 表示 producer 已结束且队列空。
    pub fn pop(&self, timeout: Option<Duration>) -> Result<Option<Vec<u8>>, CoreError> {
        let deadline = timeout.map(|t| Instant::now() + t);
        let mut g = self.inner.lock().unwrap();
        loop {
            if let Some(item) = g.queue.pop_front() {
                self.cv.notify_all();
                return Ok(Some(item));
            }
            if let Some(e) = &g.error {
                return Err(CoreError::Python(e.clone()));
            }
            if g.producer_done || self.done.load(Ordering::SeqCst) {
                return Ok(None);
            }
            if self.cancelled.load(Ordering::SeqCst) {
                return Err(CoreError::Cancelled("stream".into()));
            }
            let wait = match deadline {
                Some(dl) => {
                    let remain = dl.saturating_duration_since(Instant::now());
                    if remain.is_zero() {
                        return Err(CoreError::Timeout("stream pop".into()));
                    }
                    remain.min(Duration::from_millis(50))
                }
                None => Duration::from_millis(50),
            };
            let (ng, _t) = self.cv.wait_timeout(g, wait).unwrap();
            g = ng;
        }
    }

    /// 非阻塞尝试取一条。
    pub fn try_pop(&self) -> Option<Vec<u8>> {
        let mut g = self.inner.lock().unwrap();
        let item = g.queue.pop_front();
        if item.is_some() {
            self.cv.notify_all();
        }
        item
    }
    /// 结束流，可指定错误信息。
    pub fn finish(&self) {
        let mut g = self.inner.lock().unwrap();
        g.producer_done = true;
        self.done.store(true, Ordering::SeqCst);
        self.cv.notify_all();
    }

    /// 错误结束流，可指定错误信息。
    pub fn fail(&self, msg: String) {
        let mut g = self.inner.lock().unwrap();
        g.error = Some(msg);
        g.producer_done = true;
        self.done.store(true, Ordering::SeqCst);
        self.cv.notify_all();
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
        let mut g = self.inner.lock().unwrap();
        g.state = StreamState::Closed;
        g.queue.clear();
        self.cv.notify_all();
    }

    pub fn pause(&self) {
        let mut g = self.inner.lock().unwrap();
        g.state = StreamState::Paused;
    }

    pub fn resume(&self) {
        let mut g = self.inner.lock().unwrap();
        if g.state == StreamState::Paused {
            g.state = StreamState::Open;
        }
        self.cv.notify_all();
    }

    pub fn is_done(&self) -> bool {
        self.done.load(Ordering::SeqCst)
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::SeqCst)
    }

    pub fn len(&self) -> usize {
        self.inner.lock().unwrap().queue.len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Python 可见的流。
#[pyclass]
pub struct PyStream {
    inner: Arc<Stream>,
}

#[pymethods]
impl PyStream {
    #[new]
    #[pyo3(signature = (capacity=64))]
    fn new(capacity: usize) -> Self {
        Self { inner: Stream::new(capacity) }
    }

    /// R4：push 可能阻塞（背压），释放 GIL。
    #[pyo3(signature = (item, timeout=None))]
    fn push(&self, py: Python<'_>, item: Vec<u8>, timeout: Option<f64>) -> PyResult<()> {
        let r = py.allow_threads(|| {
            self.inner.push(
                item,
                timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64),
            )
        });
        r.map_err(Into::into)
    }

    /// R4：pop 可能阻塞，释放 GIL。
    #[pyo3(signature = (timeout=None))]
    fn pop(&self, py: Python<'_>, timeout: Option<f64>) -> PyResult<Option<Vec<u8>>> {
        let r = py.allow_threads(|| {
            self.inner
                .pop(timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64))
        });
        r.map_err(Into::into)
    }

    fn try_pop(&self) -> Option<Vec<u8>> {
        self.inner.try_pop()
    }

    fn finish(&self) {
        self.inner.finish()
    }

    fn fail(&self, msg: String) {
        self.inner.fail(msg)
    }

    fn cancel(&self) {
        self.inner.cancel()
    }

    fn pause(&self) {
        self.inner.pause()
    }

    fn resume(&self) {
        self.inner.resume()
    }

    fn is_done(&self) -> bool {
        self.inner.is_done()
    }

    fn len(&self) -> usize {
        self.inner.len()
    }
}