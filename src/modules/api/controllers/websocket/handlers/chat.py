"""chat 帧：跑对话流水线，同时把手机端输入/回复同步给电脑端舞台。

手机打字或语音转写后都会发 `chat`（data.from="mobile"）；服务端除了流式
回复给发起连接，还把输入与最终台词按 uid 定向推给 desktop，供电脑端立绘演出。
未注册连接只走原有单连接回复，不影响旧逻辑。
"""

from ..... import events

_et = events.types.WebSocketEventType
_pipe = events.types.PipelineEventType
MAX_TEXT_LENGTH = 2000


async def _to_desktop(manager, client_id: str, text: str, source: str) -> None:
    """uid 维度定向；未注册连接静默跳过（注册是可选增强）。"""
    uid = manager.uid_of(client_id)
    if not uid:
        return
    await manager.send_to_device(
        uid, "desktop", _et.DEVICE_TEXT_INPUT,
        {
            "text": text,
            "source": source,
            "from": "mobile" if source != "assistant" else "server",
            "from_id": client_id,
            "uid": uid,
        },
        primary_only=True,
        exclude=client_id,
        from_id=client_id,
    )


async def handle_chat(manager, client_id: str, data: dict) -> None:
    text = str(data.get("message") or data.get("text") or "")[:MAX_TEXT_LENGTH]
    if not text.strip():
        await manager.send_json(
            client_id, type=_et.CHAT, ok=False, message="消息不能为空",
        )
        return

    from_mobile = (
        manager.device_of(client_id) == "mobile"
        or str(data.get("from") or "") == "mobile"
    )
    source = str(data.get("source") or "text")
    if from_mobile:
        await _to_desktop(manager, client_id, text, source)

    session_id = str(data.get("session_id") or "默认会话")
    from .....core.pipeline import chat as chat_pipeline

    stream = await chat_pipeline.router_stream(
        user_input=text,
        source=source,  # type: ignore
        session_id=session_id,
    )
    chunks = []
    try:
        async for delta in stream:
            piece = str(delta)
            chunks.append(piece)
            await manager.send_json(
                client_id,
                type=_pipe.LLM_TEXT_DELTA,
                data=delta, ok=True,
            )
    finally:
        stream.cancel()

    final = "".join(chunks).strip()
    if final:
        await manager.send_json(
            client_id, type=_pipe.LLM_FINAL_TEXT, data=final, ok=True
        )
        if from_mobile:
            await _to_desktop(manager, client_id, final, "assistant")
