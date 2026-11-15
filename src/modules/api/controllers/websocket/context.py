"""WebSocket 帧级关联字段"""
from contextvars import ContextVar

frame_request_id: ContextVar[str] = ContextVar("ws_frame_request_id", default="")
frame_stream_id: ContextVar[str] = ContextVar("ws_frame_stream_id", default="")
