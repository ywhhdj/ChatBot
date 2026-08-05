from __future__ import annotations
import base64
from datetime import datetime
import time
from typing import Optional, TypeVar
import uuid
from fastapi import WebSocket, WebSocketDisconnect

from ...pipeline import chat
from ..server import get_web_app
from .models import WebSocketRequest
from ... import events
from ...logger import logger
from ...manager.websocket.manager import get_websocket_manager

T = TypeVar('T',bound=dict)
app=get_web_app()
websocket_client = get_websocket_manager()

async def handle_download_model(client_id: str, model_name: str, save_path: str = "save_path"):
    async def success_callback(_):
        await websocket_client.send_json(
            client_id, 
            type=events.types.DownloadEventType.COMPLETED,
            data={
                "model": model_name,
                "download": True,
                "message": "下载完成"
            }
        )

    async def error_callback(e: Exception):
        await websocket_client.send_json(
            client_id, 
            type=events.types.DownloadEventType.FAILED,
            data={
                "model": model_name,
                "download": False,
                "message": f"下载失败: {e}"
            }
        )
    
    async def running_callback(progress: int):
        await websocket_client.send_json(
            client_id, 
            type=events.types.DownloadEventType.RUNNING,
            data={
                "model": model_name,
                "download": True,
                "progress": progress
            }
        )
        
    if model_name == "google_facelandmarker":
        from ...pipeline.downloads.landmarker import download_google_facelandmarker
        download_google_facelandmarker(
            save_path,
            running_callback
        ).then(
            success_callback,
            error_callback
        )
    elif model_name == "paddle_ocr":
        from ...pipeline.downloads.ocr import download_paddle_ocr
        download_paddle_ocr(
            save_path,
            running_callback
        ).then(
            success_callback,
            error_callback
        )
    elif model_name == "umi_ocr":
        from ...pipeline.downloads.ocr import download_umi_ocr
        download_umi_ocr(
            save_path,
            running_callback
        ).then(
            success_callback,
            error_callback
        )
    else:
        await websocket_client.send_json(
            client_id,
            type=events.types.DownloadEventType.ERROR,
            data={
                "model": model_name,
                "download": False,
                "message": "不支持该模型下载"
            }
        )
    # 立即返回确认消息
    await websocket_client.send_json(
        client_id, 
        type=events.types.DownloadEventType.STARTED,
        data={"model": model_name, "download": True, "message": "开始下载"}
    )

async def chat_complete(client_id: str):
    for event in [
        events.types.PipelineEventType.LLM_TEXT_DELTA,
        events.types.PipelineEventType.TTS_AUDIO_CHUNK,
        events.types.PipelineEventType.LLM_FINAL_TEXT,
        events.types.PipelineEventType.TTS_FINAL_AUDIO
    ]:
        events.off(event)
        await websocket_client.send_json(
            client_id, 
            type=events.types.PipelineEventType.LLM_FINAL_TEXT,
            data="聊天完成"
        )

async def handle_chat(client_id: str, message: str):
    async for text in chat.router_stream(
        user_input=message,
        source="text",
        session_id=str(uuid.uuid4())
    ):
        await websocket_client.send_json(
            client_id, 
            type=events.types.PipelineEventType.LLM_TEXT_DELTA,
            data=text
        )
    events.on(
        events.types.PipelineEventType.TTS_AUDIO_CHUNK,
        lambda audio_chunk, current_audio_name: websocket_client.send_json(
            client_id, 
            type=events.types.PipelineEventType.TTS_AUDIO_CHUNK,
            data={
                "audio_chunk": audio_chunk,
                "audio_name": current_audio_name
            }
        )
    )
    events.on(
        events.types.PipelineEventType.LLM_FINAL_TEXT,
        lambda text: websocket_client.send_json(
            client_id, 
            type=events.types.PipelineEventType.LLM_FINAL_TEXT,
            data=text
        )
    )
    events.on(
        events.types.PipelineEventType.TTS_FINAL_AUDIO,
        chat_complete
    )

def _register_event(client_id: str):
    log_event_type = events.types.WebSocketEventType.GET_LOG
    async def send_log_to_client(log_data):
        try:
            await websocket_client.send_json(
                client_id, 
                type=events.types.WebSocketEventType.GET_LOG,
                data=log_data
            )
        except Exception as e:
            logger.error(f"Failed to send log to {client_id}: {e}")
    events.on(log_event_type, send_log_to_client)

    async def handle_qqbot_event(data):
        try:
            await websocket_client.send_json(
                client_id, 
                type=events.types.QQBotEventType.QQ_BOT_INFO,
                data=data
            )
        except Exception as e:
            logger.error(f"Failed to send QQBot bot info to {client_id}: {e}")
    events.on(events.types.QQBotEventType.QQ_BOT_INFO, handle_qqbot_event)

def _unregister_event():
    events.off(events.types.WebSocketEventType.GET_LOG)
    events.off(events.types.QQBotEventType.QQ_BOT_INFO)

async def handle_event(client_id: str, event:str, data: Optional[T]=None) :
    #保留私信事件，但后续不再使用
    # if event == events.type.WebSocketEvent.PRIVATE and data and data.get("to"):
    #     await websocket_client.send_personal(
    #         WebSocketResponse(
    #             type=events.type.WebSocketEvent.PRIVATE,
    #             from_=client_id,
    #             data=data
    #         ),
    #         data.get("to","")
    #     )
    #     await websocket_client.send_json(client_id, WebSocketResponse(
    #         type=events.type.WebSocketEvent.PRIVATE,
    #         data="私信已发送"
    #     ))
    if event == events.types.WebSocketEventType.CHAT and data:
        if data.get("message",None) is None:
            await websocket_client.send_json(
                client_id, 
                type=events.types.WebSocketEventType.CHAT,
                data="消息不能为空"
            )
        else:
            await handle_chat(client_id, data["message"])
    elif event == events.types.WebSocketEventType.DOWNLOAD_MODEL:
        if data and data.get("model_name"):
            await handle_download_model(
                client_id,
                data.get("model_name",""),
                data.get("save_path","./models")
            )
    elif event == events.types.WebSocketEventType.RECORD_START:
        await websocket_client.send_json(
            client_id, 
            type=events.types.WebSocketEventType.RECORD_START,
            data=True
        )

    elif event == events.types.WebSocketEventType.RECORD_CHUNK:
        if data and data.get("audio"):
            audio = base64.b64decode(data["audio"])
            is_final = data.get("is_final",False)
            async for text in chat.speech_to_text_stream(audio,is_final=is_final):
                await websocket_client.send_json(
                    client_id, 
                    type=events.types.WebSocketEventType.RECORD_CHUNK,
                    data=text
                )
    elif event == events.types.WebSocketEventType.RECORD_STOP:
        await websocket_client.send_json(
            client_id, 
            type=events.types.WebSocketEventType.RECORD_STOP,
            data="录音已停止"
        )

def gerenate_client_id():
   return f"client_{datetime.fromtimestamp(time.time()).strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

@app.websocket("/ws")
async def websocket_connect(websocket: WebSocket):
    client_id = gerenate_client_id()
    try:
        connected = await websocket_client.connect(client_id, websocket)
        if not connected:
            return
        _register_event(client_id)
        while True:
            try:
                raw = await websocket.receive_json()
                # 更新心跳时间
                websocket_client.update_heartbeat(client_id)
                request = WebSocketRequest(**raw)
                if not request.type or not request.data:
                    return
                client_id_=request.data.get("client_id","")
                if not client_id_:
                    websocket_client.disconnect(client_id)
                    return
                if client_id != client_id_:
                    return
                if request.type and request.type!=events.types.WebSocketEventType.HEARTBEAT:
                    await handle_event(
                        client_id=client_id, 
                        event=request.type, 
                        data=request.data
                    )
            except WebSocketDisconnect:
                logger.info(f"[WebSocket] Client {client_id} disconnected")
                break
            except Exception as e:
                logger.error(f"[WebSocket] Error processing message from {client_id}: {e}")
                break
    except Exception as e:
        logger.error(f"[WebSocket] Connection error for {client_id}: {e}")
    finally:
        websocket_client.disconnect(client_id)
        _unregister_event()

