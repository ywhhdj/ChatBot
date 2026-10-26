import asyncio
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from uuid import uuid4

from ...requests import WebSocketRequest
from .models import ClientEventBridge,logger
from .events import handle_event,events,get_websocket_manager

MAX_INFLIGHT_PER_CLIENT = 8

def generate_client_id() -> str:
    return f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"


async def __safe_handle(client_id: str, event: str, data: Optional[Dict[str, Any]]) -> None:
    try:
        await handle_event(client_id=client_id, event=event, data=data)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception(f"[WebSocket] handle {event} for {client_id} failed: {e}", exc_info=True)
        # W3：单条消息失败只回错误，不切断连接
        get_websocket_manager().submit_to_loop(
            lambda: get_websocket_manager().send_json(
                client_id,
                type=events.types.WebSocketEventType.RESULT,
                ok=False,
                message=str(e),
            )
        )


async def __handle_connection(websocket: WebSocket) -> None:
    manager = get_websocket_manager()
    client_id = generate_client_id()

    connected = await manager.connect(client_id, websocket)
    if not connected:
        return

    bridge = ClientEventBridge(client_id, manager)
    bridge.bind_defaults()
    inflight: set = set()

    try:
        while True:
            try:
                raw = await websocket.receive_json()
            except WebSocketDisconnect:
                logger.info(f"[WebSocket] Client {client_id} disconnected")
                break
            manager.update_heartbeat(client_id)
            try:
                request = WebSocketRequest(**raw)
            except Exception as e:
                logger.debug(f"[WebSocket] bad request from {client_id}: {e}")
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.RESULT,
                    ok=False,
                    message=f"请求格式错误: {e}"
                )
                continue

            # W1：只校验 type。心跳等消息本就没有 data，不能因此断开
            if not request.type:
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.RESULT,
                    ok=False,
                    message="缺少 type"
                )
                continue

            if request.type == events.types.WebSocketEventType.HEARTBEAT:
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.HEARTBEAT,
                    data={
                        "client_id": client_id,
                        "ts": datetime.now().isoformat()
                    },
                    ok=True,
                    message="心跳成功"
                )
                continue

            data = request.data or {}
            request_client_id = data.get("client_id", "") if isinstance(data, dict) else ""
            if not request_client_id:
                # W2：原来是 disconnect + return，太激进；回错误并保持连接
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.RESULT,
                    ok=False,
                    message="缺少 client_id"
                )
                continue
            if request_client_id != client_id:
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.RESULT,
                    ok=False,
                    message="client_id 不匹配"
                )
                continue

            # L6：派发为独立任务，接收循环立即返回，
            # 否则一次耗时对话会阻塞心跳与后续消息，甚至被 cleanup 误判为 stale
            inflight = {t for t in inflight if not t.done()}
            if len(inflight) >= MAX_INFLIGHT_PER_CLIENT:
                await manager.send_json(
                    client_id,
                    type=events.types.WebSocketEventType.RESULT,
                    ok=False,
                    message="请求过于频繁，请稍后再试"
                )
                continue

            task = asyncio.create_task(__safe_handle(client_id, request.type, data))
            inflight.add(task)
            manager.track_task(client_id, task)

    except Exception as e:
        logger.error(f"[WebSocket] Connection error for {client_id}: {e}")
    finally:
        for t in inflight:
            if not t.done():
                t.cancel()
        bridge.unregister()
        manager.disconnect(client_id)

def register_websocket_routes(app: FastAPI):
    @app.websocket("/")
    async def websocket_connect(websocket: WebSocket):
        await __handle_connection(websocket)
    return websocket_connect