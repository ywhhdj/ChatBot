from . import reference
from typing import AsyncGenerator, Awaitable, Callable, Optional, Union, overload
from functools import wraps
from ...types.common import P,R

@overload
def sync_task_scheduler(method: Callable[P, R]) -> Callable[P, reference.TaskReference[R]]:
    ...

@overload
def sync_task_scheduler(*, timeout: int = 10) -> Callable[[Callable[P, R]], Callable[P, reference.TaskReference[R]]]:
    ...

def sync_task_scheduler(
        method: Optional[Callable[P, R]]=None,
        *,
        timeout: int = 10,
        priority: int = 5
    ) -> Union[Callable[P, reference.TaskReference[R]], Callable[[Callable[P, R]], Callable[P, reference.TaskReference[R]]]]:
    """包装同步方法"""
    def decorator(method: Callable[P, R]):
        @wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> reference.TaskReference[R]:
            from .schedular import schedular
            return schedular.submit(
                method,
                "sync",
                timeout,
                priority,
                *args,
                **kwargs
            )
        return wrapper
    if method is None:
        return decorator
    return decorator(method)

@overload
def async_task_scheduler(method: Callable[P, Awaitable[R]]) -> Callable[P, reference.TaskReference[R]]:
    ...

@overload
def async_task_scheduler(*, timeout: int = 10) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, reference.TaskReference[R]]]:
    ...

def async_task_scheduler(
        method: Optional[Callable[P, Awaitable[R]]]=None,
        *,
        timeout: int = 10,
        priority: int = 5
    ) -> Union[Callable[P, reference.TaskReference[R]], Callable[[Callable[P, Awaitable[R]]], Callable[P, reference.TaskReference[R]]]]:
    """包装异步方法"""
    def decorator(method: Callable[P, Awaitable[R]]):
        @wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> reference.TaskReference[R]:
            from .schedular import schedular
            return schedular.submit(
                method,
                "async",
                timeout,
                priority,
                *args,
                **kwargs
            )
        return wrapper
    if method is None:
        return decorator
    return decorator(method)

@overload
def stream_task_scheduler(
    *,
    timeout: int = 10,
    auto_close:bool=True
) -> Callable[[Callable[P, AsyncGenerator[R, None]]], Callable[P, Awaitable[reference.TaskStreamingReference[R]]]]:
    ...

@overload
def stream_task_scheduler(
    method: Callable[P, AsyncGenerator[R, None]],
    *,
    timeout: int = 10,
    auto_close:bool=True
) -> Callable[P, Awaitable[reference.TaskStreamingReference[R]]]:
    ...

def stream_task_scheduler(
    method: Optional[Callable[P, AsyncGenerator[R, None]]]=None,
    *,
    timeout: int = 10,
    auto_close:bool=True
) -> Union[
    Callable[P, Awaitable[reference.TaskStreamingReference[R]]],
    Callable[[Callable[P, AsyncGenerator[R, None]]], Callable[P, Awaitable[reference.TaskStreamingReference[R]]]]
]:
    def decorator(method: Callable[P, AsyncGenerator[R, None]]):
        @wraps(method)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> reference.TaskStreamingReference[R]:
            from .schedular import schedular
            return await schedular.submit_stream(
                method,
                timeout,
                auto_close,
                *args,
                **kwargs
            )
        return wrapper
    if method is None:
        return decorator
    return decorator(method)