pub mod api;
pub mod bus;
pub mod error;
pub mod runtime;
pub mod scheduler;
pub mod stream;
pub mod task;
pub mod timer;

use pyo3::prelude::*;
use pyo3::types::PyModuleMethods;
use pyo3::wrap_pyfunction;

use crate::task::Priority;

// 模块入口 —— 任何未捕获 panic 转成 Python 异常。
#[pymodule]
fn core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // ── 设备性能检测
    m.add_class::<crate::api::PyPerf>()?;
    m.add_function(wrap_pyfunction!(crate::api::detect_performance, m)?)?;
    m.add_function(wrap_pyfunction!(crate::api::detect_performance_json, m)?)?;
    m.add_function(wrap_pyfunction!(crate::api::detect_performance_into, m)?)?;

    // ── 并发内核 ──
    m.add_class::<crate::scheduler::PyScheduler>()?;
    m.add_class::<crate::stream::PyStream>()?;
    m.add_class::<crate::bus::PyEventBus>()?;
    m.add_class::<crate::timer::PyTimer>()?;

    // ── 常量
    m.add("PRIORITY_LOW", Priority::LOW)?;
    m.add("PRIORITY_NORMAL", Priority::NORMAL)?;
    m.add("PRIORITY_HIGH", Priority::HIGH)?;
    m.add("PRIORITY_CRITICAL", Priority::CRITICAL)?;

    Ok(())
}
