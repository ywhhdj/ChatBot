"""记忆后端管理：嵌入适配器 + 存储后端选择"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any,Optional

from .storage.base import MemoryStorageBase

try:
    from numpy import concatenate, float32, ndarray, zeros
    from numpy.linalg import norm as _np_norm

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - numpy 缺失时降级
    _HAS_NUMPY = False
    ndarray = Any  # type: ignore
    float32 = None  # type: ignore

Provider = Optional[str]


def _norm(vec):
    if _HAS_NUMPY:
        return float(_np_norm(vec))
    return sum(float(x) * float(x) for x in vec) ** 0.5


def hash_embed(text: str, dim: int = 384):
    """确定性 hash 嵌入（无任何 embedding 模型时的兜底）。"""
    if _HAS_NUMPY:
        vec = zeros(dim, dtype=float32)
    else:
        vec = [0.0] * dim
    if not text:
        return vec
    for token in text.lower().split():
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(h[:8], 16) % dim
        vec[idx] += 1.0
    n = _norm(vec)
    if n > 0:
        if _HAS_NUMPY:
            vec = vec / n  # type: ignore
        else:
            vec = [float(x) / n for x in vec]
    return vec


async def embed_text(text: str, dim: int = 384):
    return hash_embed(text, dim)


class EmbeddingManager:
    """嵌入适配器管理。"""

    def __init__(self, dim: int = 384, provider: str = "sentence") -> None:
        self.dim = int(dim)
        self.provider = provider
        # C100：必须在 __init__ 里建立属性，否则 embed() 首行就 AttributeError
        self.adapter: Any = None

    def init_adapter(self, adapter: Any = None) -> None:
        """C101：传入的 adapter 真正生效。

        优先级：显式传入 > 尝试 create_adapter(provider) > hash 兜底。
        """
        if adapter is not None:
            self.adapter = adapter
            return
        try:
            from .emdedding import create_adapter

            self.adapter = create_adapter(self.provider)
            return
        except Exception:
            pass
        self.adapter = hash_embed

    async def _call_adapter(self, text: str, dim: int):
        adapter = self.adapter
        if adapter is None:
            # C100 兜底：理论上不会走到（init_adapter 总会赋值）
            adapter = hash_embed
            self.adapter = adapter

        # C103：不用 isinstance(x, typing.Callable)，直接尝试调用
        if callable(adapter):
            result = adapter(text, dim)
        elif hasattr(adapter, "embed"):
            result = adapter.embed(text)
        else:
            raise ValueError(f"Unsupported embedding adapter: {type(adapter)}")

        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            result = await result
        return result

    async def embed(self, text: str, dim: Optional[int] = None):
        target_dim = int(dim or self.dim)
        embedding = await self._call_adapter(text, target_dim)

        if _HAS_NUMPY:
            if not isinstance(embedding, ndarray):
                embedding = zeros(target_dim, dtype=float32) + 0.0
                # 非 ndarray 时尝试逐元素填充
                try:
                    for i, v in enumerate(list(embedding)[:target_dim]):
                        embedding[i] = float(v)
                except Exception:
                    pass
            if embedding.dtype != float32: # type: ignore
                embedding = embedding.astype(float32) # type: ignore
            if embedding.shape[0] != target_dim: # type: ignore
                if embedding.shape[0] > target_dim: # type: ignore
                    embedding = embedding[:target_dim]
                else:
                    pad = zeros(target_dim - embedding.shape[0], dtype=float32)
                    embedding = concatenate([embedding, pad], axis=0)
        return embedding

    async def close(self) -> None:
        close_fn = getattr(self.adapter, "close", None)
        if callable(close_fn):
            result = close_fn()
            if asyncio.iscoroutine(result):
                await result
        self.adapter = None


class MemoryBackendManager:
    def __init__(
        self,
        user_is_database: bool = False,
        db_path: str = "memory/memory.db",
        index_path: str = "memory/memory.faiss",
        embedding_dim: int = 384,
        max_records: int = 10000,
        embedding_manager: Optional[EmbeddingManager] = None,
    ) -> None:
        self.db_path = str(db_path)
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.max_records = max_records
        self.embedding_manager = embedding_manager or EmbeddingManager(dim=embedding_dim)
        self.storage = self.__select_storage(user_is_database)

    async def _embed_text(self, text: str, dim: int = 384):
        return await self.embedding_manager.embed(text, dim=dim)

    def __select_storage(self, user_is_database: bool) -> MemoryStorageBase:
        # DB 文件不存在时无法走 SQLite，退回 markdown
        if not user_is_database or not os.path.exists(self.db_path):
            from .storage.markdown import MarkDownStorage

            return MarkDownStorage(
                memory_dir=os.path.dirname(self.db_path) or "memory",
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
                memory_dir=os.path.dirname(self.db_path) or "memory",
                max_size=self.max_records,
                embedding_dim=self.embedding_dim,
                embed_fn=self._embed_text,
            )

    async def close(self) -> None:
        try:
            await self.storage.close()
        finally:
            await self.embedding_manager.close()
