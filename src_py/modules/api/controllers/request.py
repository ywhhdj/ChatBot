"""对话与推理接口：聊天（非流式 / SSE 流式）、TTS、ASR、命令执行。

对应 api文档.md 第 6 节。

核心约束（api文档.md 15 节）
───────────────────────────
* **producer 跑在调度器 loop**：`chat.router_stream` 由 `stream_task_scheduler`
  装饰，Web loop 只做 `async for` 转发 —— 流式推理期间其它 HTTP 请求照常响应。
* **非流式聊天同样提交调度器**，不在 Web loop 里 await 整个推理过程。
* **二进制走 base64**，避免 multipart 与前端（PyQt）的额外适配。
"""

from __future__ import annotations

import asyncio
import base64

import threading
import time
from typing import AsyncGenerator,Optional
from fastapi.responses import StreamingResponse
from fastapi import APIRouter

from src_py.modules.runtime import RuntimePath
from src_py.modules.utils.zipstream import stream_zip

from ..requests import (
    ASRRequest,
    ChatRequest,
    TTSRequest
)
from ..dto import (
    ASRResultData,
    ChatResultData,
    CommandResultData,
    TTSResultData,
    RequestStatusData,
    ASRResultData
)
from ..response import ApiError, ApiResponse, success, sse
from .._common import run_in_scheduler

router=APIRouter(
    prefix="",
    tags=["常规请求"]
)

STREAM_TIMEOUT = 600.0


def _route_type(value: Optional[str]):
    if not value:
        return None
    from ...routes.models import RouteType

    try:
        return RouteType(value)
    except ValueError:
        valid = [e.value for e in RouteType]
        raise ApiError.bad_request(f"路由类型 {value} 无效，可选: {', '.join(valid)}")


@router.get("/folder/{type}", response_model=ApiResponse[None])
def open_folder(type: str):
    paths={
        "images":RuntimePath.get_user_data_path("images"),
        "roles":RuntimePath.get_user_data_path("roles"),
    }
    if type not in paths.keys():
        raise ApiError.bad_request("路径越界")
    #获取系统类型
    import platform
    platform_type = platform.system().lower()
    if platform_type == "windows":
        import os
        os.startfile(paths[type])
        return success()
    elif platform_type == "mac":
        import os
        os.system(f"open {paths[type]}")
        return success()
    elif platform_type == "linux":
        import os
        os.system(f"xdg-open {paths[type]}")
        return success()
    else:
        raise ApiError.bad_request("系统不支持")


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
@router.get("/status", response_model=ApiResponse[RequestStatusData])
async def status() -> ApiResponse[RequestStatusData]:
    """LLM / TTS / ASR 的初始化状态。"""
    from ...pipeline import chat

    data = RequestStatusData()

    def _fill(attr, target):
        try:
            mgr = getattr(chat, attr, None)
        except Exception:
            mgr = None
        if mgr is None:
            return
        provider = getattr(mgr, "_provider", None)
        initialized = provider is not None
        setattr(target, "initialized", initialized)
        if provider is not None:
            name = getattr(provider, "name", None) or type(provider).__name__
            setattr(target, "provider", str(name))

    _fill("_llm", data.llm)
    _fill("_tts", data.tts)
    _fill("_asr", data.asr)

    try:
        data.ready = bool(chat.is_initialized())
    except Exception:
        data.ready = data.llm.initialized

    return success(data)


# --------------------------------------------------------------------------
# 对话
# --------------------------------------------------------------------------
@router.post("/chat", response_model=ApiResponse[ChatResultData])
async def chat_once(payload: ChatRequest) -> ApiResponse[ChatResultData]:
    """非流式对话。"""
    from ...pipeline import chat

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
    except Exception as e:
        raise ApiError.internal(f"对话失败: {e}")

    return success(
        ChatResultData(
            text=str(text or ""),
            elapsed_ms=int((time.time() - start) * 1000),
        )
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """流式对话（SSE）。

    每帧 `data: {"type":"chunk","text":"..."}`，结束帧
    `data: {"type":"done","elapsed_ms":...}`。
    """
    from ...pipeline import chat

    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")

    force = _route_type(payload.route)
    start = time.time()

    async def gen() -> AsyncGenerator[str, None]:
        ref = None
        try:
            ref = await chat.router_stream(
                payload.text,
                source=payload.source,
                session_id=payload.session_id,
                force_channel=force,
            )
            async for chunk in ref:
                if not chunk:
                    continue
                yield sse({
                    "type": "chunk",
                    "text": chunk
                })
            yield sse({
                "type": "done",
                "session_id": payload.session_id,
                "elapsed_ms": int((time.time() - start) * 1000),
            })
        except asyncio.CancelledError:
            # 客户端断开：尽力关闭流，避免 producer 留在调度器里
            if ref is not None:
                with _suppress():
                    ref.cancel()
            return
        except Exception as e:
            yield sse({
                "type": "error", 
                "message": f"{type(e).__name__}: {e}"
            })
        finally:
            if ref is not None:
                try:
                    ref.finish()
                except Exception:
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


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


# --------------------------------------------------------------------------
# TTS / ASR
# --------------------------------------------------------------------------
@router.post("/tts", response_model=ApiResponse[TTSResultData])
async def tts(payload: TTSRequest) -> ApiResponse[TTSResultData]:
    """文本转语音，返回 base64 音频。"""
    from ...pipeline import chat

    if not payload.text.strip():
        raise ApiError.bad_request("text 不能为空")

    try:
        ref = chat.text_to_speech(payload.text)
        audio = await ref.wait_async(timeout=120.0)
    except asyncio.TimeoutError:
        raise ApiError.timeout("语音合成")
    except Exception as e:
        raise ApiError.internal(f"语音合成失败: {e}")

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


@router.post("/asr", response_model=ApiResponse[ASRResultData])
async def asr(payload: ASRRequest) -> ApiResponse[ASRResultData]:
    """语音转文本，audio 为 base64 编码的音频字节。"""
    from ...pipeline import chat

    try:
        audio = base64.b64decode(payload.audio)
    except Exception as e:
        raise ApiError.bad_request(f"audio 不是合法的 base64: {e}")

    if not audio:
        raise ApiError.bad_request("audio 不能为空")

    try:
        ref = chat.speech_to_text(audio)
        text = await ref.wait_async(timeout=120.0)
    except asyncio.TimeoutError:
        raise ApiError.timeout("语音识别")
    except Exception as e:
        raise ApiError.internal(f"语音识别失败: {e}")

    return success(ASRResultData(text=str(text or "")))

progress_lock=threading.Lock()
progress_store={}
@router.post("/progress-stream/{task_id}")
async def progress_stream(task_id: str) -> StreamingResponse:
    async def event_stream():
        while True:
            while progress_lock:
                data=progress_store.get(task_id)
            if data:
                yield sse(data)
                if data.get('status') in ['done','error']:
                    break
            else:
                yield sse({
                    'status': 'finished'
                })
                break
        await asyncio.sleep(0.3)
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# @app.get("/download/{task_id}")
# async def download(task_id: str, files: list[dict[str, str]]) -> StreamingResponse:
#     files, total_bytes = await probe_sizes(files)

#     # ZIP 元数据粗略开销（Local Header + Central Directory + EOCD）
#     zip_overhead = sum(
#         30 + len(f['name'].encode('utf-8')) +
#         46 + len(f['name'].encode('utf-8'))
#         for f in files
#     ) + 22
#     total_with_overhead = total_bytes + zip_overhead
#     with progress_lock:
#         progress_store[task_id]={
#             "sent": 0,
#             "total": 0,
#             "status": 'downloading',
#             "files_done":0,
#             'total': total_with_overhead,
#             'percent': 0.0,
#             'files_total': len(files),
#         }
#     async def generate():
#         try:
#             async for chunk in stream_zip(files):
#                 yield chunk
#             with progress_lock:
#                 if task_id in progress_store:
#                     progress_store[task_id]['percent'] = 100
#                     progress_store[task_id]['status'] = 'done'
#         except Exception as e:
#             with progress_lock:
#                 if task_id in progress_store:
#                     progress_store[task_id]['status'] = 'error'
#                     progress_store[task_id]['error'] = str(e)
#             raise
#         finally:
#             await asyncio.sleep(2)   # 给 SSE 最后一次读取机会
#             progress_store.pop(task_id, None)
    
#     return StreamingResponse(
#         generate(),
#         media_type="application/zip",
#         headers={
#             "Content-Disposition": 'attachment; filename="models.zip"',
#             "X-Accel-Buffering": "no",
#             "Cache-Control": "no-store",
#         },
#     )