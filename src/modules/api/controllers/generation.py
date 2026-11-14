"""generate.py —— 生成类（generation）API 聚合控制器。

设计意图
────────
把「一次调用产出内容」的接口集中到同一模块，避免生成能力散落在

chat / chat.stream / tts / asr / image / ocr / embedding
+ command（工具命令生成与执行）
+ status（生成能力就绪状态）
+ folder / progress-stream（生成任务辅助）

`endpoints.json` 中本组端点的 handler 一律指向本模块，op 前缀统一为

硬约束（沿用 api/_common.py 与 FrontendBackendContract.md）
──────────────────────────────────────────────────────────
1. Web loop 只转发：推理/文件 IO 交给任务调度器或 asyncio.to_thread。
2. 二进制一律 base64，不引入 multipart。
3. 所有失败经 ApiError → 统一信封；不回显内部异常详情与凭据。
4. 外部传入的 provider / model_id 必须落在 Registry 白名单内。
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import os
import platform
import subprocess
import threading
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .._common import run_in_scheduler, safe_dict, to_thread
from ..dto import (
    ASRResultData,
    AbilityStatus,
    ChatResultData,
    CommandResultData,
    EmbeddingData,
    GenerationStatusData,
    ImageGenerateData,
    OCRResultData,
    TTSResultData,
)
from ..requests import (
    ASRRequest,
    ChatRequest,
    ChatStreamRequest,
    CommandRunRequest,
    EmbeddingRequest,
    ImageGenerateRequest,
    OCRRecognizeRequest,
    TTSRequest,
)
from ..response import ApiError, ApiResponse, get_request_id, sse, success

router = APIRouter(prefix="", tags=["generate"])

STREAM_TIMEOUT = 600.0
AUDIO_TIMEOUT = 120.0

# --------------------------------------------------------------------------
# 进度流：长任务（模型下载 / PPT / 批量生成）用 set_progress 写入
# --------------------------------------------------------------------------

_progress_lock = threading.Lock()
_progress_store: Dict[str, Dict[str, Any]] = {}


def set_progress(task_id: str, data: Dict[str, Any]) -> None:
    """供下载/后台任务写入进度；终态 status 取 done / error / cancelled。"""
    if not task_id:
        return
    with _progress_lock:
        snapshot = dict(_progress_store.get(task_id) or {})
        snapshot.update(data)
        snapshot["task_id"] = task_id
        snapshot["ts"] = time.time()
        _progress_store[task_id] = snapshot


def clear_progress(task_id: str) -> None:
    with _progress_lock:
        _progress_store.pop(task_id, None)


# --------------------------------------------------------------------------
# 通用辅助
# --------------------------------------------------------------------------


def _route_type(value: Optional[str]):
    if not value:
        return None
    from ...core.routes.models import RouteType

    try:
        return RouteType(value)
    except ValueError:
        valid = [e.value for e in RouteType]
        raise ApiError.bad_request(f"路由类型 {value} 无效，可选: {', '.join(valid)}")


async def _maybe_await(value: Any) -> Any:
    """门面/适配层方法可能是同步也可能是协程，统一 await。"""
    if inspect.isawaitable(value):
        return await value
    return value


def _decode_b64(value: str, field: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        raise ApiError.bad_request(f"{field} 不是合法的 base64")
    if not raw:
        raise ApiError.bad_request(f"{field} 不能为空")
    return raw


def _provider_manager():
    from ...providers.manager import provider_manager

    try:
        if not provider_manager.get_pipeline_all_configs():
            provider_manager.load_config()
    except Exception:  # noqa: BLE001
        provider_manager.load_config()
    return provider_manager


def _resolve_provider(capability: str, requested: Optional[str]) -> str:
    """校验 provider 白名单；未指定时取当前选中，再退到第一个可用。"""
    pm = _provider_manager()
    valid = list(pm.get_valid_providers(capability) or [])
    if not valid:
        raise ApiError.not_initialized(f"{capability} provider", "能力未配置")
    if requested:
        if requested not in valid:
            raise ApiError.bad_request(
                f"provider {requested} 不适用于 {capability}，可选: {', '.join(valid)}"
            )
        return requested
    current = (getattr(pm, "_current", None) or {}).get(capability) or {}
    name = str(current.get("name") or "")
    return name if name in valid else valid[0]


async def _capability_entity(capability: str, provider: Optional[str], model_id: Optional[str]):
    """优先复用已注册的能力门面；未注册时用工厂构建 shim（不写回 Registry）。"""
    pm = _provider_manager()
    entity = pm._get_adapter_manager(capability)
    if entity is not None:
        return entity
    from ...providers import factory

    name = _resolve_provider(capability, provider)
    try:
        return await to_thread(
            factory.create_adapter, capability, name, model_id=model_id
        )
    except ValueError as exc:
        raise ApiError.not_initialized(f"{capability} 适配器", str(exc))
    except Exception as exc:  # noqa: BLE001
        raise ApiError.internal(f"{capability} 适配器初始化失败")


def _as_image_data(result: Any) -> ImageGenerateData:
    """把 OpenAI / Stability / ComfyUI 三种返回归一到 ImageGenerateData。"""
    if not isinstance(result, dict):
        return ImageGenerateData(raw={"result": str(result)})
    urls: List[str] = []
    b64: List[str] = []
    for item in result.get("data") or []:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            urls.append(str(item["url"]))
        if item.get("b64_json"):
            b64.append(str(item["b64_json"]))
    for item in result.get("images") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
    if result.get("url"):
        urls.append(str(result["url"]))
    if result.get("b64_json"):
        b64.append(str(result["b64_json"]))
    if not urls and not b64 and not (result.get("data") or result.get("images")):
        return ImageGenerateData(raw=result)
    return ImageGenerateData(urls=urls, b64_json=b64, raw=result)


# --------------------------------------------------------------------------
# 1. 状态
# --------------------------------------------------------------------------


async def status() -> ApiResponse[GenerationStatusData]:
    """各生成能力的就绪状态；健康检查不得触发模型加载。"""
    pm = _provider_manager()
    try:
        described = pm.describe().get("adapters") or {}
    except Exception:  # noqa: BLE001
        described = {}

    def _ability(cap: str) -> AbilityStatus:
        info = described.get(cap) or {}
        return AbilityStatus(
            initialized=bool(info.get("initialized")),
            provider=str(info.get("current") or ""),
            detail=str(info.get("model") or ""),
        )

    try:
        embedding_ready = bool(pm.get_valid_providers("embedding"))
    except Exception:  # noqa: BLE001
        embedding_ready = False

    data = GenerationStatusData(
        llm=_ability("llm"),
        tts=_ability("tts"),
        asr=_ability("asr"),
        image=_ability("image"),
        ocr=_ability("ocr"),
        embedding=AbilityStatus(
            initialized=embedding_ready,
            provider="embedding",
            detail="memories.managers.EmbeddingManager",
        ),
        ready=bool(described.get("llm", {}).get("initialized")),
    )
    return success(data)


# --------------------------------------------------------------------------
# 2. 对话
# --------------------------------------------------------------------------


async def chat_once(payload: ChatRequest) -> ApiResponse[ChatResultData]:
    """非流式对话：一次请求返回完整回复。"""
    from ...core.pipeline import chat

    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")
    start = time.time()
    force = _route_type(payload.route)
    try:
        text = await run_in_scheduler(
            chat.router,
            payload.text,
            source=payload.source,
            session_id=payload.session_id,
            force_channel=force,
            timeout=STREAM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise ApiError.timeout("对话")
    except ApiError:
        raise
    except Exception:
        raise ApiError.internal("对话失败")
    return success(
        ChatResultData(
            text=str(text or ""),
            route=str(force.value) if force else "",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    )


async def chat_stream(payload: ChatStreamRequest) -> StreamingResponse:
    """SSE 流式对话（api.md §4.1 目标事件信封）。

    每帧带 `event:` + `data:{stream_id, request_id, seq, ts, ...}`；
    一条流恰好有一个终态：done / error / cancelled；seq 单调递增。
    `type` 字段保留，旧客户端忽略 `event:` 行仍可解析。
    """
    from ...core.pipeline import chat

    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")
    force = _route_type(payload.route)
    start = time.time()
    stream_id = uuid.uuid4().hex[:16]
    request_id = get_request_id()

    def frame(event: Dict[str, Any], name: str, seq: int) -> str:
        return sse(
            event,
            event_name=name,
            stream_id=stream_id,
            request_id=request_id,
            seq=seq,
            ts=time.time(),
        )

    async def gen() -> AsyncGenerator[str, None]:
        ref = None
        seq = 0
        try:
            ref = await chat.router_stream(
                payload.text,
                source=payload.source,
                session_id=payload.session_id,
                force_channel=force,
            )
            async for chunk in ref:
                if chunk:
                    seq += 1
                    yield frame({"type": "chunk", "text": chunk}, "chunk", seq)
            seq += 1
            yield frame({
                "type": "done",
                "session_id": payload.session_id,
                "elapsed_ms": int((time.time() - start) * 1000),
                "result": {"route": str(force.value) if force else ""},
            }, "done", seq)
        except asyncio.CancelledError:
            if ref is not None:
                try:
                    ref.cancel()
                except Exception:  # noqa: BLE001
                    pass
            # 断连也发终态（连接已断时 yield 失败由 StreamingResponse 吞掉）
            try:
                seq += 1
                yield frame({"type": "cancelled"}, "cancelled", seq)
            except Exception:  # noqa: BLE001
                pass
            return
        except ApiError as exc:
            seq += 1
            yield frame({
                "type": "error", "code": exc.code,
                "error": {"code": exc.code, "message": exc.api_message},
            }, "error", seq)
        except Exception:
            seq += 1
            yield frame({
                "type": "error", "code": 3001,
                "error": {"code": 3001, "kind": "internal", "message": "对话失败"},
            }, "error", seq)
        finally:
            if ref is not None:
                try:
                    ref.finish()
                except Exception:  # noqa: BLE001
                    pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------
# 3. 语音
# --------------------------------------------------------------------------


async def tts(payload: TTSRequest) -> ApiResponse[TTSResultData]:
    """文本转语音，返回 base64 音频。"""
    from ...core.pipeline import chat

    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")
    try:
        ref = chat.text_to_speech(payload.text)
        audio = await ref.wait_async(timeout=AUDIO_TIMEOUT)
    except asyncio.TimeoutError:
        raise ApiError.timeout("语音合成")
    except Exception:
        raise ApiError.internal("语音合成失败")
    if not audio:
        raise ApiError.not_initialized("TTS", "未返回音频数据")
    raw = audio if isinstance(audio, (bytes, bytearray)) else bytes(audio)
    return success(
        TTSResultData(
            audio=base64.b64encode(raw).decode("ascii"),
            format=payload.format,
            bytes=len(raw),
        )
    )


async def asr(payload: ASRRequest) -> ApiResponse[ASRResultData]:
    """语音转文本；audio 为 base64 音频字节。"""
    from ...core.pipeline import chat

    audio = _decode_b64(payload.audio, "audio")
    try:
        ref = chat.speech_to_text(audio)
        text = await ref.wait_async(timeout=AUDIO_TIMEOUT)
    except asyncio.TimeoutError:
        raise ApiError.timeout("语音识别")
    except Exception:
        raise ApiError.internal("语音识别失败")
    return success(ASRResultData(text=str(text or "")))


# --------------------------------------------------------------------------
# 4. 图像 / OCR / 向量
# --------------------------------------------------------------------------


async def image(payload: ImageGenerateRequest) -> ApiResponse[ImageGenerateData]:
    """按当前或指定 provider 生成图像；返回 url 或 b64_json。"""
    if not payload.prompt.strip():
        raise ApiError.bad_request("prompt 不能为空")
    entity = await _capability_entity("image", payload.provider, payload.model_id)
    body = payload.model_dump(exclude_none=True)
    body.pop("provider", None)
    body.pop("model_id", None)
    extra = dict(body.pop("extra", None) or {})
    body.update(extra)
    try:
        result = await _maybe_await(entity.generate(body))
    except ApiError:
        raise
    except asyncio.TimeoutError:
        raise ApiError.timeout("图像生成")
    except ValueError as exc:
        raise ApiError.bad_request(str(exc))
    except Exception:
        raise ApiError.internal("图像生成失败")
    if isinstance(result, dict) and result.get("error"):
        raise ApiError.internal(str(result["error"]))
    return success(_as_image_data(result))


async def ocr(payload: OCRRecognizeRequest) -> ApiResponse[OCRResultData]:
    """图片文字识别；image 为 base64 字节。"""
    raw = _decode_b64(payload.image, "image")
    entity = await _capability_entity("ocr", payload.provider, payload.model_id)
    try:
        result = await _maybe_await(entity.recognize(raw))
    except ApiError:
        raise
    except asyncio.TimeoutError:
        raise ApiError.timeout("文字识别")
    except Exception:
        raise ApiError.internal("文字识别失败")
    text = result if isinstance(result, str) else str((result or {}).get("text", ""))
    return success(
        OCRResultData(
            text=text,
            provider=payload.provider or "",
            model=payload.model_id or "",
        )
    )


async def embedding(payload: EmbeddingRequest) -> ApiResponse[EmbeddingData]:
    """批量文本向量化；返回与输入等长的向量列表。"""
    texts = [t for t in payload.texts if isinstance(t, str) and t.strip()]
    if not texts:
        raise ApiError.bad_request("texts 不能为空")
    try:
        from ...memories.managers import EmbeddingManager

        manager = EmbeddingManager(dim=payload.dim or 384, provider=payload.model_id or "sentence")
        manager.init_adapter()
        vectors = await _maybe_await(manager.embed_batch(texts))
    except ApiError:
        raise
    except asyncio.TimeoutError:
        raise ApiError.timeout("向量化")
    except Exception:
        raise ApiError.not_initialized("embedding 适配器", "模型或依赖未就绪")
    out: List[List[float]] = []
    for vec in vectors or []:
        out.append([float(x) for x in (vec.tolist() if hasattr(vec, "tolist") else vec)])
    return success(
        EmbeddingData(
            vectors=out,
            dim=len(out[0]) if out else 0,
            model=str(getattr(manager, "_model_name", "") or payload.model_id or ""),
            count=len(out),
        )
    )


# --------------------------------------------------------------------------
# 5. 工具命令
# --------------------------------------------------------------------------


async def command(payload: CommandRunRequest) -> ApiResponse[CommandResultData]:
    """执行模型输出的工具命令文本（受策略/沙箱/工作区约束）。"""
    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")
    try:
        from ...core.tools.ctl import CLTTool

        result = await CLTTool.instance().run_raw_commands_async(payload.text)
    except ApiError:
        raise
    except asyncio.TimeoutError:
        raise ApiError.timeout("命令执行")
    except Exception:
        raise ApiError.not_initialized("工具编排器")
    return success(
        CommandResultData(
            success=bool(result.get("success")),
            results=[
                item if isinstance(item, dict) else safe_dict(item)
                for item in (result.get("results") or [])
            ],
            summary=str(result.get("summary") or ""),
            rounds=int(result.get("rounds") or 0),
            stop_reason=str(result.get("stop_reason") or ""),
        )
    )


# --------------------------------------------------------------------------
# 6. 辅助：目录与进度流
# --------------------------------------------------------------------------


async def progress_stream(task_id: str) -> StreamingResponse:
    """SSE 任务进度流；生产者用 set_progress(task_id, ...) 写入。"""
    async def gen() -> AsyncGenerator[str, None]:
        stream_id = uuid.uuid4().hex[:16]
        request_id = get_request_id()
        seq = 0
        deadline = time.monotonic() + STREAM_TIMEOUT
        terminal = {"done", "error", "cancelled", "timeout", "finished"}

        def frame(payload: Dict[str, Any], name: str) -> str:
            nonlocal seq
            seq += 1
            payload.setdefault("task_id", task_id)
            payload.setdefault("type", "progress")
            return sse(
                payload,
                event_name=name,
                stream_id=stream_id,
                request_id=request_id,
                seq=seq,
                ts=time.time(),
            )

        while time.monotonic() < deadline:
            with _progress_lock:
                data = dict(_progress_store.get(task_id) or {})
            if data:
                status = str(data.get("status", "running")).lower()
                yield frame(data, status if status in terminal else "progress")
                if status in terminal:
                    clear_progress(task_id)
                    break
            else:
                yield frame({"status": "pending", "percent": 0.0}, "progress")
            await asyncio.sleep(0.3)
        else:
            yield frame({"status": "timeout", "percent": 0.0}, "timeout")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = [
    "status",
    "chat_once",
    "chat_stream",
    "tts",
    "asr",
    "image_generate",
    "ocr",
    "embedding",
    "command",
    "progress_stream",
    "set_progress",
    "clear_progress",
]
