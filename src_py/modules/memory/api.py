"""记忆系统**唯一对外入口**（统一 API）。

之前对外有五套彼此重叠的入口：
`HybridMemorySystem`（老门面）、`controllers/memory.py` 直接摸
`sysm.storage.*`、`MemoryRetentionService`、`MemoryGCService`、
`MemoryRanker`。调用方各自决定 scope 过滤、墓碑闸门、指纹与错误语义，
结果是同一份数据在不同路径上给出不同答案。

现在收敛成一个 `MemoryAPI`：

| 层 | 职责 |
|---|---|
| Controller / 其它模块 | 只调 `get_memory_api()`，不认识 storage / repo / Milvus |
| **MemoryAPI（本文件）** | scope 校验、预算、缓存、装配、错误语义、审计 |
| Application 服务 | ranker / retention / gc / usage / consolidation（纯编排） |
| Domain | 分层、强度、评分、完整性判定（纯函数） |
| Adapter | SQLite 元数据、Milvus 向量、Embedding、Rust kernel |

**向量后端只有一个：Milvus。** 配置 `backend=memory` 是显式的开发选择；
Milvus 不可用时 `status()['vector']['degraded']=True`，dense 通道置空，
其它召回通道照常 —— 不静默替换实现、不假装语义检索正常。

硬性约束：不在构造期连接 Milvus，不下载依赖，不执行构建/测试。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..logger import audit, logger
from .application.gc import MemoryGCService
from .application.ranker import MemoryRanker, RetrievalPlan, RetrievalReport
from .application.retention import MemoryRetentionService
from .compute.kernel import get_kernel
from .config import MemoryConfig, load_memory_config
from .domain.layers import MemoryLayer, layers_for_query, policy_of
from .features import DEFAULT_FEATURES, MemoryFeatures
from .integrity import EmbeddingFingerprint, cache_key
from .managers import EmbeddingManager, MemoryBackendManager
from .originator import MemoryOriginator
from .ports.protocols import VectorStore
from .storage.models import CompressedMemory, Memory
from .vector.factory import VectorUnavailable, create_vector_store

#: 检索缓存上限与有效期。缓存键含 session / revision / fingerprint / query，
#: 不含这些字段的缓存必然导致跨会话或跨模型串味
CACHE_MAX = 256
CACHE_TTL_SEC = 30.0


class MemoryNotReady(RuntimeError):
    """记忆系统尚未初始化。调用方应显式 await `start()`。"""


class MemoryAPI:
    """统一门面。**所有方法都带 session_id**，scope 在入口处校验。"""

    def __init__(
        self,
        *,
        config: Optional[MemoryConfig] = None,
        llm_client: Any = None,
        embedding_adapter: Any = None,
        conn_factory: Optional[Callable[[], sqlite3.Connection]] = None,
    ) -> None:
        self.config = config or load_memory_config()
        self.config.ensure_parent_dirs()
        self.llm_client = llm_client

        self.features: MemoryFeatures = (
            self.config.feature_flags() or DEFAULT_FEATURES
        )
        self.kernel = get_kernel(force_python=not self.features.rust_kernel)
        self.clock = self.config.clock()
        self.embedding = EmbeddingManager(dim=int(self.config.embedding_dim))
        self.embedding.init_adapter(embedding_adapter)

        self._vector_store: Optional[VectorStore] = None
        self._vector_status: Dict[str, Any] = {"selected": "", "degraded": False}
        self._vector_tried = False
        self._vector_lock = threading.RLock()

        self.backend = MemoryBackendManager(
            db_path=str(self.config.db_path),
            embedding_dim=int(self.config.embedding_dim),
            max_records=int(self.config.max_records),
            short_term_days=int(self.config.short_term_days),
            embedding_manager=self.embedding,
            vector_provider=lambda: self._vector_store,
            fingerprint_provider=lambda: self.embedding.fingerprint,
            backend=str(self.config.storage_backend or "sqlite"),
        )
        self.storage = self.backend.storage

        # 同步 sqlite 连接工厂：给 retention / gc / originator 用。
        # 它们跑在线程池里，不能复用 storage worker 的异步连接。
        self._conn_factory = conn_factory or (
            lambda: sqlite3.connect(
                str(self.config.db_path), 
                timeout=5.0,
                check_same_thread=False
            )
        )
        self.retention_service = MemoryRetentionService(
            self._conn_factory,
            clock=self.clock,
            now=time.time
        )
        self.gc = MemoryGCService(
            self._conn_factory,
            features=self.features,
            vector_remove=self._remove_vectors,
        )
        self.originator = MemoryOriginator(
            self._conn_factory,
            tombstone_provider=self._tombstones,
            now_seconds=time.time,
        )

        self.ranker = MemoryRanker(
            kernel=self.kernel,
            vector_store=None,           # rank() 时按最新后端注入
            clock=self.clock,
            features=self.features,
            candidate_provider=self._candidate_provider,
        )

        self._cache: "OrderedDict[str, Tuple[float, List[Dict[str, Any]]]]" = (
            OrderedDict()
        )
        self._cache_lock = threading.RLock()
        self._revision = 0
        self._started = False
        self._closing = False
        self._bg_tasks: set[asyncio.Task] = set()

    # ─────────────────────────────────────────────────────────
    # 生命周期
    # ─────────────────────────────────────────────────────────

    async def start(self) -> Dict[str, Any]:
        """显式启动。**不连 Milvus**（连接延迟到第一次检索）。"""
        if self._started:
            return self.status()
        await self.storage.start()
        self._started = True
        logger.info("[MemoryAPI] 已启动（SQLite 权威，Milvus 延迟连接）")
        return self.status()

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    async def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            if self._bg_tasks:
                try:
                    await asyncio.wait(list(self._bg_tasks), timeout=5.0)
                except Exception:  # noqa: BLE001
                    pass
                for task in list(self._bg_tasks):
                    if task.done() and not task.cancelled():
                        exc = task.exception()
                        if exc is not None:
                            logger.warning(
                                f"[MemoryAPI] 后台任务失败: {type(exc).__name__}"
                            )
            await self.backend.close()
        finally:
            if self._vector_store is not None:
                try:
                    self._vector_store.flush()
                except Exception:  # noqa: BLE001
                    pass
            self._started = False

    @property
    def initialized(self) -> bool:
        return self._started

    # ─────────────────────────────────────────────────────────
    # 向量后端（延迟、可解释）
    # ─────────────────────────────────────────────────────────

    def ensure_vector_backend(self) -> Dict[str, Any]:
        """第一次真正需要检索时才连接。**失败不抛给业务，标记 degraded**。"""
        with self._vector_lock:
            if self._vector_tried:
                return dict(self._vector_status)
            self._vector_tried = True
            try:
                cfg = self.config.vector_config()
                store, status = create_vector_store(
                    cfg,
                    dim=int(self.config.embedding_dim),
                    fingerprint=self.embedding.fingerprint,
                )
                self._vector_store = store
                self._vector_status = status
                self.ranker.vector_store = store
            except (VectorUnavailable, ValueError) as exc:
                self._vector_store = None
                self.ranker.vector_store = None
                self._vector_status = {
                    "selected": "none",
                    "degraded": True,
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                    "fallback_chain": [],
                }
                logger.warning(
                    f"[MemoryAPI] 向量后端不可用，dense 通道置空: "
                    f"{type(exc).__name__}"
                )
            except Exception as exc:  # noqa: BLE001
                self._vector_status = {
                    "selected": "none",
                    "degraded": True,
                    "error": type(exc).__name__,
                }
                logger.warning(f"[MemoryAPI] 向量初始化异常: {type(exc).__name__}")
            return dict(self._vector_status)

    @property
    def vector_store(self) -> Optional[VectorStore]:
        return self._vector_store

    def _remove_vectors(self, ids: Sequence[int], session_id: str) -> None:
        store = self._vector_store
        if store is None:
            return
        store.remove([int(x) for x in ids], session_id=str(session_id or ""))

    def _tombstones(self) -> List[Dict[str, Any]]:
        conn = self._conn_factory()
        try:
            rows = conn.execute(
                "SELECT memory_id, session_id, digest, deleted_at, reason "
                "FROM memory_tombstones"
            ).fetchall()
            keys = ("memory_id", "session_id", "digest", "deleted_at", "reason")
            return [dict(zip(keys, row)) for row in rows]
        except sqlite3.Error:
            return []
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    async def _fetch_candidates(
        self, 
        session_id: str,
        layers: Sequence[MemoryLayer], limit: int
    ) -> List[Dict[str, Any]]:
        await self._ensure_started()
        fn = getattr(self.storage, "candidates", None)
        if callable(fn):
            rows = await fn(
                session_id,
                layers=[str(getattr(x, "value", x)) for x in layers],
                limit=int(limit),
            )
            return [dict(r) for r in (rows or [])]
        rows = await self.storage.get_detailed(session_id=session_id, limit=limit)
        return [dict(r) for r in (rows or [])]

    def _cache_get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            ts, value = item
            if time.time() - ts > CACHE_TTL_SEC:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return [dict(x) for x in value]

    def _cache_put(self, key: str, value: List[Dict[str, Any]]) -> None:
        with self._cache_lock:
            self._cache[key] = (time.time(), [dict(x) for x in value])
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_MAX:
                self._cache.popitem(last=False)

    def _invalidate(self) -> None:
        self._revision += 1
        with self._cache_lock:
            self._cache.clear()

    async def search(
        self,
        query: str,
        *,
        session_id: str = "default",
        top_k: int = 10,
        explicit_recall: bool = False,
        per_channel: int = 50,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """语义/混合检索。**统一入口**：scope → 预算 → 多路召回 → 门控。
        
        Returns:
        
            ```
                {
                    "items": [
                        {
                            "id": int,
                            "content": str,
                            "score": float,
                            "metadata": Dict[str, Any],
                            "layer": str,
                            "session_id": str,
                            "digest": str,
                            "created_at": float,
                            "updated_at": float,
                            "deleted_at": float,
                        }
                    ],
                    "report": {
                        "reason": str,
                        "cache_hit": bool,
                        "degraded": bool,
                        "vector_degraded": bool,
                        "vector_selected": str,
                        "vector_degraded_chain": List[str],
                        "vector_degraded_reason": str,
                        "vector_degraded_message": str,
                    },
                    "degraded": bool,
                }
            ```
        """
        q = str(query or "").strip()
        if not q:
            return {
                "items": [],
                "report": {"reason": "empty_query"},
                "degraded": False
            }
        sid = str(session_id or "default")
        layers = layers_for_query(explicit_recall=explicit_recall)
        plan = RetrievalPlan(
            session_id=sid, query=q, top_k=max(1, int(top_k)),
            explicit_recall=bool(explicit_recall),
            per_channel=int(per_channel), layers=tuple(layers),
            fingerprint=self.embedding.fingerprint,
        )
        detail = self.embedding.fingerprint_detail()
        key = cache_key(sid, q, detail, memory_revision=str(self._revision))
        if use_cache:
            hit = self._cache_get(key)
            if hit is not None:
                return {
                    "items": hit,
                    "report": {"cache_hit": True},
                    "degraded": False
                }

        vector_status = self.ensure_vector_backend()
        degraded = bool(vector_status.get("degraded"))
        query_vector: Optional[List[float]] = None
        if not degraded:
            try:
                query_vector = await self.embedding.embed(q)
            except Exception as exc:  # noqa: BLE001
                degraded = True
                logger.warning(f"[MemoryAPI] query 编码失败: {type(exc).__name__}")

        candidates = await self._fetch_candidates(
            sid, layers, max(int(per_channel) * 4, int(top_k) * 4, 50)
        )
        # ranker 无 IO：candidates 显式注入，vector_store 由 ensure 注入
        self.ranker.vector_store = self._vector_store
        items, report = self.ranker.rank(
            plan, query_vector=query_vector, candidates=candidates
        )

        # 门控与墓碑：ranker 只给候选，**不拥有权限**（MemoryDesign §12）
        marks = await self._async_tombstones()
        if marks:
            from .integrity import Tombstone, filter_resurrected

            typed = [t for t in (Tombstone.from_dict(m) for m in marks) if t]
            before = len(items)
            items = filter_resurrected(items, typed)
            if len(items) != before:
                report.warnings.append(
                    f"剔除 {before - len(items)} 条命中墓碑的记忆"
                )
        if use_cache and items:
            self._cache_put(key, items)
        self._emit_audit("memory.retrieve", sid, len(items))
        return {
            "items": items,
            "report": report.as_dict(),
            "degraded": degraded,
        }

    async def _async_tombstones(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._tombstones)

    # ─────────────────────────────────────────────────────────
    # 读（统一 DTO 形态）
    # ─────────────────────────────────────────────────────────

    async def short(
        self,
        session_id: str = "default",
        limit: int = 10
    ) -> str:
        """获取短期记忆

        Args:
            session_id (str, optional): 会话ID. Defaults to "default".
            limit (int, optional): 限制数. Defaults to 10.

        Returns:
            str: 短期记忆
        """
        from datetime import datetime, timedelta

        await self._ensure_started()
        rows = await self.storage.get_short_term(
            session_id=str(session_id), limit=max(1, int(limit) * 4)
        )
        boundary = datetime.now() - timedelta(days=int(self.config.short_term_days))
        lines, seen = [], set()
        for row in rows:
            text = " ".join(str(row.get("content", "") or "").split())
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            if len(text) > 160:
                text = text[:157] + "..."
            try:
                stamp = datetime.fromtimestamp(
                    float(row.get("created_at", 0.0) or 0.0)
                )
            except (ValueError, OSError, OverflowError):
                continue
            if stamp < boundary:
                continue
            lines.append(
                f"[{stamp.strftime('%Y-%m-%d')}] "
                f"({row.get('role', 'memory')}) {text}"
            )
        return "\n".join(lines[-max(1, int(limit)):])

    async def long(
        self,
        session_id: str = "default",
        limit: int = 12
    ) -> str:
        await self._ensure_started()
        try:
            chunks = await self.storage.get_compressed(
                session_id=str(session_id), short_first=False,
                limit=max(1, int(limit)),
            )
            if chunks:
                return "\n".join(
                    f"- {x.summary or x.compressed_content[:180]}"
                    for x in chunks[:limit]
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[MemoryAPI] 读取压缩记忆失败: {type(exc).__name__}")
        return ""

    async def compressed(
        self,
        session_id: str = "default",
        limit: int = 24
    ) -> List[Dict[str, Any]]:
        """压缩记忆

        Args:
            session_id (str, optional): 会话ID. Defaults to "default".
            limit (int, optional): 限制数. Defaults to 24.

        Returns:
            List[Dict[str, Any]]: _description_
        """
        
        await self._ensure_started()
        rows = await self.storage.get_compressed(
            session_id=str(session_id), short_first=True, limit=int(limit)
        )
        out = []
        for row in rows:
            meta = row.metadata or {}
            out.append({
                "id": str(row.id),
                "summary": str(row.summary or ""),
                "created_at": float(row.created_at),
                "original_count": int(meta.get("original_count", 0) or 0),
            })
        return out

    async def layers(
        self,
        *,
        session_id: str = "default",
        query: str = "",
        detail_top_k: int = 12,
        summary_limit: int = 12,
    ) -> Dict[str, Any]:
        """获取所有记忆层
        
        Args:
            session_id: 会话 ID
            query: 查询
            detail_top_k: 详细结果数量
            summary_limit: 概要结果数量
        
        Returns:
            Dict[str, Any]: 记忆层信息
            ```json
            {
                "short_term": "...",
                "long_term": "...",
                "detailed": [
                    {
                        "id": "...",
                        "summary": "...",
                        "created_at": 1234567890.0,
                        "original_count": 123
                    },
                    ...
                ]
            }
            ```
        """
        sid = str(session_id or "default")
        short_text = await self.short(sid, limit=summary_limit)
        long_text = await self.long(sid, limit=summary_limit)
        detailed: Optional[List[Dict[str, Any]]] = None
        q = str(query or "").strip()
        if q:
            result = await self.search(q, session_id=sid, top_k=detail_top_k)
            detailed = result["items"]
        return {
            "short_term": short_text,
            "long_term": long_text,
            "detailed": detailed
        }

    async def stats(self) -> Dict[str, Any]:
        """获取

        Returns:
            Dict[str, Any]: _description_
        """
        
        await self._ensure_started()
        fn = getattr(self.storage, "stats", None)
        base = await fn() if callable(fn) else {}
        base.update({
            "vector": dict(self._vector_status),
            "features": self.features.as_dict(),
            "kernel": self.kernel.status(),
            "revision": self._revision,
        })
        return base

    async def health(self) -> Dict[str, Any]:
        await self._ensure_started()
        fn = getattr(self.storage, "health_report", None)
        return await fn() if callable(fn) else {"available": False}

    async def embedding_status(self) -> Dict[str, Any]:
        fn = getattr(self.storage, "embedding_status", None)
        return await fn() if callable(fn) else {}

    def status(self) -> Dict[str, Any]:
        """
        获取服务状态
        
        Returns
            ```json
            {
                "initialized": true,
                "kernel": {
                    "status": "running",
                    "uptime": 1234567890.0
                },
                "features": {
                    "rag": true,
                    "compression": true,
                    "vector": true,
                    "short_term": true,
                    "long_term": true,
                    "compaction": true,
                    "retention": true,
                    "user_is_database": true
                },
                "clock": "wall",
                "clock_day": 1234567890.0,
                "vector": {
                    "status": "running",
                    "uptime": 1234567890.0
                },
                "embedding_fingerprint": "...",
                "embedding_provider": "...",
                "embedding_dim": 384,
                "cache_entries": 123,
                "revision": "...",
                "backend": "sqlite+milvus"
            }
        """
        
        return {
            "initialized": self._started,
            "kernel": self.kernel.status(),
            "features": self.features.as_dict(),
            "clock": self.clock.kind(),
            "clock_day": self.clock.now_day(),
            "vector": dict(self._vector_status),
            "embedding_fingerprint": self.embedding.fingerprint,
            "embedding_provider": self.embedding.fingerprint_detail().provider,
            "embedding_dim": int(self.config.embedding_dim),
            "cache_entries": len(self._cache),
            "revision": self._revision,
            "backend": "sqlite+milvus",
        }

    # ─────────────────────────────────────────────────────────
    # 写
    # ─────────────────────────────────────────────────────────

    async def add(self, memories: List[Memory]) -> List[int]:
        await self._ensure_started()
        ids = await self.storage.add_memories(memories)
        self._invalidate()
        self._emit_audit("memory.add", "", len(ids))
        return ids

    async def add_compressed(self, memory: CompressedMemory) -> None:
        await self._ensure_started()
        await self.storage.add_compressed_memory(memory)
        self._invalidate()

    async def delete(
        self, 
        memory_id: Any, 
        *, 
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """隐私删除：墓碑 + 元数据 + 向量，一次调用完成。"""
        await self._ensure_started()
        try:
            mid = int(memory_id)
        except (TypeError, ValueError):
            return {"ok": False, "code": "bad_id", "message": "memory_id 非法"}
        try:
            await self.storage.delete_memory(
                str(mid), session_id=str(session_id)
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "code": "delete_failed",
                "message": type(exc).__name__
            }
        self._invalidate()
        self._emit_audit("memory.delete", str(session_id), 1)
        return {
            "ok": True,
            "id": mid,
            "deleted": True
        }

    async def decay(self) -> None:
        await self._ensure_started()
        await self.storage.decay_now()
        self._invalidate()

    async def flush(self, timeout: float = 5.0) -> None:
        if not self._bg_tasks:
            return
        try:
            await asyncio.wait(list(self._bg_tasks), timeout=max(0.1, timeout))
        except Exception:  # noqa: BLE001
            pass

    # ─────────────────────────────────────────────────────────
    # 管理动作（委托应用服务，线程池执行同步 sqlite）
    # ─────────────────────────────────────────────────────────

    async def retention(self, **kwargs: Any) -> Dict[str, Any]:
        result = await asyncio.to_thread(self.retention_service.set_retention, **kwargs)
        if result.get("applied"):
            self._invalidate()
        return result

    async def pin(self, **kwargs: Any) -> Dict[str, Any]:
        result = await asyncio.to_thread(self.retention_service.pin, **kwargs)
        if result.get("applied"):
            self._invalidate()
        return result

    async def revive(self, **kwargs: Any) -> Dict[str, Any]:
        result = await asyncio.to_thread(self.retention.revive, **kwargs)
        if result.get("applied"):
            self._invalidate()
        return result

    async def gc_preview(self, *, session_id: str = "default") -> Dict[str, Any]:
        """GC dry-run：只列候选，**永不删除**。"""
        rows = await self._fetch_candidates(
            str(session_id), tuple(MemoryLayer), limit=200_000
        )
        now_day = self.clock.now_day()
        shaped = []
        for row in rows:
            shaped.append({
                "id": row.get("id"),
                "session_id": row.get("session_id", session_id),
                "layer": row.get("layer", "episodic"),
                "stability": row.get("stability", 1.0),
                "last_reinforced_day": row.get("last_reinforced_day", now_day),
                "importance": row.get("importance", 0.0),
                "pinned": row.get("pinned", 0),
                "created_day": float(row.get("created_at", 0.0) or 0.0) / 86400.0,
                "covered_by_summary": row.get("covered_by_summary", 0),
                "bytes": len(str(row.get("content", "") or "")),
            })
        return self.gc.dry_run(
            shaped, 
            scope=str(session_id),
            now_day=now_day
        ).as_dict()

    async def gc_apply(
        self,
        *, 
        approved: bool = False,
        override_privacy: bool = False,
        session_id: str = "default",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """硬删除。**两把钥匙**：`features.gc_apply` + `approved`。"""
        preview = await self.gc_preview(session_id=session_id)
        from .application.gc import GCReport, GCCandidate

        report = GCReport(
            operation_id=preview.get("operation_id", ""),
            scope=str(session_id), now_day=self.clock.now_day(),
            inspected=preview.get("inspected", 0),
            candidates=[
                GCCandidate(**c) for c in preview.get("candidates", [])
            ],
            estimated_release_bytes=preview.get("estimated_release_bytes", 0),
            warnings=list(preview.get("warnings", [])),
        )
        out = await asyncio.to_thread(
            self.gc.apply, 
            report,
            approved=approved,
            override_privacy=override_privacy,
            request_id=request_id,
        )
        if out.applied:
            self._invalidate()
        return out.as_dict()

    # ─────────────────────────────────────────────────────────
    # 存档集成
    # ─────────────────────────────────────────────────────────

    @property
    def snapshot_originator(self) -> MemoryOriginator:
        return self.originator

    # ─────────────────────────────────────────────────────────
    # 审计
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _emit_audit(action: str, session_id: str, count: int) -> None:
        try:
            audit.record(
                action,
                session_id=str(session_id or ""),
                decision=audit.Decision.ALLOW.value,
                result=audit.Result.SUCCESS.value,
                resource=audit.Resource(
                    type=audit.ResourceType.MEMORY.value, count=int(count)
                ),
            )
        except Exception:  # noqa: BLE001
            pass


_api: Optional[MemoryAPI] = None
_api_lock = threading.RLock()


def peek_memory_api() -> Optional[MemoryAPI]:
    with _api_lock:
        return _api


def get_memory_api(**kwargs: Any) -> MemoryAPI:
    global _api
    if _api is None:
        with _api_lock:
            if _api is None:
                _api = MemoryAPI(**kwargs)
    return _api


def reset_memory_api() -> None:
    global _api
    with _api_lock:
        _api = None
