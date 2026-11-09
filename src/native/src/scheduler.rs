//! 调度核心：优先级队列 / 并发门限 / 超时 / 取消 / 统计。
//!
//! 队列、优先级、并发门限、超时扫描、统计全在 Rust 侧完成，无 GIL。
//! 只有"真正执行 Python callable"那一步才 acquire GIL。
//!
//! 异步（协程）任务不能在 Rust 里跑 —— 协程需要 asyncio loop。
//! 这里只管**排队与生命周期**，执行时回调 Python 侧提供的 executor。

use std::cmp::Ordering as CmpOrdering;
use std::collections::{BTreeMap, BinaryHeap, HashMap};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::thread;
use std::time::{Duration, Instant};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::error::CoreError;
use crate::runtime::{lock_or_recover, read_or_recover, write_or_recover, Counter, Job, Seq, Wake, WorkerPool};
use crate::task::{Priority, TaskKind, TaskStatus};

/// 任务在内部的主键（对外仍是 Python 给的 `task_id` 字符串）。
pub type TaskKey = u64;

/// 一个待执行任务。
struct Task {
    id: String,
    kind: TaskKind,
    priority: i32,
    timeout: Option<Duration>,
    /// Python 可调用对象（执行完立即释放，不长期持有 —— R3）
    func: Option<Py<PyAny>>,
    args: Option<Py<PyAny>>,
    kwargs: Option<Py<PyAny>>,
    status: TaskStatus,
    /// 提交时刻
    #[allow(dead_code)]
    created: Instant,
    started: Option<Instant>,
    finished: Option<Instant>,
    error: Option<String>,
    result: Option<Py<PyAny>>,
    cancelled: Arc<AtomicBool>,
}

impl Task {
    /// 该任务在 deadlines 索引里的键（只有 Running 且带 timeout 才存在）。
    fn deadline_key(&self, key: TaskKey) -> Option<(Instant, TaskKey)> {
        match (self.started, self.timeout) {
            (Some(st), Some(to)) => Some((st + to, key)),
            _ => None,
        }
    }
}

/// 优先级队列元素。`BinaryHeap` 是**大顶堆**，所以 Ord 反转：
/// 优先级高的、seq 小的先出。只带 `u64` key，避免入队时的 String 分配。
struct Queued {
    priority: i32,
    seq: u64,
    key: TaskKey,
}

impl Ord for Queued {
    fn cmp(&self, other: &Self) -> CmpOrdering {
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
        self.priority == other.priority && self.seq == other.seq && self.key == other.key
    }
}

impl Eq for Queued {}

struct Registry {
    tasks: HashMap<TaskKey, Task>,
    /// task_id → key
    index: HashMap<String, TaskKey>,
    sync_q: BinaryHeap<Queued>,
    async_q: BinaryHeap<Queued>,
    /// 在途任务的到期时刻索引（只含 Running 且带 timeout 的任务）
    deadlines: BTreeMap<(Instant, TaskKey), ()>,
    running: bool,
    /// 队列/在途的即时计数，供 stats 走读锁快速读出
    pending: u64,
    running_cnt: u64,
}

pub struct Scheduler {
    reg: RwLock<Registry>,
    /// 状态变更广播（读写分离下唯一的等待通道）
    wake: Wake,
    seq: Seq,
    /// 并发门限（同步 / 异步各一个），同时决定常驻 worker 数
    sync_limit: usize,
    async_limit: usize,
    /// 队列容量上限（0 = 无界）。热路径只读，用原子量避免为它单独加锁。
    sync_queue_size: AtomicUsize,
    async_queue_size: AtomicUsize,
    in_flight_sync: Arc<AtomicU64>,
    in_flight_async: Arc<AtomicU64>,
    sync_pool: Arc<WorkerPool>,
    async_pool: Arc<WorkerPool>,
    /// Python 侧提供的执行钩子（协程要投回 loop）
    executor: Mutex<Option<Py<PyAny>>>,
    exc_store: Mutex<HashMap<String, PyErr>>,
    /// 完成回调（Python 侧可订阅）
    on_done: Mutex<Option<Py<PyAny>>>,
    /// 暂停：stop() 置位，start() 清除，线程不退出
    stopped: AtomicBool,
    /// 终止：只有 Drop 会置位，线程收到后退出
    closed: AtomicBool,

    // R13：无锁统计
    st_submitted: Counter,
    st_completed: Counter,
    st_failed: Counter,
    st_cancelled: Counter,
    st_timeout: Counter,
}

impl Scheduler {
    pub fn new(sync_threads: usize, async_threads: usize) -> Arc<Self> {
        let sync_limit = sync_threads.max(1);
        let async_limit = async_threads.max(1);

        // 返回的 Sender 只是备用通道；派发统一走 `pool.submit`（带排队计数）
        let (sync_pool, _sync_tx) = WorkerPool::spawn("chatbot-sync", sync_limit);
        let (async_pool, _async_tx) = WorkerPool::spawn("chatbot-async", async_limit);

        let s = Arc::new(Self {
            reg: RwLock::new(Registry {
                tasks: HashMap::new(),
                index: HashMap::new(),
                sync_q: BinaryHeap::new(),
                async_q: BinaryHeap::new(),
                deadlines: BTreeMap::new(),
                running: false,
                pending: 0,
                running_cnt: 0,
            }),
            wake: Wake::new(),
            seq: Seq::new(),
            sync_limit,
            async_limit,
            sync_queue_size: AtomicUsize::new(0),
            async_queue_size: AtomicUsize::new(0),
            in_flight_sync: Arc::new(AtomicU64::new(0)),
            in_flight_async: Arc::new(AtomicU64::new(0)),
            sync_pool,
            async_pool,
            executor: Mutex::new(None),
            exc_store: Mutex::new(HashMap::new()),
            on_done: Mutex::new(None),
            stopped: AtomicBool::new(false),
            closed: AtomicBool::new(false),
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

    // ---------- 唤醒 ----------

    fn bump(&self) {
        self.wake.notify();
    }

    // ---------- 生命周期 ----------

    pub fn start(&self) {
        {
            let mut g = write_or_recover(&self.reg);
            g.running = true;
        }
        self.stopped.store(false, Ordering::Release);
        self.bump();
    }

    /// 置停止 → 停止接收 → 队列里没开跑的任务标记取消 → 等待在途（带超时）。
    pub fn stop(&self, timeout: Duration) -> bool {
        self.stopped.store(true, Ordering::Release);
        {
            let mut g = write_or_recover(&self.reg);
            g.running = false;
            let mut cancelled_keys: Vec<TaskKey> = Vec::new();
            for kind in [TaskKind::Sync, TaskKind::Async] {
                let q = match kind {
                    TaskKind::Sync => &mut g.sync_q,
                    TaskKind::Async => &mut g.async_q,
                };
                while let Some(qe) = q.pop() {
                    cancelled_keys.push(qe.key);
                }
            }
            let now = Instant::now();
            for key in cancelled_keys {
                if let Some(t) = g.tasks.get_mut(&key) {
                    if !t.status.is_terminal() {
                        t.status = TaskStatus::Cancelled;
                        t.cancelled.store(true, Ordering::Release);
                        t.finished = Some(now);
                        self.st_cancelled.inc();
                    }
                }
            }
            g.deadlines.clear();
            g.pending = 0;
        }
        self.bump();

        let deadline = Instant::now() + timeout;
        while (self.in_flight_sync.load(Ordering::Acquire)
            + self.in_flight_async.load(Ordering::Acquire))
            > 0
        {
            if Instant::now() >= deadline {
                return false;
            }
            thread::sleep(Duration::from_millis(2));
        }
        true
    }

    pub fn is_running(&self) -> bool {
        !self.stopped.load(Ordering::Acquire) && read_or_recover(&self.reg).running
    }

    pub fn set_executor(&self, cb: Py<PyAny>) {
        *lock_or_recover(&self.executor) = Some(cb);
    }

    pub fn set_on_done(&self, cb: Py<PyAny>) {
        *lock_or_recover(&self.on_done) = Some(cb);
    }

    /// 设置队列容量（0 = 无界）。旧实现把容量写死成 0 且没有 setter，
    /// `QueueFull` 保护形同虚设。
    pub fn set_queue_limit(&self, kind: TaskKind, size: usize) {
        match kind {
            TaskKind::Sync => self.sync_queue_size.store(size, Ordering::Release),
            TaskKind::Async => self.async_queue_size.store(size, Ordering::Release),
        }
    }

    pub fn queue_limit(&self, kind: TaskKind) -> usize {
        match kind {
            TaskKind::Sync => self.sync_queue_size.load(Ordering::Acquire),
            TaskKind::Async => self.async_queue_size.load(Ordering::Acquire),
        }
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
        if self.stopped.load(Ordering::Acquire) || self.closed.load(Ordering::Acquire) {
            return Err(CoreError::Stopped);
        }
        let key = self.seq.next();
        let task = Task {
            id: id.clone(),
            kind,
            priority: Priority::clamp(priority),
            timeout: timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64),
            func: Some(func),
            args: Some(args),
            kwargs: Some(kwargs),
            status: TaskStatus::Pending,
            created: Instant::now(),
            started: None,
            finished: None,
            error: None,
            result: None,
            cancelled: Arc::new(AtomicBool::new(false)),
        };

        {
            let mut g = write_or_recover(&self.reg);
            if !g.running {
                return Err(CoreError::Stopped);
            }
            if g.index.contains_key(&id) {
                return Err(CoreError::Invalid("任务 id 重复"));
            }
            let limit = self.queue_limit(kind);
            {
                let q = match kind {
                    TaskKind::Sync => &mut g.sync_q,
                    TaskKind::Async => &mut g.async_q,
                };
                if limit > 0 && q.len() >= limit {
                    return Err(CoreError::QueueFull {
                        kind: kind.as_str(),
                        size: q.len(),
                        limit,
                    });
                }
                q.push(Queued { priority: task.priority, seq: key, key });
            }
            g.index.insert(id, key);
            g.tasks.insert(key, task);
            g.pending += 1;
        }
        self.st_submitted.inc();
        self.bump();
        Ok(())
    }

    // ---------- 状态查询 ----------

    pub fn status(&self, id: &str) -> Option<TaskStatus> {
        let g = read_or_recover(&self.reg);
        let key = *g.index.get(id)?;
        g.tasks.get(&key).map(|t| t.status)
    }

    pub fn is_done(&self, id: &str) -> bool {
        self.status(id).map(|s| s.is_terminal()).unwrap_or(false)
    }

    /// 等待任务完成（阻塞）。R4：调用方应包在 `allow_threads` 里。
    pub fn wait(&self, id: &str, timeout: Option<Duration>) -> bool {
        let deadline = timeout.map(|t| Instant::now() + t);
        let mut last = self.wake.current();
        loop {
            {
                let g = read_or_recover(&self.reg);
                match g.index.get(id) {
                    Some(key) => {
                        if let Some(t) = g.tasks.get(key) {
                            if t.status.is_terminal() {
                                return true;
                            }
                        }
                    }
                    None => return false,
                }
            }
            if let Some(dl) = deadline {
                let remain = dl.saturating_duration_since(Instant::now());
                if remain.is_zero() {
                    return false;
                }
                last = self.wake.wait(last, remain.min(Duration::from_millis(50)));
            } else {
                last = self.wake.wait(last, Duration::from_millis(50));
            }
        }
    }

    /// 取结果。任务失败时**返回 Err**，让 PyO3 在 Python 侧 raise。
    ///
    /// 绝不能静默返回 None —— 调用方会以为"任务成功但没有结果"。
    pub fn take_result(&self, py: Python<'_>, id: &str) -> PyResult<Option<Py<PyAny>>> {
        if let Some(exc) = lock_or_recover(&self.exc_store).get(id) {
            return Err(exc.clone_ref(py));
        }
        let g = read_or_recover(&self.reg);
        let key = match g.index.get(id) {
            Some(k) => *k,
            None => return Err(CoreError::NotFound(id.to_string()).into()),
        };
        let t = g.tasks.get(&key).unwrap();
        if t.status == TaskStatus::Timeout {
            return Err(CoreError::Timeout(id.to_string()).into());
        }
        if !t.status.is_terminal() {
            return Ok(None);
        }
        if let Some(e) = &t.error {
            return Err(CoreError::Python(e.clone()).into());
        }
        Ok(t.result.as_ref().map(|r| r.clone_ref(py)))
    }

    pub fn cancel(&self, id: &str) -> bool {
        let mut g = write_or_recover(&self.reg);
        let key = match g.index.get(id) {
            Some(k) => *k,
            None => return false,
        };

        let (deadline_opt, was_running) = {
            let t = match g.tasks.get_mut(&key) {
                Some(t) => t,
                None => return false,
            };
            if t.status.is_terminal() {
                return false;
            }
            let was_running = t.status == TaskStatus::Running;
            t.status = TaskStatus::Cancelled;
            t.cancelled.store(true, Ordering::Release);
            t.finished = Some(Instant::now());
            (t.deadline_key(key), was_running)
        };

        if let Some(dk) = deadline_opt {
            g.deadlines.remove(&dk);
        }
        if was_running {
            g.running_cnt = g.running_cnt.saturating_sub(1);
        } else {
            g.pending = g.pending.saturating_sub(1);
        }
        self.st_cancelled.inc();
        drop(g);
        self.bump();
        true
    }

    pub fn stats(&self) -> HashMap<String, u64> {
        // 走读锁
        let g = read_or_recover(&self.reg);
        let mut m = HashMap::with_capacity(12);
        m.insert("total_submitted".into(), self.st_submitted.get());
        m.insert("completed".into(), self.st_completed.get());
        m.insert("failed".into(), self.st_failed.get());
        m.insert("cancelled".into(), self.st_cancelled.get());
        m.insert("timeout".into(), self.st_timeout.get());
        m.insert("sync_queue".into(), g.sync_q.len() as u64);
        m.insert("async_queue".into(), g.async_q.len() as u64);
        m.insert("in_flight_sync".into(), self.in_flight_sync.load(Ordering::Acquire));
        m.insert("in_flight_async".into(), self.in_flight_async.load(Ordering::Acquire));
        m.insert("pending".into(), g.pending);
        m.insert("running".into(), g.running_cnt);
        m.insert("sync_limit".into(), self.sync_limit as u64);
        m.insert("async_limit".into(), self.async_limit as u64);
        m.insert("sync_workers_alive".into(), self.sync_pool.alive());
        m.insert("async_workers_alive".into(), self.async_pool.alive());
        m
    }

    // ---------- 派发 ----------

    fn spawn_dispatchers(self: &Arc<Self>) {
        for kind in [TaskKind::Sync, TaskKind::Async] {
            let this = self.clone();
            thread::Builder::new()
                .name(format!("chatbot-disp-{:?}", kind))
                .spawn(move || this.dispatch_loop(kind))
                .expect("spawn dispatcher");
        }
    }

    fn dispatch_loop(self: Arc<Self>, kind: TaskKind) {
        let limit = match kind {
            TaskKind::Sync => self.sync_limit,
            TaskKind::Async => self.async_limit,
        };
        let in_flight = match kind {
            TaskKind::Sync => self.in_flight_sync.clone(),
            TaskKind::Async => self.in_flight_async.clone(),
        };
        let pool = match kind {
            TaskKind::Sync => self.sync_pool.clone(),
            TaskKind::Async => self.async_pool.clone(),
        };

        let mut last = self.wake.current();
        while !self.closed.load(Ordering::Acquire) {
            if self.stopped.load(Ordering::Acquire) {
                last = self.wake.wait(last, Duration::from_millis(50));
                continue;
            }
            // 并发门限：睡到"有任务完成"为止，不做 1ms 忙轮询
            if in_flight.load(Ordering::Acquire) as usize >= limit {
                last = self.wake.wait(last, Duration::from_millis(50));
                continue;
            }
            match self.pop_ready(kind) {
                None => {
                    last = self.wake.wait(last, Duration::from_millis(50));
                }
                Some(key) => {
                    in_flight.fetch_add(1, Ordering::AcqRel);
                    let s2 = self.clone();
                    let if2 = in_flight.clone();
                    let job: Job = Box::new(move || {
                        s2.execute(key);
                        if2.fetch_sub(1, Ordering::AcqRel);
                        s2.bump();
                    });
                    if !pool.submit(job) {
                        // 池已关闭：回滚计数，退出派发
                        in_flight.fetch_sub(1, Ordering::AcqRel);
                        break;
                    }
                }
            }
        }
    }

    /// 弹出一个真正可以跑的任务；跳过已被取消/已终止的残留项。
    fn pop_ready(&self, kind: TaskKind) -> Option<TaskKey> {
        let mut g = write_or_recover(&self.reg);
        loop {
            let qe = {
                let q = match kind {
                    TaskKind::Sync => &mut g.sync_q,
                    TaskKind::Async => &mut g.async_q,
                };
                q.pop()
            };
            let qe = match qe {
                Some(qe) => qe,
                None => return None,
            };
            let key = qe.key;

            let deadline_opt = {
                let t = match g.tasks.get_mut(&key) {
                    Some(t) => t,
                    None => continue,
                };
                if t.status != TaskStatus::Pending {
                    continue;
                }
                t.status = TaskStatus::Running;
                t.started = Some(Instant::now());
                t.deadline_key(key)
            };

            if let Some(dk) = deadline_opt {
                g.deadlines.insert(dk, ());
            }
            g.pending = g.pending.saturating_sub(1);
            g.running_cnt += 1;
            return Some(key);
        }
    }

    /// 真正执行一个任务。R3/R5：只在这一段 acquire GIL。
    fn execute(&self, key: TaskKey) {
        // 取消/终止发生在"出队之后、执行之前"时，不再白跑一次 Python 回调
        {
            let g = read_or_recover(&self.reg);
            match g.tasks.get(&key) {
                Some(t) => {
                    if t.cancelled.load(Ordering::Acquire) || t.status != TaskStatus::Running {
                        return;
                    }
                }
                None => return,
            }
        }

        let outcome = Python::with_gil(|py| {
            let (kind, id, func, args, kwargs) = {
                let g = read_or_recover(&self.reg);
                match g.tasks.get(&key) {
                    Some(t) => (
                        t.kind,
                        t.id.clone(),
                        t.func.as_ref().map(|f| f.clone_ref(py)),
                        t.args.as_ref().map(|a| a.clone_ref(py)),
                        t.kwargs.as_ref().map(|k| k.clone_ref(py)),
                    ),
                    None => return Err("任务在执行前被移除".to_string()),
                }
            };
            let func = match func {
                Some(f) => f,
                None => return Err("任务没有可执行对象".to_string()),
            };
            let args = args.unwrap_or_else(|| PyTuple::empty_bound(py).unbind().into_any());
            let kwargs = kwargs.unwrap_or_else(|| PyDict::new_bound(py).unbind().into_any());

            if kind == TaskKind::Async {
                // 协程交给 Python 侧 executor（它负责投回 asyncio loop）
                let exec = lock_or_recover(&self.executor)
                    .as_ref()
                    .map(|cb| cb.clone_ref(py));
                match exec {
                    Some(cb) => match cb.bind(py).call1((func, args, kwargs)) {
                        Ok(f) => Ok(f.unbind()),
                        Err(e) => {
                            lock_or_recover(&self.exc_store).insert(id, e.clone_ref(py));
                            Err(e.to_string())
                        }
                    },
                    None => Err("未设置异步执行器（async executor）".to_string()),
                }
            } else {
                let args_bound = args.bind(py);
                let args_tuple = match args_bound.downcast::<PyTuple>() {
                    Ok(t) => t,
                    Err(e) => return Err(format!("args 不是元组: {}", e)),
                };
                let kwargs_bound = kwargs.bind(py);
                let kwargs_dict = match kwargs_bound.downcast::<PyDict>() {
                    Ok(d) => d,
                    Err(e) => return Err(format!("kwargs 不是字典: {}", e)),
                };
                match func.bind(py).call(args_tuple, Some(kwargs_dict)) {
                    Ok(v) => Ok(v.unbind()),
                    Err(e) => {
                        let msg = e.to_string();
                        lock_or_recover(&self.exc_store).insert(id, e);
                        Err(msg)
                    }
                }
            }
        });

        self.finish(key, outcome);
    }

    fn finish(&self, key: TaskKey, outcome: Result<Py<PyAny>, String>) {
        let mut fire_done = false;
        let task_id: String;
        {
            let mut g = write_or_recover(&self.reg);

            // 内部块：只操作 t，不碰 g 的其它字段
            let (deadline_opt, id) = {
                let t = match g.tasks.get_mut(&key) {
                    Some(t) => t,
                    None => return,
                };
                // 终态不可改写：超时/取消之后才跑完的任务，保持原状态
                let locked = t.status == TaskStatus::Timeout
                    || t.status == TaskStatus::Cancelled;

                t.finished = Some(Instant::now());
                match outcome {
                    Ok(v) => {
                        t.result = Some(v);
                        if !locked {
                            t.status = TaskStatus::Done;
                            self.st_completed.inc();
                            fire_done = true;
                        }
                    }
                    Err(e) => {
                        t.error = Some(e);
                        if !locked {
                            t.status = TaskStatus::Failed;
                            self.st_failed.inc();
                            fire_done = true;
                        }
                    }
                }
                t.func = None;
                t.args = None;
                t.kwargs = None;
                (t.deadline_key(key), t.id.clone())
            };
            if let Some(dk) = deadline_opt {
                g.deadlines.remove(&dk);
            }
            g.running_cnt = g.running_cnt.saturating_sub(1);
            task_id = id;
        }
        self.bump();
        if fire_done {
            Python::with_gil(|py| {
                let cb = lock_or_recover(&self.on_done)
                    .as_ref()
                    .map(|c| c.clone_ref(py));
                if let Some(cb) = cb {
                    if let Err(e) = cb.bind(py).call1((task_id,)) {
                        e.print(py);
                    }
                }
            });
        }
    }

    /// 超时扫描：一个线程管所有到期，按 deadlines 索引精确定时。
    fn spawn_timeout_sweeper(self: &Arc<Self>) {
        let this = self.clone();
        thread::Builder::new()
            .name("chatbot-sweeper".into())
            .spawn(move || {
                let mut last = this.wake.current();
                while !this.closed.load(Ordering::Acquire) {
                    if this.stopped.load(Ordering::Acquire) {
                        last = this.wake.wait(last, Duration::from_millis(50));
                        continue;
                    }
                    let next = {
                        let g = read_or_recover(&this.reg);
                        g.deadlines.keys().next().map(|k| k.0)
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
                        let expired = this.sweep_once(Instant::now());
                        if expired == 0 {
                            // 理论上不会发生（索引里全是到期项）；兜底避免忙等
                            last = this.wake.wait(last, Duration::from_millis(20));
                        }
                        continue;
                    }
                    last = this.wake.wait(last, wait);
                    this.sweep_once(Instant::now());
                }
            })
            .expect("spawn sweeper");
    }

    /// 只处理 deadlines 中已到期的项，返回处理条数。
    fn sweep_once(&self, now: Instant) -> usize {
        let mut expired: Vec<String> = Vec::new();
        {
            let mut g = write_or_recover(&self.reg);
            while let Some(dk) = g.deadlines.keys().next().copied() {
                if dk.0 > now {
                    break;
                }
                g.deadlines.remove(&dk);
                let expired_id: Option<String> = {
                    let t = match g.tasks.get_mut(&dk.1) {
                        Some(t) => t,
                        None => continue,
                    };
                    if t.status != TaskStatus::Running {
                        None
                    } else {
                        let timeout = t.timeout.unwrap_or_default();
                        t.status = TaskStatus::Timeout;
                        t.error = Some(format!("任务超时 {}s", timeout.as_secs_f64()));
                        t.finished = Some(now);
                        t.func = None;
                        t.args = None;
                        t.kwargs = None;
                        Some(t.id.clone())            // t 最后一次使用
                    }
                };

                // 此时 t 已经释放，安全访问 g 的其他字段
                if let Some(id) = expired_id {
                    g.running_cnt = g.running_cnt.saturating_sub(1);
                    self.st_timeout.inc();
                    expired.push(id);
                }
            }
        }
        if !expired.is_empty() {
            self.bump();
            Python::with_gil(|py| {
                let cb = lock_or_recover(&self.on_done)
                    .as_ref()
                    .map(|c| c.clone_ref(py));
                if let Some(cb) = cb {
                    for id in &expired {
                        if let Err(e) = cb.bind(py).call1((id.as_str(),)) {
                            e.print(py);
                        }
                    }
                }
            });
        }
        expired.len()
    }

    /// 清理已完成任务（避免 HashMap 无限增长）。
    pub fn sweep_completed(&self, older_than: Duration) -> usize {
        let now = Instant::now();
        let mut removed: Vec<String> = Vec::new();
        {
            let mut g = write_or_recover(&self.reg);
            let keys: Vec<TaskKey> = g
                .tasks
                .iter()
                .filter(|(_, t)| {
                    t.status.is_terminal()
                        && t.finished.map(|f| now.duration_since(f) >= older_than).unwrap_or(false)
                })
                .map(|(k, _)| *k)
                .collect();
            for key in keys {
                if let Some(t) = g.tasks.remove(&key) {
                    if let Some(dk) = t.deadline_key(key) {
                        g.deadlines.remove(&dk);
                    }
                    g.index.remove(&t.id);
                    removed.push(t.id);
                }
            }
        }
        if removed.is_empty() {
            return 0;
        }
        // 任务清了，异常对象也要清，否则 HashMap 无限增长
        let mut ex = lock_or_recover(&self.exc_store);
        for id in &removed {
            ex.remove(id);
        }
        removed.len()
    }
}

impl Drop for Scheduler {
    /// 置终止标志 → 三个后台线程自行退出 → 释放它们持有的 `Arc<Self>`，
    /// 否则实例与线程会双双泄漏（旧实现没有任何回收路径）。
    fn drop(&mut self) {
        self.closed.store(true, Ordering::Release);
        self.stopped.store(true, Ordering::Release);
        self.bump();
        self.sync_pool.close();
        self.async_pool.close();
    }
}

/// 全局调度器单例。
static GLOBAL: Mutex<Option<Arc<Scheduler>>> = Mutex::new(None);

pub fn global_scheduler(sync_threads: usize, async_threads: usize) -> Arc<Scheduler> {
    let mut g = lock_or_recover(&GLOBAL);
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
    #[pyo3(signature = (sync_threads=4, async_threads=4, shared=true))]
    fn new(sync_threads: usize, async_threads: usize, shared: bool) -> Self {
        // shared=false 时给独立实例（测试/多租户场景），默认沿用进程内单例
        let inner = if shared {
            global_scheduler(sync_threads, async_threads)
        } else {
            Scheduler::new(sync_threads, async_threads)
        };
        Self { inner }
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

    /// 队列容量上限（0 = 无界）。默认无界，与旧行为一致。
    fn set_queue_limit(&self, kind: &str, size: usize) {
        let k = match kind {
            "async" => TaskKind::Async,
            _ => TaskKind::Sync,
        };
        self.inner.set_queue_limit(k, size)
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
        let a = args.unwrap_or_else(|| PyTuple::empty_bound(py).unbind().into_any());
        let kw = kwargs.unwrap_or_else(|| PyDict::new_bound(py).unbind().into_any());
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

    /// 等待会阻塞，必须释放 GIL —— 否则一个等待卡死整个解释器。
    #[pyo3(signature = (task_id, timeout=None))]
    fn wait(&self, py: Python<'_>, task_id: &str, timeout: Option<f64>) -> bool {
        py.allow_threads(|| {
            self.inner.wait(
                task_id,
                timeout.filter(|t| *t > 0.0).map(Duration::from_secs_f64),
            )
        })
    }

    /// 取结果。任务失败时抛出原异常
    fn result(&self, py: Python<'_>, task_id: &str) -> PyResult<Option<Py<PyAny>>> {
        self.inner.take_result(py, task_id)
    }

    fn cancel(&self, task_id: &str) -> bool {
        self.inner.cancel(task_id)
    }

    fn stats(&self) -> HashMap<String, u64> {
        self.inner.stats()
    }

    fn sweep_completed(&self, older_than_secs: f64) -> usize {
        self.inner.sweep_completed(Duration::from_secs_f64(older_than_secs.max(0.0)))
    }
}
