"""记忆后端装配：嵌入适配器 + 存储后端。

**只装配两种东西**：一个 `EmbeddingManager`（文本→向量）与一个
`SQLiteMemoryStorage`（SQLite 元数据 + Milvus 向量）。
不再有本地索引路径、不再有 FAISS、也不再有"DB 文件不存在就悄悄
退回 Markdown"的隐式分支。

修复清单
────────
* C-08 旧 `__select_storage()` 判断 `not os.path.exists(db_path)` 就返回
  `MarkDownStorage`。首次启动 DB 必然不存在 → **SQLite 永远不会被使用**，
  而分层 schema、墓碑、强度表全在 SQLite 里。等于整套记忆系统空转。
  现在由 SQLite 自己建库；Markdown 只在显式 `backend=markdown` 时启用。
* C-09 `EmbeddingManager.fingerprint` 用构造时的 `provider` 字符串，
  可实际 adapter 可能是 hash 兜底或注入的第三方实现 —— 指纹与真实
  向量来源不符，B1-06 的"混用检测"形同虚设。现在按实际 adapter 取。
* C-10 批量写入逐条 embed（N 次适配层往返）。新增 `embed_batch()`。
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Callable, List, Optional, Sequence

from .storage.base import MemoryStorageBase

try:
    from numpy import concatenate, float32, ndarray, zeros
    from numpy.linalg import norm as _np_norm

    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False
    ndarray = Any  # type: ignore
    float32 = None  # type: ignore


def _norm(vec) -> float:
    if _HAS_NUMPY:
        return float(_np_norm(vec))
    return sum(float(x) * float(x) for x in vec) ** 0.5


def hash_embed(text: str, dim: int = 384):
    """确定性 hash 嵌入（无任何 embedding 模型时的显式兜底）。

    注意：这是**语义无意义**的兜底，只用于开发/离线回放。
     fingerprint 会明确写 `hash-fallback`，避免与真实模型向量混用。
    """
    vec = zeros(dim, dtype=float32) if _HAS_NUMPY else [0.0] * dim
    if not text:
        return vec
    for token in str(text).lower().split():
        h = hashlib.md5(token.encode("utf-8")).hexdigest()
        vec[int(h[:8], 16) % dim] += 1.0
    n = _norm(vec)
    if n > 0:
        if _HAS_NUMPY:
            vec = vec / n
        else:
            vec = [float(x) / n for x in vec]
    return vec


class EmbeddingManager:
    """嵌入适配器管理。"""

    def __init__(self, dim: int = 384, provider: str = "sentence") -> None:
        self.dim = int(dim)
        self.provider = str(provider)
        self.adapter: Any = None
        self.use_rust = False
        self._rust_failures = 0
        self._adapter_kind = "uninitialized"
        self._model_name = ""

    def init_adapter(self, adapter: Any = None) -> None:
        """显式传入 > 按 provider 构造 > 明确的 hash 兜底。"""
        if adapter is not None:
            self.adapter = adapter
            self._adapter_kind = type(adapter).__name__ if not callable(adapter) \
                else getattr(adapter, "__name__", "callable")
            self._model_name = str(getattr(adapter, "model_name", "") or "")
            return
        try:
            from .emdedding import create_adapter

            self.adapter = create_adapter(self.provider)
            self._adapter_kind = type(self.adapter).__name__
            self._model_name = str(getattr(self.adapter, "model_name", "") or "")
            return
        except Exception:  # noqa: BLE001
            pass
        self.adapter = hash_embed
        self._adapter_kind = "hash-fallback"
        self._model_name = "md5-bow"

        # 仅在明确编译了 Rust embedding 后端时接管前向。
        # 没编译就保持原 adapter，绝不静默切换到另一套向量空间。
        try:
            from .compute.kernel import get_kernel

            if get_kernel().status().get("embedding_backend_compiled"):
                self.use_rust = True
                self._adapter_kind = "rust-local"
        except Exception:  # noqa: BLE001
            self.use_rust = False

    @property
    def fingerprint(self) -> str:
        """B1-06 用的向量生产条件标识。按**实际** adapter 取，不是配置字符串。"""
        from .integrity import EmbeddingFingerprint

        provider = (
            "rust-local" if self.use_rust else self._adapter_kind
        ) or "unknown"
        return EmbeddingFingerprint(
            provider=provider,
            model=self._model_name or self.provider,
            dim=int(self.dim),
            version="2" if self.use_rust else "1",
        ).digest()

    def fingerprint_detail(self) -> Any:
        from .integrity import EmbeddingFingerprint

        return EmbeddingFingerprint(
            provider=("rust-local" if self.use_rust else self._adapter_kind)
            or "unknown",
            model=self._model_name or self.provider,
            dim=int(self.dim),
            version="2" if self.use_rust else "1",
        )

    def embed_batch_sync(self, texts: Sequence[str]) -> List[List[float]]:
        """Rust 前向（同步，调用方负责 to_thread）。"""
        from .compute.kernel import get_kernel

        return get_kernel().encode_batch([str(t) for t in texts])

    async def _call_adapter(self, text: str, dim: int):
        adapter = self.adapter
        if adapter is None:
            self.init_adapter()
            adapter = self.adapter
        if callable(adapter):
            result = adapter(text, dim)
        elif hasattr(adapter, "embed"):
            result = adapter.embed(text)
        else:
            raise ValueError(f"Unsupported embedding adapter: {type(adapter)}")
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            result = await result
        return result

    @staticmethod
    def _coerce(row: Any, dim: int) -> List[float]:
        """统一成 `list[float]`，长度严格等于 dim。

        C-11：旧实现把非 ndarray 结果先 `zeros()` 再 `list(x)` 填，
        填进去全是 0 —— 任何返回 list/tuple 的 adapter 都被静默
        丢弃成零向量，检索结果完全随机且无法察觉。
        """
        out = [float(v) for v in list(row)[:dim]]
        if len(out) < dim:
            out.extend([0.0] * (dim - len(out)))
        return out

    async def embed(self, text: str, dim: Optional[int] = None) -> List[float]:
        target_dim = int(dim or self.dim)
        if self.use_rust:
            try:
                rows = await asyncio.to_thread(self.embed_batch_sync, [text])
                if rows:
                    from .compute.kernel import get_kernel

                    normalized = get_kernel().normalize_batch([rows[0]])[0]
                    return self._coerce(normalized, target_dim)
                self._rust_failures += 1
            except Exception as exc:  # noqa: BLE001
                self._rust_failures += 1
                from ..logger import logger

                logger.warning(
                    f"[Embedding] Rust 前向失败，回退 adapter: {type(exc).__name__}"
                )
                if self._rust_failures >= 3:
                    self.use_rust = False
        embedding = await self._call_adapter(text, target_dim)
        return self._coerce(embedding, target_dim)

    async def embed_batch(
        self, texts: Sequence[str], dim: Optional[int] = None
    ) -> List[List[float]]:
        """批量编码。**一次适配层往返**，避免 N 次调用。

        适配器若支持 list 输入就一次传完；否则逐条回退（正确性优先）。
        """
        items = [str(t or "") for t in texts]
        if not items:
            return []
        target_dim = int(dim or self.dim)

        if self.use_rust:
            try:
                rows = await asyncio.to_thread(self.embed_batch_sync, items)
                from .compute.kernel import get_kernel

                return [self._coerce(v, target_dim)
                        for v in get_kernel().normalize_batch(rows)]
            except Exception as exc:  # noqa: BLE001
                from ..logger import logger

                logger.warning(
                    f"[Embedding] Rust 批量前向失败: {type(exc).__name__}"
                )
                self._rust_failures += 1
                if self._rust_failures >= 3:
                    self.use_rust = False

        adapter = self.adapter
        if adapter is None:
            self.init_adapter()
            adapter = self.adapter
        # 支持批量接口的适配器（encode(list) / embed(list)）
        batch_fn = None
        if hasattr(adapter, "encode"):
            batch_fn = adapter.encode
        elif hasattr(adapter, "embed") and not callable(adapter):
            batch_fn = adapter.embed
        if batch_fn is not None:
            try:
                result = batch_fn(items)
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    result = await result
                rows = list(result)
                if len(rows) == len(items):
                    return [self._coerce(row, target_dim) for row in rows]
            except Exception as exc:  # noqa: BLE001
                from ..logger import logger

                logger.debug(f"[Embedding] 批量接口不可用，逐条回退: {type(exc).__name__}")
        return [await self.embed(t, dim=target_dim) for t in items]

    async def close(self) -> None:
        close_fn = getattr(self.adapter, "close", None)
        if callable(close_fn):
            result = close_fn()
            if asyncio.iscoroutine(result):
                await result
        self.adapter = None


class MemoryBackendManager:
    """把嵌入与存储装配起来。**向量后端由外部注入**（延迟连接）。"""

    def __init__(
        self,
        *,
        db_path: str,
        embedding_dim: int = 384,
        max_records: int = 10000,
        short_term_days: int = 2,
        embedding_manager: Optional[EmbeddingManager] = None,
        vector_provider: Optional[Callable[[], Any]] = None,
        fingerprint_provider: Optional[Callable[[], str]] = None,
        backend: str = "sqlite",
    ) -> None:
        self.db_path = str(db_path)
        self.embedding_dim = int(embedding_dim)
        self.max_records = int(max_records)
        self.embedding_manager = embedding_manager or EmbeddingManager(
            dim=embedding_dim
        )
        self.storage: MemoryStorageBase = self.__select_storage(
            str(backend), vector_provider, fingerprint_provider
        )

    async def _embed_text(
        self, text: str, dim: Optional[int] = None
    ) -> List[float]:
        """兼容两种调用方：sqlite 传 1 个参数，markdown 传 (text, dim)。"""
        return await self.embedding_manager.embed(text, dim=dim)

    async def _embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return await self.embedding_manager.embed_batch(texts)

    def __select_storage(
        self,
        backend: str,
        vector_provider: Optional[Callable[[], Any]],
        fingerprint_provider: Optional[Callable[[], str]],
    ) -> MemoryStorageBase:
        if backend == "markdown":
            from .storage.markdown import MarkDownStorage

            return MarkDownStorage(
                memory_dir=self.db_path.rsplit("/", 1)[0] or "memory",
                max_size=self.max_records,
                embedding_dim=self.embedding_dim,
                embed_fn=self._embed_text,
            )

        from .storage.sqlite import SQLiteMemoryStorage

        fp = self.embedding_manager.fingerprint_detail()
        return SQLiteMemoryStorage(
            embed_fn=self._embed_text,
            embed_batch_fn=self._embed_batch,
            db_path=self.db_path,
            embedding_dim=self.embedding_dim,
            max_records=self.max_records,
            short_term_days=self.short_term_days,
            embedding_provider=fp.provider,
            embedding_model=fp.model,
            embedding_version=fp.version,
            vector_provider=vector_provider,
            fingerprint_provider=fingerprint_provider,
        )

    async def close(self) -> None:
        try:
            await self.storage.close()
        finally:
            await self.embedding_manager.close()
