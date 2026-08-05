from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

class CommandStatus(str, Enum):
    PENDING  = "pending"
    SUCCESS  = "success"
    ERROR    = "error"
    SKIPPED  = "skipped"

class CommandData(TypedDict):
    service: str
    method: str
    params: dict[str, Any]
    raw: str

class CommandResult(TypedDict):
    ok: bool
    service: str
    method: str
    status: str
    data: Optional[Any]
    error: Optional[str]
    elapsed_ms: int
    raw: str

@dataclass
class OrchestrationState:
    round: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    last_results: List[CommandResult] = field(default_factory=list)
    stop_reason: str = ""

class OrchestrationConfig(TypedDict):
    external_skill_dir: str
    max_rounds: int       # 最大轮次 (防止死循环)
    exec_mode: str        # sequential / concurrent
    stop_on_fatal: bool   # 遇到 fatal 错误是否立即停止
