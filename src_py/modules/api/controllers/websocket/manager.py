from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Set

from fastapi import WebSocket

from ....manager import base
from ....events import types, on_event_class
from ....logger import logger
from .models import ConnectionInfo
from ...response import WebSocketAPIResponse


@on_event_class([
    (types.AppEventType.ManagerEventType.WEB_SOCKET_START, "start"),
    (types.AppEventType.ManagerEventType.WEB_SOCKET_STOP, "stop"),
])
class WebSocketClientManager(base.BaseManager):
    """WebSocket 客户端管理器。

    线程模型：
        写操作（send/disconnect）  ──> 必须发生在 Web loop 线程
        投递操作（submit_to_loop） ──> 任意线程，内部 call_soon_threadsafe
    """

    def __init__(
        self,
        cleanup_interval: float = 30.0,
        heartbeat_timeout: float = 90.0,
        max_connections: int = 50,
        max_pending: int = 500,
    ):
        if self._initialized:
            return
        super().__init__()
        self._instance = self

        self.cleanup_interval = max(5.0, cleanup_interval)
        # W9：心跳超时与清理周期统一由构造参数控制，不再两处硬编码不一致
        self.heartbeat_timeout = max(self.cleanup_interval, heartbeat_timeout)
        self.max_connections = max(1, max_connections)
        self.max_pending = max(16, max_pending)

        # L12：跨线程读写，必须加锁
        self.__lock = threading.RLock()
        self.active_connections: Dict[str, WebSocket] = {}
        self.conn_info: Dict[str, ConnectionInfo] = {}
        self.client_tasks: Dict[str, Set[asyncio.Task]] = {}

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self.is_runing = False
        self.__pending = 0
        self.__closing: Set[str] = set()

        self._initialized = True

    def bind_loop(self, loop: Optional[asyncio.AbstractEventLoop]) -> None:
        """绑定 Web 事件循环（由 api/server.py 在 Web 线程里调用）"""
        self._loop = loop
        if loop is not None and self.is_runing and self._cleanup_task is None:
            self._cleanup_task = loop.create_task(self.__cleanup_stale_connections())

    def start(self):
        if self.is_runing:
            return
        self.is_runing = True
        loop = self._loop
        if loop is not None and self._cleanup_task is None:
            self._cleanup_task = loop.create_task(self.__cleanup_stale_connections())
        logger.info("[WebSocket] manager started")

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._loop

    # ---------- 连接 ----------

    async def connect(self, client_id: str, websocket: WebSocket) -> bool:
        """接受连接。必须在 Web loop 内调用（由 websocket 路由协程调用）。"""
        try:
            from starlette.websockets import WebSocketState

            if websocket.client_state != WebSocketState.CONNECTING:
                logger.warning(f"[WebSocket] Client {client_id} already accepted or closed")
                return False
        except Exception:
            pass

        with self.__lock:
            if len(self.active_connections) >= self.max_connections:
                logger.warning(
                    f"[WebSocket] 连接数已达上限 {self.max_connections}，拒绝 {client_id}"
                )
                return False

        try:
            await websocket.accept()
        except Exception as e:
            logger.error(f"[WebSocket] Failed to accept client {client_id}: {e}")
            return False

        with self.__lock:
            self.active_connections[client_id] = websocket
            self.conn_info[client_id] = ConnectionInfo(client_id=client_id)
            self.client_tasks.setdefault(client_id, set())

        logger.info(f"[WebSocket] Connected client {client_id}")

        await self.send_json(
            client_id,
            type=types.WebSocketEventType.CONNECT,
            data={
                "client_id": client_id,
                "connected_at": datetime.now().isoformat(),
                "last_heartbeat": datetime.now().isoformat(),
            }
        )
        return True

    def disconnect(self, client_id: str) -> None:
        with self.__lock:
            if client_id in self.__closing:
                return
            self.__closing.add(client_id)

        try:
            ws = None
            with self.__lock:
                ws = self.active_connections.pop(client_id, None)
                self.conn_info.pop(client_id, None)
                tasks = self.client_tasks.pop(client_id, set())

            # 取消该连接的所有在途任务（必须在 loop 线程内做）
            loop = self._loop
            if tasks and loop is not None and loop.is_running():
                for task in tasks:
                    if not task.done():
                        try:
                            loop.call_soon_threadsafe(task.cancel)
                        except RuntimeError:
                            pass

            # L11：无 loop 时不能 ensure_future，否则抛 RuntimeError
            if ws is not None:
                self.__request_close(ws)
        finally:
            with self.__lock:
                self.__closing.discard(client_id)

    def __request_close(self, ws: WebSocket) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return
        try:
            from starlette.websockets import WebSocketState

            if getattr(ws, "client_state", None) == WebSocketState.DISCONNECTED:
                return
        except Exception:
            pass
        try:
            # 用 run_coroutine_threadsafe 而不是 ensure_future：
            # 后者要求当前线程有 running loop
            fut = asyncio.run_coroutine_threadsafe(self.__safe_close(ws), loop)
            fut.add_done_callback(_consume_future_exception)
        except RuntimeError:
            pass

    async def __safe_close(self, websocket: WebSocket) -> None:
        try:
            await websocket.close(code=1000, reason="服务端关闭连接")
        except Exception:
            pass

    # ---------- 跨线程投递（核心） ----------

    def submit_to_loop(
        self,
        coro_func: Callable[..., Any],
        *args,
        **kwargs,
    ) -> Optional[Any]:
        """把「发送协程」投递到 Web loop 执行，**立即返回，不阻塞调用线程**。

        这是日志线程 / pipeline 线程 / Qt 主线程向 WebSocket 推消息的唯一正确方式。

        Args:
            coro_func: 返回协程的**函数**（不是协程对象），例如
                       `lambda: manager.send_json(cid, type=..., data=...)`

        Returns:
            concurrent.futures.Future，或 None（loop 不可用 / 背压丢弃 / 连接已断）。
        """
        loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return None

        # 背压：待发送任务过多时丢弃，宁可丢消息也不能让 loop 堆积到卡死
        with self.__lock:
            if self.__pending >= self.max_pending:
                return None
            self.__pending += 1

        def _runner():
            try:
                return asyncio.run_coroutine_threadsafe(coro_func(*args, **kwargs), loop)
            except Exception:
                with self.__lock:
                    self.__pending -= 1
                raise

        try:
            fut = _runner()
        except Exception:
            return None

        def _done(_):
            with self.__lock:
                self.__pending -= 1

        try:
            fut.add_done_callback(_done)
        except Exception:
            with self.__lock:
                self.__pending -= 1
        return fut

    # ---------- 发送（Web loop 内） ----------

    async def send_json(
        self,
        client_id: str,
        type: str,
        data: Optional[Any] = None,
        message: str = "ok",
        ok: bool = True
    ) -> bool:
        """发送 JSON。应在 Web loop 内调用。

        防御：若从其他线程/其他 loop 调用，自动降级为投递，
        避免跨 loop 操作 transport 导致状态损坏（L1/L12）。
        """
        if not self.__in_web_loop:
            # 跨线程调用：转为投递，绝不在这里 await WebSocket
            self.submit_to_loop(lambda: self.send_json(client_id, type=type, data=data, message=message, ok=ok))
            return True

        with self.__lock:
            ws = self.active_connections.get(client_id)
        if ws is None:
            return False

        try:
            await ws.send_json(data=WebSocketAPIResponse(type=type, ok=ok, message=message, data=data, from_id=client_id).model_dump())
            return True
        except Exception as e:
            logger.debug(f"[WebSocket] Send failed for {client_id}: {e}")
            self.disconnect(client_id)
            return False

    async def send_bytes(self, client_id: str, data: bytes) -> bool:
        if not self.__in_web_loop:
            self.submit_to_loop(lambda: self.send_bytes(client_id, data))
            return True

        with self.__lock:
            ws = self.active_connections.get(client_id)
        if ws is None:
            return False
        try:
            await ws.send_bytes(data)
            return True
        except Exception as e:
            logger.debug(f"[WebSocket] Send bytes failed for {client_id}: {e}")
            self.disconnect(client_id)
            return False

    async def broadcast(self, message: dict, exclude: Optional[str] = None) -> None:
        """广播（Web loop 内）。W10：统一用 WebSocketResponse 包装。"""
        if not self.__in_web_loop:
            self.submit_to_loop(lambda: self.broadcast(message, exclude=exclude))
            return

        with self.__lock:
            targets = [
                (cid, ws) for cid, ws in self.active_connections.items() if cid != exclude
            ]

        payload = WebSocketAPIResponse(
            type=message.get("type", ""),
            data=message.get("data"),
            from_id=None,
        )
        disconnected = []
        for cid, ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.append(cid)

        for cid in disconnected:
            self.disconnect(cid)

    @property
    def __in_web_loop(self) -> bool:
        loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return False
        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            return False

    # ---------- 心跳 / 清理 ----------

    def update_heartbeat(self, client_id: str) -> None:
        with self.__lock:
            info = self.conn_info.get(client_id)
            if info is not None:
                info.update_heartbeat()

    def is_alive(self, client_id: str, timeout: Optional[float] = None) -> bool:
        with self.__lock:
            info = self.conn_info.get(client_id)
        if info is None:
            return False
        return info.is_alive(timeout or self.heartbeat_timeout)

    def get_connection_count(self) -> int:
        with self.__lock:
            return len(self.active_connections)

    async def __cleanup_stale_connections(self):
        while self.is_runing:
            try:
                stale = []
                with self.__lock:
                    for cid, info in list(self.conn_info.items()):
                        if not info.is_alive(self.heartbeat_timeout):
                            stale.append(cid)
                for cid in stale:
                    logger.info(f"[WebSocket] Cleaning stale connection {cid}")
                    self.disconnect(cid)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[WebSocket] Cleanup error: {e}")

            await asyncio.sleep(self.cleanup_interval)

    # ---------- per-client 任务管理（W7） ----------

    def track_task(self, client_id: str, task: asyncio.Task) -> None:
        with self.__lock:
            self.client_tasks.setdefault(client_id, set()).add(task)
        task.add_done_callback(lambda t: self.__forget_task(client_id, t))

    def __forget_task(self, client_id: str, task: asyncio.Task) -> None:
        with self.__lock:
            tasks = self.client_tasks.get(client_id)
            if tasks is not None:
                tasks.discard(task)

    # ---------- 停止 ----------

    def stop(self) -> None:
        """停止管理器。

        改为**同步**方法：`WEB_SOCKET_STOP` 由 app 的关闭流程在主线程 emit，
        此时 Web loop 已退出、调度器已停止，任何 async 回调都没有可运行的 loop。
        同步实现保证清理一定能执行完。
        """
        self.is_runing = False

        task = self._cleanup_task
        self._cleanup_task = None
        loop = self._loop
        if task is not None and not task.done():
            if loop is not None and loop.is_running():
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass
            else:
                task.cancel()

        with self.__lock:
            client_ids = list(self.active_connections.keys())
            all_tasks = [t for tasks in self.client_tasks.values() for t in tasks]
            self.client_tasks.clear()

        for cid in client_ids:
            self.disconnect(cid)

        for t in all_tasks:
            if not t.done():
                t.cancel()

        logger.info("[WebSocket] manager stopped")


def _consume_future_exception(fut) -> None:
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        logger.debug(f"[WebSocket] background send failed: {exc}")


_websocket_manager: Optional[WebSocketClientManager] = None
_manager_lock = threading.Lock()


def get_websocket_manager() -> WebSocketClientManager:
    global _websocket_manager
    if _websocket_manager is None:
        with _manager_lock:
            if _websocket_manager is None:
                _websocket_manager = WebSocketClientManager()
    return _websocket_manager