//! 错误类型与跨边界错误转换。
//!
//! Rust 侧的错误必须能变成 Python 异常，Python 侧的异常也必须能被Rust 捕获并记下来 —— 绝不能 panic 掉整个进程。

use pyo3::exceptions::{PyRuntimeError, PyTimeoutError, PyValueError};
use pyo3::PyErr;

/// 内核内部错误。
#[derive(Debug)]
pub enum CoreError {
    Stopped,
    QueueFull { kind: &'static str, size: usize, limit: usize },
    NotFound(String),
    Cancelled(String),
    Timeout(String),
    Invalid(&'static str),
    Python(String),
}

impl std::fmt::Display for CoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CoreError::Stopped => write!(f, "调度器未启动或已停止"),
            CoreError::QueueFull { kind, size, limit } => {
                write!(f, "{}任务队列已满({}/{})，请稍后重试", kind, size, limit)
            }
            CoreError::NotFound(id) => write!(f, "任务不存在: {}", id),
            CoreError::Cancelled(id) => write!(f, "任务已取消: {}", id),
            CoreError::Timeout(id) => write!(f, "任务超时: {}", id),
            CoreError::Invalid(s) => write!(f, "参数非法: {}", s),
            CoreError::Python(s) => write!(f, "Python 回调失败: {}", s),
        }
    }
}

impl std::error::Error for CoreError {}

impl From<CoreError> for PyErr {
    fn from(e: CoreError) -> Self {
        match e {
            // 超时映射成 Python 内置的 TimeoutError，调用方 `except TimeoutError`
            CoreError::Timeout(_) => PyTimeoutError::new_err(e.to_string()),
            CoreError::Invalid(_) => PyValueError::new_err(e.to_string()),
            other => PyRuntimeError::new_err(other.to_string()),
        }
    }
}

/// Python 异常格式化成字符串
pub fn py_err_to_string(e: &PyErr) -> String {
    format!("{}", e)
}
