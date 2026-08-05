import asyncio
from datetime import datetime
from typing import Any, Optional
from fastapi import WebSocket
from typing import Dict

from .. import base
from ...events.types import WebSocketEventType
from ...logger import logger
from ...events import types,on_event_class
from .models import ConnectionInfo, WebSocketResponse

@on_event_class([
    (types.AppEventType.ManagerEventType.WEB_SOCKET_START, "start"),
    (types.AppEventType.ManagerEventType.WEB_SOCKET_STOP, "stop")
])
class WebSocketClinetManager(base._BaseManager):

    def __init__(self, cleanup_interval: int = 120):
        if self._initialized:
            return
        super().__init__()
        self._instance=self
        self.cleanup_interval = cleanup_interval
        self.active_connections: Dict[str, WebSocket] = {}
        self.conn_info: Dict[str, ConnectionInfo] = {}
        self.client_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task = None
        self.is_runing=False
        self._initialized=True
    
    def start(self):
        self._cleanup_task = asyncio.create_task(self.__cleanup_stale_connections())
        self.is_runing=True

    async def connect(self, client_id: str, websocket: WebSocket) -> bool:
        try:
            # 先检查连接状态
            if hasattr(websocket, 'client_state'):
                from starlette.websockets import WebSocketState
                if websocket.client_state != WebSocketState.CONNECTING:
                    logger.warning(f"[WebSocket] Client {client_id} already accepted or closed")
                    return False
            
            await websocket.accept()
            logger.info(f"[WebSocket] Connected client {client_id}")
            
            self.active_connections[client_id] = websocket
            self.conn_info[client_id] = ConnectionInfo(client_id=client_id)
            
            # 发送连接确认
            await self.send_json(
                client_id,
                type=WebSocketEventType.CONNECT,
                data={
                    "client_id": client_id,
                    "connected_at": datetime.now().isoformat(),
                    "last_heartbeat": datetime.now().isoformat()
                }
            )

            return True
        except Exception as e:
            logger.error(f"[WebSocket] Failed to connect client {client_id}: {e}")
            return False

    def disconnect(self, client_id: str) -> None:
        if client_id in self.active_connections:
            ws = self.active_connections[client_id]
            try:
                # 尝试安全关闭
                if hasattr(ws, 'client_state'):
                    from starlette.websockets import WebSocketState
                    if ws.client_state != WebSocketState.DISCONNECTED:
                        asyncio.ensure_future(self.__safe_close(ws))
            except:
                pass
            finally:
                del self.active_connections[client_id]
        
        if client_id in self.conn_info:
            del self.conn_info[client_id]
        
        # 清理任务
        if client_id in self.client_tasks:
            task = self.client_tasks.pop(client_id)
            if not task.done():
                task.cancel()
    
    async def __safe_close(self, websocket: WebSocket) -> None:
        try:
            await websocket.close(code=1000, reason="服务端关闭连接")
        except:
            pass

    async def send_json(self, client_id: str, type: str, data: Optional[Any] = None) -> bool:
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(data=WebSocketResponse(type=type,data=data).to_dict())
                return True
            except Exception as e:
                logger.debug(f"[WebSocket] Send failed for {client_id}: {e}")
                self.disconnect(client_id)
                return False
        return False
    
    async def send_bytes(self, client_id: str, data: bytes) -> bool:
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_bytes(data)
                return True
            except Exception as e:
                logger.debug(f"[WebSocket] Send failed for {client_id}: {e}")
                self.disconnect(client_id)
                return False
        return False

    async def broadcast(self, message: dict, exclude: Optional[str] = None):
        disconnected = []
        for cid, ws in self.active_connections.items():
            if cid == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(cid)
        
        # 批量清理断开的连接
        for cid in disconnected:
            self.disconnect(cid)

    def update_heartbeat(self, client_id: str):
        if client_id in self.conn_info:
            self.conn_info[client_id].update_heartbeat()
            logger.debug(f"[WebSocket] Updated heartbeat for {client_id}")

    def is_alive(self, client_id: str, timeout: int = 60) -> bool:
        info = self.conn_info.get(client_id)
        return info is not None and info.is_alive(timeout)

    async def __cleanup_stale_connections(self, timeout: int = 60):
        while self.is_runing:
            try:
                stale = []
                for cid, info in self.conn_info.items():
                    if not info.is_alive():
                        stale.append(cid)
                for cid in stale:
                    logger.info(f"[WebSocket] Cleaning stale connection {cid}")
                    self.disconnect(cid)
            except Exception as e:
                logger.error(f"[WebSocket] Cleanup error: {e}")
            
            await asyncio.sleep(self.cleanup_interval)
    
    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
         # 关闭所有连接
        for cid in list(self.active_connections.keys()):
            self.disconnect(cid)
        
        # 取消所有任务
        for task in self.client_tasks.values():
            if not task.done():
                task.cancel()
        self.client_tasks.clear()
        self.is_runing=False

_websocket_manager = None

def get_websocket_manager():
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketClinetManager()
    return _websocket_manager