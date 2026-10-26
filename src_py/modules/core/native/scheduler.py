from __future__ import annotations
import os
from typing import Any, Callable, Dict, Literal, Optional
from .common.async_dispatch import get_async_dispatch
from ...logger import logger


try:
    import core as _core
except Exception as _exc:  # noqa: BLE001
    _core = None
    _IMPORT_ERROR = str(_exc)
else:
    _IMPORT_ERROR = ""

ASYNC_EXEC_TIMEOUT = float(os.environ.get("ASYNC_EXEC_TIMEOUT", "300"))

class _Handle:
    """Rust 任务的句柄。"""

    __slots__ = ("_sch", "_id")

    def __init__(self, sch: "PyScheduler", task_id: str) -> None:
        self._sch = sch
        self._id = task_id

    @property
    def task_id(self) -> str:
        return self._id

    @property
    def status(self) -> str:
        return self._sch._raw.status(self._id) or "unknown"

    def done(self) -> bool:
        return bool(self._sch._raw.is_done(self._id))

    def wait(self, timeout: Optional[float] = None) -> bool:
        return bool(self._sch._raw.wait(self._id, timeout))

    def result(self, timeout: Optional[float] = None) -> Any:
        if timeout is not None:
            if not self.wait(timeout):
                raise TimeoutError(f"任务 {self._id} 超时")
        st = self.status
        if st in ("pending", "running"):
            self.wait(None)
        return self._sch._raw.result(self._id)

    def cancel(self) -> bool:
        return bool(self._sch._raw.cancel(self._id))

    def __repr__(self) -> str:
        return f"<TaskHandle {self._id} [{self.status}]>"
    
    async def wait_async(self, timeout: Optional[float] = None) -> Any:
        """在调用方 loop 中 await 结果，**不阻塞**。

        注意：Rust 侧的 `wait` 会阻塞等待任务完成，
        必须走专用等待池（已在公共实现里处理），
        绝不能在调用方 loop 上直接阻塞。
        """
        from .common._await import wait_async_generic

        return await wait_async_generic(self.done, self.result, timeout)
    
    def then(
        self,
        success_callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ) -> "_Handle":
        """任务完成后执行回调，返回自身（可链式）。

        与 `TaskReference.then` 语义一致。
        回调在 dispatch 的 loop 上执行，**不阻塞调用方**。
        """
        from .common._await import then_generic

        return then_generic(
            self,
            lambda: self.wait_async(),
            success_callback,
            error_callback,
        )


# ─────────────────────────────────────────────────────────────
# 调度器
# ─────────────────────────────────────────────────────────────

class PyScheduler:
    """Rust 调度器的 Python 包装。"""

    def __init__(self, sync_threads: int = 4, async_threads: int = 4) -> None:
        if _core is None:
            raise RuntimeError(f"Rust 内核不可用: {_IMPORT_ERROR}")
        self._raw = _core.PyScheduler(sync_threads, async_threads)  # type: ignore
        self._sync_threads = sync_threads
        self._async_threads = async_threads
        self._async_executor_wired=False

    # ---------- 生命周期 ----------

    def start(self) -> None:
        self._raw.start()

    def stop(self, timeout: float = 5.0, wait: bool = False) -> None:
        # wait=True 时给更长的宽限，但 Rust 侧仍带硬超时（R14：绝不无限等）
        self._raw.stop(timeout * 3 if wait else timeout)

    def is_running(self) -> bool:
        return bool(self._raw.is_running())

    # ---------- 提交 ----------

    def submit(
        self,
        func: Callable,
        *args,
        task_type:Optional[Literal["sync","async"]]=None,
        timeout: float = 10.0,
        priority: int = 50,
        **kwargs,
    ) -> _Handle:
        import uuid

        task_id = uuid.uuid4().hex[:16]
        kind = task_type if task_type else (
            "async" if _is_coroutine_func(func) else "sync"
        )
        self._raw.submit(
            task_id,
            kind,
            int(priority),
            float(timeout),
            func,
            tuple(args),
            dict(kwargs),
        )
        return _Handle(self, task_id)

    def set_async_executor(self, fn: Callable) -> None:
        """注册协程执行器：`fn(func, args, kwargs) -> awaitable`。

        R9：协程不能在 Rust 里跑，Rust 只管排队与生命周期，
        真正执行时回调到这里，由它投回 asyncio loop。
        """
        self._raw.set_executor(fn)

    def set_on_done(self, fn: Callable) -> None:
        self._raw.set_on_done(fn)

    # ---------- 查询 ----------

    def status_of(self, task_id: str) -> Optional[str]:
        return self._raw.status(task_id)

    def wait(self, task_id: str, timeout: Optional[float] = None) -> bool:
        return bool(self._raw.wait(task_id, timeout))

    def result_of(self, task_id: str, timeout: Optional[float] = None) -> Any:
        if timeout is not None and not self.wait(task_id, timeout):
            raise TimeoutError(f"任务 {task_id} 超时")
        return self._raw.result(task_id)

    def cancel(self, task_id: str) -> bool:
        return bool(self._raw.cancel(task_id))

    def stats(self) -> Dict[str, Any]:
        return dict(self._raw.stats())

    def sweep_completed(self, older_than_secs: float = 300.0) -> int:
        return int(self._raw.sweep_completed(older_than_secs))


def _is_coroutine_func(fn: Any) -> bool:
    import asyncio
    import inspect

    return inspect.iscoroutinefunction(fn) or (
        callable(fn)
        and not inspect.isbuiltin(fn)
        and inspect.iscoroutinefunction(getattr(fn, "__call__", None))
    ) or asyncio.iscoroutinefunction(fn)

_scheduler = None

_wired_schedulers: "set[int]" = set()


def _make_async_executor():
    def _executor(func, args=(), kwargs=None):
        coro = func(*(args or ()), **(kwargs or {}))
        fut= get_async_dispatch().dispatch(coro)
        if hasattr(fut, "result"):
            return fut.result(ASYNC_EXEC_TIMEOUT)
        import asyncio as _aio
        try:
            _aio.get_running_loop()
            raise RuntimeError("执行器在无 loop 线程中被调用，无法 await")
        except RuntimeError:
            return _aio.run(coro)
    return _executor


def _wire_async_executor(scheduler) -> bool:
    """给调度器接上协程执行器与完成回调。

    注册失败**必须告警**。没注册的话异步任务会全部失败，
    Rust 侧直接返回 "未设置异步执行器（async executor）"。
    """
    key = id(scheduler)
    if key in _wired_schedulers:
        return True

    ok = False
    try:
        scheduler.set_async_executor(_make_async_executor())
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[native] 协程执行器注册失败，"
                        f"异步任务将不可用: {exc}")

    # 完成回调同样从未被调用过，一并接上（能接就接，不阻断）
    try:
        scheduler.set_on_done(lambda *args, **kwargs: None)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[native] on_done 注册失败（不影响功能）: {exc}")

    if ok:
        _wired_schedulers.add(key)
    # 记录到调度器上，便于断言"确实注册了"
    try:
        scheduler._async_executor_wired = ok #type:ignore
    except Exception:  # noqa: BLE001
        pass
    return ok


def get_scheduler(sync_threads: int = 4, async_threads: int = 4):
    global _scheduler
    if _scheduler is None:
        from . import scheduler
        _scheduler = scheduler.PyScheduler(sync_threads, async_threads)
        try:
            _scheduler.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[native] 调度器启动失败: {exc}")
        _wire_async_executor(_scheduler)
    return _scheduler