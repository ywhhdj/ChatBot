from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict,Field
from typing import ParamSpec, TypeVar

class DictModel(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

class TermColors:
    GREY = '\033[30m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    BLUE = '\033[34m'
    RESET = '\033[0m'
    WHITE = '\033[37m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'
    ORANGE = '\033[38;5;208m'
    BOLD = '\033[1m'

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

class TimeRange(BaseModel):
    start: datetime
    end: datetime


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

    @staticmethod
    def get_zh_name(role: str) -> str:
        return {
            Role.USER.value: "用户",
            Role.ASSISTANT.value: "助手",
            Role.SYSTEM.value: "系统",
            Role.TOOL.value: "工具",
        }.get(role, "用户")

    def __str__(self) -> str:
        return str(self.value)


class Message(BaseModel):
    role: str=Role.USER.value
    content: str

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content
        }

class MessageContext(Message,BaseModel):
    id: str
    timestamp: float
    session_id: str = "default"
    tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    tool_calls: Optional[list[dict[str, Any]]] = Field(default=None)
    tool_call_id: Optional[str] = Field(default=None)

class CompressedContext(BaseModel):
    id: str
    original_ids: list[str]
    compressed_content: str
    summary: str
    created_at: float
    time_range: TimeRange
    session_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)
