"""主线程任务调度器（Qt 驱动，零 asyncio 依赖）。

架构前提（见清单第 0 节）：
  * 主线程跑 Qt，**没有 asyncio loop**。
  * 因此本调度器不能用 loop.call_soon_threadsafe 之类的手段唤醒，
    全部改为 threading 原语 + Qt 侧 QTimer(16ms) 轮询消费。
  * 跨线程调用一律带超时（默认 30s），杜绝 D3 类永久阻塞。
"""

import asyncio
import threading
import time
from concurrent import futures
from typing import Any, Callable, Optional

from ..logger import logger
from ..events import on_event_class, types
from ..manager.base import BaseManager

# 默认超时：Live2DController.initialize() 要加载模型 + MediaPipe
DEFAULT_MAIN_THREAD_TIMEOUT = 30.0

def __get_process_events():
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return None
        return app.processEvents
    except Exception:
        return None

def join_with_pump(thread: Optional[threading.Thread], timeout: float = 5.0) -> bool:
    """带 Qt 事件泵的 join（D1）
    Args:
        thread: 线程对象
        timeout: 最长等待时间（秒）
    Returns:
        True 表示线程已结束。

    主线程等待工作线程时，如果干等，而工作线程又在等主线程派发 Qt 任务，
    就会形成「主线程等线程、线程等主线程」的死锁。
    这里一边小步 join，一边处理 Qt 事件，让主线程的派发继续生效。

    如果当前不在 Qt 主循环中（processEvents 不可用），退化为普通 join。
    """
    if thread is None:
        return True
    if not thread.is_alive():
        return True

    process_events = __get_process_events()
    deadline = time.monotonic() + max(0.0, timeout)
    while thread.is_alive():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(0.02)
        if process_events is not None:
            try:
                process_events()
            except Exception:
                process_events = None  # Qt 已退出，别再尝试
    return not thread.is_alive()


@on_event_class([
    (types.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD, "run_on_main_thread"),
    (
        types.AppEventType.MainThreadDispatcherEventType.RUN_ASYNC_ON_MAIN_THREAD,
        "run_async_on_main_thread",
    ),
    (types.AppEventType.MainThreadDispatcherEventType.STOP, "stop"),
])
class MainThreadDispatcher(BaseManager):
    """把任务投递到主线程（Qt 线程）执行。

    - 快路径：调用方本身就在主线程 -> 直接执行，零开销。
    - 慢路径：来自 Web 线程 / 服务线程 -> 入队，由 Qt 侧 16ms 定时器消费，
      调用方在 `future.result(timeout)` 上等待（阻塞的是工作线程，不是 UI）。
    """

    def __init__(self):
        if self._initialized:
            return
        self._sync_tasks: list = []
        self._tasks_lock = threading.Lock()
        self._running = False
        self._ready = False
        self._pending_futures: dict = {}
        self._future_counter = 0
        self._future_lock = threading.Lock()

        self._initialized = True
        logger.info("MainThreadDispatcher initialized")

    def start_processing(self):
        if self._ready:
            return
        self._ready = True
        self._running = True
        logger.info("MainThreadDispatcher processor started")

    # ---------- Qt 侧心跳：消费来自工作线程的任务 ----------

    def pump(self) -> None:
        """由 QTimer(16ms) 在主线程调用。"""
        with self._tasks_lock:
            if not self._sync_tasks:
                return
            tasks_to_execute = self._sync_tasks.copy()
            self._sync_tasks.clear()

        for func, args, kwargs, future_id in tasks_to_execute:
            # B10：先摘掉登记再结算，避免泄漏与超时后的重复 settle
            with self._future_lock:
                future = self._pending_futures.pop(future_id, None)
            try:
                result = func(*args, **kwargs)
            except BaseException as e:  # noqa: BLE001 - 异常要转交给等待方
                if future is not None and not future.done():
                    future.set_exception(e)
                else:
                    logger.exception(f"[Dispatcher] main thread task error: {e}", exc_info=True)
            else:
                if future is not None and not future.done():
                    future.set_result(result)

    def _discard_future(self, future_id: int) -> None:
        with self._future_lock:
            self._pending_futures.pop(future_id, None)

    def run_on_main_thread(
        self,
        func: Callable,
        timeout: float = DEFAULT_MAIN_THREAD_TIMEOUT,
        *args,
        **kwargs
    ) -> Any:
        """在主线程执行同步函数，可从任意线程调用，返回函数结果。

        `kwargs["timeout"]` 会被提取为等待超时（默认 30s），不会传给目标函数。
        """
        if not self._ready:
            raise RuntimeError("MainThreadDispatcher is not ready yet")

        # 快路径：已经在主线程，直接跑
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)

        with self._future_lock:
            future_id = self._future_counter
            self._future_counter += 1
            future: futures.Future = futures.Future()
            self._pending_futures[future_id] = future

        with self._tasks_lock:
            self._sync_tasks.append((func, args, kwargs, future_id))

        try:
            # D3：一律带超时，绝不无限等待
            return future.result(timeout=timeout)
        except futures.TimeoutError:
            self._discard_future(future_id)
            raise TimeoutError(
                f"[Dispatcher] main thread task timed out after {timeout}s: {getattr(func, '__name__', func)}"
            )
        except futures.CancelledError:
            raise
        except Exception as e:
            logger.error(f"run_on_main_thread error: {e}")
            raise

    async def run_async_on_main_thread(
        self,
        coro_or_func,
        timeout: float = DEFAULT_MAIN_THREAD_TIMEOUT,
        *args,
        **kwargs
    ) -> Any:
        """执行一个协程，其中对 Qt 的访问会被路由回主线程。

        A8：主线程不承载 asyncio loop，所以不能在 Qt 线程里
        `new_event_loop().run_until_complete(...)` —— 那会冻结 UI 并可能死锁。
        正确做法：在**调用方自己的 loop** 里 await 这个协程；
        协程内部凡是碰 Qt 的地方，通过 run_on_main_thread() 回到主线程即可。
        语义上依然满足「Qt 操作只在主线程发生」。
        """
        if not self._ready:
            raise RuntimeError("MainThreadDispatcher is not ready yet")

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "[Dispatcher] run_async_on_main_thread 只能在有运行中事件循环的线程调用"
            )
        if asyncio.iscoroutine(coro_or_func):
            return await coro_or_func
        if asyncio.iscoroutinefunction(coro_or_func):
            return await coro_or_func(*args, **kwargs)
        # 普通同步函数：仍然投递到主线程执行，避免阻塞调用方 loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_on_main_thread(coro_or_func, timeout, *args, **kwargs)
        )

    def stop(self):
        self._running = False
        self._ready = False

        with self._future_lock:
            for future in self._pending_futures.values():
                if not future.done():
                    future.cancel()
            self._pending_futures.clear()

        with self._tasks_lock:
            self._sync_tasks.clear()

        logger.info("MainThreadDispatcher stopped")


main_thread_dispatcher = None


def get_main_thread_dispatcher():
    global main_thread_dispatcher
    if main_thread_dispatcher is None:
        main_thread_dispatcher = MainThreadDispatcher()
    return main_thread_dispatcher
