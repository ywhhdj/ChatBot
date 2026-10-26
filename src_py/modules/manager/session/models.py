from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional

class RoundRecord:
    """一轮对话的完整记录。"""

    def __init__(
        self,
        round_id: str = "",
        session_id: str = "",
        character_id: str = "",
        route: str = "pure_chat",
        user_input: str = "",
        reply: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        started_at: float = 0.0,
        ended_at: float = 0.0,
    ) -> None:
        self.id = round_id or f"r{int(time.time() * 1000)}"
        self.session_id = session_id
        self.character_id = character_id
        self.route = route
        self.user_input = user_input
        self.reply = reply
        self.tool_calls = list(tool_calls or [])
        self.started_at = started_at or time.time()
        self.ended_at = ended_at

    #: A19：有工具调用的任务轮，与纯聊天分开存，避免污染角色人设上下文
    @property
    def is_task(self) -> bool:
        value = str(getattr(self.route, "value", self.route) or "")
        return value in ("tool_call", "mixed") or bool(self.tool_calls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "character_id": self.character_id,
            "route": str(getattr(self.route, "value", self.route)),
            "user_input": self.user_input,
            "reply": self.reply,
            "tool_calls": list(self.tool_calls or []),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "RoundRecord":
        d = data if isinstance(data, dict) else {}
        return cls(
            round_id=str(d.get("id") or ""),
            session_id=str(d.get("session_id") or ""),
            character_id=str(d.get("character_id") or ""),
            route=str(d.get("route") or "pure_chat"),
            user_input=str(d.get("user_input") or ""),
            reply=str(d.get("reply") or ""),
            tool_calls=list(d.get("tool_calls") or []),
            started_at=float(d.get("started_at") or 0),
            ended_at=float(d.get("ended_at") or 0),
        )


@dataclass
class SaveMetadata:
    last_interaction: float = 0.0
    last_role: Dict[str, Any] = field(default_factory=lambda: {
        "name": "", 
        "mood": 4
    })


@dataclass
class Session:
    id: str
    name: str
    character_id: str
    created_at: float
    updated_at: float
    messages: List[Dict] = field(default_factory=list)   # 最近 N 条，用于快速恢复
    memory_ids: List[str] = field(default_factory=list)  # 关联的压缩记忆 ID
    metadata: SaveMetadata = field(default_factory=SaveMetadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        payload = dict(data)
        raw_meta = payload.pop("metadata", None)
        if isinstance(raw_meta, SaveMetadata):
            metadata = raw_meta
        elif isinstance(raw_meta, dict):
            metadata = SaveMetadata(**raw_meta)
        else:
            metadata = SaveMetadata()
        return cls(metadata=metadata, **payload)