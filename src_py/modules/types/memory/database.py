from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
from .context import TimeRange
from ..common import Role


@dataclass
class Memory:
    id: str
    session_id: str = "default"
    role: str = Role.USER
    source: str = "text"
    content: str = ""
    importance: float = 1.0
    access_count: int = 0
    last_access_time: float = field(default_factory=lambda: datetime.now().timestamp())
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompressedMemory:
    id: str
    original_ids: list[str]
    compressed_content: str
    summary: str
    created_at: float
    time_range: TimeRange
    session_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    _persisted: bool = False


@dataclass
class MemoryStorgeData(Memory):
    vector: Optional[np.ndarray] = None
    _persisted: bool = False
