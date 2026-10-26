"""事件总线（线程安全版本）
核心约定：
  * emit() 可以被任意线程调用（主线程(Qt)、Web 线程(有 loop)、工作线程(无 loop)）。
  * 对 async 回调：
      - 当前线程已有运行中的 loop  -> ensure_future 排 task，绝不 asyncio.run()
      - 当前线程没有 loop          -> 交给 `core/native` 的异步派发器
  * 遍历期间允许回调内部再 on/off：先加锁取快照，再脱离锁执行。
"""

import asyncio
import contextlib
import inspect
from collections import defaultdict
from threading import RLock
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar
import weakref

T = TypeVar("T", bound=object)

_dispatcher_cache = None


def _get_dispatcher():
    """取异步派发器（AsyncDispatchLike）"""
    global _dispatcher_cache
    if _dispatcher_cache is None:
        try:
            from ..core.native import get_async_dispatch
            _dispatcher_cache = get_async_dispatch()
        except Exception as exc:  # noqa: BLE001
            print(f"[EventBus] 异步派发器不可用: {exc}")
            _dispatcher_cache = False      # 记负，避免反复尝试
    return _dispatcher_cache or None


def _listener_id(event: str, callback: Any) -> int:
    return hash((event, id(callback))) & 0x7FFFFFFF


class LeakProofEventBus(Generic[T]):
    def __init__(self):
        self.__strong_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.__weak_listeners: Dict[str, List[Any]] = defaultdict(list)
        self.__lock = RLock()

    # ---------- 注册 ----------

    def on(self, event_type: str, callback: Callable, weak: bool = False) -> None:
        with self.__lock:
            if weak:
                # bound method 必须用 WeakMethod，普通 weakref 对 bound method 立即失效
                if inspect.ismethod(callback):
                    ref: Any = weakref.WeakMethod(callback)
                else:
                    ref = weakref.ref(callback)
                self.__weak_listeners[event_type].append(ref)
            else:
                self.__strong_listeners[event_type].append(callback)

    def off(self, event_type: str, callback: Optional[Callable] = None) -> None:
        """取消注册。callback 为 None 时清空该事件的所有监听器"""
        with self.__lock:
            if callback is None:
                self.__strong_listeners.pop(event_type, None)
                self.__weak_listeners.pop(event_type, None)
                return

            if event_type in self.__strong_listeners:
                self.__strong_listeners[event_type] = [
                    cb for cb in self.__strong_listeners[event_type] if cb != callback
                ]
                if not self.__strong_listeners[event_type]:
                    del self.__strong_listeners[event_type]

            if event_type in self.__weak_listeners:
                self.__weak_listeners[event_type] = [
                    r for r in self.__weak_listeners[event_type] if r() != callback
                ]
                if not self.__weak_listeners[event_type]:
                    del self.__weak_listeners[event_type]

    # ---------- 触发 ----------

    def __collect(self, event: str) -> List[Callable]:
        """加锁取快照并顺带清理死亡弱引用，回调内部改动集合不影响本次遍历。"""
        with self.__lock:
            callbacks = list(self.__strong_listeners.get(event, ()))

            alive = []
            for ref in self.__weak_listeners.get(event, ()):
                cb = ref()
                if cb is not None:
                    alive.append(ref)
                    callbacks.append(cb)
            if alive:
                self.__weak_listeners[event] = alive
            else:
                self.__weak_listeners.pop(event, None)

        return callbacks

    @staticmethod
    def __invoke(callback: Callable, args: tuple, kwargs: dict) -> Any:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = None
        if inspect.iscoroutinefunction(callback):
            coro = callback(*args, **kwargs)
        else:
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                coro = result
            else:
                return result
        if loop is not None:
            task = asyncio.ensure_future(coro)
            task.add_done_callback(_consume_task_exception)
            return task
        dispatcher = _get_dispatcher()
        if dispatcher is not None:
            try:
                dispatcher.dispatch(coro)
                return None
            except Exception as e:
                print(f"Event async dispatch failed: {e}")
                # 协程可能已无法安全关闭，显式 close 避免 "never awaited"
                with contextlib.suppress(Exception):
                    coro.close()  # type: ignore
                return None
        print(
            "[EventBus] 警告: 无事件循环且异步派发器不可用，"
            "已丢弃该异步回调（不阻塞调用线程）"
        )
        with contextlib.suppress(Exception):
            coro.close()  # type: ignore
        return None

    def emit(self, event: str, *args, **kwargs) -> Optional[T]:
        results: List[Any] = []
        for callback in self.__collect(event):
            try:
                results.append(self.__invoke(callback, args, kwargs))
            except Exception as e:
                # 单个监听器炸了不能影响其他监听器，也不该让调用方崩掉
                print(f"Event callback error for {event}: {e}")
        return results[-1] if results else None

    def clear(self) -> None:
        with self.__lock:
            self.__strong_listeners.clear()
            self.__weak_listeners.clear()

    # ---------- EventBusLike 协议适配 ----------

    __implements__ = ("EventBusLike",)

    def subscribe(self, event: str, callback: Callable) -> int:
        """协议要求的订阅（返回 id）。"""
        self.on(event, callback, weak=False)
        return _listener_id(event, callback)

    def unsubscribe(self, event: str, sub_id: int) -> bool:
        """按 id 精确解绑。

        协议要求精确解绑 —— 早期 `off(event)` 不带回调会清空
        该事件**所有**监听器，把别人的监听一起摘掉。
        """
        with self.__lock:
            lst = self.__strong_listeners.get(event)
            if not lst:
                return False
            kept = [cb for cb in lst if _listener_id(event, cb) != sub_id]
            removed = len(kept) != len(lst)
            self.__strong_listeners[event] = kept
            return removed

    def subscriber_count(self, event: str) -> int:
        with self.__lock:
            n = len(self.__strong_listeners.get(event, []))
            n += sum(1 for r in self.__weak_listeners.get(event, [])
                     if r() is not None)
            return n


def _consume_task_exception(task: "asyncio.Future") -> None:
    """避免 fire-and-forget 的 task 异常被静默吞掉。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        print(f"Event async callback error: {exc}")
