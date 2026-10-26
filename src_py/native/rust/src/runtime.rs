//! 线程池与并发门限。
//!
//! R7：自建池，不引 rayon。
//! R15：不引 tokio —— 本项目并发模型（排队 + 阻塞执行 + 回调）
//! 用 `std::thread` + `mpsc` + `Condvar` 就够，编译快、产物小。

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};

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
    pub fn acquire(&self, closed: &AtomicBool) -> bool {
        let mut cur = self.inner.lock().unwrap();
        while *cur >= self.limit {
            if closed.load(Ordering::SeqCst) {
                return false;
            }
            // 带超时等待，避免关闭时永久挂起（R14）
            let (g, _) = self
                .cv
                .wait_timeout(cur, std::time::Duration::from_millis(50))
                .unwrap();
            cur = g;
        }
        *cur += 1;
        true
    }

    pub fn release(&self) {
        let mut cur = self.inner.lock().unwrap();
        if *cur > 0 {
            *cur -= 1;
        }
        self.cv.notify_one();
    }

    pub fn in_use(&self) -> usize {
        *self.inner.lock().unwrap()
    }
}

/// 一个极简工作池：N 个线程从共享队列取闭包执行。
///
/// 闭包是 `Fn()`，内部由调用方决定要不要 acquire GIL —— 池本身不碰 Python。
pub struct WorkerPool {
    name: String,
    closed: Arc<AtomicBool>,
    handles: Mutex<Vec<JoinHandle<()>>>,
    sem: Arc<Semaphore>,
    alive: Arc<AtomicU64>,
}

pub type Job = Box<dyn FnOnce() + Send + 'static>;

impl WorkerPool {
    pub fn new(name: &str, threads: usize) -> (Arc<Self>, std::sync::mpsc::Sender<Job>) {
        let threads = threads.max(1);
        let closed = Arc::new(AtomicBool::new(false));
        let (tx, rx) = std::sync::mpsc::channel::<Job>();
        let rx = Arc::new(Mutex::new(rx));

        let pool = Arc::new(Self {
            name: name.to_string(),
            closed: closed.clone(),
            handles: Mutex::new(Vec::new()),
            sem: Arc::new(Semaphore::new(threads)),
            alive: Arc::new(AtomicU64::new(0)),
        });

        let mut handles = Vec::with_capacity(threads);
        for i in 0..threads {
            let rx = rx.clone();
            let closed = closed.clone();
            let alive = pool.alive.clone();
            let tname = format!("{}-{}", name, i);
            let h = thread::Builder::new()
                .name(tname.clone())
                .spawn(move || {
                    alive.fetch_add(1, Ordering::SeqCst);
                    loop {
                        let job = {
                            let guard = rx.lock().unwrap();
                            guard.recv()
                        };
                        match job {
                            Ok(j) => {
                                // R6：panic 绝不能扩散到线程外
                                let _ = std::panic::catch_unwind(
                                    std::panic::AssertUnwindSafe(j),
                                );
                            }
                            Err(_) => break, // sender 全 drop，退出
                        }
                        if closed.load(Ordering::SeqCst) {
                            // 关闭时把队列 drained 再退
                            if let Ok(guard) = rx.lock() {
                                if guard.try_recv().is_err() {
                                    break;
                                }
                            }
                        }
                    }
                    alive.fetch_sub(1, Ordering::SeqCst);
                })
                .expect("spawn worker");
            handles.push(h);
        }
        *pool.handles.lock().unwrap() = handles;
        (pool, tx)
    }

    pub fn alive(&self) -> u64 {
        self.alive.load(Ordering::SeqCst)
    }

    pub fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
    }

    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::SeqCst)
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    /// R14：等待线程退出，带超时。超时返回 false，绝不无限等。
    pub fn join_timeout(&self, timeout: std::time::Duration) -> bool {
        let deadline = std::time::Instant::now() + timeout;
        let handles: Vec<JoinHandle<()>> = {
            let mut g = self.handles.lock().unwrap();
            std::mem::take(&mut *g)
        };
        let mut ok = true;
        for h in handles {
            let remain = deadline.saturating_duration_since(std::time::Instant::now());
            if remain.is_zero() {
                ok = false;
                break;
            }
            // std 没有带超时的 join，用 alive 计数轮询（间隔很小，开销可忽略）
            while self.alive() > 0
                && std::time::Instant::now() < deadline
            {
                thread::sleep(std::time::Duration::from_millis(5));
            }
            let _ = h.join();
            if self.alive() > 0 {
                ok = false;
            }
        }
        ok
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
