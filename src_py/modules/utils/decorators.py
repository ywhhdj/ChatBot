import asyncio
import time
from functools import wraps
from time import sleep
from typing import Callable, Optional, Tuple, Type,overload
from typing_extensions import ParamSpec, TypeVar
from ..logger import logger

P=ParamSpec("P")
R=TypeVar("R")

@overload
def profile_time(func: Callable[P, R]) -> Callable[P, R]:
    ...

@overload
def profile_time(*, is_debug: bool = False) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...

def profile_time(func: Optional[Callable[P, R]] = None, *, is_debug: bool = False):
    def decorator(inner_func: Callable[P, R]) -> Callable[P, R]:
        @wraps(inner_func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.time()
            result = inner_func(*args, **kwargs)
            end_time = time.time()
            if is_debug:
                logger.debug(f"函数 {inner_func.__name__} 执行时间: {end_time - start_time:.4f} 秒")
            return result
        return wrapper
    if func is None:
        return decorator
    return decorator(func)

@overload
def async_retry(func: Callable[P, R]) -> Callable[P, R]:
    ...

@overload
def async_retry(
    *,
    retry_count: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
    raise_last_exception: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...

def async_retry(
    func: Optional[Callable[P, R]] = None,
    *,
    retry_count: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
    raise_last_exception: bool = True,
):
    def decorator(func: Callable[P, R]):
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
            for attempt in range(retry_count + 1):
                try:
                    return await func(*args, **kwargs)  # type: ignore[misc]
                except (exceptions + exclude_exceptions) as e:
                    if isinstance(e, exclude_exceptions):
                        break
                    logger.error(f"异步函数 {func.__name__} 第 {attempt} 次重试，错误信息: {e}")
                    if attempt == retry_count:
                        if raise_last_exception:
                            raise
                        return None
                    await asyncio.sleep(delay * (backoff_factor**attempt))
        return async_wrapper
    if func is None:
        return decorator
    return decorator(func)
    
@overload
def sync_retry(func: Callable[P, R]) -> Callable[P, R]:
    ...

@overload
def sync_retry(
    *,
    retry_count: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
    raise_last_exception: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...

def sync_retry(
    func: Optional[Callable[P, R]] = None,
    *,
    retry_count: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    exclude_exceptions: Tuple[Type[Exception], ...] = (),
    raise_last_exception: bool = True
):
    def decorator(func: Callable[P, R]):
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
            for attempt in range(retry_count + 1):
                try:
                    return func(*args, **kwargs)
                except (exceptions + exclude_exceptions) as e:
                    if isinstance(e, exclude_exceptions):
                        break
                    logger.error(f"函数 {func.__name__} 第 {attempt} 次重试，错误信息: {e}")
                    if attempt == retry_count:
                        if raise_last_exception:
                            raise
                        return None
                    sleep(delay * (backoff_factor**attempt))
        return sync_wrapper  # type: ignore[return-value]
    if func is None:
        return decorator
    return decorator(func)


