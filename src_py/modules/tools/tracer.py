"""工具调用追踪器（TD1–TD8）。

为什么需要它
────────────
工具执行跑在**调度器 loop**（`router_stream` 的 producer 里）。
前端在 Web loop 的 WebSocket 上。两者不是同一个 loop ——
在 producer 里直接 `await send_json` 是跨 loop 操作 transport，必然出错。

所以追踪器只做一件事：**把生命周期事件交给 events.emit**，
由总线路由到 Web loop 再下发（这一条链路前几轮已经修好了）。

用法
────
    tracer = ToolCallTracer(message_id=mid, emit_tools=True)
    orch.set_tool_listener(tracer.listener)
    tracer.start(route="mixed")          # -> chat.message.start
    tracer.phase("tooling")
    ...                                   # ctl 执行时回调 listener
    tracer.finish(content="...")          # -> chat.message.end
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from ..events import types
from ..events.data import BaseEvent
from ..logger import logger

__all__ = ["ToolCallTracer", "new_message_id"]


def new_message_id() -> str:
    return uuid.uuid4().hex[:16]


class ToolCallTracer:
    """收集一轮对话里的工具调用，并发元信息事件。"""

    def __init__(
        self,
        message_id: Optional[str] = None,
        role: str = "assistant",
        emit_tools: bool = True,
    ) -> None:
        self.message_id = message_id or new_message_id()
        self.role = role
        #: TD5：只有 TOOL_CALL / MIXED 才发工具事件。
        #: PURE_CHAT 一条工具都不调，发 `phase=tooling` 只会让前端空转。
        self.emit_tools = bool(emit_tools)
        self.tools: List[Dict[str, Any]] = []
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self.phase: str = "thinking"
        self.route: str = ""
        self.content: str = ""
        self._started = False

    # ---------- 生命周期 ----------

    def start(self, route: str = "") -> None:
        self.route = route
        self._started = True
        self._emit(types.ChatStreamEventType.MESSAGE_START, {
            "message_id": self.message_id,
            "route": route,
            "has_tools": self.emit_tools,
        })

    def phase_change(self, phase: str) -> None:
        self.phase = phase
        self._emit(types.ChatStreamEventType.PHASE, {
            "message_id": self.message_id,
            "phase": phase,
            "route": self.route,
        })

    def finish(self, content: str = "", phase: str = "done") -> Dict[str, Any]:
        self.content = content or self.content
        self.phase = phase
        msg = self.to_message()
        self._emit(types.ChatStreamEventType.MESSAGE_END, {"message": msg})
        return msg

    # ---------- TD7：给 ServiceOrchestrator 的回调 ----------

    def listener(self, event: str, item: Dict[str, Any]) -> None:
        """同步回调（在调度器 loop 里被调用）。"""
        if not self.emit_tools:
            return
        item = dict(item or {})
        item_id = str(item.get("id") or "")

        if event == "start":
            self._upsert(item)
            self._emit(types.ChatStreamEventType.TOOL_START, {
                "message_id": self.message_id,
                "tool": item,
            })
        elif event == "end":
            # end 可能带 elapsedMs / result / error，合并到已存在的卡片
            merged = self._upsert(item)
            self._emit(types.ChatStreamEventType.TOOL_END, {
                "message_id": self.message_id,
                "tool": merged,
            })
        _ = item_id

    def _upsert(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """同一个 id 的卡片做增量更新，不重复追加。"""
        key = str(item.get("id") or "") or new_message_id()
        existing = self._by_id.get(key)
        if existing is None:
            item["id"] = key
            self._by_id[key] = item
            self.tools.append(item)
            return item
        for k, v in item.items():
            if v not in (None, "", 0) or k not in existing:
                existing[k] = v
        existing["id"] = key
        return existing

    # ---------- 输出 ----------

    def to_message(self) -> Dict[str, Any]:
        return {
            "id": self.message_id,
            "role": self.role,
            "content": self.content,
            "tools": list(self.tools),
            "phase": self.phase,
            "createdAt": int(time.time() * 1000),
        }

    # ---------- 内部 ----------

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        try:
            
            from ..events import emit

            emit(BaseEvent(type=event_type, args=(data,)))
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[ToolTracer] emit {event_type} failed: {exc}")

    # ---------- 便捷：按 route 判定 ----------

    @staticmethod
    def should_emit_tools(route: Any) -> bool:
        """TD5：只在 TOOL_CALL / MIXED 发工具事件。"""
        value = getattr(route, "value", None) or str(route or "")
        return value in ("tool_call", "mixed", "TOOL_CALL", "MIXED")
