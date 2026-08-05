import asyncio
import hashlib
from types import CoroutineType
from typing import Generic, Literal, TypeVar, Union
import os
from numpy import float32,ndarray,zeros,concatenate,linalg
from typing import Optional, Callable

Provider = Optional[Literal["sentence", "openai", "ollama"]]

async def embed_text(text: str, dim: int = 384) -> ndarray:
    """
    Simple, deterministic hash embedding (fallback when no embedding model is configured).
    """
    vec = zeros(dim, dtype=float32)
    if not text:
        return vec
    for token in text.lower().split():
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        vec[idx] += 1.0
    norm_val = linalg.norm(vec)
    if norm_val > 0:
        vec /= norm_val
    return vec

class EmbeddingManager:
    def __init__(
        self,
        dim: int = 384,
        provider:str="sentence",
    ) -> None:
        self.dim = dim

    def init_adapter(self,adapter: Provider=None) -> None:
        if adapter is None:
            try:
                from .emdedding import create_adapter
                self.adapter=create_adapter("sentence")
                return
            except Exception:
                self.adapter=embed_text
        else:
            self.adapter=embed_text

    async def embed(self, text: str, dim: Optional[int] = None) -> ndarray:
        target_dim = int(dim or self.dim)
        if self.adapter is None:
            from .utils import embed_text
            self.adapter=embed_text
        if isinstance(self.adapter, Callable):
            res = self.adapter(text, target_dim)
            embedding = await res if asyncio.iscoroutine(res) else res
        else:
            embedding = await self.adapter.embed(text)
        if not isinstance(embedding, ndarray):
            raise ValueError(f"Unsupported embedding type: {type(embedding)}")
        if embedding.dtype != float32:
            embedding = embedding.astype(float32)
        if embedding.shape[0] != target_dim:
            if embedding.shape[0] > target_dim:
                embedding = embedding[:target_dim]
            else:
                padding = zeros(target_dim - embedding.shape[0], dtype=float32)
                embedding = concatenate([embedding, padding], axis=0)
        return embedding


class MemoryBackendManager:
    def __init__(
        self,
        user_is_database:bool=False,
        db_path: str = "memory/memory.db",
        index_path: str = "memory/memory.faiss",
        embedding_dim: int = 384,
        max_records: int = 10000,
        embedding_manager: Optional[EmbeddingManager] = None,
    ) -> None:
        self.db_path = db_path
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.max_records = max_records
        self.embedding_manager = embedding_manager or EmbeddingManager(dim=embedding_dim)
        self.storage = self.__select_storage(user_is_database)

    async def _embed_text(self, text: str, dim: int = 384) -> ndarray:
        return await self.embedding_manager.embed(text, dim=dim)

    def __select_storage(self,user_is_database:bool)  :
        # If there is no existing DB, default to in-memory strategy.
        if not user_is_database or not os.path.exists(self.db_path):
            from .storage.markdown import MarkDownStorage
            return MarkDownStorage(
                memory_dir="memory",
                max_size=self.max_records,
                embedding_dim=self.embedding_dim,
                embed_fn=self._embed_text,
            )
        try:
            from .storage.sqlite import SQLiteFAISSStorage
            return SQLiteFAISSStorage(
                db_path=self.db_path,
                index_path=self.index_path,
                embedding_dim=self.embedding_dim,
                max_records=self.max_records,
                decay_rate=0.995,
                decay_interval_sec=3600,
                reinforce_boost=0.08,
                embed_fn=self._embed_text,
            )
        except Exception:
            from .storage.markdown import MarkDownStorage
            return MarkDownStorage(
                memory_dir="memory",
                max_size=self.max_records,
                embedding_dim=self.embedding_dim,
                embed_fn=self._embed_text,
            )

    async def close(self) -> None:
        await self.storage.close()
