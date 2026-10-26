import base64
from typing import Any, Callable, List,Tuple

from ....logger import logger
from .... import events

def _b64(chunk: Any) -> Any:
    """音频块转成 base64 字符串，便于 JSON 传输。bytes 之外原样返回。"""
    if isinstance(chunk, (bytes, bytearray)):
        return base64.b64encode(bytes(chunk)).decode("ascii")
    return chunk

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

@dataclass
class ConnectionInfo:
    client_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def update_heartbeat(self) -> None:
        self.last_heartbeat = datetime.now()

    @property
    def idle_seconds(self) -> float:
        return (datetime.now() - self.last_heartbeat).total_seconds()

    def is_alive(self, timeout_seconds: float = 90.0) -> bool:
        return self.idle_seconds < timeout_seconds


class ClientEventBridge:
    """管理单个 WebSocket 连接注册到事件总线上的回调。

    核心价值：
      * 对外暴露 async handler（写起来自然）
      * 实际注册的是同步包装（投递到 Web loop，零阻塞）
      * 解绑时按引用精确移除，不污染其他连接
    """

    def __init__(self, client_id: str, manager):
        self.client_id = client_id
        self.manager = manager
        self._bindings: List[Tuple[str, Callable[..., None]]] = []

    # ---------- 注册 ----------

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """注册一个 async handler；真正挂到总线上的是同步包装。

        Args:
            event: 事件名
            handler: async def handler(*args)，内部可安全 await send_json
        """

        def sync_dispatcher(*args, **kwargs):
            # 同步、非阻塞：只把协程投递到 Web loop
            try:
                self.manager.submit_to_loop(handler, *args, **kwargs)
            except Exception as e:  # 投递失败不能影响 emit 方
                logger.debug(f"[WebSocket] dispatch {event} to {self.client_id} failed: {e}")
            return None

        events.on(event, sync_dispatcher)
        self._bindings.append((event, sync_dispatcher))

    def unregister(self) -> None:
        """L2：按 (event, callback) 精确解绑。

        绝不能 `events.off(event)` —— 那会清空该事件的全部监听器，
        把其他客户端和 Live2D 的唇形同步回调一起干掉。
        """
        for event, callback in self._bindings:
            try:
                events.off(event, callback)
            except Exception:
                pass
        self._bindings.clear()

    # ---------- 预置绑定 ----------

    def bind_defaults(self) -> None:
        """L7：连接建立时一次性注册全部事件，避免漏掉流式期间产生的数据。"""
        cid = self.client_id

        async def send_log(log_data):
            await self.manager.send_json(
                cid, type=events.types.WebSocketEventType.GET_LOG, data=log_data
            )

        async def send_qqbot_info(data):
            await self.manager.send_json(
                cid, type=events.types.QQBotEventType.QQ_BOT_INFO, data=data
            )

        async def send_text_delta(text):
            await self.manager.send_json(
                cid, type=events.types.PipelineEventType.LLM_TEXT_DELTA, data=text
            )

        async def send_audio_chunk(audio_chunk, current_audio_name=None):
            await self.manager.send_json(
                cid,
                type=events.types.PipelineEventType.TTS_AUDIO_CHUNK,
                data={
                    "audio_chunk": _b64(audio_chunk),
                    "audio_name": current_audio_name,
                },
            )

        async def send_final_text(text):
            await self.manager.send_json(
                cid, type=events.types.PipelineEventType.LLM_FINAL_TEXT, data=text
            )

        async def send_final_audio(*args, **kwargs):
            """W14：完成事件用 RESULT 类型，不再拿 LLM_FINAL_TEXT 发 "聊天完成" 字符串。"""
            await self.manager.send_json(
                cid,
                type=events.types.WebSocketEventType.RESULT,
                data={"finished": True},
            )

        self.on(events.types.WebSocketEventType.GET_LOG, send_log)
        self.on(events.types.QQBotEventType.QQ_BOT_INFO, send_qqbot_info)
        self.on(events.types.PipelineEventType.LLM_TEXT_DELTA, send_text_delta)
        self.on(events.types.PipelineEventType.TTS_AUDIO_CHUNK, send_audio_chunk)
        self.on(events.types.PipelineEventType.LLM_FINAL_TEXT, send_final_text)
        self.on(events.types.PipelineEventType.TTS_FINAL_AUDIO, send_final_audio)