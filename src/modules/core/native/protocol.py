"""并发层抽象契约

业务代码**只**按这里的协议用并发能力，不关心底层是 Rust 还是 Python。
"""

from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Optional,
    Protocol,
    runtime_checkable,
)


@runtime_checkable
class TaskHandleLike(Protocol):
    """一次提交的句柄。"""

    @property
    def task_id(self) -> str: ...

    def done(self) -> bool: ...

    async def wait_async(self, timeout: Optional[float] = None) -> Any:
        ...

    def wait(self, timeout: Optional[float] = None) -> bool:
        ...

    def result(self, timeout: Optional[float] = None) -> Any:
        ...

    def cancel(self) -> bool: ...

    def then(
        self,
        success_callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ) -> "TaskHandleLike":
        ...


@runtime_checkable
class SchedulerLike(Protocol):
    """调度器协议。"""

    def start(self) -> None: ...

    def stop(self, timeout: float = 5.0, wait: bool = False) -> None: ...

    def is_running(self) -> bool: ...

    def submit(
        self,
        func: Callable,
        *args,
        timeout: float = 10.0,
        priority: int = 50,
        task_type: str = "auto",
        **kwargs,
    ) -> TaskHandleLike:
        ...

    def status_of(self, task_id: str) -> Optional[str]: ...

    def wait(self, task_id: str, timeout: Optional[float] = None) -> bool: ...

    async def wait_async(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Any:
        ...

    def result_of(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Any: ...

    def cancel(self, task_id: str) -> bool: ...

    def stats(self) -> Dict[str, Any]: ...


@runtime_checkable
class StreamReaderLike(Protocol):
    """流消费侧协议"""

    def __aiter__(self) -> "AsyncIterator[Any]": ...

    async def __anext__(self) -> Any: ...

    def is_done(self) -> bool: ...

    def cancel(self) -> bool: ...


@runtime_checkable
class StreamLike(Protocol):
    """流协议"""

    def __aiter__(self) -> "AsyncIterator[Any]": ...

    async def __anext__(self) -> Any: ...

    def push(self, item: Any, timeout: Optional[float] = None) -> None: ...

    def pop(self, timeout: Optional[float] = None) -> Optional[Any]: ...

    def try_pop(self) -> Optional[Any]: ...

    def finish(self) -> None: ...

    def fail(self, msg: str) -> None: ...

    def cancel(self) -> None: ...

    def is_done(self) -> bool: ...

    @property
    def error(self) -> Optional[str]: ...


@runtime_checkable
class EventBusLike(Protocol):
    """事件总线协议"""

    def subscribe(self, event: str, callback: Callable) -> int: ...

    def unsubscribe(self, event: str, sub_id: int) -> bool: ...

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> int:
        ...

    def subscriber_count(self, event: str) -> int: ...


@runtime_checkable
class TimerLike(Protocol):
    """定时器 / 防抖协议。"""

    def debounce(
        self,
        window_ms: int,
        max_wait_ms: int,
        callback: Callable,
        payload: Any = None,
    ) -> int: ...

    def touch(self, timer_id: int) -> bool: ...

    def flush(self, timer_id: int) -> None: ...

    def cancel(self, timer_id: int) -> bool: ...
