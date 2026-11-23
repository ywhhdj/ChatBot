"""WebSocket 帧派发：控制帧即时执行，业务帧按类型分流（docs/api.md §4.2 / §4.5）。

* REGISTER 属于 CONTROL_EVENTS，不校验 data.client_id、不占 inflight；
* 设备帧（device.*）与录音控制帧是高频短路径，同样不占业务 inflight；
* request_id / stream_id 写入 ContextVar，所有出站帧自动继承；
* 只有真正需要 data 的业务帧才做「缺少 data」校验，心跳/控制帧不受影响。
"""

from typing import Any, Dict, Optional

from .... import events
from .manager import get_websocket_manager
from .context import frame_request_id, frame_stream_id

manager = get_websocket_manager()

_et = events.types.WebSocketEventType
_rec = _et.RecordEventType
DEVICE_EVENTS = _et.device_events()

# 这些帧必须有 data；其余（心跳、register、record.start/stop…）容忍空 data
_NEEDS_DATA = frozenset({
    _et.CHAT,
    _et.DOWNLOAD_MODEL,
    _rec.RECORD_CHUNK,
    _et.DEVICE_HELLO,
    _et.DEVICE_POSE,
    _et.DEVICE_STAGE_EVENT,
    _et.DEVICE_PLAY_ANIMATION,
    _et.DEVICE_MODEL_SET,
    _et.DEVICE_TEXT_INPUT,
    _et.DEVICE_ASR_TEXT,
})


async def _wm_send_json(
    client_id: str,
    event_type: str,
    payload,
    ok: bool = True,
    message: str = "ok",
) -> None:
    await manager.send_json(
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
    """派发一帧；控制帧不进业务 inflight，由连接层即时处理。"""
    payload: Dict[str, Any] = data if isinstance(data, dict) else {}
    tok_r = frame_request_id.set(request_id)
    tok_s = frame_stream_id.set(stream_id)
    try:
        # ---- 1. REGISTER：CONNECT 之后、业务消息之前的可选首帧 ----
        if event == _et.REGISTER:
            result = manager.register(
                client_id,
                uid=str(payload.get("uid") or ""),
                device=str(payload.get("device") or "unknown"),
                token=str(payload.get("token") or ""),
            )
            ok = bool(result.get("ok"))
            await manager.send_json(
                client_id,
                type=_et.REGISTER,
                ok=ok,
                message="绑定成功" if ok else str(result.get("message") or "绑定失败"),
                data={
                    "uid": str(result.get("uid") or ""),
                    "device": str(result.get("device") or "unknown"),
                },
                request_id=request_id,
            )
            return

        # ---- 2. 其它控制帧：订阅 / 退订 / 取消 ----
        if event == _et.SUBSCRIBE:
            subscribed = manager.subscribe(
                client_id, payload.get("events") or payload.get("types") or []
            )
            await manager.send_json(
                client_id,
                type=event,
                data={"subscriptions": subscribed},
                request_id=request_id,
            )
            return
        if event == _et.UNSUBSCRIBE:
            remaining = manager.unsubscribe(
                client_id, payload.get("events") or payload.get("types") or []
            )
            await manager.send_json(
                client_id,
                type=event,
                data={"subscriptions": remaining},
                request_id=request_id,
            )
            return
        if event == _et.CANCEL:
            rid = str(payload.get("request_id") or request_id or "")
            cancelled = manager.cancel_request(client_id, rid) if rid else False
            await manager.send_json(
                client_id,
                type=event,
                data={"request_id": rid, "cancelled": cancelled},
                ok=cancelled,
                message="已取消在途请求" if cancelled else "无对应在途请求",
                request_id=request_id,
            )
            return

        # ---- 3. 空 data 校验（只针对需要载荷的业务帧） ----
        if event in _NEEDS_DATA and not payload:
            await _wm_send_json(
                client_id, _et.ERROR, payload, ok=False, message="缺少 data"
            )
            return

        # ---- 4. 业务帧 ----
        if event == _et.CHAT:
            from .handlers import chat

            await chat.handle_chat(manager, client_id, payload)

        elif event == _et.DOWNLOAD_MODEL:
            from .handlers import download

            await download.handle_download_model(manager, client_id, payload)

        elif event == _rec.RECORD_START:
            await manager.send_json(
                client_id,
                type=_rec.RECORD_START,
                data=True,
                request_id=request_id,
            )

        elif event == _rec.RECORD_CHUNK:
            # 原来写的是 `event == RecordEventType`（类对象），永远不成立
            from .handlers import speech

            await speech.handle_speech_chunk(manager, client_id, payload)

        elif event == _rec.RECORD_STOP:
            await manager.send_json(
                client_id,
                type=_rec.RECORD_STOP,
                data={"finished": True},
                ok=True,
                message="录音已停止",
                request_id=request_id,
            )

        elif event in DEVICE_EVENTS:
            from .handlers import device

            await device.dispatch_device(manager, client_id, event, payload)

        else:
            await manager.send_json(
                client_id,
                type=_et.ERROR,
                message="未知事件",
                ok=False,
                request_id=request_id,
            )
    finally:
        frame_request_id.reset(tok_r)
        frame_stream_id.reset(tok_s)
