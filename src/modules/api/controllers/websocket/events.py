import base64
from typing import Any, Dict, Optional

from .... import events
from .manager import get_websocket_manager
from .context import frame_request_id, frame_stream_id
from ....core.pipeline import chat

manager = get_websocket_manager()

async def handle_download_model(client_id: str, model_name: str, save_path: str = ""):
    if not model_name:
        await manager.send_json(
            client_id,
            type=events.types.DownloadEventType.ERROR,
            ok=False,
            message="缺少 model_name",
        )
        return
    from ....providers.manager import provider_manager

    async def _send(event_type: str, payload, ok: bool = True, message: str = "ok"):
        await manager.send_json(client_id, type=event_type, data=payload, message=message, ok=ok)

    parsed = _parse_download_target(model_name)
    if parsed is None:
        await _send(
            events.types.DownloadEventType.ERROR,
            {"model": model_name},
            ok=False,
            message="不支持该模型下载",
        )
        return

    capability, provider, model_id = parsed

    # 已安装检测
    status = provider_manager.get_provider_status(capability, provider, model_id)
    if status is None:
        await _send(
            events.types.DownloadEventType.ERROR,
            {"model": model_name, "capability": capability, "provider": provider},
            ok=False,
            message=f"provider {provider} 不存在或不支持下载",
        )
        return
    if status["download_status"].get("installed"):
        await _send(
            events.types.DownloadEventType.ERROR,
            {
                "model": model_name,
                "provider": provider
            },
            ok=False,
            message="模型已存在，无需下载",
        )
        return

    task_id = f"{capability}:{provider}:{model_id or ''}"

    async def _progress(evt: dict) -> None:
        phase = evt.get("phase")
        if phase == "complete":
            await _send(
                events.types.DownloadEventType.COMPLETED,
                {
                    "model": model_name,
                    "capability": capability,
                    "provider": provider,
                    "model_id": model_id,
                    "target_dir": evt.get("target_dir", ""),
                },
                ok=True,
                message="下载完成",
            )
            return
        await _send(
            events.types.DownloadEventType.RUNNING,
            {
                "model": model_name,
                "capability": capability,
                "provider": provider,
                "model_id": model_id,
                "progress": evt.get("progress", 0),
                "file": evt.get("file"),
                "phase": phase or "download",
            },
            ok=True,
            message=f"下载进度: {evt.get('progress', 0)}",
        )

    await _send(
        events.types.DownloadEventType.STARTED,
        {
            "model": model_name,
            "capability": capability,
            "provider": provider,
            "model_id": model_id,
            "task_id": task_id,
        },
        ok=True,
        message="开始下载",
    )

    try:
        result = await provider_manager.download_model(
            capability, provider, model_id,
            progress_callback=_progress,
        )
    except Exception as exc:  # noqa: BLE001
        await _send(
            events.types.DownloadEventType.FAILED,
            {"model": model_name, "capability": capability,
             "provider": provider, "error": str(exc)},
            ok=False,
            message=f"下载失败: {exc}",
        )
        return

    if not result.get("success"):
        await _send(
            events.types.DownloadEventType.FAILED,
            {"model": model_name, "capability": capability,
             "provider": provider, "error": result.get("error", "")},
            ok=False,
            message=f"下载失败: {result.get('error', '')}",
        )


def _parse_download_target(model_name: str):
    """解析下载目标。

    新格式：``"ocr:paddle"`` / ``"ocr:paddle:ppocr"`` / ``"image:comfyui-local"``。
    兼容别名：
      * ``paddle_ocr`` → (``ocr``, ``paddle``, None)
      * ``umi_ocr``    → (``ocr``, ``umi``, None)
      * ``whisper``    → (``asr``, ``whisper``, None)
    暂不支持的 ``google_facelandmarker`` 返回 None（由旧逻辑另行处理）。
    """
    if model_name == "google_facelandmarker":
        return None
    if model_name == "paddle_ocr":
        return ("ocr", "paddle", None)
    if model_name == "umi_ocr":
        return ("ocr", "umi", None)
    if model_name == "whisper":
        return ("asr", "whisper", None)
    parts = model_name.split(":")
    if len(parts) == 2:
        return (parts[0], parts[1], None)
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    return None

async def _wm_send_json(client_id: str, event_type: str, payload, ok: bool = True, message: str = "ok"):
    await get_websocket_manager().send_json(
        client_id,
        type=event_type,
        data=payload,
        message=message,
        ok=ok,
    )


async def handle_chat(client_id: str, message: str) -> None:
    if not message:
        await manager.send_json(
            client_id,
            type=events.types.WebSocketEventType.CHAT,
            ok=False,
            message="消息不能为空",
        )
        return
    """L5：producer 交给调度器，Web loop 只做转发。"""
    stream=await chat.router_stream(
        user_input=message,
        source="text",
        session_id="默认会话",
    )
    try:
        async for text in stream:
            await _wm_send_json(
                client_id,
                events.types.PipelineEventType.LLM_TEXT_DELTA,
                text,
                ok=True,
            )
    finally:
        stream.cancel()


async def handle_speech_chunk(client_id: str, audio: str, is_final: bool) -> None:
    if not audio:
        await manager.send_json(
            client_id,
            type=events.types.WebSocketEventType.RECORD_CHUNK,
            ok=False,
            message="缺少 audio",
        )
        return
    try:
        bd_audio = base64.b64decode(audio)
    except Exception as e:
        await manager.send_json(
            client_id,
            type=events.types.WebSocketEventType.RECORD_CHUNK,
            ok=False,
            message=f"audio 解码失败: {e}",
        )
        return
    stream=await chat.speech_to_text_stream(
        audio_bytes=bd_audio,
        is_final=is_final,
    )
    async for text in stream:
        await _wm_send_json(
            client_id,
            events.types.WebSocketEventType.RECORD_CHUNK,
            text,
            ok=True,
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
                client_id, data.get("events") or data.get("types") or []
            )
            await manager.send_json(
                client_id,
                type=event,
                data={"subscriptions": remaining},
                request_id=request_id,
            )
            return
        if event == events.types.WebSocketEventType.CANCEL:
            rid = str(data.get("request_id") or request_id or "")
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
            await handle_chat(client_id, data.get("message", ""))

        elif event == events.types.WebSocketEventType.DOWNLOAD_MODEL:
            await handle_download_model(
                client_id, data.get("model_name", ""), data.get("save_path", "./models")
            )

        elif event == events.types.WebSocketEventType.RECORD_START:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RECORD_START,
                data=True,
            )

        elif event == events.types.WebSocketEventType.RECORD_CHUNK:
            await handle_speech_chunk(
                client_id, data.get("audio", ""), bool(data.get("is_final", False))
            )

        elif event == events.types.WebSocketEventType.RECORD_STOP:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RECORD_STOP,
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