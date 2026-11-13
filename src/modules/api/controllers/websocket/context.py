"""WebSocket 帧级关联字段（api.md §4.2 / FrontendBackendContract §7）。

`dispatch` 在派发一条入站帧时设置 request_id / stream_id；
`WebSocketClientManager.send_json` / `broadcast` 在未显式传值时自动读取，
这样所有既有事件推送代码无需逐个改签名就能带上关联字段。

ContextVar 保证同一连接上并发的多个在途请求互不串线。
"""
from __future__ import annotations

from contextvars import ContextVar

frame_request_id: ContextVar[str] = ContextVar("ws_frame_request_id", default="")
frame_stream_id: ContextVar[str] = ContextVar("ws_frame_stream_id", default="")

__all__ = ["frame_request_id", "frame_stream_id"]
