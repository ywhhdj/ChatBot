from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TypedDict

from ...types.common import Role

@dataclass
class Message:
    id: str
    content: str
    timestamp: float
    role: str = Role.USER
    session_id: str = "default"
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

class TimeRange(TypedDict):
    start: datetime
    end: datetime

@dataclass
class CompressedContext:
    id: str
    original_ids: list[str]
    compressed_content: str
    summary: str
    created_at: float
    time_range: TimeRange
    session_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

class MemoryContext(TypedDict):
    short_term: str
    long_term: str
    detailed: Optional[list[dict[str, Any]]]
