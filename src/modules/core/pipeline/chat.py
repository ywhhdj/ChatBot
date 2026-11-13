"""对话入口：把用户输入接到 路由 / 角色 / 存档 / 上下文 / provider 上。

线程模型：
    router()        —— 可在任意有 loop 的线程调用（Web loop / 调度器 loop）
    router_stream() —— 由 stream_task_scheduler 包成异步生成器，
                       producer 实际跑在**调度器 loop**，Web loop 只消费队列

两条铁律：
  1. 初始化必须**可等待**。原实现装饰成后台任务后直接拿返回值，
     紧接着 router() 必然拿到 None。
  2. 流式结果必须来自**本次调用**，不能读单例上的 `_last_result`（并发串台）。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any, AsyncGenerator, Literal, Optional

from ..routes.models import RouteType
from ...models import Role
from ... import events
from ...config import get_config
from ...logger import logger
from ..native import decorator
from .orchestrator import CharacterOrchestrator
from ...providers.entity import LLM, ASR, TTS

from ... import runtime
from ...manager.session.models import Session

SourceType = Literal["ocr", "asr", "text"]

_llm: Optional[LLM] = None
_asr: Optional[ASR] = None
_tts: Optional[TTS] = None
_char_router: Optional["Router"] = None
_saved_sessions: Optional[Any] = None

SYNC_TIMEOUT = 50
STREAM_TIMEOUT = 600

# 初始化只做一次。不能用 asyncio.Event：项目里 Web loop、调度器 loop 与
# to_thread 临时 loop 并存，Event 绑定创建它的 loop，跨 loop await 会直接
# RuntimeError。改用线程安全的 concurrent Future + asyncio.wrap_future，
# 每个调用方在自己的 loop 上等待同一个初始化过程。
_init_lock = threading.Lock()
_init_future: Optional["concurrent.futures.Future[None]"] = None
_init_error: Optional[BaseException] = None
_default_character_id = "qingmei"

#: capability → 配置里的字段名（app.conf 允许覆盖 Registry 默认值）
_CONFIG_KEYS = {
    "llm": ("llm", "provider", "model", "api_key", "base_url"),
    "tts": ("tts", "provider", "", "api_key", "base_url"),
    "asr": ("asr", "provider", "model", "api_key", "base_url"),
}


class Router:
    """把用户输入交给 CharacterOrchestrator，并把结果转成事件广播出去。"""

    def __init__(self, llm_manager: LLM) -> None:
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
    return _TASK_EXECUTED_TYPE


# --------------------------------------------------------------------------
# 供应商初始化（唯一入口：Registry）
# --------------------------------------------------------------------------

def _normalize_provider(name: str, available: list, fallback: str) -> str:
    """app.conf 里的驼峰/别名（GPTSovits、ope…）映射到 Registry 的 provider id。"""
    wanted = str(name or "").strip().lower().replace("-", "").replace("_", "")
    for pid in available:
        if str(pid).lower().replace("-", "").replace("_", "") == wanted:
            return str(pid)
    return fallback if fallback in available else (available[0] if available else "")


def _provider_kwargs(
    config, capability: str, provider: str = "", model: str = ""
) -> tuple:
    """从 Registry 取扁平配置，并叠加 app.conf 的显式覆盖。

    返回 ``(flat, provider_id, model_id)``。不再按供应商名写死分支：
    新增一个云端供应商只需改 JSON，不用改这里。
    """
    from ...providers import factory

    reg = factory.reload_registry()
    available = reg.provider_ids(capability)
    if not available:
        raise RuntimeError(f"[Chat] {capability} 没有任何可用供应商配置")

    section, provider_field, model_field, key_field, url_field = _CONFIG_KEYS[capability]
    cfg = getattr(config, section, None)
    raw_provider = provider or str(getattr(cfg, provider_field, "") or "")
    fallback = {"llm": "deepseek", "tts": "gptsovits", "asr": "whisper"}[capability]
    provider_id = _normalize_provider(raw_provider, available, fallback)

    raw_model = model or str(getattr(cfg, model_field, "") or "") if model_field else model
    spec = reg.spec(capability, provider_id, raw_model or None)
    flat = spec.flat(include_secrets=True)

    if cfg is not None:
        key = getattr(cfg, key_field, "") or ""
        url = getattr(cfg, url_field, "") or ""
        secret_field = str((spec.endpoint.get("auth") or {}).get("field") or "api_key")
        if str(key).strip():
            flat[secret_field] = str(key).strip()
        if str(url).strip():
            flat["base_url"] = str(url).strip().rstrip("/")
    return flat, provider_id, spec.model_id


# --------------------------------------------------------------------------
# 初始化
# --------------------------------------------------------------------------

def _init_ready() -> bool:
    """编排器与 LLM 门面都已建立，即视为初始化完成。"""
    return _char_router is not None and _llm is not None


def _claim_initialization() -> tuple:
    """返回 (future, owner)。owner=True 的调用方负责真正执行初始化。"""
    global _init_future
    with _init_lock:
        if _init_future is None and _init_ready():
            return None, False
        if _init_future is None:
            _init_future = concurrent.futures.Future()
            owner = True
        else:
            owner = False
        return _init_future, owner


def _release_initialization(fut: "concurrent.futures.Future[None]", exc: Optional[BaseException]) -> None:
    """广播结果；失败时清空状态，让下一次请求可以重试。"""
    global _init_future
    if exc is not None:
        with _init_lock:
            _init_future = None
        if not fut.done():
            fut.set_exception(exc)
    elif not fut.done():
        fut.set_result(None)


async def ensure_initialized_async() -> None:
    """任意 loop 都可调用；并发请求共享同一次初始化。"""
    global _init_error

    fut, owner = _claim_initialization()
    if fut is None:
        return
    if not owner:
        # wrap_future 把线程安全的 concurrent Future 适配到调用方自己的 loop，
        # 回调经 call_soon_threadsafe 派发，不会跨 loop 复用 asyncio 原语。
        await asyncio.wrap_future(fut)
        return

    try:
        _init_error = None
        await _do_initialize()
    except BaseException as exc:  # noqa: BLE001 - 广播给所有等待方
        _init_error = exc
        logger.warning(f"[Chat] 初始化失败: {exc}")
        _release_initialization(fut, exc)
        raise
    else:
        _release_initialization(fut, None)


async def _do_initialize() -> None:
    global _llm, _asr, _tts, _char_router, _saved_sessions

    config = get_config()
    _saved_sessions = runtime.manager.session_manager.get("default") # type: ignore

    if _llm is None:
        _llm = LLM()
        if config.llm.enabled:
            flat, provider_id, model_id = _provider_kwargs(config, "llm")
            _llm.initialize_provider(provider_id, model_id=model_id, **flat) # type: ignore
            _llm.init_provider_client(**flat) # type: ignore
        _char_router = Router(llm_manager=_llm) # type: ignore

    try:
        from ..context.user import UserContext

        user_context = UserContext()
        await user_context.init_memory_async(
            session_id=_saved_sessions.id if _saved_sessions else "default",
            llm_client=_llm,
            is_db=bool(getattr(config.sqlite, "enabled", False)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Chat] memory init skipped: {exc}")

    if _tts is None and config.tts.enabled:
        try:
            flat, provider_id, model_id = _provider_kwargs(config, "tts")
            _tts = TTS()
            _tts.initialize_provider(provider_id, model_id=model_id, **flat) # type: ignore
            _tts.init_provider_client(**flat) # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Chat] TTS init skipped: {exc}")
            _tts = None

    if _asr is None and config.asr.enabled:
        try:
            flat, provider_id, model_id = _provider_kwargs(config, "asr")
            _asr = ASR()
            _asr.initialize_provider(provider_id, model_id=model_id, **flat) # type: ignore
            await _asr.init_provider_client(**flat)  # # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Chat] ASR init skipped: {exc}")
            _asr = None


def ensure_initialized() -> None:
    """启动阶段的同步入口（无运行中 loop 时使用）"""
    global _init_error
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "[Chat] 当前线程已有事件循环，请改用 await ensure_initialized_async()"
        )

    fut, owner = _claim_initialization()
    if fut is None:
        return
    if not owner:
        fut.result(timeout=SYNC_TIMEOUT)
        return

    try:
        _init_error = None
        asyncio.run(_do_initialize())
    except BaseException as exc:  # noqa: BLE001
        _init_error = exc
        logger.warning(f"[Chat] 同步初始化失败: {exc}")
        _release_initialization(fut, exc)
        raise
    else:
        _release_initialization(fut, None)


def is_initialized() -> bool:
    return _char_router is not None and _llm is not None and _llm.is_initialized


def _ensure_session(session_id: str):
    sess = runtime.manager.session_manager.get(session_id) # type: ignore
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
        runtime.manager.session_manager.switch(sess.id) # type: ignore
    except Exception as exc:  # noqa: BLE001
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
    await ensure_initialized_async()
    if not is_initialized():
        raise RuntimeError("[Chat] LLM 未初始化（检查 config.llm.enabled 与供应商配置）")

    sess = _ensure_session(session_id)
    result = await _char_router.route(  # type: ignore[union-attr]
        user_input=user_input,
        source=source,
        session_id=session_id,
        force_channel=force_channel,
    )

    try:
        sess.updated_at = time.time()
        runtime.manager.session_manager.save_sync(sess) # type: ignore
    except Exception as exc:  # noqa: BLE001
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
    await ensure_initialized_async()
    if not is_initialized():
        raise RuntimeError("[Chat] LLM 未初始化（检查 config.llm.enabled 与供应商配置）")

    _ensure_session(session_id)
    async for chunk in _char_router.route_stream(  # type: ignore[union-attr]
        user_input=user_input,
        source=source,
        session_id=session_id or "default",
        force_channel=force_channel,
    ):
        if not chunk:
            continue
        events.emit(events.data.BaseEvent(
            type=events.types.PipelineEventType.LLM_TEXT_DELTA,
            args=(chunk,),
        ))
        yield chunk


def _append_session_messages(sess: Session, user_input: str, reply: str) -> None:
    sess.messages.append({
        "role": Role.USER,
        "content": user_input,
        "timestamp": time.time(),
    })
    sess.messages.append({
        "role": Role.ASSISTANT,
        "content": reply,
        "timestamp": time.time(),
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
    except Exception as exc:  # noqa: BLE001
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
