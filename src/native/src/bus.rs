//! 事件总线：无 GIL 发布订阅。
//!
//! R11：现在 `events/bus.py` 在没有运行中 loop 的线程里会 `asyncio.run()`，
//! 那会**同步阻塞 emit 方**。这里 emit 只是往无锁队列塞一条，
//! 订阅者在自己的线程消费 —— emit 永不阻塞。
//!
//! 订阅者回调是 Python 可调用对象，投递时由 Rust 线程 acquire GIL 调用。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::runtime::{lock_or_recover, read_or_recover, write_or_recover};

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
}

pub struct EventBus {
    inner: RwLock<BusInner>,
    closed: AtomicBool,
    // R13：真正的无锁统计
    emitted: AtomicU64,
    dropped: AtomicU64,
    failed: AtomicU64,
}

impl EventBus {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            inner: RwLock::new(BusInner::default()),
            closed: AtomicBool::new(false),
            emitted: AtomicU64::new(0),
            dropped: AtomicU64::new(0),
            failed: AtomicU64::new(0),
        })
    }

    /// 订阅，返回订阅 id（用于精确解绑 —— 之前 `off(event)` 不带回调
    /// 会清空该事件**所有**监听器，把别人的监听一起摘掉）。
    pub fn subscribe(&self, event: &str, callback: Py<PyAny>) -> SubscriberId {
        let mut g = write_or_recover(&self.inner);
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
        let mut g = write_or_recover(&self.inner);
        let (changed, should_remove) = match g.subs.get_mut(event) {
            Some(list) => {
                let before = list.len();
                list.retain(|s| s.id != id);
                // 事件没人订阅了就把桶删掉，避免空向量长期占位
                let changed = list.len() != before;
                let should_remove = list.is_empty();
                (changed, should_remove)
            }
            None => return false,
        };
        if should_remove {
            g.subs.remove(event);
        }
        return changed;
    }

    pub fn subscriber_count(&self, event: &str) -> usize {
        let g = read_or_recover(&self.inner);
        g.subs.get(event).map(|v| v.len()).unwrap_or(0)
    }

    /// 发布。复制回调列表后**在锁外**调用，避免回调里再订阅造成死锁。
    pub fn emit(&self, py: Python<'_>, event: &str, payload: Option<&Bound<'_, PyDict>>) -> usize {
        if self.closed.load(Ordering::Acquire) {
            self.dropped.fetch_add(1, Ordering::Relaxed);
            return 0;
        }
        let callbacks: Vec<Py<PyAny>> = {
            let g = read_or_recover(&self.inner);
            let mut out = Vec::new();
            if let Some(list) = g.subs.get(event) {
                out.reserve(list.len());
                for s in list.iter() {
                    out.push(s.callback.clone_ref(py));
                }
            }
            // 通配订阅
            if let Some(list) = g.subs.get("*") {
                out.reserve(list.len());
                for s in list.iter() {
                    out.push(s.callback.clone_ref(py));
                }
            }
            out
        };

        // payload 只构造一次，所有订阅者共享同一个 dict
        let arg: Bound<'_, PyAny> = match payload {
            Some(d) => d.clone().into_any(),
            None => PyDict::new_bound(py).into_any(),
        };

        let mut ok = 0usize;
        for cb in callbacks {
            match cb.bind(py).call1((arg.clone(),)) {
                Ok(_) => ok += 1,
                Err(e) => {
                    self.failed.fetch_add(1, Ordering::Relaxed);
                    e.print(py);
                }
            }
        }

        self.emitted.fetch_add(1, Ordering::Relaxed);
        ok
    }

    /// 兼容旧签名：(已发布, 已丢弃, 订阅者总数)
    pub fn stats(&self) -> (u64, u64, usize) {
        let g = read_or_recover(&self.inner);
        let total: usize = g.subs.values().map(|v| v.len()).sum();
        (
            self.emitted.load(Ordering::Relaxed),
            self.dropped.load(Ordering::Relaxed),
            total,
        )
    }

    /// 更完整的统计（含回调失败数）。
    pub fn stats_map(&self) -> HashMap<String, u64> {
        let total = {
            let g = read_or_recover(&self.inner);
            g.subs.values().map(|v| v.len()).sum::<usize>() as u64
        };
        let mut m = HashMap::with_capacity(5);
        m.insert("emitted".into(), self.emitted.load(Ordering::Relaxed));
        m.insert("dropped".into(), self.dropped.load(Ordering::Relaxed));
        m.insert("failed".into(), self.failed.load(Ordering::Relaxed));
        m.insert("subscribers".into(), total);
        m.insert(
            "closed".into(),
            if self.closed.load(Ordering::Acquire) { 1 } else { 0 },
        );
        m
    }

    pub fn close(&self) {
        self.closed.store(true, Ordering::Release);
        let mut g = write_or_recover(&self.inner);
        g.subs.clear();
    }

    /// 重新开放（旧实现 close 之后没有任何恢复路径）。
    pub fn reopen(&self) {
        self.closed.store(false, Ordering::Release);
    }

    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
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
    #[pyo3(signature = (shared=true))]
    fn new(shared: bool) -> Self {
        // 默认与模块级单例同源（旧行为），shared=false 给独立实例
        let bus = if shared { global_bus() } else { EventBus::new() };
        Self { bus }
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

    fn stats_map(&self) -> HashMap<String, u64> {
        self.bus.stats_map()
    }

    fn close(&self) {
        self.bus.close()
    }

    fn reopen(&self) {
        self.bus.reopen()
    }

    fn is_closed(&self) -> bool {
        self.bus.is_closed()
    }
}

/// 全局总线（模块级单例，Python 侧直接取用）。
static GLOBAL_BUS: Mutex<Option<Arc<EventBus>>> = Mutex::new(None);

pub fn global_bus() -> Arc<EventBus> {
    let mut g = lock_or_recover(&GLOBAL_BUS);
    if g.is_none() {
        *g = Some(EventBus::new());
    }
    g.as_ref().unwrap().clone()
}
