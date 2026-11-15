import base64
from typing import Any, Dict, Optional

from .... import events
from .manager import get_websocket_manager
from .context import frame_request_id, frame_stream_id
from ....core.pipeline import chat

manager = get_websocket_manager()

async def _wm_send_json(client_id: str, event_type: str, payload, ok: bool = True, message: str = "ok"):
    await get_websocket_manager().send_json(
        client_id,
        type=event_type,
        data=payload,
        message=message,
        ok=ok,
    )

async def dispatch(
    client_id: str,
    event: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    request_id: str = "",
    stream_id: str = "",
) -> None:
    """派发一帧；控制帧不进业务 inflight，由连接层即时处理。

    request_id / stream_id 写入 ContextVar，所有 send_json 出站帧自动继承，
    保证同一连接上并发的多条流不串线（api.md §4.2）。
    """
    data = data or {}
    tok_r = frame_request_id.set(request_id)
    tok_s = frame_stream_id.set(stream_id)
    try:
        if event == events.types.WebSocketEventType.SUBSCRIBE:
            subscribed = manager.subscribe(
                client_id, data.get("events") or data.get("types") or []
            )
            await manager.send_json(
                client_id,
                type=event,
                data={"subscriptions": subscribed},
                request_id=request_id,
            )
            return
        if event == events.types.WebSocketEventType.UNSUBSCRIBE:
            remaining = manager.unsubscribe(
                client_id, 
                data.get("events") or data.get("types") or []
            )
            await manager.send_json(
                client_id,
                type=event,
                data={
                    "subscriptions": remaining
                },
                request_id=request_id,
            )
            return
        if event == events.types.WebSocketEventType.CANCEL:
            rid = str(data.get("request_id") or request_id or "")
            cancelled = manager.cancel_request(client_id, rid) if rid else False
            await manager.send_json(
                client_id,
                type=event,
                data={
                    "request_id": rid,
                    "cancelled": cancelled
                },
                ok=cancelled,
                message="已取消在途请求" if cancelled else "无对应在途请求",
                request_id=request_id,
            )
            return
        if not data:
            await _wm_send_json(
                client_id,
                events.types.WebSocketEventType.ERROR,
                data,
                ok=False,
                message="缺少 data",
            )
            return

        if event == events.types.WebSocketEventType.CHAT:
            from .handlers import chat
            await chat.handle_chat(manager,client_id, data)

        elif event == events.types.WebSocketEventType.DOWNLOAD_MODEL:
            from .handlers import download
            await download.handle_download_model(manager,client_id,data)

        elif event == events.types.WebSocketEventType.RecordEventType.RECORD_START:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RecordEventType.RECORD_START,
                data=True,
            )

        elif event == events.types.WebSocketEventType.RecordEventType:
            from .handlers import speech
            await speech.handle_speech_chunk(manager,client_id,data)

        elif event == events.types.WebSocketEventType.RecordEventType.RECORD_STOP:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RecordEventType.RECORD_STOP,
                ok=True,
                message="录音已停止",
            )
        else:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.ERROR,
                message="未知事件",
                ok=False,
            )
    finally:
        frame_request_id.reset(tok_r)
        frame_stream_id.reset(tok_s)