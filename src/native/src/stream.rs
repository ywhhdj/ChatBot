//! 有界流：无 GIL 的 mpsc + 背压 + 暂停/恢复/取消。
//!：
//! * 结束判定用 `AtomicBool`，**不用 sentinel 占槽位** ——
//!   sentinel 会和数据抢容量，drain 时还容易把未消费数据冲掉（之前踩过）。
//! * 容量有界，producer 在满时阻塞（背压），避免内存膨胀。

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

use pyo3::prelude::*;

use crate::error::CoreError;
use crate::runtime::lock_or_recover;

/// 单次 wait 的上限：即使漏掉一次 notify，最多也只多睡这么久。
const WAIT_SLICE: Duration = Duration::from_millis(50);

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
    /// 数据到达 / 流结束 → 唤醒 consumer
    not_empty: Condvar,
    /// 队列腾出空间 / 流关闭 → 唤醒 producer
    not_full: Condvar,
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
            not_empty: Condvar::new(),
            not_full: Condvar::new(),
            done: AtomicBool::new(false),
            cancelled: AtomicBool::new(false),
        })
    }

    fn wait_slice(deadline: Option<Instant>) -> Duration {
        match deadline {
            Some(dl) => {
                let remain = dl.saturating_duration_since(Instant::now());
                if remain.is_zero() {
                    Duration::ZERO
                } else {
                    remain.min(WAIT_SLICE)
                }
            }
            None => WAIT_SLICE,
        }
    }

    /// producer 推一条。队列满则阻塞（背压），可超时。
    pub fn push(&self, bytes: Vec<u8>, timeout: Option<Duration>) -> Result<(), CoreError> {
        let deadline = timeout.map(|t| Instant::now() + t);
        let mut g = lock_or_recover(&self.inner);
        loop {
            if self.cancelled.load(Ordering::Acquire) {
                return Err(CoreError::Cancelled("stream".into()));
            }
            if g.state == StreamState::Closed {
                return Err(CoreError::Cancelled("stream closed".into()));
            }
            if g.producer_done {
                // 已经 finish 了还往里塞：数据永远不会被消费，直接报错
                return Err(CoreError::Invalid("流已结束，不能再 push"));
            }
            if g.queue.len() < g.capacity {
                g.queue.push_back(bytes);
                drop(g);
                self.not_empty.notify_one();
                return Ok(());
            }
            let wait = Self::wait_slice(deadline);
            if wait.is_zero() {
                return Err(CoreError::Timeout("stream push".into()));
            }
            // 背压：只等"队列腾出空间"这一条通道
            let (ng, _) = self
                .not_full
                .wait_timeout(g, wait)
                .unwrap_or_else(|p| p.into_inner());
            g = ng;
        }
    }

    /// consumer 取一条。`Ok(None)` 表示 producer 已结束且队列空。
    pub fn pop(&self, timeout: Option<Duration>) -> Result<Option<Vec<u8>>, CoreError> {
        let deadline = timeout.map(|t| Instant::now() + t);
        let mut g = lock_or_recover(&self.inner);
        loop {
            // 暂停：真的停住消费（旧实现里 Paused 没有任何效果）。
            // 流已结束时不再等待，否则会永久挂起。
            if g.state == StreamState::Paused && !g.producer_done && !self.done.load(Ordering::Acquire) {
                let wait = Self::wait_slice(deadline);
                if wait.is_zero() {
                    return Err(CoreError::Timeout("stream pop".into()));
                }
                let (ng, _) = self
                    .not_empty
                    .wait_timeout(g, wait)
                    .unwrap_or_else(|p| p.into_inner());
                g = ng;
                continue;
            }
            if let Some(item) = g.queue.pop_front() {
                drop(g);
                self.not_full.notify_one();
                return Ok(Some(item));
            }
            if let Some(e) = &g.error {
                return Err(CoreError::Python(e.clone()));
            }
            if g.producer_done || self.done.load(Ordering::Acquire) {
                return Ok(None);
            }
            if self.cancelled.load(Ordering::Acquire) {
                return Err(CoreError::Cancelled("stream".into()));
            }
            let wait = Self::wait_slice(deadline);
            if wait.is_zero() {
                return Err(CoreError::Timeout("stream pop".into()));
            }
            let (ng, _) = self
                .not_empty
                .wait_timeout(g, wait)
                .unwrap_or_else(|p| p.into_inner());
            g = ng;
        }
    }

    /// 非阻塞尝试取一条。
    pub fn try_pop(&self) -> Option<Vec<u8>> {
        let mut g = lock_or_recover(&self.inner);
        let item = g.queue.pop_front();
        if item.is_some() {
            drop(g);
            self.not_full.notify_one();
        }
        item
    }

    /// 正常结束流。
    pub fn finish(&self) {
        let mut g = lock_or_recover(&self.inner);
        g.producer_done = true;
        g.state = StreamState::Closed;
        self.done.store(true, Ordering::Release);
        drop(g);
        // 结束是全体事件：consumer 要醒（拿 None），producer 也要醒（拿到错误）
        self.not_empty.notify_all();
        self.not_full.notify_all();
    }

    /// 错误结束流。
    pub fn fail(&self, msg: String) {
        let mut g = lock_or_recover(&self.inner);
        g.error = Some(msg);
        g.producer_done = true;
        g.state = StreamState::Closed;
        self.done.store(true, Ordering::Release);
        drop(g);
        self.not_empty.notify_all();
        self.not_full.notify_all();
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
        let mut g = lock_or_recover(&self.inner);
        g.state = StreamState::Closed;
        g.queue.clear();
        drop(g);
        self.not_empty.notify_all();
        self.not_full.notify_all();
    }

    pub fn pause(&self) {
        let mut g = lock_or_recover(&self.inner);
        if g.state == StreamState::Open {
            g.state = StreamState::Paused;
        }
    }

    pub fn resume(&self) {
        let mut g = lock_or_recover(&self.inner);
        if g.state == StreamState::Paused {
            g.state = StreamState::Open;
        }
        drop(g);
        self.not_empty.notify_all();
    }

    pub fn is_done(&self) -> bool {
        self.done.load(Ordering::Acquire)
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }

    pub fn len(&self) -> usize {
        lock_or_recover(&self.inner).queue.len()
    }

    pub fn is_empty(&self) -> bool {
        lock_or_recover(&self.inner).queue.is_empty()
    }

    pub fn capacity(&self) -> usize {
        lock_or_recover(&self.inner).capacity
    }

    pub fn is_paused(&self) -> bool {
        lock_or_recover(&self.inner).state == StreamState::Paused
    }

    pub fn is_closed(&self) -> bool {
        lock_or_recover(&self.inner).state == StreamState::Closed
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

    /// push 可能阻塞（背压），释放 GIL。
    #[pyo3(signature = (item, timeout=None))]
    fn push(&self, py: Python<'_>, item: Vec<u8>, timeout: Option<f64>) -> PyResult<()> {
        let r = py.allow_threads(|| {
            self.inner
                .push(item, timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64))
        });
        r.map_err(Into::into)
    }

    /// pop 可能阻塞，释放 GIL。
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

    fn is_paused(&self) -> bool {
        self.inner.is_paused()
    }

    fn is_cancelled(&self) -> bool {
        self.inner.is_cancelled()
    }

    fn capacity(&self) -> usize {
        self.inner.capacity()
    }

    fn len(&self) -> usize {
        self.inner.len()
    }

    #[getter]
    fn closed(&self) -> bool {
        self.inner.is_closed()
    }
}
