"""record.audio_chunk：按 stream_id 聚合分片 → 后台 ASR → 回传 + 送电脑端。

* 停录空块（audio='' + is_final=True）直接 flush 收尾，不再回「缺少 audio」；
* ASR 识别是慢活：final 帧只投递后台任务，不阻塞 WebSocket 接收循环与心跳；
* 识别文本除回给来源连接外，还按 uid 定向发给 desktop（手机语音送电脑端）。
"""

import asyncio
import base64
from typing import Dict, Set

from ..... import events
from .....core.pipeline import chat as chat_pipeline

_et = events.types.WebSocketEventType
_rec = _et.RecordEventType

_SESSIONS: Dict[str, Dict[str, object]] = {}
_MAX_SESSIONS = 32
_ASR_TASKS: Set[asyncio.Task] = set()
_MAX_ASR_TASKS = 4


def _key(client_id: str, stream_id: str) -> str:
    return client_id + "|" + (stream_id or "asr-default")


def _spawn_recognize(manager, client_id: str, payload: bytes) -> None:
    """有界后台任务：超出上限取消最旧的一条，避免语音连发拖垮 loop。"""
    if len(_ASR_TASKS) >= _MAX_ASR_TASKS:
        oldest = next(iter(_ASR_TASKS), None)
        if oldest is not None and not oldest.done():
            oldest.cancel()
    try:
        task = asyncio.create_task(_recognize(manager, client_id, payload))
    except RuntimeError:  # 无运行中 loop（理论不会，连接层一定在 web loop）
        return
    _ASR_TASKS.add(task)
    task.add_done_callback(_ASR_TASKS.discard)


async def handle_speech_chunk(manager, client_id: str, data: dict) -> None:
    audio = str(data.get("audio") or "")
    is_final = bool(data.get("is_final", False))
    sid = str(data.get("stream_id") or "")
    key = _key(client_id, sid)

    if is_final and not audio:
        state = _SESSIONS.pop(key, None)
        chunks = state.get("chunks", []) if state else []
        payload = b"".join(chunks) if isinstance(chunks, list) else b""
        if payload:
            _spawn_recognize(manager, client_id, payload)
        await manager.send_json(
            client_id,
            type=_rec.RECORD_STOP,
            data={
                "finished": True
            },
            ok=True,
            message="录音已停止",
        )
        return

    if not audio:
        await manager.send_json(
            client_id, type=_rec.RECORD_CHUNK, ok=False, message="缺少 audio"
        )
        return
    try:
        raw = base64.b64decode(audio)
    except Exception as exc:
        await manager.send_json(
            client_id,
            type=_rec.RECORD_CHUNK,
            ok=False,
            message="audio 解码失败: %s" % exc,
        )
        return

    if len(_SESSIONS) >= _MAX_SESSIONS and key not in _SESSIONS:
        await manager.send_json(
            client_id,
            type=_rec.RECORD_CHUNK,
            ok=False,
            message="识别会话过多",
        )
        return

    state = _SESSIONS.setdefault(key, {"chunks": []})
    chunks = state["chunks"]
    if isinstance(chunks, list):
        chunks.append(raw)
    if not is_final:
        await manager.send_json(
            client_id,
            type=_rec.RECORD_CHUNK,
            data={"accepted": True, "bytes": len(raw)},
            ok=True,
        )
        return

    state = _SESSIONS.pop(key, {"chunks": []})
    parts = state.get("chunks", [])
    payload = b"".join(parts) if isinstance(parts, list) else b""
    if payload:
        _spawn_recognize(manager, client_id, payload)


async def _recognize(manager, client_id: str, payload: bytes) -> None:
    parts = []
    try:
        stream = await chat_pipeline.speech_to_text_stream(
            audio_bytes=payload,
            is_final=True,
        )
        async for text in stream:
            piece = str(text)
            parts.append(piece)
            await manager.send_json(
                client_id, type=_rec.RECORD_CHUNK, data=piece, ok=True
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        await manager.send_json(
            client_id,
            type=_rec.RECORD_CHUNK,
            ok=False,
            message="语音识别失败: %s" % type(exc).__name__,
        )
        return

    full = "".join(parts).strip()
    if not full:
        return
    await manager.send_json(
        client_id,
        type=_rec.RECORD_ASR_RESULT,
        data={"text": full},
        ok=True,
    )
    uid = manager.uid_of(client_id)
    if uid:
        await manager.send_to_device(
            uid, "desktop", _et.DEVICE_TEXT_INPUT,
            {
                "text": full,
                "source": "asr",
                "from": "mobile",
                "from_id": client_id,
                "uid": uid,
            },
            primary_only=True,
            exclude=client_id,
            from_id=client_id,
        )
