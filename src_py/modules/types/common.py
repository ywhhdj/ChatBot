from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Optional
from pydantic import BaseModel
from typing_extensions import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T", bound=object)

class LLMProvider(str, Enum):
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"

class BowserType(str,Enum):
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"


class Role:
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

    @staticmethod
    def get_zh_name(role:str) -> str:
        return {
            Role.USER: "用户",
            Role.ASSISTANT: "助手",
            Role.SYSTEM: "系统",
            Role.TOOL: "工具",
        }.get(role,"user")

@dataclass
class Message:
    role: str
    content: str

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content
        }

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