# chat 帧处理
from ..... import events
from .....core.pipeline import chat as chat_pipeline


async def handle_chat(manager, client_id: str, data: dict) -> None:
    text = str(data.get('message') or data.get('text') or '')
    if not text.strip():
        await manager.send_json(
            client_id, type=events.types.WebSocketEventType.CHAT,
            ok=False, message='消息不能为空',
        )
        return
    session_id = str(data.get('session_id') or '默认会话')
    source = str(data.get('source') or 'text')
    stream = await chat_pipeline.router_stream(
        user_input=text, 
        source=source, #type:ignore 
        session_id=session_id,
    )
    try:
        async for delta in stream:
            await manager.send_json(
                client_id, 
                type=events.types.PipelineEventType.LLM_TEXT_DELTA,
                data=delta, ok=True,
            )
    finally:
        stream.cancel()
