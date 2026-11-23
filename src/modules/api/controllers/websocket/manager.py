from __future__ import annotations

import asyncio
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Set

from fastapi import WebSocket

from ....manager import base
from ....events import types, on_event_class
from ....logger import logger
from .models import ConnectionInfo
from .context import frame_request_id, frame_stream_id
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
        # 订阅 allowlist：敏感事件必须显式 subscribe 后才推送
        self.client_subscriptions: Dict[str, Set[str]] = {}
        self.request_tasks: Dict[str, Dict[str, asyncio.Task]] = {}
        self.subscribable_events = frozenset({
            types.WebSocketEventType.GET_LOG,
            types.WebSocketEventType.GET_AUDIT_LOGS,
            types.QQBotEventType.QQ_BOT_INFO,
        })

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self.is_runing = False
        self.__pending = 0
        self.__closing: Set[str] = set()
        # 连接标识仍是服务端生成的 client_id；下面三项是「可选增强」的注册索引。
        self.uid_index: Dict[str, Set[str]] = {}
        # uid -> {device: {client_id}}
        self.uid_device_index: Dict[str, Dict[str, Set[str]]] = {}
        # uid -> {device: 主 client_id}（primary_only 定向用，避免多桌面重复演出）
        self._primary_by_device: Dict[str, Dict[str, str]] = {}

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
                info = self.conn_info.pop(client_id, None)
                self._unregister_index_locked(client_id, info)
                tasks = self.client_tasks.pop(client_id, set())
                self.client_subscriptions.pop(client_id, None)
                self.request_tasks.pop(client_id, None)

            # 角色表 / 姿态去重窗口同样必须随连接释放（否则重连会无限堆积）
            try:
                from ....devices import role_registry, stage_router

                role_registry.unregister(client_id)
                stage_router.reset_pose(client_id)
            except Exception:
                pass

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
        ok: bool = True,
        request_id: str = "",
        stream_id: str = "",
        from_id: Optional[str] = None,
    ) -> bool:
        """发送 JSON 帧；带 request_id / stream_id 关联，敏感事件按订阅过滤。

        from_id 表示**真实发送方**；缺省为空。此前误填成接收方 client_id，
        会让「丢弃自己回灌帧」的客户端把服务端推给自己的帧全部丢掉。
        """
        request_id = request_id or frame_request_id.get()
        stream_id = stream_id or frame_stream_id.get()
        if not self.__in_web_loop:
            # 跨线程调用：转为投递，绝不在这里 await WebSocket
            self.submit_to_loop(lambda: self.send_json(
                client_id, type=type, data=data, message=message, ok=ok,
                request_id=request_id, stream_id=stream_id, from_id=from_id,
            ))
            return True

        with self.__lock:
            ws = self.active_connections.get(client_id)
            if type in self.subscribable_events and type not in (
                self.client_subscriptions.get(client_id) or set()
            ):
                return False
        if ws is None:
            return False

        try:
            await ws.send_json(data=WebSocketAPIResponse(
                type=type,
                ok=ok,
                message=message,
                data=data,
                from_id=from_id,
                request_id=request_id,
                stream_id=stream_id,
            ).model_dump())
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

        event_type = message.get("type", "")
        payload = WebSocketAPIResponse(
            type=event_type,
            data=message.get("data"),
            from_id=None,
            request_id=str(message.get("request_id", "") or "") or frame_request_id.get(),
            stream_id=str(message.get("stream_id", "") or "") or frame_stream_id.get(),
        ).model_dump()
        with self.__lock:
            allowed = {
                cid for cid, _ in targets
                if event_type not in self.subscribable_events
                or event_type in (self.client_subscriptions.get(cid) or set())
            }
        disconnected = []
        for cid, ws in targets:
            if cid not in allowed:
                continue
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

    # ---------- 注册维度：uid / device ----------

    def register(
        self,
        client_id: str,
        uid: str,
        device: str = "unknown",
        token: str = "",
    ) -> dict:
        """处理 REGISTER 帧：绑定 uid / device，建立两级索引。

        注册是**可选增强**：失败或未注册的连接仍可按 client_id 正常收发，
        只是不能参与 send_to_uid / send_to_device 的定向。
        """
        raw_uid = str(uid or "").strip()
        if not raw_uid or len(raw_uid) > 64 or not _UID_RE.match(raw_uid):
            return {"ok": False, "message": "uid 非法（1-64 位字母数字 . _ : -）"}

        dev = str(device or "unknown").strip().lower()
        if dev not in ("mobile", "desktop", "unknown"):
            dev = "unknown"

        # 有登录体系时可注入 token 解析器，校验通过后覆盖客户端上报的 uid
        resolved = _resolve_token(token)
        if resolved:
            if len(resolved) > 64 or not _UID_RE.match(resolved):
                return {
                    "ok": False,
                    "message": "token 解析出的 uid 非法"
                }
            raw_uid = resolved

        with self.__lock:
            if client_id not in self.active_connections:
                return {
                    "ok": False,
                    "message": "连接已失效"
                }
            info = self.conn_info.get(client_id)
            if info is None:
                return {
                    "ok": False,
                    "message": "连接信息缺失"
                }
            # 重复注册（重连后 uid/device 变化）先摘掉旧索引，避免幽灵连接
            self._unregister_index_locked(client_id, info)
            info.uid = raw_uid
            info.device = dev
            info.registered = True
            self.uid_index.setdefault(raw_uid, set()).add(client_id)
            self.uid_device_index.setdefault(raw_uid, {}).setdefault(dev, set()).add(client_id)
            self._primary_by_device.setdefault(raw_uid, {})[dev] = client_id
            try:
                from ....devices import role_registry

                role_registry.set_role(client_id, dev, uid=raw_uid)
            except Exception:
                pass
        return {
            "ok": True,
            "uid": raw_uid,
            "device": dev
        }

    def _unregister_index_locked(self, client_id: str, info) -> None:
        """必须在 self.__lock 内调用：按旧值精确摘除索引，空桶立即回收。"""
        uid = getattr(info, "uid", "") if info is not None else ""
        dev = getattr(info, "device", "unknown") if info is not None else "unknown"
        if not uid:
            return
        bucket = self.uid_index.get(uid)
        if bucket is not None:
            bucket.discard(client_id)
            if not bucket:
                self.uid_index.pop(uid, None)

        dev_map = self.uid_device_index.get(uid)
        if dev_map is not None:
            conns = dev_map.get(dev)
            if conns is not None:
                conns.discard(client_id)
                if not conns:
                    dev_map.pop(dev, None)
            if not dev_map:
                self.uid_device_index.pop(uid, None)

        primary = self._primary_by_device.get(uid)
        if primary is not None and primary.get(dev) == client_id:
            rest = dev_map.get(dev) if dev_map else None
            if rest:
                primary[dev] = next(iter(rest))
            else:
                primary.pop(dev, None)
            if not primary:
                self._primary_by_device.pop(uid, None)

    def uid_of(self, client_id: str) -> str:
        with self.__lock:
            info = self.conn_info.get(client_id)
            return info.uid if info is not None else ""

    def device_of(self, client_id: str) -> str:
        with self.__lock:
            info = self.conn_info.get(client_id)
            return info.device if info is not None else "unknown"

    def device_targets(
        self,
        uid: str,
        device: str,
        primary_only: bool = False,
        exclude: str = "",
    ) -> list:
        """uid + device 命中连接；primary_only 时只返回该设备的「主连接」。"""
        if not uid:
            return []
        with self.__lock:
            if primary_only:
                cid = self._primary_by_device.get(uid, {}).get(device, "")
                if not cid or cid == exclude or cid not in self.active_connections:
                    return []
                return [cid]
            targets = list(self.uid_device_index.get(uid, {}).get(device, set()))
        return [c for c in targets if c != exclude and c in self.active_connections]

    async def send_to_uid(
        self,
        uid: str,
        type: str,
        data: Optional[Any] = None,
        *,
        message: str = "ok",
        ok: bool = True,
        exclude: str = "",
        from_id: Optional[str] = None,
        request_id: str = "",
        stream_id: str = "",
    ) -> int:
        """向同一 uid 的所有连接发送；返回实际送达的连接数。"""
        with self.__lock:
            targets = [
                c for c in self.uid_index.get(uid, set())
                if c != exclude and c in self.active_connections
            ]
        return await self._send_many(
            targets,
            type,
            data,
            message=message,
            ok=ok,
            from_id=from_id,
            request_id=request_id,
            stream_id=stream_id
        )

    async def send_to_device(
        self,
        uid: str,
        device: str,
        type: str,
        data: Optional[Any] = None,
        *,
        message: str = "ok",
        ok: bool = True,
        primary_only: bool = False,
        exclude: str = "",
        from_id: Optional[str] = None,
        request_id: str = "",
        stream_id: str = "",
    ) -> int:
        """向同一 uid 下指定 device 发送（手机 → 电脑 / 电脑 → 手机）。"""
        targets = self.device_targets(
            uid, device, primary_only=primary_only, exclude=exclude
        )
        return await self._send_many(
            targets, 
            type, 
            data, 
            message=message, 
            ok=ok,
            from_id=from_id,
            request_id=request_id,
            stream_id=stream_id
        )

    async def broadcast_to_device(
        self,
        device: str,
        type: str,
        data: Optional[Any] = None,
        *,
        exclude: str = "",
        from_id: Optional[str] = None,
    ) -> int:
        """跨 uid 向某类设备广播（可选增强，未注册连接不参与）。"""
        with self.__lock:
            targets = []
            for uid, dev_map in self.uid_device_index.items():
                del uid
                for cid in dev_map.get(device, set()):
                    if cid != exclude and cid in self.active_connections:
                        targets.append(cid)
        return await self._send_many(targets, type, data, from_id=from_id)

    async def _send_many(
        self,
        targets: list,
        type: str,
        data: Optional[Any],
        *,
        message: str = "ok",
        ok: bool = True,
        from_id: Optional[str] = None,
        request_id: str = "",
        stream_id: str = "",
    ) -> int:
        sent = 0
        for cid in targets:
            delivered = await self.send_json(
                cid, type=type, data=data, message=message, ok=ok,
                from_id=from_id, request_id=request_id, stream_id=stream_id,
            )
            if delivered:
                sent += 1
        return sent

    # ---------- 订阅 / 请求级取消（api.md） ----------

    def subscribe(self, client_id: str, events: Optional[list] = None) -> list:
        """只接受固定 allowlist，拒绝任意敏感事件订阅。"""
        with self.__lock:
            if client_id not in self.active_connections:
                return []
            current = self.client_subscriptions.setdefault(client_id, set())
            for item in events or []:
                if str(item) in self.subscribable_events:
                    current.add(str(item))
            return sorted(current)

    def unsubscribe(self, client_id: str, events: Optional[list] = None) -> list:
        with self.__lock:
            current = self.client_subscriptions.get(client_id)
            if current is None:
                return []
            for item in events or []:
                current.discard(str(item))
            return sorted(current)

    def subscriptions(self, client_id: str) -> list:
        with self.__lock:
            return sorted(self.client_subscriptions.get(client_id) or set())

    def track_request(
        self, client_id: str, request_id: str, task: asyncio.Task
    ) -> None:
        """绑定 request_id → task，供 cancel 精确取消自己的在途请求。"""
        if not request_id:
            return
        with self.__lock:
            self.request_tasks.setdefault(client_id, {})[request_id] = task
        task.add_done_callback(
            lambda t: self._forget_request(client_id, request_id, t)
        )

    def _forget_request(
        self, client_id: str, request_id: str, task: asyncio.Task
    ) -> None:
        with self.__lock:
            bucket = self.request_tasks.get(client_id)
            if bucket is not None and bucket.get(request_id) is task:
                bucket.pop(request_id, None)

    def cancel_request(self, client_id: str, request_id: str) -> bool:
        with self.__lock:
            task = (self.request_tasks.get(client_id) or {}).get(request_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    # ---------- per-client 任务管理 ----------

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
            self.uid_index.clear()
            self.uid_device_index.clear()
            self._primary_by_device.clear()

        try:
            from ....devices import role_registry

            role_registry.clear()
        except Exception:
            pass

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


_UID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

# 有登录体系时由应用启动时注入：def resolver(token: str) -> str（返回可信 uid，失败返回 ""）
_token_resolver: Optional[Callable[[str], str]] = None


def set_token_resolver(resolver: Optional[Callable[[str], str]]) -> None:
    """注册 token → uid 解析器；未注入时 token 字段被安全忽略。"""
    global _token_resolver
    _token_resolver = resolver


def _resolve_token(token: str) -> str:
    if not token or _token_resolver is None:
        return ""
    try:
        return str(_token_resolver(str(token)) or "").strip()
    except Exception as exc:  # noqa: BLE001 - 校验失败不能影响注册
        logger.debug(f"[WebSocket] token resolver failed: {type(exc).__name__}")
        return ""


_websocket_manager: Optional[WebSocketClientManager] = None
_manager_lock = threading.Lock()


def get_websocket_manager() -> WebSocketClientManager:
    global _websocket_manager
    if _websocket_manager is None:
        with _manager_lock:
            if _websocket_manager is None:
                _websocket_manager = WebSocketClientManager()
    return _websocket_manager