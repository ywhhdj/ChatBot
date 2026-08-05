from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Literal, Optional

from src_py.modules.manager.task.decorator import async_task_scheduler
from src_py.modules.routes.models import RouteType

from .. import events
from ..characters.orchestrator import CharacterOrchestrator
from ..config import get_config
from ..logger import logger
from ..memory.main import HybridMemorySystem
from . import enum, manager

SourceType = Literal["ocr", "asr", "text"]

_llm: Optional[manager.LLM] = None
_asr: Optional[manager.ASR] = None
_tts: Optional[manager.TTS] = None
_memory: Optional[HybridMemorySystem] = None
_char_router: Optional["CharacterChatRouter"] = None


class CharacterChatRouter:
    def __init__(self, llm_manager: manager.LLM) -> None:
        self._orchestrator = CharacterOrchestrator(llm_manager=llm_manager)

    async def route(
        self,
        user_input: str,
        source: str = "text",
        session_id: str = "default",
    ):
        result = await self._orchestrator.process(
            user_input,
            source=source,
            session_id=session_id or "default",
        )
        self._emit_events(result)
        return result

    async def route_stream(
        self,
        user_input: str,
        source: str = "text",
        session_id: str = "default",
        route_type: RouteType = RouteType.PURE_CHAT,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self._orchestrator.process_stream(
            user_input,
            force_channel=route_type,
            session_id=session_id or "default",
            source=source,
        ):
            yield chunk
            await asyncio.sleep(0.02)
        result= self._orchestrator._last_result
        self._emit_events(result)

    def _emit_events(self, result) -> None:
        try:
            if result.chat_response:
                events.emit(events.data.BaseEvent(
                    type=events.types.PipelineEventType.LLM_FINAL_TEXT,
                    args=(result.chat_response,),
                ))
            if result.commands_executed and hasattr(events.types.PipelineEventType, "TASK_EXECUTED"):
                events.emit(events.data.BaseEvent(
                    type=events.types.PipelineEventType.TASK_EXECUTED,
                    args=(result.commands_executed,),
                ))
        except Exception as exc:
            logger.warning(f"Failed to emit chat events: {exc}")


def _provider_kwargs(config) -> dict:
    kwargs = {"model": config.llm.model}
    if config.llm.provider == enum.LLMProviderType.DeepSeek.value:
        kwargs.update({"api_key": config.llm.api_key, "model": config.llm.model})
    elif config.llm.provider == enum.LLMProviderType.ChatGPT.value:
        kwargs.update({"api_url": config.llm.base_url, "api_key": config.llm.api_key, "model": config.llm.model})
    elif config.llm.provider == enum.LLMProviderType.Ollama.value:
        kwargs.update({"api_url": config.llm.base_url, "model": config.llm.model})
    return kwargs


@async_task_scheduler
async def ensure_initialized(session_id: str = "default"):
    print("ensure_initialized")
    global _llm, _asr, _tts, _memory, _char_router
    config = get_config()
    if _llm is None:
        _llm = manager.LLM()
        if config.llm.enabled:
            provider = enum.LLMProviderType(config.llm.provider)
            _llm.intialize_provider(provider, **_provider_kwargs(config))
            _char_router = CharacterChatRouter(
                llm_manager=_llm,
            )
            await _char_router._orchestrator._user_context.init_memory(
                session_id=session_id or "default",
                llm_client=_llm._provider,
                is_db=config.sqlite.enabled,
            )
    if _tts is None and config.tts.enabled:
        _tts = manager.TTS()
        try:
            _tts.intialize_provider(enum.TTSProviderType(config.tts.provider), api_url=config.tts.base_url)
        except Exception as exc:
            logger.warning(f"TTS init skipped: {exc}")
    if _asr is None and config.asr.enabled:
        _asr = manager.ASR()
        try:
            _asr.intialize_provider(enum.ASRProviderType(config.asr.provider), model=config.asr.model)
            _asr.init_asr()
        except Exception as exc:
            logger.warning(f"ASR init skipped: {exc}")

ensure_initialized(session_id="default")
logger.info("LLM manager initialized")


async def router(
    user_input: str,
    source: SourceType,
    session_id: str = "default",
):
    global _char_router
    if not _char_router:
        raise ValueError("LLM manager is not initialized")
    result = await _char_router.route(
        user_input=user_input,
        source=source,
        session_id=session_id or "default",
    )
    return result.chat_response


async def router_stream(
    user_input: str,
    source: SourceType,
    session_id: str = "default",
) -> AsyncGenerator[str, None]:
    global _char_router
    if not _char_router:
        raise ValueError("LLM manager is not initialized")
    async for chunk in _char_router.route_stream(
        user_input=user_input,
        source=source,
        session_id=session_id or "default",
    ):
        events.emit(events.data.BaseEvent(
            type=events.types.PipelineEventType.LLM_TEXT_DELTA,
            args=(chunk,),
        ))
        yield chunk

async def text_to_speech(text: str):
    global _tts
    if _tts is None or not text.strip():
        return
    return await _tts.process_text(text)


async def text_to_speech_stream(text: str):
    global _tts
    if _tts is None or not text.strip():
        return
    stream_ref = await _tts.process_text_stream(text)
    try:
        async for audio_chunk in stream_ref.data:
            if not audio_chunk:
                stream_ref.send_control("stop")
                break
            yield audio_chunk
    finally:
        await stream_ref.close()


async def speech_to_text(audio_bytes: bytes) -> str:
    global _asr
    if _asr is None or not audio_bytes:
        return ""
    try:
        return await _asr.process_audio(audio_bytes)
    except Exception as exc:
        logger.error(f"Error in speech_to_text: {exc}")
        return ""


async def speech_to_text_stream(audio_bytes: bytes, is_final: bool=False):
    global _asr
    if _asr is None or not audio_bytes:
        yield ""
        return
    text = await _asr.process_audio_stream(audio_bytes, is_final=is_final)
    async for chunk in text.data:
        if chunk:
            yield chunk
