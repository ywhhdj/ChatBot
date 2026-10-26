"""native 共用的异步等待实现。

W5：上一轮 `wait_async` 写在 `fallback._Handle` 里，
Rust 后端的 `binding._Handle` 要用得复制一份 ——
两份实现迟早会分叉，而"分叉"比"缺失"更难查
（一个后端不阻塞，另一个卡死，表现还不一样）。

抽成公共函数，两套后端共用一份逻辑。

对应清单：W1 / W5 / W9 / W14 / W15。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

#: 轮询间隔。只在拿不到专用等待池时作为**降级**使用。
#: 正常路径是 executor + 通知，不走轮询。
_POLL_INTERVAL = 0.005

#: 等待池最大线程数。只跑阻塞等待，不跑业务（S7 原则）。
_WAIT_POOL_SIZE = 32


_wait_pool = None
_wait_pool_lock = None


def _get_wait_pool():
    """native 自己的等待池"""
    global _wait_pool, _wait_pool_lock
    if _wait_pool is None:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        if _wait_pool_lock is None:
            _wait_pool_lock = threading.Lock()
        with _wait_pool_lock:
            if _wait_pool is None:
                _wait_pool = ThreadPoolExecutor(
                    max_workers=_WAIT_POOL_SIZE,
                    thread_name_prefix="native-wait",
                )
    return _wait_pool


async def wait_async_generic(
    done_fn: Callable[[], bool],
    result_fn: Callable[[], Any],
    timeout: Optional[float] = None,
    interval: float = _POLL_INTERVAL,
) -> Any:
    """异步等待一个"同步句柄"。
    Parameters
    ----
        done_fn    判断是否结束
        result_fn  取结果（失败时应抛出异常）
        timeout    超时秒数，None 表示不限
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的 loop —— 只能阻塞等
        return _blocking_wait(done_fn, result_fn, timeout)

    try:
        pool = _get_wait_pool()
    except Exception:  # noqa: BLE001
        pool = None

    if pool is not None:
        # 正常路径：阻塞发生在池线程里，loop 完全空闲
        def _block():
            return _blocking_wait(done_fn, result_fn, timeout)

        if timeout is None:
            return await loop.run_in_executor(pool, _block)
        return await asyncio.wait_for(
            loop.run_in_executor(pool, _block), timeout=timeout
        )

    # 降级：让出 + 短间隔
    deadline = None if timeout is None else loop.time() + timeout
    while True:
        if done_fn():
            return result_fn()
        if deadline is not None and loop.time() >= deadline:
            raise TimeoutError("等待超时")
        await asyncio.sleep(interval)


def _blocking_wait(
    done_fn: Callable[[], bool],
    result_fn: Callable[[], Any],
    timeout: Optional[float] = None,
) -> Any:
    """阻塞等待（在池线程里执行，不在调用方 loop 上）。"""
    import time

    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        if done_fn():
            return result_fn()
        now = time.monotonic()
        if deadline is not None and now >= deadline:
            raise TimeoutError("等待超时")
        time.sleep(min(_POLL_INTERVAL,
                       (deadline - now) if deadline else _POLL_INTERVAL))


async def stream_anext(
    try_pop_fn: Callable[[], Any],
    pop_fn: Callable[[], Any],
    is_done_fn: Callable[[], bool],
    timeout: Optional[float] = None,
    error_fn: Optional[Callable[[], Any]] = None,
) -> Any:
    """流的 `__anext__` 公共实现。

    * 队列空但流未结束 → 继续等
    * 流已结束且队列空 → 先查 `error_fn`，有错就 raise，否则
      `StopAsyncIteration`
    * 失败 / 取消 → raise

    混淆前两种会**提前结束**，静默丢掉尾部数据 ——
    这是流实现里最典型的坑。
    """
    loop = asyncio.get_running_loop()

    # 先无阻塞试一次（快路径）
    item = try_pop_fn()
    if item is not None:
        return item

    if is_done_fn():
        # 已结束且拿不到数据 → 真正结束。
        # 但要再确认一次队列确实空了，避免"刚 push 完就 finish"的竞态。
        item = try_pop_fn()
        if item is None:
            _raise_if_error(error_fn)
            raise StopAsyncIteration
        return item

    # 阻塞取（在专用池里，不占调用方 loop）
    try:
        pool = _get_wait_pool()
    except Exception:  # noqa: BLE001
        pool = None

    def _take():
        return pop_fn(timeout) #type: ignore

    try:
        if pool is not None:
            if timeout is None:
                item = await loop.run_in_executor(pool, _take)
            else:
                item = await asyncio.wait_for(
                    loop.run_in_executor(pool, _take), timeout=timeout
                )
        else:
            item = pop_fn(timeout) #type: ignore
    except TimeoutError:
        raise

    if item is None:
        # None 表示 pop 超时或流结束 —— 用 is_done 区分
        if is_done_fn():
            _raise_if_error(error_fn)
            raise StopAsyncIteration
        raise TimeoutError("流读取超时")
    return item


def _raise_if_error(error_fn: Optional[Callable[[], Any]]) -> None:
    """W-C：结束前先检查是否有错误，有就抛出。"""
    if error_fn is None:
        return
    try:
        err = error_fn()
    except Exception:  # noqa: BLE001
        return
    if err:
        raise RuntimeError(str(err))

def then_generic(
    handle: Any,
    wait_async_fn: Callable[[], Any],
    success_callback: Optional[Callable] = None,
    error_callback: Optional[Callable] = None,
) -> Any:
    import inspect as _inspect

    if success_callback is None and error_callback is None:
        return handle

    async def _run():
        try:
            result = await wait_async_fn()
        except asyncio.CancelledError:
            raise                      # Y14：取消不吞
        except Exception as exc:  # noqa: BLE001
            if error_callback is None:
                return
            try:
                r = error_callback(exc)
                if _inspect.isawaitable(r):
                    await r
            except Exception as cb_exc:  # noqa: BLE001
                print(f"[native.then] error_callback 抛异常: {cb_exc}")
            return

        if success_callback is None:
            return
        try:
            r = success_callback(result)
            if _inspect.isawaitable(r):
                await r
        except Exception as cb_exc:  # noqa: BLE001
            print(f"[native.then] success_callback 抛异常: {cb_exc}")

    # 延迟导入，避免 _await → native 的模块级环
    from .. import get_async_dispatch

    get_async_dispatch().dispatch(_run())
    return handle