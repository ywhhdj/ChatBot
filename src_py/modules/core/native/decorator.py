"""任务装饰器 —— 走 native 并发内核"""

from __future__ import annotations

from functools import wraps
from typing import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Optional,
    Union,
    overload,
)

from ...types.common import P, R
from .protocol import StreamLike, TaskHandleLike
from . import get_scheduler, get_async_dispatch,new_stream

__all__ = [
    "sync_task_scheduler",
    "async_task_scheduler",
    "stream_task_scheduler",
]


# ═════════════════════════════════════════════════════════════
# 同步任务
# ═════════════════════════════════════════════════════════════


@overload
def sync_task_scheduler(
    method: Callable[P, R],
) -> Callable[P, TaskHandleLike]: ...


@overload
def sync_task_scheduler(
    *,
    timeout: int = 10,
    priority: int = 50,
) -> Callable[[Callable[P, R]], Callable[P, TaskHandleLike]]: ...


def sync_task_scheduler(
    method: Optional[Callable[P, R]] = None,
    *,
    timeout: int = 10,
    priority: int = 50,
) -> Union[
    Callable[P, TaskHandleLike],
    Callable[[Callable[P, R]], Callable[P, TaskHandleLike]],
]:
    """包装同步方法：调用后返回句柄，不阻塞调用线程。"""

    def decorator(method: Callable[P, R]):
        @wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> TaskHandleLike:
            return get_scheduler().submit(
                method,
                task_type="sync",
                priority=priority,
                timeout=timeout,
                *args,
                **kwargs,
            )

        return wrapper

    if method is None:
        return decorator
    return decorator(method)


# ═════════════════════════════════════════════════════════════
# 异步任务
# ═════════════════════════════════════════════════════════════


@overload
def async_task_scheduler(
    method: Callable[P, Awaitable[R]],
) -> Callable[P, TaskHandleLike]: ...


@overload
def async_task_scheduler(
    *,
    timeout: int = 10,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, TaskHandleLike]]: ...


def async_task_scheduler(
    method: Optional[Callable[P, Awaitable[R]]] = None,
    *,
    timeout: int = 10,
    priority: int = 50,
) -> Union[
    Callable[P, TaskHandleLike],
    Callable[[Callable[P, Awaitable[R]]], Callable[P, TaskHandleLike]],
]:
    """包装异步方法：调用后返回句柄，不阻塞调用线程。"""

    def decorator(method: Callable[P, Awaitable[R]]):
        @wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> TaskHandleLike:
            return get_scheduler().submit(
                method,
                task_type="async",
                timeout=timeout,
                priority=priority,
                *args,
                **kwargs,
            )

        return wrapper

    if method is None:
        return decorator
    return decorator(method)


# ═════════════════════════════════════════════════════════════
# 流式任务
# ═════════════════════════════════════════════════════════════


@overload
def stream_task_scheduler(
    *,
    timeout: int = 10,
    auto_close: bool = True,
) -> Callable[
    [Callable[P, AsyncGenerator[R, None]]],
    Callable[P, Awaitable[StreamLike]],
]: ...


@overload
def stream_task_scheduler(
    method: Callable[P, AsyncGenerator[R, None]],
    *,
    timeout: int = 10,
    auto_close: bool = True,
) -> Callable[P, Awaitable[StreamLike]]: ...


def stream_task_scheduler(
    method: Optional[Callable[P, AsyncGenerator[R, None]]] = None,
    *,
    timeout: int = 10,
    auto_close: bool = True,
) -> Union[
    Callable[P, Awaitable[StreamLike]],
    Callable[
        [Callable[P, AsyncGenerator[R, None]]], Callable[P, Awaitable[StreamLike]]
    ],
]:
    """包装异步生成器：`await obj.stream(...)` 后得到流引用。"""

    def decorator(method: Callable[P, AsyncGenerator[R, None]]):
        @wraps(method)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamLike:
            # Rust 内核的 PyScheduler 目前没有 submit_stream。
            # 降级路径：在调度器 loop 上起一个协程，把异步生成器的
            # 产出灌进 native 流。语义与 submit_stream 一致
            # （producer 在调度器侧，消费方拿到 StreamLike）。
            stream = new_stream(capacity=64)
            async def _producer():
                try:
                    async for item in method(*args, **kwargs):
                        try:
                            stream.push(item, timeout=timeout)
                        except Exception:  # noqa: BLE001  流被取消
                            return
                except Exception as exc:  # noqa: BLE001
                    stream.fail(str(exc))
                    return
                finally:
                    if auto_close:
                        stream.finish()
            get_async_dispatch().dispatch(_producer())
            return stream
        return wrapper

    if method is None:
        return decorator
    return decorator(method)