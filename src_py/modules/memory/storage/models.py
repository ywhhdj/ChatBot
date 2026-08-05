from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, PrivateAttr
from numpy import ndarray

class TimeRange(BaseModel):
    start: datetime
    end: datetime

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

    @staticmethod
    def get_zh_name(role:str) -> str:
        return {
            Role.USER.value: "用户",
            Role.ASSISTANT.value: "助手",
            Role.SYSTEM.value: "系统",
            Role.TOOL.value: "工具",
        }.get(role,"用户")

@dataclass
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
        }

class Memory(BaseModel):
    id: str
    session_id: str = "default"
    role: str = Role.USER
    source: str = "text"
    content: str = ""
    importance: float = 1.0
    access_count: int = 0
    last_access_time: float = Field(default_factory=lambda: datetime.now().timestamp())
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompressedMemory(BaseModel):
    id: str
    original_ids: list[str]
    compressed_content: str
    summary: str
    created_at: float
    time_range: TimeRange
    session_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)
    _persisted: bool =  PrivateAttr(default=False)


class MemoryStorgeData(Memory):
    vector: Optional[ndarray] = None
    _persisted: bool = False