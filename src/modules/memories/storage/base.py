"""记忆存储抽象基类"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from .models import CompressedMemory, Memory


class MemoryStorageBase(ABC):

    @abstractmethod
    async def add_memory(
        self, memory: Memory, vector: Any = None, importance: float = 0.0
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def retrieve_memory(
        self,
        query_vector: Sequence[float],
        limit: int = 10,
        session_id: str = "default",
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def delete_memory(
        self, memory_id: str, *, session_id: str = "default"
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_short_term(
        self, session_id: str = "default", limit: int = 100
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_long_term(
        self, session_id: str = "default", query: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_detailed(
        self, session_id: str = "default", limit: int = 20
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_compressed(
        self,
        session_id: str = "default",
        short_first: bool = True,
        limit: int = 24
    ) -> List[CompressedMemory]:
        raise NotImplementedError

    @abstractmethod
    async def add_memories(self, memories: List[Memory]) -> List[int]:
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

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
