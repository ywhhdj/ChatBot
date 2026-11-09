//! 任务状态与优先级（与 Python 侧常量保持一致）。
//!
//! 两套实现行为必须一致，所以这里的取值与 `manager/task/schedular.py`
//! 里的 `TaskPriority` / `TaskStatus` 严格对齐。

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Priority(pub i32);

impl Priority {
    pub const LOW: i32 = 10;
    pub const NORMAL: i32 = 50;
    pub const HIGH: i32 = 90;
    pub const CRITICAL: i32 = 100;

    pub fn clamp(v: i32) -> i32 {
        v.clamp(0, 100)
    }
}

impl Default for Priority {
    fn default() -> Self {
        Self(Self::NORMAL)
    }
}

/// 任务状态。取值与 Python 侧 `TaskStatus` 字符串一致。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskStatus {
    Pending,
    Running,
    Done,
    Failed,
    Cancelled,
    Timeout,
}

impl TaskStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            TaskStatus::Pending => "pending",
            TaskStatus::Running => "running",
            TaskStatus::Done => "done",
            TaskStatus::Failed => "failed",
            TaskStatus::Cancelled => "cancelled",
            TaskStatus::Timeout => "timeout",
        }
    }

    pub fn is_terminal(&self) -> bool {
        !matches!(self, TaskStatus::Pending | TaskStatus::Running)
    }
}

/// 任务类型：同步（阻塞）还是异步（协程）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskKind {
    Sync,
    Async,
}

impl TaskKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            TaskKind::Sync => "sync",
            TaskKind::Async => "async",
        }
    }
}
