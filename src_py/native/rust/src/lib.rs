pub mod bus;
pub mod error;
pub mod runtime;
pub mod scheduler;
pub mod stream;
pub mod task;
pub mod timer;

use std::sync::Arc;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3::types::PyModuleMethods;


/// 模块入口—— 任何未捕获 panic 转成 Python 异常。
#[pymodule]
fn core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<crate::scheduler::PyScheduler>()?;
    m.add_class::<crate::stream::PyStream>()?;
    m.add_class::<crate::bus::PyEventBus>()?;
    m.add_class::<crate::timer::PyTimer>()?;
    Ok(())
}