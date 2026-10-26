from typing import Any, Optional
from ....logger import logger

class _NativeAsyncDispatch:
    """把协程送到长期存活的 loop —— 给 `events` 用。"""

    def __init__(self) -> None:
        self._submitter = None       # 外部注入的优先
        self._own_loop = None
        self._own_thread = None

    def set_submitter(self, fn) -> None:
        self._submitter = fn

    def _ensure_own_loop(self):
        """没有注入时自建一个后台 loop —— 保证 `is_available()` 恒为真。"""
        import asyncio
        import threading

        if self._own_loop is not None:
            return self._own_loop
        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def _run():
            asyncio.set_event_loop(loop)
            loop.call_soon(ready.set)
            try:
                loop.run_forever()
            finally:
                try:
                    loop.close()
                except Exception:  # noqa: BLE001
                    pass

        t = threading.Thread(
            target=_run,
            name="native-async-dispatch",
            daemon=True
        )
        t.start()
        ready.wait(5.0)
        self._own_loop = loop
        self._own_thread = t
        return loop

    def dispatch(self, coro) -> Any:
        fn = self._submitter
        if fn is not None:
            try:
                return fn(coro)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[native] 注入的提交器失败: {exc}")
        import asyncio

        loop = self._ensure_own_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def is_available(self) -> bool:
        return True


_dispatch: Optional[_NativeAsyncDispatch] = None


def get_async_dispatch():
    global _dispatch
    if _dispatch is None:
        _dispatch = _NativeAsyncDispatch()
    return _dispatch