//! 线程池与并发原语。
//!
//! 自建池，不引 rayon。
//! 不引 tokio —— 本项目并发模型（排队 + 阻塞执行 + 回调）
//! 用 `std::thread` + `mpsc` + `Condvar` 就够，编译快、产物小。

use std::panic::{self, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, RecvTimeoutError, Sender};
use std::sync::{Arc, Condvar, Mutex, MutexGuard, RwLock, RwLockReadGuard, RwLockWriteGuard};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

/// 锁中毒兜底。
pub fn lock_or_recover<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|p| p.into_inner())
}

pub fn read_or_recover<T>(m: &RwLock<T>) -> RwLockReadGuard<'_, T> {
    m.read().unwrap_or_else(|p| p.into_inner())
}

pub fn write_or_recover<T>(m: &RwLock<T>) -> RwLockWriteGuard<'_, T> {
    m.write().unwrap_or_else(|p| p.into_inner())
}

/// 并发门限。用 Condvar 而不是忙等。
pub struct Semaphore {
    inner: Mutex<usize>,
    cv: Condvar,
    limit: usize,
}

impl Semaphore {
    pub fn new(limit: usize) -> Self {
        Self { inner: Mutex::new(0), cv: Condvar::new(), limit: limit.max(1) }
    }

    /// 获取一个许可。返回 `false` 表示池已关闭。
    ///
    /// 修复：原实现的 `while` 循环里只在**进入前**检查 closed，且每次超时后
    /// 重新回到循环头才检查；这里改成超时后立刻复查，关闭信号不会延迟一整轮。
    pub fn acquire(&self, closed: &AtomicBool) -> bool {
        let mut cur = lock_or_recover(&self.inner);
        loop {
            if *cur < self.limit {
                *cur += 1;
                return true;
            }
            if closed.load(Ordering::Acquire) {
                return false;
            }
            let (g, _) = self
                .cv
                .wait_timeout(cur, Duration::from_millis(25))
                .unwrap_or_else(|p| p.into_inner());
            cur = g;
            if closed.load(Ordering::Acquire) && *cur >= self.limit {
                return false;
            }
        }
    }

    pub fn release(&self) {
        let mut cur = lock_or_recover(&self.inner);
        if *cur > 0 {
            *cur -= 1;
        }
        self.cv.notify_one();
    }

    pub fn in_use(&self) -> usize {
        *lock_or_recover(&self.inner)
    }

    pub fn limit(&self) -> usize {
        self.limit
    }
}

pub type Job = Box<dyn FnOnce() + Send + 'static>;

/// 一个极简工作池：N 个常驻线程从共享队列取闭包执行。
///
/// 闭包是 `FnOnce()`，内部由调用方决定要不要 acquire GIL —— 池本身不碰 Python。
/// 线程常驻，不为每个任务新建线程
pub struct WorkerPool {
    name: String,
    closed: Arc<AtomicBool>,
    handles: Mutex<Vec<JoinHandle<()>>>,
    /// 关闭时置 None → drop Sender → 工作线程收到 Disconnected 后退出
    tx: Mutex<Option<Sender<Job>>>,
    alive: Arc<AtomicU64>,
    threads: usize,
    queued: Arc<AtomicU64>,
}

impl WorkerPool {
    pub fn spawn(name: &str, threads: usize) -> (Arc<Self>, Sender<Job>) {
        let threads = threads.max(1);
        let closed = Arc::new(AtomicBool::new(false));
        let (tx, rx) = mpsc::channel::<Job>();
        let rx = Arc::new(Mutex::new(rx));

        let pool = Arc::new(Self {
            name: name.to_string(),
            closed: closed.clone(),
            handles: Mutex::new(Vec::new()),
            tx: Mutex::new(Some(tx.clone())),
            alive: Arc::new(AtomicU64::new(0)),
            threads,
            queued: Arc::new(AtomicU64::new(0)),
        });

        let mut handles = Vec::with_capacity(threads);
        for i in 0..threads {
            let rx = rx.clone();
            let closed = closed.clone();
            let alive = pool.alive.clone();
            let queued = pool.queued.clone();
            let tname = format!("{}-{}", name, i);
            let h = thread::Builder::new()
                .name(tname)
                .spawn(move || {
                    alive.fetch_add(1, Ordering::SeqCst);
                    loop {
                        // 关键：recv 带超时，超时后释放锁，让其它线程有机会接收。
                        let job = {
                            let guard = lock_or_recover(&rx);
                            guard.recv_timeout(Duration::from_millis(50))
                        };
                        match job {
                            Ok(j) => {
                                queued.fetch_sub(1, Ordering::AcqRel);
                                // R6：panic 绝不能扩散到线程外
                                let _ = panic::catch_unwind(AssertUnwindSafe(j));
                            }
                            Err(RecvTimeoutError::Timeout) => {
                                if closed.load(Ordering::Acquire) {
                                    break;
                                }
                            }
                            Err(RecvTimeoutError::Disconnected) => break,
                        }
                    }
                    alive.fetch_sub(1, Ordering::SeqCst);
                })
                .expect("spawn worker");
            handles.push(h);
        }
        *lock_or_recover(&pool.handles) = handles;
        (pool, tx)
    }

    /// 投递一个任务。池已关闭或线程全挂时返回 false（调用方负责回滚计数）。
    pub fn submit(&self, job: Job) -> bool {
        if self.closed.load(Ordering::Acquire) {
            return false;
        }
        let ok = match lock_or_recover(&self.tx).as_ref() {
            Some(tx) => tx.send(job).is_ok(),
            None => false,
        };
        if ok {
            self.queued.fetch_add(1, Ordering::AcqRel);
        }
        ok
    }

    pub fn alive(&self) -> u64 {
        self.alive.load(Ordering::SeqCst)
    }

    pub fn queued(&self) -> u64 {
        self.queued.load(Ordering::Acquire)
    }

    pub fn threads(&self) -> usize {
        self.threads
    }

    /// 关闭：停止接收新任务，等线程把手头的活干完再退。
    pub fn close(&self) {
        self.closed.store(true, Ordering::Release);
        *lock_or_recover(&self.tx) = None;
    }

    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    /// 等待线程退出，带超时。超时返回 false，绝不无限等。
    ///
    /// 修复：先等 `alive` 归零（这是"活干完了"的真正判据），再 join；
    /// 原来的写法把"还有别的线程活着"当成本线程 join 失败，必然返回 false。
    pub fn join_timeout(&self, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        while self.alive() > 0 && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(2));
        }
        if self.alive() > 0 {
            return false;
        }
        let handles: Vec<JoinHandle<()>> = {
            let mut g = lock_or_recover(&self.handles);
            std::mem::take(&mut *g)
        };
        for h in handles {
            let _ = h.join();
        }
        true
    }
}

/// 无锁计数器，用于统计（R13：读统计不抢调度锁）。
#[derive(Default)]
pub struct Counter(AtomicU64);

impl Counter {
    pub fn inc(&self) {
        self.0.fetch_add(1, Ordering::Relaxed);
    }
    pub fn add(&self, n: u64) {
        self.0.fetch_add(n, Ordering::Relaxed);
    }
    pub fn get(&self) -> u64 {
        self.0.load(Ordering::Relaxed)
    }
    pub fn reset(&self) {
        self.0.store(0, Ordering::Relaxed);
    }
}

/// 单调序号：保证同优先级下 FIFO（R8）。
pub struct Seq(AtomicU64);

impl Seq {
    pub fn new() -> Self {
        Self(AtomicU64::new(0))
    }
    pub fn next(&self) -> u64 {
        self.0.fetch_add(1, Ordering::Relaxed)
    }
}

impl Default for Seq {
    fn default() -> Self {
        Self::new()
    }
}

/// 唤醒版本号 + Condvar。
///
/// 调度器的数据放在 `RwLock` 里（读写分离），但 `RwLock` 没法配 `Condvar`，
/// 所以额外维护一个单调递增的计数器：**任何状态变更都 +1 并 notify_all**。
/// 等待方记住自己看过的版本号，只有版本没变时才真的睡 —— 这样即使
/// "改数据"与"进入等待"之间发生唤醒，也不会丢事件（不会永久挂起）。
pub struct Wake {
    epoch: Mutex<u64>,
    cv: Condvar,
}

impl Wake {
    pub fn new() -> Self {
        Self { epoch: Mutex::new(0), cv: Condvar::new() }
    }

    /// 广播一次状态变更。
    pub fn notify(&self) {
        let mut g = lock_or_recover(&self.epoch);
        *g += 1;
        self.cv.notify_all();
    }

    pub fn current(&self) -> u64 {
        *lock_or_recover(&self.epoch)
    }

    /// 等到版本变化或超时，返回当前版本。
    pub fn wait(&self, last: u64, timeout: Duration) -> u64 {
        let g = lock_or_recover(&self.epoch);
        if *g != last {
            return *g;
        }
        let (g, _) = self
            .cv
            .wait_timeout(g, timeout)
            .unwrap_or_else(|p| p.into_inner());
        *g
    }
}

impl Default for Wake {
    fn default() -> Self {
        Self::new()
    }
}
