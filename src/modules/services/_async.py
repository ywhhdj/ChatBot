"""服务层共享持久事件循环。

同步服务方法（`PptService.outline` 等）需要调用异步 LLM 门面。若每次都
用 `asyncio.run()`，httpx 连接池按 loop 隔离，每调用一次就新建一个
AsyncClient；临时 loop 关闭后这些 client 再也不会被复用，只会把 LRU 池
里的活跃连接挤掉。

这里用一个进程内共享的 `run_forever()` loop：所有同步服务方法把协程
投递到它，连接池只建一次，停机时由 `shutdown_service_loop()` 释放。
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from .manager import _ServiceLoop

_lock = threading.Lock()
_holder: Optional[_ServiceLoop] = None


def run_coroutine(coro: Any, timeout: Optional[float] = 120.0) -> Any:
    """在共享 loop 上执行协程并同步等待结果"""
    global _holder
    with _lock:
        if _holder is None:
            _holder = _ServiceLoop("shared")
        holder = _holder
    future = holder.submit(coro)
    return future.result(timeout=timeout)


def shutdown_service_loop(timeout: float = 5.0) -> None:
    """应用停机时释放共享 loop（由 ServiceManager.stop 调用）。"""
    global _holder
    with _lock:
        holder = _holder
        _holder = None
    if holder is not None:
        # 先在这个 loop 上关闭 HTTP 连接池：pool.shutdown 对绑定本 loop 的
        # client 会直接 await aclose()，换一个 loop 关等于没关。
        try:
            from ....providers.adapters.adapters.transports.http import shutdown_clients

            holder.submit(shutdown_clients()).result(timeout=min(timeout, 5.0))
        except Exception:  # noqa: BLE001 - 停机清理不允许再抛
            pass
        holder.close(timeout)


__all__ = ["run_coroutine", "shutdown_service_loop"]
