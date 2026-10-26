"""对话入口：把用户输入接到 路由 / 角色 / 存档 / 上下文 / pipeline 上。

修复对应清单：C5 C6 C7 C8 C9 C15 C17–C21 / CD2 CD6

线程模型：
    router()        —— 可在任意有 loop 的线程调用（Web loop / 调度器 loop）
    router_stream() —— 由 stream_task_scheduler 包成异步生成器，
                       producer 实际跑在**调度器 loop**，Web loop 只消费队列

两条铁律：
  1. 初始化必须**可等待**。原实现 `@async_task_scheduler` 装饰 ensure_initialized，
     调用后返回 TaskReference 就走了，紧接着 router() 必然拿到 None。
  2. 流式结果必须来自**本次调用**，不能读单例上的 `_last_result`（并发会串台）。
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, AsyncGenerator, Literal, Optional

from ..routes.models import RouteType
from ..models import Role
from .. import events
from ..config import get_config
from ..logger import logger
from . import enum, manager
from ..core.native import decorator
from .orchestrator import CharacterOrchestrator
from .emotion.predictor import LLMEmotionClassifier

from .. import runtime
from ..manager.session.models import Session

SourceType = Literal["ocr", "asr", "text"]

_llm: Optional["manager.LLM"] = None
_asr: Optional["manager.ASR"] = None
_tts: Optional["manager.TTS"] = None
_char_router: Optional["Router"] = None
_saved_sessions: Optional[Any] = None  # C15：显式定义，避免 global 悬空

# C18：删除从未赋值的 `_memory`
SYNC_TIMEOUT = 50
STREAM_TIMEOUT = 600

# 初始化只做一次；用 Event 让并发调用方等待同一个初始化过程（CD2）
_init_lock = threading.Lock()
_init_event: Optional[asyncio.Event] = None
_init_error: Optional[BaseException] = None
_default_character_id = "qingmei"
_emotion_classifier: Optional["LLMEmotionClassifier"] = None


class Router:
    """把用户输入交给 CharacterOrchestrator，并把结果转成事件广播出去。"""

    def __init__(self, llm_manager: "manager.LLM") -> None:
        self._orchestrator = CharacterOrchestrator(llm_manager=llm_manager)

    async def route(
        self,
        user_input: str,
        source: str = "text",
        session_id: str = "default",
        force_channel: Optional[RouteType] = None,
    ):
        result = await self._orchestrator.process(
            user_input,
            force_channel=force_channel,
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
        force_channel: Optional[RouteType] = None,
    ) -> AsyncGenerator[str, None]:
        holder: dict = {}
        async for chunk in self._orchestrator.process_stream(
            user_input,
            force_channel=force_channel,
            session_id=session_id or "default",
            source=source,
            result_holder=holder,
        ):
            yield chunk
        result = holder.get("result")
        if result is not None:
            self._emit_events(result)

    def _emit_events(self, result) -> None:
        if result is None:
            return
        try:
            if getattr(result, "chat_response", None):
                events.emit(events.data.BaseEvent(
                    type=events.types.PipelineEventType.LLM_FINAL_TEXT,
                    args=(result.chat_response,),
                ))
            commands = getattr(result, "commands_executed", None)
            if commands:
                # C21：常量化，缺失时只在启动期探测一次，不再每次 hasattr
                event_type = _task_executed_event_type()
                if event_type is not None:
                    events.emit(events.data.BaseEvent(
                        type=event_type,
                        args=(commands,),
                    ))
        except Exception as exc:
            logger.warning(f"Failed to emit chat events: {exc}")


_TASK_EXECUTED_TYPE: Optional[str] = None
_TASK_EXECUTED_PROBED = False


def _task_executed_event_type() -> Optional[str]:
    global _TASK_EXECUTED_TYPE, _TASK_EXECUTED_PROBED
    if not _TASK_EXECUTED_PROBED:
        _TASK_EXECUTED_TYPE = getattr(
            events.types.PipelineEventType, "TASK_EXECUTED", None
        )
        _TASK_EXECUTED_PROBED = True
        if _TASK_EXECUTED_TYPE is None:
            logger.debug("[Chat] PipelineEventType.TASK_EXECUTED 未定义，命令事件不广播")
    return _TASK_EXECUTED_TYPE


# --------------------------------------------------------------------------
# 初始化
# --------------------------------------------------------------------------

def _provider_kwargs(config) -> dict:
    kwargs = {"model": config.llm.model}
    provider = config.llm.provider
    if provider == enum.LLMProviderType.DeepSeek.value:
        kwargs.update({"api_key": config.llm.api_key, "model": config.llm.model})
    elif provider == enum.LLMProviderType.ChatGPT.value:
        kwargs.update({
            "api_url": config.llm.base_url,
            "api_key": config.llm.api_key,
            "model": config.llm.model,
        })
    elif provider == enum.LLMProviderType.Ollama.value:
        kwargs.update({
            "api_url": config.llm.base_url,
            "model": config.llm.model
        })
    return kwargs


def _initialize_provider(target, provider_type, **kwargs) -> None:
    """兼容 `intialize_provider` 的历史拼写。"""
    for name in ("initialize_provider", "intialize_provider"):
        fn = getattr(target, name, None)
        if callable(fn):
            fn(provider_type, **kwargs)
            return
    raise AttributeError(f"{type(target).__name__} 没有 initialize_provider 方法")


async def ensure_initialized_async() -> None:
    global _llm, _asr, _tts, _char_router, _saved_sessions, _init_event, _init_error

    asyncio.get_running_loop()  # 确保在 loop 线程中被调用

    with _init_lock:
        if _init_event is None:
            _init_event = asyncio.Event()
            owner = True
        else:
            owner = False
        event = _init_event

    if not owner:
        await event.wait()
        if _init_error is not None:
            raise _init_error
        return

    try:
        await _do_initialize()
    except BaseException as exc:  # noqa: BLE001 - 要广播给所有等待方
        _init_error = exc
        logger.exception(f"[Chat] 初始化失败: {exc}", exc_info=True)
        raise
    finally:
        # 无论成败都要唤醒等待方，否则他们永久挂起
        event.set()


async def _do_initialize() -> None:
    global _llm, _asr, _tts, _char_router, _saved_sessions, _emotion_classifier

    config = get_config()
    _saved_sessions = runtime.manager.session_manager.get("default")

    if _emotion_classifier is None:
        _emotion_classifier = LLMEmotionClassifier()
        _emotion_classifier.initialize()

    if _llm is None:
        _llm = manager.LLM()
        if config.llm.enabled:
            provider = enum.LLMProviderType(config.llm.provider)
            _initialize_provider(_llm, provider, **_provider_kwargs(config))
            _char_router = Router(llm_manager=_llm)  # type: ignore[union-attr]

    # 记忆系统的初始化只在真正可用时做；失败不能拖垮整个启动
    try:
        from ..context.user import UserContext

        user_context = UserContext()
        await user_context.init_memory_async(
            session_id=_saved_sessions.id if _saved_sessions else "default",
            llm_client=_llm,
            is_db=bool(getattr(config.sqlite, "enabled", False)),
        )
    except Exception as exc:
        logger.warning(f"[Chat] memory init skipped: {exc}")

    if _tts is None and getattr(config.tts, "enabled", False):
        _tts = manager.TTS()
        try:
            _initialize_provider(
                _tts,
                enum.TTSProviderType(config.tts.provider),
                api_url=config.tts.base_url,
            )
        except Exception as exc:
            logger.warning(f"[Chat] TTS init skipped: {exc}")

    if _asr is None and getattr(config.asr, "enabled", False):
        _asr = manager.ASR()
        try:
            _initialize_provider(
                _asr,
                enum.ASRProviderType(config.asr.provider),
                model=config.asr.model,
            )
            # -> ASR 尚未就绪就开始转写。这里用可等待版本。
            if hasattr(_asr, "init_asr_async"):
                await _asr.init_asr_async()  # type: ignore
        except Exception as exc:
            logger.warning(f"[Chat] ASR init skipped: {exc}")


def ensure_initialized() -> None:
    """启动阶段的同步入口（无运行中 loop 时使用）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_do_initialize())
        return
    raise RuntimeError(
        "[Chat] 当前线程已有事件循环，请改用 await ensure_initialized_async()"
    )


def is_initialized() -> bool:
    return _char_router is not None


def _ensure_session(session_id: str):
    """create() 必须沿用传入的 session_id 作为 id。"""
    sess = runtime.manager.session_manager.get(session_id)
    if sess is not None:
        return sess

    char = runtime.manager.character_manager.get_current()
    character_id = getattr(char, "id", None) or _default_character_id
    sess = runtime.manager.session_manager.create(
        name=session_id,
        character_id=character_id,
        session_id=session_id,
    )
    try:
        runtime.manager.session_manager.switch(sess.id)
    except Exception as exc:
        logger.warning(f"[Chat] switch session failed: {exc}")
    return sess


# --------------------------------------------------------------------------
# 对外能力
# --------------------------------------------------------------------------
@decorator.sync_task_scheduler(timeout=SYNC_TIMEOUT)
async def router(
    user_input: str,
    source: SourceType = "text",
    session_id: str = "default",
    force_channel: Optional[RouteType] = None,
):
    """一轮对话（非流式），返回角色回复文本。"""
    global _char_router
    await ensure_initialized_async()

    sess = _ensure_session(session_id)
    result = await _char_router.route(  # type: ignore[union-attr]
        user_input=user_input,
        source=source,
        session_id=session_id,
        force_channel=force_channel,
    )

    # 存档：用同步保存，保证返回前已落盘（CD4）
    try:
        sess.updated_at = time.time()
        runtime.manager.session_manager.save_sync(sess)
    except Exception as exc:
        logger.warning(f"[Chat] save session failed: {exc}")

    return result.chat_response


@decorator.stream_task_scheduler(timeout=STREAM_TIMEOUT)
async def router_stream(
    user_input: str,
    source: SourceType = "text",
    session_id: str = "default",
    force_channel: Optional[RouteType] = None,
) -> AsyncGenerator[str, None]:
    """一轮对话（流式）。producer 跑在调度器 loop，Web loop 只消费。"""
    global _char_router
    await ensure_initialized_async()

    sess = _ensure_session(session_id)

    full: list[str] = []
    try:
        async for chunk in _char_router.route_stream(  # type: ignore[union-attr]
            user_input=user_input,
            source=source,
            session_id=session_id or "default",
            force_channel=force_channel,
        ):
            if not chunk:
                continue
            full.append(chunk)
            events.emit(events.data.BaseEvent(
                type=events.types.PipelineEventType.LLM_TEXT_DELTA,
                args=(chunk,),
            ))
            yield chunk
    finally:
        pass


def _append_session_messages(sess: Session, user_input: str, reply: str) -> None:
    sess.messages.append({
        "role": Role.USER, 
        "content": user_input, 
        "timestamp": time.time()
    })
    sess.messages.append({
        "role": Role.ASSISTANT, 
        "content": reply, 
        "timestamp": time.time()
    })
    if len(sess.messages) > 200:
        sess.messages = sess.messages[-200:]


@decorator.async_task_scheduler
async def text_to_speech(text: str):
    global _tts
    if _tts is None or not text or not text.strip():
        return None
    return await _tts.process_text(text)


@decorator.stream_task_scheduler(timeout=STREAM_TIMEOUT)
async def text_to_speech_stream(text: str):
    global _tts
    if _tts is None or not text or not text.strip():
        return
    async for audio_chunk in _tts.process_text_stream(text):
        if audio_chunk:
            yield audio_chunk


@decorator.async_task_scheduler
async def speech_to_text(audio_bytes: bytes) -> str:
    global _asr
    if _asr is None or not audio_bytes:
        raise ValueError("ASR manager is not initialized")
    try:
        return await _asr.process_audio(audio_bytes)
    except Exception as exc:
        logger.error(f"Error in speech_to_text: {exc}")
        return ""


@decorator.stream_task_scheduler(timeout=STREAM_TIMEOUT)
async def speech_to_text_stream(audio_bytes: bytes, is_final: bool = False):
    global _asr
    if _asr is None or not audio_bytes:
        raise ValueError("ASR manager is not initialized")
    async for chunk in _asr.process_audio_stream(audio_bytes, is_final=is_final):
        if chunk:
            yield chunk
