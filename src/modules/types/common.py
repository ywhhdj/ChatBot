from enum import Enum
from pydantic import BaseModel
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

class Role:
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class Message(BaseModel):
    role: str=Role.USER
    content: str
    
    def to_dict(self):
        return  self.model_dump()

class RouteType(Enum):
    PURE_CHAT = "pure_chat"  # 纯聊天
    TOOL_CALL = "tool_call"  # 纯工具调用
    MIXED = "mixed"          # 混合模式