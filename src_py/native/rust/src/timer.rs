//! 定时器与防抖。
//!
//! R12：输入防抖现在是 `threading.Timer` + 回投 loop，
//! 每个连接一个 Python 线程。改到这里后：一个 Rust 定时线程管所有到期，
//! 不占 Python 线程，精度也更稳。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use pyo3::prelude::*;

type TimerId = u64;

struct Entry {
    id: TimerId,
    /// 到期时刻
    deadline: Instant,
    /// 硬上限：即使持续输入也必须在此时刻触发
    hard_deadline: Instant,
    callback: Py<PyAny>,
    payload: Py<PyAny>,
    /// 防抖窗口：被 `touch` 时顺延
    window: Duration,
}

struct TimerInner {
    /// 按 hard_deadline 排序的最小堆（用 Vec 简化，条目数很小）
    entries: Vec<Entry>,
    next_id: TimerId,
}

pub struct TimerWheel {
    inner: Mutex<TimerInner>,
    cv: Condvar,
    closed: AtomicBool,
    fired: AtomicU64,
}

impl TimerWheel {
    pub fn new() -> Arc<Self> {
        let t = Arc::new(Self {
            inner: Mutex::new(TimerInner { entries: Vec::new(), next_id: 1 }),
            cv: Condvar::new(),
            closed: AtomicBool::new(false),
            fired: AtomicU64::new(0),
        });
        t.spawn_worker();
        t
    }

    fn spawn_worker(self: &Arc<Self>) {
        let this = self.clone();
        thread::Builder::new()
            .name("chatbot-timer".into())
            .spawn(move || {
                while !this.closed.load(Ordering::SeqCst) {
                    let mut g = this.inner.lock().unwrap();
                    // 等到最近一个到期时刻
                    let wait = if g.entries.is_empty() {
                        Duration::from_millis(200)
                    } else {
                        let now = Instant::now();
                        let next = g
                            .entries
                            .iter()
                            .map(|e| if e.deadline > now { e.deadline - now } else { Duration::ZERO })
                            .min()
                            .unwrap_or(Duration::from_millis(50));
                        next.max(Duration::from_millis(1))
                    };
                    let (ng, _t) = this.cv.wait_timeout(g, wait).unwrap();
                    g = ng;

                    let now = Instant::now();
                    // 取出到期项
                    let mut fired = Vec::new();
                    let mut keep = Vec::new();
                    for e in g.entries.drain(..) {
                        if e.deadline <= now || e.hard_deadline <= now {
                            fired.push(e);
                        } else {
                            keep.push(e);
                        }
                    }
                    g.entries = keep;
                    drop(g);

                    if !fired.is_empty() {
                        this.fired.fetch_add(fired.len() as u64, Ordering::Relaxed);
                        // R5：回调 Python 必须重新拿 GIL
                        Python::with_gil(|py| {
                            for e in fired {
                                if let Err(err) = e.callback.bind(py).call1((e.payload.clone_ref(py),)) {
                                    err.print(py);
                                }
                            }
                        });
                    }
                }
            })
            .expect("spawn timer");
    }

    /// 注册一个防抖定时器。
    pub fn debounce(
        &self,
        window_ms: u64,
        max_wait_ms: u64,
        callback: Py<PyAny>,
        payload: Py<PyAny>,
    ) -> TimerId {
        let mut g = self.inner.lock().unwrap();
        let id = g.next_id;
        g.next_id += 1;
        let now = Instant::now();
        g.entries.push(Entry {
            id,
            deadline: now + Duration::from_millis(window_ms),
            hard_deadline: now + Duration::from_millis(max_wait_ms.max(window_ms)),
            callback,
            payload,
            window: Duration::from_millis(window_ms),
        });
        self.cv.notify_all();
        id
    }

    /// 顺延（用户还在连续输入）。已触发则返回 false。
    pub fn touch(&self, id: TimerId) -> bool {
        let mut g = self.inner.lock().unwrap();
        for e in g.entries.iter_mut() {
            if e.id == id {
                let now = Instant::now();
                let proposed = now + e.window;
                // 不能超过硬上限，否则连续输入永远不触发
                if proposed < e.hard_deadline {
                    e.deadline = proposed;
                }
                return true;
            }
        }
        false
    }

    /// 立即触发（不等到期）。
    pub fn flush(&self, id: TimerId) {
        let mut g = self.inner.lock().unwrap();
        for e in g.entries.iter_mut() {
            if e.id == id {
                e.deadline = Instant::now();
            }
        }
        self.cv.notify_all();
    }

    pub fn cancel(&self, id: TimerId) -> bool {
        let mut g = self.inner.lock().unwrap();
        let before = g.entries.len();
        g.entries.retain(|e| e.id != id);
        let removed = g.entries.len() != before;
        if removed {
            self.cv.notify_all();
        }
        removed
    }

    pub fn pending(&self) -> usize {
        self.inner.lock().unwrap().entries.len()
    }

    pub fn fired_count(&self) -> u64 {
        self.fired.load(Ordering::Relaxed)
    }

    pub fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
        self.cv.notify_all();
    }
}

/// 全局定时器。
static GLOBAL: Mutex<Option<Arc<TimerWheel>>> = Mutex::new(None);

pub fn global_timer() -> Arc<TimerWheel> {
    let mut g = GLOBAL.lock().unwrap();
    if g.is_none() {
        *g = Some(TimerWheel::new());
    }
    g.as_ref().unwrap().clone()
}

#[pyclass]
pub struct PyTimer {
    wheel: Arc<TimerWheel>,
}

#[pymethods]
impl PyTimer {
    #[new]
    fn new() -> Self {
        Self { wheel: global_timer() }
    }

    fn debounce(
        &self,
        window_ms: u64,
        max_wait_ms: u64,
        callback: Py<PyAny>,
        payload: Py<PyAny>,
    ) -> u64 {
        self.wheel.debounce(window_ms, max_wait_ms, callback, payload)
    }

    fn touch(&self, id: u64) -> bool {
        self.wheel.touch(id)
    }

    fn flush(&self, id: u64) {
        self.wheel.flush(id)
    }

    fn cancel(&self, id: u64) -> bool {
        self.wheel.cancel(id)
    }

    fn pending(&self) -> usize {
        self.wheel.pending()
    }

    fn fired_count(&self) -> u64 {
        self.wheel.fired_count()
    }
}
