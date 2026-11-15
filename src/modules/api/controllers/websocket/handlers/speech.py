# record.audio_chunk 处理：
# 停录空块（audio='' + is_final=True）直接 flush 收尾，不再回「缺少 audio」；
# 按 stream_id 聚合分片为单次识别会话，避免每 160ms 起一条流打满 inflight。
import base64
from typing import Dict

from ..... import events
from .....core.pipeline import chat as chat_pipeline

_SESSIONS: Dict[str, Dict[str, object]] = {}
_MAX_SESSIONS = 32

def _key(client_id: str, stream_id: str) -> str:
    return client_id + '|' + (stream_id or 'asr-default')

async def handle_speech_chunk(manager, client_id: str, data: dict) -> None:
    et = events.types.WebSocketEventType.RecordEventType
    audio = str(data.get('audio') or '')
    is_final = bool(data.get('is_final', False))
    sid = str(data.get('stream_id') or '')
    key = _key(client_id, sid)

    if is_final and not audio:
        state = _SESSIONS.pop(key, None)
        chunks = state.get('chunks', []) if state else []
        payload = b''.join(chunks) if isinstance(chunks, list) else b''
        if payload:
            await _recognize(manager, client_id, payload)
        await manager.send_json(
            client_id,
            type=et.RECORD_STOP,
            data={'finished': True}, 
            ok=True, 
            message='录音已停止'
        )
        return

    if not audio:
        await manager.send_json(
            client_id,
            type=et.RECORD_CHUNK,
            ok=False,
            message='缺少 audio'
        )
        return
    try:
        raw = base64.b64decode(audio)
    except Exception as exc:
        await manager.send_json(
            client_id,
            type=et.RECORD_CHUNK,
            ok=False,
            message='audio 解码失败: %s' % exc
        )
        return

    if len(_SESSIONS) >= _MAX_SESSIONS and key not in _SESSIONS:
        await manager.send_json(
            client_id,
            type=et.RECORD_CHUNK,
            ok=False, 
            message='识别会话过多'
        )
        return

    state = _SESSIONS.setdefault(key, {'chunks': []})
    chunks = state['chunks']
    if isinstance(chunks, list):
        chunks.append(raw)
    if not is_final:
        await manager.send_json(
            client_id,
            type=et.RECORD_CHUNK,
            data={
                'accepted': True, 
                'bytes': len(raw)
            },
            ok=True
        )
        return

    state = _SESSIONS.pop(key, {'chunks': []})
    payload = b''.join(state.get('chunks', []))
    if payload:
        await _recognize(manager, client_id, payload)


async def _recognize(manager, client_id: str, payload: bytes) -> None:
    et = events.types.WebSocketEventType.RecordEventType
    stream = await chat_pipeline.speech_to_text_stream(
        audio_bytes=payload, 
        is_final=True,
    )
    async for text in stream:
        await manager.send_json(
            client_id,
            type=et.RECORD_CHUNK,
            data=text,
            ok=True
        )
