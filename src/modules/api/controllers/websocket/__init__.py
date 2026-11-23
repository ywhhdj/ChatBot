"""WebSocket 连接层。

帧分级：
  * HEARTBEAT：连接层直接回执，不进派发；
  * CONTROL_EVENTS（subscribe / unsubscribe / cancel / **register**）：
    即时执行、不校验 data.client_id、不占 inflight；
  * IMMEDIATE_EVENTS（device.* / record.*）：仍校验 client_id，
    但不占业务 inflight —— 姿态流 18Hz、录音 160ms 分片不会把 8 个
    inflight 名额打满，也不会阻塞心跳；
  * 其余（chat / download_model）：独立任务派发，占用 inflight 与 request_id 取消表。

注册时机：CONNECT 出站帧之后、任何业务消息之前，客户端发 REGISTER；
未注册的连接保持原有 client_id 逻辑，只是不参与 uid / device 定向。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from uuid import uuid4

from ...requests import WebSocketRequest
from .... import events
from .models import ClientEventBridge, logger
from .dispatch import dispatch, get_websocket_manager

MAX_INFLIGHT_PER_CLIENT = 8

_et = events.types.WebSocketEventType
_rec = _et.RecordEventType

# 控制帧：即时执行、不占 inflight，也不强制要求 data.client_id
CONTROL_EVENTS = frozenset({
    _et.SUBSCRIBE,
    _et.UNSUBSCRIBE,
    _et.CANCEL,
    _et.REGISTER,
})

# 高频短帧：即时执行但不跳过 client_id 校验
IMMEDIATE_EVENTS = frozenset({
    *_et.device_events(),
    _rec.RECORD_START,
    _rec.RECORD_STOP,
    _rec.RECORD_CHUNK,
})


def generate_client_id() -> str:
    return f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"


async def __safe_handle(
    client_id: str,
    event: str,
    data: Optional[Dict[str, Any]],
    *,
    request_id: str = "",
    stream_id: str = "",
) -> None:
    try:
        await dispatch(
            client_id=client_id, event=event, data=data,
            request_id=request_id, stream_id=stream_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception(f"[WebSocket] handle {event} for {client_id} failed: {e}", exc_info=True)
        # 单条消息失败只回错误，不切断连接
        get_websocket_manager().submit_to_loop(
            lambda: get_websocket_manager().send_json(
                client_id,
                type=_et.RESULT,
                ok=False,
                message="请求处理失败",
                request_id=request_id,
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
                # receive_json() 已返回 dict；model_validate_json 只吃 str/bytes
                raw = await websocket.receive_json()
                request = (
                    WebSocketRequest.model_validate(raw)
                    if isinstance(raw, dict)
                    else WebSocketRequest.model_validate_json(raw)
                )
            except WebSocketDisconnect:
                logger.info(f"[WebSocket] Client {client_id} disconnected")
                break
            except Exception as exc:  # 坏帧只记录，不断连
                logger.debug(f"[WebSocket] invalid frame from {client_id}: {type(exc).__name__}")
                continue

            manager.update_heartbeat(client_id)
            rid = request.request_id or ""
            sid = request.stream_id or ""
            data = request.data or {}
            # 帧级字段也放进 data，兼容只解析 data 的旧 handler
            if rid and isinstance(data, dict):
                data.setdefault("request_id", rid)
            if sid and isinstance(data, dict):
                data.setdefault("stream_id", sid)

            # 只校验 type。心跳等消息本就没有 data，不能因此断开
            if not request.type:
                await manager.send_json(
                    client_id,
                    type=_et.ERROR,
                    ok=False,
                    message="缺少 type",
                    request_id=rid,
                )
                continue

            if request.type == _et.HEARTBEAT:
                await manager.send_json(
                    client_id,
                    type=_et.HEARTBEAT,
                    data={"client_id": client_id, "ts": datetime.now().isoformat()},
                    ok=True,
                    message="心跳成功",
                    request_id=rid,
                )
                continue

            # 控制帧：不校验 client_id、不占 inflight、立即执行（cancel / register 必须即时）
            if request.type in CONTROL_EVENTS:
                try:
                    await dispatch(
                        client_id=client_id, event=request.type, data=data,
                        request_id=rid, stream_id=sid,
                    )
                except Exception:  # noqa: BLE001
                    await manager.send_json(
                        client_id,
                        type=_et.ERROR,
                        ok=False,
                        message="控制帧处理失败",
                        request_id=rid,
                    )
                continue

            request_client_id = data.get("client_id", "") if isinstance(data, dict) else ""
            if not request_client_id:
                # 原来是 disconnect + return，太激进；回错误并保持连接
                await manager.send_json(
                    client_id,
                    type=_et.RESULT,
                    ok=False,
                    message="缺少 client_id",
                    request_id=rid,
                )
                continue
            if request_client_id != client_id:
                await manager.send_json(
                    client_id,
                    type=_et.RESULT,
                    ok=False,
                    message="client_id 不匹配",
                    request_id=rid,
                )
                continue

            # 设备帧 / 录音帧：同一即时路径，但跳过 inflight 计数，避免高频流互相饿死
            if request.type in IMMEDIATE_EVENTS:
                try:
                    await dispatch(
                        client_id=client_id, event=request.type, data=data,
                        request_id=rid, stream_id=sid,
                    )
                except Exception:  # noqa: BLE001
                    await manager.send_json(
                        client_id,
                        type=_et.ERROR,
                        ok=False,
                        message="即时帧处理失败",
                        request_id=rid,
                    )
                continue

            # 派发为独立任务，接收循环立即返回，
            # 否则一次耗时对话会阻塞心跳与后续消息，甚至被 cleanup 误判为 stale
            inflight = {t for t in inflight if not t.done()}
            if len(inflight) >= MAX_INFLIGHT_PER_CLIENT:
                await manager.send_json(
                    client_id,
                    type=_et.RESULT,
                    ok=False,
                    message="请求过于频繁，请稍后再试",
                    request_id=rid,
                )
                continue

            task = asyncio.create_task(__safe_handle(
                client_id, request.type, data, request_id=rid, stream_id=sid,
            ))
            inflight.add(task)
            manager.track_task(client_id, task)
            # request_id → task 绑定，供 cancel 精确取消自己的在途请求
            if rid:
                manager.track_request(client_id, rid, task)

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
