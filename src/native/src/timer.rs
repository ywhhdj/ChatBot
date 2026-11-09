//! 定时器与防抖。
//!
//! 输入防抖现在是 `threading.Timer` + 回投 loop，
//! 每个连接一个 Python 线程。改到这里后：一个 Rust 定时线程管所有到期，
//! 不占 Python 线程，精度也更稳。

use std::collections::{BTreeMap, HashMap};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use pyo3::prelude::*;

use crate::runtime::{lock_or_recover, Wake};

type TimerId = u64;

struct Entry {
    id: TimerId,
    /// 防抖窗口到期时刻（被 `touch` 顺延）
    deadline: Instant,
    /// 硬上限：即使持续输入也必须在此时刻触发
    hard_deadline: Instant,
    callback: Py<PyAny>,
    payload: Py<PyAny>,
    /// 防抖窗口长度
    window: Duration,
}

impl Entry {
    /// 实际触发时刻 = min(窗口到期, 硬上限)。
    /// 用这个值做 BTreeMap 的键，队首就是下一个要触发的定时器。
    fn effective(&self) -> Instant {
        if self.deadline < self.hard_deadline {
            self.deadline
        } else {
            self.hard_deadline
        }
    }
}

struct TimerInner {
    /// 按"实际触发时刻"排序；配合 index 做 O(log n) 的 touch / cancel / flush
    entries: BTreeMap<(Instant, TimerId), Entry>,
    /// id → 当前排序键（避免 touch 时线性查找）
    index: HashMap<TimerId, Instant>,
    next_id: TimerId,
}

pub struct TimerWheel {
    inner: Mutex<TimerInner>,
    wake: Wake,
    closed: AtomicBool,
    /// 定时线程是否在运行（用于"关闭后自动重启"）
    running: AtomicBool,
    /// 只允许一个线程执行 spawn
    spawn_lock: Mutex<()>,
    fired: AtomicU64,
}

impl TimerWheel {
    pub fn new() -> Arc<Self> {
        let t = Arc::new(Self {
            inner: Mutex::new(TimerInner {
                entries: BTreeMap::new(),
                index: HashMap::new(),
                next_id: 1,
            }),
            wake: Wake::new(),
            closed: AtomicBool::new(false),
            running: AtomicBool::new(false),
            spawn_lock: Mutex::new(()),
            fired: AtomicU64::new(0),
        });
        t.spawn_worker();
        t
    }

    fn spawn_worker(self: &Arc<Self>) {
        self.running.store(true, Ordering::Release);
        let this = self.clone();
        thread::Builder::new()
            .name("chatbot-timer".into())
            .spawn(move || {
                let mut last = this.wake.current();
                while !this.closed.load(Ordering::Acquire) {
                    // 精确睡到最近的到期时刻
                    let next = {
                        let g = lock_or_recover(&this.inner);
                        g.entries.keys().next().map(|k| k.0)
                    };
                    let wait = match next {
                        Some(t) => {
                            let now = Instant::now();
                            if t <= now {
                                Duration::ZERO
                            } else {
                                (t - now).min(Duration::from_millis(500))
                            }
                        }
                        None => Duration::from_millis(500),
                    };
                    if wait.is_zero() {
                        let due = this.take_due(Instant::now());
                        if due.is_empty() {
                            last = this.wake.wait(last, Duration::from_millis(20));
                        } else {
                            this.fire_all(due);
                        }
                        continue;
                    }
                    last = this.wake.wait(last, wait);
                    let due = this.take_due(Instant::now());
                    this.fire_all(due);
                }
                this.running.store(false, Ordering::Release);
            })
            .expect("spawn timer");
    }

    /// 关闭后再次注册时自动拉起定时线程（旧实现这里会永久失效）。
    fn ensure_worker(self: &Arc<Self>) {
        if self.running.load(Ordering::Acquire) && !self.closed.load(Ordering::Acquire) {
            return;
        }
        let _guard = lock_or_recover(&self.spawn_lock);
        if self.running.load(Ordering::Acquire) && !self.closed.load(Ordering::Acquire) {
            return;
        }
        self.closed.store(false, Ordering::Release);
        self.spawn_worker();
    }

    /// 取出所有已到期项（只碰队首，O(k log n)）。
    fn take_due(&self, now: Instant) -> Vec<Entry> {
        let mut g = lock_or_recover(&self.inner);
        let mut out = Vec::new();
        while let Some(key) = g.entries.keys().next().copied() {
            if key.0 > now {
                break;
            }
            if let Some(e) = g.entries.remove(&key) {
                g.index.remove(&e.id);
                out.push(e);
            }
        }
        out
    }

    fn fire_all(&self, entries: Vec<Entry>) {
        if entries.is_empty() {
            return;
        }
        self.fired.fetch_add(entries.len() as u64, Ordering::Relaxed);
        // R5：回调 Python 必须重新拿 GIL
        Python::with_gil(|py| {
            for e in entries {
                if let Err(err) = e.callback.bind(py).call1((e.payload.clone_ref(py),)) {
                    err.print(py);
                }
            }
        });
    }

    /// 注册一个防抖定时器。
    pub fn debounce(
        &self,
        window_ms: u64,
        max_wait_ms: u64,
        callback: Py<PyAny>,
        payload: Py<PyAny>,
    ) -> TimerId {
        let mut g = lock_or_recover(&self.inner);
        let id = g.next_id;
        g.next_id += 1;
        let now = Instant::now();
        let e = Entry {
            id,
            deadline: now + Duration::from_millis(window_ms),
            hard_deadline: now + Duration::from_millis(max_wait_ms.max(window_ms)),
            callback,
            payload,
            window: Duration::from_millis(window_ms),
        };
        let key = (e.effective(), id);
        g.index.insert(id, key.0);
        g.entries.insert(key, e);
        drop(g);
        self.wake.notify();
        id
    }

    /// 顺延（用户还在连续输入）。已触发或已取消则返回 false。
    pub fn touch(&self, id: TimerId) -> bool {
        let mut g = lock_or_recover(&self.inner);
        let old = match g.index.get(&id).copied() {
            Some(t) => t,
            None => return false,
        };
        let mut e = match g.entries.remove(&(old, id)) {
            Some(e) => e,
            None => {
                g.index.remove(&id);
                return false;
            }
        };
        let now = Instant::now();
        let proposed = now + e.window;
        // 不能超过硬上限，否则连续输入永远不触发
        if proposed < e.hard_deadline {
            e.deadline = proposed;
        }
        let new_key = e.effective();
        g.index.insert(id, new_key);
        g.entries.insert((new_key, id), e);
        true
    }

    /// 立即触发（不等到期）。返回是否命中。
    pub fn flush(&self, py: Python<'_>, id: TimerId) -> bool {
        let e = {
            let mut g = lock_or_recover(&self.inner);
            match g.index.remove(&id) {
                Some(t) => g.entries.remove(&(t, id)),
                None => None,
            }
        };
        match e {
            None => false,
            Some(e) => {
                self.fired.fetch_add(1, Ordering::Relaxed);
                if let Err(err) = e.callback.bind(py).call1((e.payload.clone_ref(py),)) {
                    err.print(py);
                }
                true
            }
        }
    }

    pub fn cancel(&self, id: TimerId) -> bool {
        let mut g = lock_or_recover(&self.inner);
        match g.index.remove(&id) {
            Some(t) => g.entries.remove(&(t, id)).is_some(),
            None => false,
        }
    }

    pub fn pending(&self) -> usize {
        lock_or_recover(&self.inner).entries.len()
    }

    pub fn fired_count(&self) -> u64 {
        self.fired.load(Ordering::Relaxed)
    }

    /// 关闭：停掉定时线程并清空未触发项（旧实现清了订阅但不停止线程，
    /// 且状态不可恢复）。
    pub fn close(&self) {
        self.closed.store(true, Ordering::Release);
        {
            let mut g = lock_or_recover(&self.inner);
            g.entries.clear();
            g.index.clear();
        }
        self.wake.notify();
    }

    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }
}

impl Drop for TimerWheel {
    fn drop(&mut self) {
        self.closed.store(true, Ordering::Release);
        self.wake.notify();
    }
}

/// 全局定时器。
static GLOBAL: Mutex<Option<Arc<TimerWheel>>> = Mutex::new(None);

pub fn global_timer() -> Arc<TimerWheel> {
    let mut g = lock_or_recover(&GLOBAL);
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
    #[pyo3(signature = (shared=true))]
    fn new(shared: bool) -> Self {
        let wheel = if shared { global_timer() } else { TimerWheel::new() };
        Self { wheel }
    }

    fn debounce(
        &self,
        window_ms: u64,
        max_wait_ms: u64,
        callback: Py<PyAny>,
        payload: Py<PyAny>,
    ) -> u64 {
        // 关过一次也能继续用：必要时重新拉起定时线程
        (&self.wheel).ensure_worker();
        self.wheel.debounce(window_ms, max_wait_ms, callback, payload)
    }

    fn touch(&self, id: u64) -> bool {
        self.wheel.touch(id)
    }

    fn flush(&self, py: Python<'_>, id: u64) -> bool {
        self.wheel.flush(py, id)
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

    fn close(&self) {
        self.wheel.close()
    }

    fn is_closed(&self) -> bool {
        self.wheel.is_closed()
    }
}
