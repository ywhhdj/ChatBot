"""记忆存储数据模型"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from numpy import ndarray
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from ...models import Role, TimeRange

class Memory(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    session_id: str = "default"
    role: str = Role.USER.value
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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    original_ids: list[str]
    compressed_content: str
    summary: str
    created_at: float
    time_range: TimeRange
    session_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)
    _persisted: bool = PrivateAttr(default=False)


class MemoryStorgeData(Memory):
    vector: Optional[ndarray] = None
    # C130：pydantic 私有属性必须用 PrivateAttr
    _persisted: bool = PrivateAttr(default=False)
