"""记忆存储抽象基类。

| 方法 | 基类签名 | 实际实现（sqlite.py / markdown.py） | main.py 调用 |
|---|---|---|---|
| `add_memory` | `(memory, vector, importance) -> int` | `-> list[int]` | — |
| `retrieve_memory` | `(query_vector, limit)` | `(query_vector, limit, session_id)` | 有 session_id |
| `get_detailed` | `(memory_id)` | `(session_id, limit)` | `(session_id, limit)` |
| `get_long_term` | `(session_id, limit)` | `(session_id, query, limit)` | 有 query |
| `get_compressed` | `()` | `(session_id, short_first, limit)` | 有参数 |

`HybridMemorySystem` 按实现签名调用，一旦存储后端切换（SQLite ↔ Markdown）
或有人照基类签名写代码，立刻 TypeError。这里统一为**实现侧的真实签名**
（带 session_id），并把 `get_detailed` 的参数名从 `memory_id` 改对。
"""

from abc import ABC, abstractmethod
from typing import Any

from numpy import ndarray

from .models import CompressedMemory, Memory


class MemoryStorageBase(ABC):

    @abstractmethod
    async def add_memory(
        self, memory: Memory, vector: ndarray, importance: float = 0.0
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def retrieve_memory(
        self, query_vector: ndarray, limit: int = 10, session_id: str = "default"
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_short_term(
        self, session_id: str = "default", limit: int = 100
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_long_term(
        self, session_id: str = "default", query: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_detailed(
        self, session_id: str = "default", limit: int = 20
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_compressed(
        self, session_id: str = "default", short_first: bool = True, limit: int = 24
    ) -> list[CompressedMemory]:
        raise NotImplementedError

    @abstractmethod
    async def add_memories(self, memories: list[Memory]) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    async def add_compressed_memory(self, memory: CompressedMemory) -> None:
        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def decay_now(self) -> None:
        raise NotImplementedError
