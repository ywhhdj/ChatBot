from enum import Enum
from pydantic import BaseModel
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

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

class Message(BaseModel):
    role: str=Role.USER
    content: str