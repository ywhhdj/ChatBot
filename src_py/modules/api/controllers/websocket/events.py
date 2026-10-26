import base64
from typing import Any, Dict, Optional

from src_py.modules.runtime import RuntimePath

from .... import events
from .manager import get_websocket_manager
from ....pipeline import chat

async def handle_download_model(client_id: str, model_name: str, save_path: str = ""):
    manager = get_websocket_manager()

    async def _send(event_type: str, payload, ok: bool = True, message: str = "ok"):
        await manager.send_json(client_id, type=event_type, data=payload, message=message, ok=ok)

    def success_callback(_):
        # W6：同步回调，只投递；不能在这里 await（会跨 loop 操作 WebSocket）
        manager.submit_to_loop(
            lambda: _send(
                events.types.DownloadEventType.COMPLETED,
                {
                    "model": model_name,
                },
                ok=True,
                message="下载完成",
            )
        )

    def error_callback(e: Exception):
        manager.submit_to_loop(
            lambda: _send(
                events.types.DownloadEventType.FAILED,
                {
                    "model": model_name,
                },
                ok=False,
                message=f"下载失败: {e}",
            )
        )

    def running_callback(progress: int):
        # W5：原实现是 async，而下载函数在同步线程里调用它 ->
        # 返回的协程从未被 await，进度全部丢失 + "coroutine was never awaited" 警告
        manager.submit_to_loop(
            lambda: _send(
                events.types.DownloadEventType.RUNNING,
                {
                    "model": model_name,
                    "progress": progress,
                },
                ok=True,
                message=f"下载进度: {progress}",
            )
        )

    # 惰性导入：下载器依赖较重，且只在需要时加载
    try:
        if model_name == "google_facelandmarker":
            #先检查模型目录下是否存在，如果没指定则使用默认路径
            path=RuntimePath.get_models_path("mediapipe/face_landmarker.task")
            if path.exists():
                await _send(
                events.types.DownloadEventType.ERROR,
                {
                    "model": model_name,
                },
                ok=False,
                message="模型已存在，无需下载",
            )
                return

            from ....pipeline.downloads.landmarker import download_google_facelandmarker as downloader
        elif model_name == "paddle_ocr":
            path=RuntimePath.get_models_path("paddleocr/paddleocr.task")
            if path.exists():
                await _send(
                events.types.DownloadEventType.ERROR,
                {
                    "model": model_name,
                },
                ok=False,
                message="模型已存在，无需下载",
            )
                return

            from ....pipeline.downloads.ocr import download_paddle_ocr as downloader
        elif model_name == "umi_ocr":
            from ....pipeline.downloads.ocr import download_umi_ocr as downloader
        else:
            # W13：不支持的模型 -> 报错后返回，不能再发 "开始下载"
            await _send(
                events.types.DownloadEventType.ERROR,
                {
                    "model": model_name,
                },
                ok=False,
                message="不支持该模型下载",
            )
            return
    except Exception as e:
        await _send(
            events.types.DownloadEventType.ERROR,
                {
                    "model": model_name,
                },
                ok=False,
                message=f"下载器加载失败: {e}",
            )
        return

    try:
        task_ref = downloader(save_path, running_callback)
    except Exception as e:
        await _send(
            events.types.DownloadEventType.ERROR,
                {
                    "model": model_name,
                },
                ok=False,
                message=f"下载启动失败: {e}",
            )
        return

    if task_ref:
        task_ref.then(success_callback, error_callback)
    else:
        # 下载器不是异步任务（同步返回），则视为立即完成
        success_callback(None)

    await _send(
        events.types.DownloadEventType.STARTED,
        {
            "model": model_name,
        },
        ok=True,
        message="开始下载",
    )

async def _wm_send_json(client_id: str, event_type: str, payload, ok: bool = True, message: str = "ok"):
    await get_websocket_manager().send_json(
        client_id,
        type=event_type,
        data=payload,
        message=message,
        ok=ok,
    )


async def handle_chat(client_id: str, message: str) -> None:
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


async def handle_speech_chunk(client_id: str, audio: bytes, is_final: bool) -> None:
    stream=await chat.speech_to_text_stream(
        audio_bytes=audio,
        is_final=is_final,
    )
    async for text in stream:
        await _wm_send_json(
            client_id,
            events.types.WebSocketEventType.RECORD_CHUNK,
            text,
            ok=True,
        )


async def handle_event(client_id: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    manager = get_websocket_manager()
    data = data or {}

    if event == events.types.WebSocketEventType.CHAT:
        message = data.get("message")
        if not message:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.CHAT,
                ok=False,
                message="消息不能为空",
            )
            return
        await handle_chat(client_id, message)

    elif event == events.types.WebSocketEventType.DOWNLOAD_MODEL:
        model_name = data.get("model_name")
        if not model_name:
            await manager.send_json(
                client_id,
                type=events.types.DownloadEventType.ERROR,
                ok=False,
                message="缺少 model_name",
            )
            return
        await handle_download_model(client_id, model_name, data.get("save_path", "./models"))

    elif event == events.types.WebSocketEventType.RECORD_START:
        await manager.send_json(
            client_id, type=events.types.WebSocketEventType.RECORD_START, data=True
        )

    elif event == events.types.WebSocketEventType.RECORD_CHUNK:
        raw_audio = data.get("audio")
        if not raw_audio:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RECORD_CHUNK,
                ok=False,
                message="缺少 audio",
            )
            return
        try:
            audio = base64.b64decode(raw_audio)
        except Exception as e:
            await manager.send_json(
                client_id,
                type=events.types.WebSocketEventType.RECORD_CHUNK,
                ok=False,
                message=f"audio 解码失败: {e}",
            )
            return
        await handle_speech_chunk(client_id, audio, bool(data.get("is_final", False)))

    elif event == events.types.WebSocketEventType.RECORD_STOP:
        await manager.send_json(
            client_id,
            type=events.types.WebSocketEventType.RECORD_STOP,
            ok=True,
            message="录音已停止",
        )

