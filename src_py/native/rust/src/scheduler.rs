//! 调度核心：优先级队列 / 超时 / 取消 / 统计。
//!
//! 队列、优先级、并发门限、超时扫描、统计全在 Rust 侧完成，无 GIL。
//! 只有"真正执行 Python callable"那一步才 acquire GIL。
//!
//! 异步（协程）任务不能在 Rust 里跑 —— 协程需要 asyncio loop。
//! 这里只管**排队与生命周期**，执行时回调 Python 侧提供的 executor。
//!
//! 统计用无锁计数，读统计不抢调度锁。

use std::cmp::Ordering as CmpOrdering;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::error::CoreError;
use crate::runtime::{Counter, Seq};
use crate::task::{Priority, TaskKind, TaskStatus};

/// 一个待执行任务。
struct Task {
    id: String,
    kind: TaskKind,
    priority: i32,
    seq: u64,
    timeout: Option<Duration>,
    /// Python 可调用对象（只在执行那一刻用，不做长期业务引用）
    func: Py<PyAny>,
    args: Py<PyAny>,
    kwargs: Py<PyAny>,
    status: TaskStatus,
    created: Instant,
    started: Option<Instant>,
    finished: Option<Instant>,
    error: Option<String>,
    /// 结果（执行成功后填入）
    result: Option<Py<PyAny>>,
    /// 完成信号（由 Python 侧轮询或由 Rust 侧回调）
    done: Arc<AtomicBool>,
    cancelled: Arc<AtomicBool>,
}

/// 优先级队列元素。注意 `BinaryHeap` 是**大顶堆**，
/// 所以 Ord 反转：优先级高的、seq 小的先出。
struct Queued {
    priority: i32,
    seq: u64,
    id: String,
}

impl Ord for Queued {
    fn cmp(&self, other: &Self) -> CmpOrdering {
        // 高优先级在前；同优先级按 seq（FIFO）
        other
            .priority
            .cmp(&self.priority)
            .then_with(|| other.seq.cmp(&self.seq))
    }
}

impl PartialOrd for Queued {
    fn partial_cmp(&self, other: &Self) -> Option<CmpOrdering> {
        Some(self.cmp(other))
    }
}

impl PartialEq for Queued {
    fn eq(&self, other: &Self) -> bool {
        self.priority == other.priority && self.seq == other.seq
    }
}

impl Eq for Queued {}

struct SchedulerInner {
    tasks: HashMap<String, Task>,
    sync_q: std::collections::BinaryHeap<Queued>,
    async_q: std::collections::BinaryHeap<Queued>,
    running: bool,
}

pub struct Scheduler {
    inner: Mutex<SchedulerInner>,
    cv: Condvar,
    seq: Seq,
    /// 并发门限（同步 / 异步各一个）
    sync_limit: usize,
    async_limit: usize,
    /// 队列容量上限（0 = 无界）
    sync_queue_size: usize,
    async_queue_size: usize,
    in_flight_sync: Arc<AtomicU64>,
    in_flight_async: Arc<AtomicU64>,
    /// Python 侧提供的执行钩子（协程要投回 loop）
    executor: Mutex<Option<Py<PyAny>>>,
    exc_store: Mutex<HashMap<String, PyErr>>,
    /// 完成回调（Python 侧可订阅）
    on_done: Mutex<Option<Py<PyAny>>>,
    stopped: AtomicBool,

    // R13：无锁统计
    st_submitted: Counter,
    st_completed: Counter,
    st_failed: Counter,
    st_cancelled: Counter,
    st_timeout: Counter,
}

impl Scheduler {
    pub fn new(sync_threads: usize, async_threads: usize) -> Arc<Self> {
        let s = Arc::new(Self {
            inner: Mutex::new(SchedulerInner {
                tasks: HashMap::new(),
                sync_q: std::collections::BinaryHeap::new(),
                async_q: std::collections::BinaryHeap::new(),
                running: false,
            }),
            cv: Condvar::new(),
            seq: Seq::new(),
            sync_limit: sync_threads.max(1),
            async_limit: async_threads.max(1),
            sync_queue_size: 0,
            async_queue_size: 0,
            in_flight_sync: Arc::new(AtomicU64::new(0)),
            in_flight_async: Arc::new(AtomicU64::new(0)),
            executor: Mutex::new(None),
            exc_store: Mutex::new(HashMap::new()),
            on_done: Mutex::new(None),
            stopped: AtomicBool::new(false),
            st_submitted: Counter::default(),
            st_completed: Counter::default(),
            st_failed: Counter::default(),
            st_cancelled: Counter::default(),
            st_timeout: Counter::default(),
        });
        s.spawn_dispatchers();
        s.spawn_timeout_sweeper();
        s
    }

    // ---------- 生命周期 ----------

    pub fn start(&self) {
        let mut g = self.inner.lock().unwrap();
        g.running = true;
        self.stopped.store(false, Ordering::SeqCst);
        self.cv.notify_all();
    }

    /// R14：置停止 → 停止接收 → 等待在途（带超时）→ 超时则标记返回。
    pub fn stop(&self, timeout: Duration) -> bool {
        self.stopped.store(true, Ordering::SeqCst);
        {
            let mut g = self.inner.lock().unwrap();
            g.running = false;
            g.sync_q.clear();
            g.async_q.clear();
        }
        self.cv.notify_all();

        let deadline = Instant::now() + timeout;
        while (self.in_flight_sync.load(Ordering::SeqCst)
            + self.in_flight_async.load(Ordering::SeqCst))
            > 0
        {
            if Instant::now() >= deadline {
                return false;
            }
            thread::sleep(Duration::from_millis(5));
        }
        true
    }

    pub fn is_running(&self) -> bool {
        !self.stopped.load(Ordering::SeqCst)
            && self.inner.lock().unwrap().running
    }

    pub fn set_executor(&self, cb: Py<PyAny>) {
        *self.executor.lock().unwrap() = Some(cb);
    }

    pub fn set_on_done(&self, cb: Py<PyAny>) {
        *self.on_done.lock().unwrap() = Some(cb);
    }

    // ---------- 提交 ----------
    pub fn submit(
        &self,
        id: String,
        kind: TaskKind,
        priority: i32,
        timeout: Option<f64>,
        func: Py<PyAny>,
        args: Py<PyAny>,
        kwargs: Py<PyAny>,
    ) -> Result<(), CoreError> {
        if self.stopped.load(Ordering::SeqCst) {
            return Err(CoreError::Stopped);
        }
        let seq = self.seq.next();
        let done = Arc::new(AtomicBool::new(false));
        let cancelled = Arc::new(AtomicBool::new(false));
        let task = Task {
            id: id.clone(),
            kind,
            priority: Priority::clamp(priority),
            seq,
            timeout: timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64),
            func,
            args,
            kwargs,
            status: TaskStatus::Pending,
            created: Instant::now(),
            started: None,
            finished: None,
            error: None,
            result: None,
            done: done,
            cancelled: cancelled,
        };

        let mut g = self.inner.lock().unwrap();
        if !g.running {
            return Err(CoreError::Stopped);
        }
        let (q, limit) = match kind {
            TaskKind::Sync => (&mut g.sync_q, self.sync_queue_size),
            TaskKind::Async => (&mut g.async_q, self.async_queue_size),
        };
        if limit > 0 && q.len() >= limit {
            return Err(CoreError::QueueFull {
                kind: kind.as_str(),
                size: q.len(),
                limit,
            });
        }
        q.push(Queued { priority: task.priority, seq, id: id.clone() });
        g.tasks.insert(id, task);
        self.st_submitted.inc();

        // 立即唤醒对应派发器，零派发延迟
        self.cv.notify_all();
        Ok(())
    }

    // ---------- 状态查询 ----------

    pub fn status(&self, id: &str) -> Option<TaskStatus> {
        let g = self.inner.lock().unwrap();
        g.tasks.get(id).map(|t| t.status)
    }

    pub fn is_done(&self, id: &str) -> bool {
        self.status(id).map(|s| s.is_terminal()).unwrap_or(false)
    }

    /// 等待任务完成（阻塞）。R4：调用方应包在 `allow_threads` 里。
    pub fn wait(&self, id: &str, timeout: Option<Duration>) -> bool {
        let deadline = timeout.map(|t| Instant::now() + t);
        loop {
            {
                let g = self.inner.lock().unwrap();
                if let Some(t) = g.tasks.get(id) {
                    if t.status.is_terminal() {
                        return true;
                    }
                } else {
                    return false;
                }
            }
            if let Some(dl) = deadline {
                if Instant::now() >= dl {
                    return false;
                }
            }
            let g = self.inner.lock().unwrap();
            let wait_ms = match deadline {
                Some(dl) => {
                    let r = dl.saturating_duration_since(Instant::now());
                    r.min(Duration::from_millis(20)).max(Duration::from_millis(1))
                }
                None => Duration::from_millis(20),
            };
            let (_g, _t) = self.cv.wait_timeout(g, wait_ms).unwrap();
        }
    }

    /// 取结果。任务失败时**返回 Err**，让 PyO3 在 Python 侧 raise。
    ///
    /// 绝不能静默返回 None —— 调用方会以为"任务成功但没有结果"。
    pub fn take_result(&self,py: Python<'_>, id: &str) -> PyResult<Option<Py<PyAny>>> {
        if let Some(exc) = self.exc_store.lock().unwrap().get(id) {
            return Err(exc.clone_ref(py));
        }
        let g = self.inner.lock().unwrap();
        let t = match g.tasks.get(id) {
            Some(t) => t,
            None => return Err(CoreError::NotFound(id.to_string()).into()),
        };
        if !t.status.is_terminal() {
            return Ok(None);
        }
        if let Some(e) = &t.error {
            return Err(CoreError::Python(e.clone()).into());
        }
        Ok(t.result.as_ref().map(|r| r.clone_ref(py)))
    }

    pub fn cancel(&self, id: &str) -> bool {
        let mut g = self.inner.lock().unwrap();
        match g.tasks.get_mut(id) {
            Some(t) if !t.status.is_terminal() => {
                t.status = TaskStatus::Cancelled;
                t.cancelled.store(true, Ordering::SeqCst);
                t.finished = Some(Instant::now());
                t.done.store(true, Ordering::SeqCst);
                self.st_cancelled.inc();
                self.cv.notify_all();
                true
            }
            _ => false,
        }
    }

    pub fn stats(&self) -> HashMap<String, u64> {
        let g = self.inner.lock().unwrap();
        let mut m = HashMap::new();
        m.insert("total_submitted".into(), self.st_submitted.get());
        m.insert("completed".into(), self.st_completed.get());
        m.insert("failed".into(), self.st_failed.get());
        m.insert("cancelled".into(), self.st_cancelled.get());
        m.insert("timeout".into(), self.st_timeout.get());
        m.insert("sync_queue".into(), g.sync_q.len() as u64);
        m.insert("async_queue".into(), g.async_q.len() as u64);
        m.insert("in_flight_sync".into(), self.in_flight_sync.load(Ordering::SeqCst));
        m.insert("in_flight_async".into(), self.in_flight_async.load(Ordering::SeqCst));
        m
    }

    // ---------- 派发 ----------

    fn spawn_dispatchers(self: &Arc<Self>) {
        for kind in [TaskKind::Sync, TaskKind::Async] {
            let this = self.clone();
            let limit = match kind {
                TaskKind::Sync => self.sync_limit,
                TaskKind::Async => self.async_limit,
            };
            let in_flight = match kind {
                TaskKind::Sync => self.in_flight_sync.clone(),
                TaskKind::Async => self.in_flight_async.clone(),
            };
            thread::Builder::new()
                .name(format!("chatbot-disp-{:?}", kind))
                .spawn(move || loop {
                    if this.stopped.load(Ordering::SeqCst) {
                        break;
                    }
                    // 并发门限
                    if in_flight.load(Ordering::SeqCst) as usize >= limit {
                        thread::sleep(Duration::from_millis(1));
                        continue;
                    }
                    let job = this.pop_ready(kind);
                    match job {
                        None => {
                            let g = this.inner.lock().unwrap();
                            let (_g, _t) = this
                                .cv
                                .wait_timeout(g, Duration::from_millis(20))
                                .unwrap();
                        }
                        Some(id) => {
                            in_flight.fetch_add(1, Ordering::SeqCst);
                            let s2 = this.clone();
                            let if2 = in_flight.clone();
                            thread::Builder::new()
                                .name(format!("chatbot-worker-{}", id))
                                .spawn(move || {
                                    s2.execute(&id);
                                    if2.fetch_sub(1, Ordering::SeqCst);
                                })
                                .ok();
                        }
                    }
                })
                .expect("spawn dispatcher");
        }
    }

    fn pop_ready(&self, kind: TaskKind) -> Option<String> {
        let mut g = self.inner.lock().unwrap();
        let q = match kind {
            TaskKind::Sync => &mut g.sync_q,
            TaskKind::Async => &mut g.async_q,
        };
        let id = q.pop().map(|q| q.id)?;
        if let Some(t) = g.tasks.get_mut(&id) {
            t.status = TaskStatus::Running;
            t.started = Some(Instant::now());
        }
        Some(id)
    }

    /// 真正执行一个任务。R3/R5：只在这一段 acquire GIL。
    fn execute(&self, id: &str) {
        {
            let g = self.inner.lock().unwrap();
            if !g.tasks.contains_key(id) {
                return;
            }
        }

        let outcome = Python::with_gil(|py| {
            // 先取出任务的三要素
            let (kind, func, args, kwargs) = {
                let g = self.inner.lock().unwrap();
                match g.tasks.get(id) {
                    Some(t) => (
                        t.kind,
                        t.func.clone_ref(py),
                        t.args.clone_ref(py),
                        t.kwargs.clone_ref(py),
                    ),
                    None => return Err("任务在执行前被移除".into()),
                }
            };

            if kind == TaskKind::Async {
                // 协程交给 Python 侧 executor（它负责投回 asyncio loop）
                let exec = self.executor.lock().unwrap().as_ref().map(|cb| cb.clone_ref(py));
                match exec {
                    Some(cb) => {
                        let fut = cb.bind(py).call1((
                            func.clone_ref(py),
                            args.clone_ref(py),
                            kwargs.clone_ref(py),
                        ));
                        match fut {
                            Ok(f) => Ok(f.unbind()),
                            Err(e) => Err(e.to_string()),
                        }
                    }
                    None => Err("未设置异步执行器（async executor）".into()),
                }
            } else {
                // 同步：直接调用
                let args_bound = args.bind(py);
                let args_tuple = args_bound
                    .downcast::<PyTuple>()
                    .map_err(|e| format!("args 不是元组: {}", e))?;

                let kwargs_bound = kwargs.bind(py);
                let kwargs_dict = kwargs_bound
                    .downcast::<PyDict>()
                    .map_err(|e| format!("kwargs 不是字典: {}", e))?;
                match func.bind(py).call(args_tuple, Some(kwargs_dict)) {
                    Ok(v) => Ok(v.unbind()),
                    Err(e) => {
                        let msg = e.to_string();
                        self.exc_store
                            .lock()
                            .unwrap()
                            .insert(id.to_string(), e); 
                        Err(msg)
                    }
                }
            }
        });

        self.finish(id, outcome);
    }

    fn finish(&self, id: &str, outcome: Result<Py<PyAny>, String>) {
        {
            let mut g = self.inner.lock().unwrap();
            let t = match g.tasks.get_mut(id) {
                Some(t) => t,
                None => return,
            };
            if t.status == TaskStatus::Cancelled {
                return;
            }
            t.finished = Some(Instant::now());
            t.done.store(true, Ordering::SeqCst);
            match outcome {
                Ok(v) => {
                    t.result = Some(v);
                    t.status = TaskStatus::Done;
                    self.st_completed.inc();
                }
                Err(e) => {
                    t.error = Some(e);
                    t.status = TaskStatus::Failed;
                    self.st_failed.inc();
                }
            }
        }
        self.cv.notify_all();

        // R5：回调 Python 重新拿 GIL
        Python::with_gil(|py| {
            let cb = self
                .on_done
                .lock()
                .unwrap()
                .as_ref()
                .map(|c| c.clone_ref(py));
            if let Some(cb) = cb {
                if let Err(e) = cb.bind(py).call1((id.to_string(),)) {
                    e.print(py);
                }
            }
        });
    }

    /// 超时扫描：一个线程扫全部，不用每任务一个定时器。
    fn spawn_timeout_sweeper(self: &Arc<Self>) {
        let this = self.clone();
        thread::Builder::new()
            .name("chatbot-sweeper".into())
            .spawn(move || loop {
                if this.stopped.load(Ordering::SeqCst) {
                    break;
                }
                this.sweep_once();
                thread::sleep(Duration::from_millis(100));
            })
            .expect("spawn sweeper");
    }

    fn sweep_once(&self) {
        let now = Instant::now();
        let mut expired = Vec::new();
        {
            let mut g = self.inner.lock().unwrap();
            for (id, t) in g.tasks.iter_mut() {
                if t.status != TaskStatus::Running {
                    continue;
                }
                if let Some(to) = t.timeout {
                    if let Some(st) = t.started {
                        if now.duration_since(st) >= to {
                            t.status = TaskStatus::Timeout;
                            t.error = Some(format!("任务超时 {}s", to.as_secs_f64()));
                            t.finished = Some(now);
                            t.done.store(true, Ordering::SeqCst);
                            self.st_timeout.inc();
                            expired.push(id.clone());
                        }
                    }
                }
            }
        }
        if !expired.is_empty() {
            self.cv.notify_all();
        }
    }

    /// 清理已完成任务（避免 HashMap 无限增长）。
    pub fn sweep_completed(&self, older_than: Duration) -> usize {
        let now = Instant::now();
        let mut g = self.inner.lock().unwrap();
        let before = g.tasks.len();
        let removed: Vec<String> = g
            .tasks
            .iter()
            .filter(|(_, t)| {
                t.status.is_terminal()
                    && t.finished.map(|f| now.duration_since(f) >= older_than).unwrap_or(false)
            })
            .map(|(id, _)| id.clone())
            .collect();
        g.tasks.retain(|_, t| {
            !(t.status.is_terminal()
                && t.finished.map(|f| now.duration_since(f) >= older_than).unwrap_or(false))
        });
        let after = g.tasks.len();
        drop(g);
        // 任务清了，异常对象也要清，否则 HashMap 无限增长
        let mut ex = self.exc_store.lock().unwrap();
        for id in &removed {
            ex.remove(id);
        }
        before - after
    }
}

/// 全局调度器单例。
static GLOBAL: Mutex<Option<Arc<Scheduler>>> = Mutex::new(None);

pub fn global_scheduler(sync_threads: usize, async_threads: usize) -> Arc<Scheduler> {
    let mut g = GLOBAL.lock().unwrap();
    if g.is_none() {
        *g = Some(Scheduler::new(sync_threads, async_threads));
    }
    g.as_ref().unwrap().clone()
}

/// Python 可见的调度器。
#[pyclass]
pub struct PyScheduler {
    inner: Arc<Scheduler>,
}

#[pymethods]
impl PyScheduler {
    #[new]
    #[pyo3(signature = (sync_threads=4, async_threads=4))]
    fn new(sync_threads: usize, async_threads: usize) -> Self {
        Self { inner: global_scheduler(sync_threads, async_threads) }
    }

    fn start(&self) {
        self.inner.start()
    }

    /// 可能阻塞，释放 GIL。
    fn stop(&self, py: Python<'_>, timeout: f64) -> bool {
        py.allow_threads(|| self.inner.stop(Duration::from_secs_f64(timeout.max(0.1))))
    }

    fn is_running(&self) -> bool {
        self.inner.is_running()
    }

    /// 设置异步执行器：`executor(func, args, kwargs) -> awaitable`
    fn set_executor(&self, cb: Py<PyAny>) {
        self.inner.set_executor(cb)
    }

    fn set_on_done(&self, cb: Py<PyAny>) {
        self.inner.set_on_done(cb)
    }

    #[pyo3(signature = (task_id, kind, priority=50, timeout=10.0, func=None, args=None, kwargs=None))]
    fn submit(
        &self,
        task_id: String,
        kind: &str,
        priority: i32,
        timeout: f64,
        func: Option<Py<PyAny>>,
        args: Option<Py<PyAny>>,
        kwargs: Option<Py<PyAny>>,
        py: Python<'_>,
    ) -> PyResult<()> {
        let k = match kind {
            "async" => TaskKind::Async,
            _ => TaskKind::Sync,
        };
        let f = func.ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>("func 不能为空")
        })?;
        let a = args.unwrap_or_else(|| PyTuple::empty_bound(py).unbind().into());
        let kw= kwargs.unwrap_or_else(|| PyDict::new_bound(py).unbind().into());
        self.inner
            .submit(task_id, k, priority, Some(timeout), f, a, kw)
            .map_err(Into::into)
    }

    fn status(&self, task_id: &str) -> Option<String> {
        self.inner.status(task_id).map(|s| s.as_str().to_string())
    }

    fn is_done(&self, task_id: &str) -> bool {
        self.inner.is_done(task_id)
    }

    /// R4：等待会阻塞，必须释放 GIL —— 否则一个等待卡死整个解释器。
    #[pyo3(signature = (task_id, timeout=None))]
    fn wait(&self, py: Python<'_>, task_id: &str, timeout: Option<f64>) -> bool {
        py.allow_threads(|| {
            self.inner.wait(
                task_id,
                timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64),
            )
        })
    }

    /// 取结果。任务失败时**抛出**原异常（R6）。
    fn result(&self,py: Python<'_>, task_id: &str) -> PyResult<Option<Py<PyAny>>> {
        self.inner.take_result(py,task_id)
    }

    fn cancel(&self, task_id: &str) -> bool {
        self.inner.cancel(task_id)
    }

    fn stats(&self) -> std::collections::HashMap<String, u64> {
        self.inner.stats()
    }

    fn sweep_completed(&self, older_than_secs: f64) -> usize {
        self.inner.sweep_completed(Duration::from_secs_f64(older_than_secs.max(0.0)))
    }
}