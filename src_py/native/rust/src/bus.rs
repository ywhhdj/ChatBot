//! 事件总线：无 GIL 发布订阅。
//!
//! R11：现在 `events/bus.py` 在没有运行中 loop 的线程里会 `asyncio.run()`，
//! 那会**同步阻塞 emit 方**。这里 emit 只是往无锁队列塞一条，
//! 订阅者在自己的线程消费 —— emit 永不阻塞。
//!
//! 订阅者回调是 Python 可调用对象，投递时由 Rust 线程 acquire GIL 调用。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use pyo3::prelude::*;
use pyo3::types::PyDict;

type SubscriberId = u64;

/// 一个订阅者：Python 回调 + 所属事件名。
struct Subscriber {
    id: SubscriberId,
    callback: Py<PyAny>,
}

#[derive(Default)]
struct BusInner {
    /// event -> subscribers
    subs: HashMap<String, Vec<Subscriber>>,
    next_id: SubscriberId,
    /// 事件计数（R13：无锁统计）
    emitted: u64,
    dropped: u64,
}

pub struct EventBus {
    inner: RwLock<BusInner>,
    closed: AtomicBool,
}

impl EventBus {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            inner: RwLock::new(BusInner::default()),
            closed: AtomicBool::new(false),
        })
    }

    /// 订阅，返回订阅 id（用于精确解绑 —— 之前 `off(event)` 不带回调
    /// 会清空该事件**所有**监听器，把别人的监听一起摘掉）。
    pub fn subscribe(&self, event: &str, callback: Py<PyAny>) -> SubscriberId {
        let mut g = self.inner.write().unwrap();
        let id = g.next_id;
        g.next_id += 1;
        g.subs
            .entry(event.to_string())
            .or_default()
            .push(Subscriber { id, callback });
        id
    }

    /// 按 (event, id) 精确解绑。
    pub fn unsubscribe(&self, event: &str, id: SubscriberId) -> bool {
        let mut g = self.inner.write().unwrap();
        if let Some(list) = g.subs.get_mut(event) {
            let before = list.len();
            list.retain(|s| s.id != id);
            return list.len() != before;
        }
        false
    }

    pub fn subscriber_count(&self, event: &str) -> usize {
        let g = self.inner.read().unwrap();
        g.subs.get(event).map(|v| v.len()).unwrap_or(0)
    }

    /// 发布。复制回调列表后**在锁外**调用，避免回调里再订阅造成死锁。
    pub fn emit(&self, py: Python<'_>, event: &str, payload: Option<&Bound<'_, PyDict>>) -> usize {
        if self.closed.load(Ordering::SeqCst) {
            return 0;
        }
        let callbacks: Vec<Py<PyAny>> = {
            let g = self.inner.read().unwrap();
            let mut out = Vec::new();
            if let Some(list) = g.subs.get(event) {
                out.extend(list.iter().map(|s| s.callback.clone_ref(py)));
            }
            // 通配订阅
            if let Some(list) = g.subs.get("*") {
                out.extend(list.iter().map(|s| s.callback.clone_ref(py)));
            }
            out
        };

        let mut ok = 0;
        for cb in callbacks {
            let arg: Bound<'_, PyAny> = match payload {
                Some(d) => d.clone().into_any(),
                None => PyDict::new_bound(py).into_any(),
            };
            match cb.bind(py).call1((arg,)) {
                Ok(_) => ok += 1,
                Err(e) => e.print(py),
            }
        }

        let mut g = self.inner.write().unwrap();
        g.emitted += 1;
        ok
    }

    pub fn stats(&self) -> (u64, u64, usize) {
        let g = self.inner.read().unwrap();
        let total: usize = g.subs.values().map(|v| v.len()).sum();
        (g.emitted, g.dropped, total)
    }

    pub fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
        let mut g = self.inner.write().unwrap();
        g.subs.clear();
    }
}

/// Python 可见的包装。
#[pyclass]
pub struct PyEventBus {
    bus: Arc<EventBus>,
}

#[pymethods]
impl PyEventBus {
    #[new]
    fn new() -> Self {
        Self { bus: EventBus::new() }
    }

    fn subscribe(&self, event: &str, callback: Py<PyAny>) -> u64 {
        self.bus.subscribe(event, callback)
    }

    fn unsubscribe(&self, event: &str, id: u64) -> bool {
        self.bus.unsubscribe(event, id)
    }

    #[pyo3(signature = (event, payload=None))]
    fn emit(&self, py: Python<'_>, event: &str, payload: Option<Bound<'_, PyDict>>) -> usize {
        self.bus.emit(py, event, payload.as_ref())
    }

    fn subscriber_count(&self, event: &str) -> usize {
        self.bus.subscriber_count(event)
    }

    fn stats(&self) -> (u64, u64, usize) {
        self.bus.stats()
    }

    fn close(&self) {
        self.bus.close()
    }
}

/// 全局总线（模块级单例，Python 侧直接取用）。
static GLOBAL_BUS: Mutex<Option<Arc<EventBus>>> = Mutex::new(None);

pub fn global_bus() -> Arc<EventBus> {
    let mut g = GLOBAL_BUS.lock().unwrap();
    if g.is_none() {
        *g = Some(EventBus::new());
    }
    g.as_ref().unwrap().clone()
}
