"""并发层统一入口
后端选择
────────
`CHATBOT_NATIVE=1` → 强制 Rust，缺失则**报错**（不静默降级，便于发现问题）
"""
from __future__ import annotations
import os
from typing import Optional
from .scheduler import get_async_dispatch,get_scheduler

from ...logger import logger

_ENV = "CHATBOT_NATIVE"

_backend: Optional[str] = None
_bus = None
_timer = None
ASYNC_EXEC_TIMEOUT = float(os.environ.get("ASYNC_EXEC_TIMEOUT", "300"))


def _probe() -> str:
    """决定后端：`rust` 或 `python`。"""
    forced = os.environ.get(_ENV, "").strip().lower()
    try:
        from . import bindings
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[native] binding 导入失败: {exc}")
        bindings = None  # type: ignore

    rust_ok = bool(bindings and bindings.available())
    if forced == "1":
        if not rust_ok:
            raise RuntimeError(
                "CHATBOT_NATIVE=1 但 Rust 内核不可用。"
                "先在 rust/ 目录执行 ./build.sh 构建，或去掉该环境变量。"
            )
        return "rust"
    return "rust" if rust_ok else "python"


def backend() -> str:
    """当前后端名。首次调用时探测并缓存。"""
    global _backend
    if _backend is None:
        forced = os.environ.get(_ENV, "").strip().lower()
        try:
            _backend = _probe()
        except Exception as exc:  # noqa: BLE001
            if forced == "1":
                raise
            logger.warning(f"[native] 后端探测失败，回退 Python: {exc}")
            _backend = "python"
        logger.info(f"[native] 并发后端: {_backend}")
    return _backend


def _rust_impl():
    from . import bindings
    return bindings

def get_bus():
    global _bus
    if _bus is None:
        _bus = _rust_impl().PyEventBus() # type: ignore
    return _bus


def get_timer():
    """取全局定时器（防抖不占 Python 线程）。"""
    global _timer
    if _timer is None:
        _timer = _rust_impl().PyTimer()
    return _timer


def new_stream(capacity: int = 64):
    return _rust_impl().PyStream(capacity)


def reset() -> None:
    """测试用：清空缓存的全局对象。"""
    global _backend, _bus, _timer
    _backend = None
    _bus = None
    _timer = None

__all__=[
    "get_async_dispatch",
    "get_scheduler"
]
