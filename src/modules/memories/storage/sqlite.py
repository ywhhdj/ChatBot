"""记忆存储后端：SQLite 元数据 + Milvus 向量（单一职责）。

**FAISS 已从本文件彻底移除**：不再有本地索引文件、id 映射表、
`save()`/`load_meta()`。元数据是权威，向量只由 `VectorStore` 端口管理。

修复清单（本轮）
──────────────
* C-02 旧 `__worker_loop` 每次循环都 `create_task(sleep(...))`，
  命中任务分支后**不 cancel 这个 sleep** → 每个请求泄漏一个
  最长 decay_interval 的协程，高频对话下稳定堆积到内存耗尽；
  且 `asyncio.Queue` / `Future` 绑定首次 start 的 loop，从 Web loop
  与调度器 loop 分别调用必然 "attached to a different loop"。
  **本轮整体移除 worker 队列**：AsyncSqlite 已用单线程 executor +
  threading.Lock 保证串行，队列只多一次往返与一层死结；
* C-03 `__add_memories_write` 用 `asyncio.create_task` 写映射/裁剪，
  异常无人接收（"Task exception was never retrieved"），且写入顺序
  与元数据不原子；
* C-04 `retrieve_memory` 从全局索引取 top-K 再按 session 过滤 ——
  高并发会话下真正属于本会话的结果会被别会话的向量挤出去。
  现在 scope 过滤由 Milvus 服务端完成；
* C-05 写入正文与向量分两步且无补偿，向量写失败会留下
  "元数据有、检索不到"的静默不一致。现在明确记录并交给
  `health_report()` 报出待补建清单；
* C-06 `get_compressed` 用 `str(r.id) not in blocked` 比较，
  而 `blocked` 来自 `verdict.row_id`（int），类型不匹配导致
  引用已删记忆的压缩摘要**根本没被排除**；
* C-07 `close()` cancel worker 后未排空的队列任务只置异常，
  但 worker 循环仍可能持有本地索引引用；现在无本地索引，关闭路径
  收敛为"排空 → 置异常 → 关连接"。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...logger import audit, logger
from .. import integrity, utils
from ..domain.layers import MemoryLayer
from ..ports.protocols import VectorStore
from .base import MemoryStorageBase
from .database import MemoryRepository
from .models import CompressedMemory, Memory


class SQLiteMemoryStorage(MemoryStorageBase):
    """唯一的生产存储后端。类名不再带任何向量库名。"""

    def __init__(
        self,
        embed_fn: Callable[[str], Any],
        *,
        db_path: str = "memory/memory.db",
        embedding_dim: int = 384,
        max_records: int = 10000,
        decay_rate: float = 0.995,
        decay_interval_sec: int = 3600,
        reinforce_boost: float = 0.08,
        short_term_days: int = 2,
        embedding_provider: str = "",
        embedding_model: str = "",
        embedding_version: str = "1",
        embed_batch_fn: Optional[Callable[[Sequence[str]], Any]] = None,
        vector_provider: Optional[Callable[[], Optional[VectorStore]]] = None,
        fingerprint_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__()
        self.db_path = str(db_path)
        self.embedding_dim = int(embedding_dim)
        self.embedding_provider = str(embedding_provider or "")
        self.embedding_model = str(embedding_model or "")
        self.embedding_version = str(embedding_version or "1")
        self.max_records = int(max_records)
        self.decay_rate = float(decay_rate)
        self.decay_interval_sec = max(60, int(decay_interval_sec))
        self.reinforce_boost = float(reinforce_boost)
        self.short_term_days = max(1, int(short_term_days))
        self._embed_one = embed_fn
        self._embed_many = embed_batch_fn
        self._vector_provider = vector_provider
        self._fingerprint_provider = fingerprint_provider or (lambda: "")

        self._sqlite: Optional[MemoryRepository] = None
        self._running = False
        self._last_decay_time: float = 0.0
        self._rebuild_plan: Optional[integrity.RebuildPlan] = None
        #: 向量写入失败但元数据已落盘的 id。health_report 会报出来。
        self._unindexed: List[int] = []
        self._stat_writes = 0
        self._stat_searches = 0

    # ---------- 向量端口 ----------

    def _vector(self) -> Optional[VectorStore]:
        if self._vector_provider is None:
            return None
        try:
            return self._vector_provider()
        except Exception:  # noqa: BLE001
            return None

    def _fingerprint(self) -> str:
        try:
            return str(self._fingerprint_provider() or "")
        except Exception:  # noqa: BLE001
            return ""

    # ---------- 嵌入 ----------

    async def _embed_text(self, text: str) -> List[float]:
        result = self._embed_one(text)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            result = await result
        return [float(x) for x in list(result)]

    async def _embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        """批量编码。优先一次性调用，避免 N 次往返。"""
        if self._embed_many is not None:
            result = self._embed_many(list(texts))
            if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                result = await result
            return [[float(x) for x in list(row)] for row in (result or [])]
        return [await self._embed_text(t) for t in texts]

    # ---------- 初始化 ----------

    async def __initialize(self) -> None:
        if self._sqlite is None:
            repo = MemoryRepository(self.db_path)
            await repo.connect()
            await repo._init_db()
            self._sqlite = repo
        await self.__verify_embedding_fingerprint()

    async def __verify_embedding_fingerprint(self) -> None:
        """指纹不一致**只告警不重建**（B1-06）。"""
        assert self._sqlite is not None
        target = self.embedding_fingerprint()
        try:
            current_raw = await self._sqlite.get_embedding_fingerprint()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Memory] 读取 embedding 指纹失败: {type(exc).__name__}")
            return
        if current_raw is None:
            try:
                await self._sqlite.set_embedding_fingerprint(
                    provider=target.provider, model=target.model,
                    dim=target.dim, version=target.version,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 写入 embedding 指纹失败: {type(exc).__name__}")
            return
        current = integrity.EmbeddingFingerprint.from_dict(current_raw)
        self._rebuild_plan = integrity.plan_rebuild(current, target)
        if self._rebuild_plan.required:
            logger.warning(
                f"[Memory] embedding 指纹变化，需重建 Milvus 索引: "
                f"{self._rebuild_plan.reason}"
            )

    def embedding_fingerprint(self) -> integrity.EmbeddingFingerprint:
        return integrity.EmbeddingFingerprint(
            provider=self.embedding_provider or "default",
            model=self.embedding_model or "default",
            dim=self.embedding_dim,
            version=self.embedding_version or "1",
        )

    async def embedding_status(self) -> Dict[str, Any]:
        assert self._sqlite is not None
        current_raw = await self._sqlite.get_embedding_fingerprint()
        current = integrity.EmbeddingFingerprint.from_dict(current_raw)
        plan = integrity.plan_rebuild(current, self.embedding_fingerprint())
        return plan.as_dict()

    # ---------- 执行（无 worker 队列） ----------

    async def _run_on_worker(self, fn: Callable[[], Any]) -> Any:
        """在当前调用方的 loop 里直接执行；SQL 串行由 AsyncSqlite 保证。

        旧实现把 fn 投递到绑定调度器 loop 的队列并 `await future`：
        Web loop 调用时 worker 在另一个 loop 里 `set_result()`，必然抛
        "got Future attached to a different loop"；而队列空时循环条件
        写反还会让 worker 瞬间退出，所有读写永久挂起。
        """
        await self._ensure_ready()
        result = fn()
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            return await result
        return result

    async def _ensure_ready(self) -> None:
        if self._sqlite is None:
            await self.__initialize()

    async def start(self) -> None:
        """显式初始化。**不绑定任何事件循环**。"""
        await self.__initialize()
        self._running = True

    async def close(self) -> None:
        self._running = False
        if self._sqlite is not None:
            try:
                await self._sqlite.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 数据库关闭失败: {type(exc).__name__}")
            self._sqlite = None

    # ---------- 写入 ----------

    def _mark_unindexed(self, ids: Sequence[int]) -> None:
        """记入待补建清单。**有界且去重**：写入失败重试会反复 append，
        无界列表本身会变成新的内存泄漏点。"""
        if not ids:
            return
        merged = list(dict.fromkeys([*self._unindexed, *[int(i) for i in ids]]))
        if len(merged) > 20_000:
            merged = merged[-20_000:]
        self._unindexed = merged

    async def __add_memories_write(self, memories: List[Memory]) -> List[int]:
        assert self._sqlite is not None
        texts = [str(m.content or "").strip() for m in memories]
        vectors = await self._embed_batch(texts)
        ids = await self._sqlite.add_memories(memories)

        # 三个序列必须严格同长才能按位置配对。适配层批量返回行数不足、
        # 或仓储跳过部分行时，旧代码会 IndexError / 把向量挂到错误的 id 上。
        # 只索引可对齐的前缀，其余明确记入待补建，不静默错配。
        aligned_n = min(len(memories), len(vectors), len(ids))
        if aligned_n < len(ids):
            self._mark_unindexed(ids[aligned_n:])
        aligned = list(zip(ids[:aligned_n], vectors[:aligned_n], memories[:aligned_n]))

        store = self._vector()
        if store is None:
            # 向量后端不可用：**不假装成功**。全部记入待补建清单，
            # health_report 会明确报出，其余召回通道仍可用。
            self._mark_unindexed(ids)
        elif aligned:
            fp = self._fingerprint()
            valid_layers = {x.value for x in MemoryLayer}
            # Milvus 单批有上限，分批写；按 (session, layer) 分组，
            # 绝不能用"批次第一条的 session_id"代表整批 —— 混合会话写入
            # 会把别会话的向量挂到本会话分区，造成静默丢失。
            batch = 256
            for offset in range(0, len(aligned), batch):
                groups: Dict[tuple, tuple] = {}
                for mid, vec, mem in aligned[offset:offset + batch]:
                    sid = str(mem.session_id or "default")
                    layer = str((mem.metadata or {}).get("layer", "") or "episodic")
                    if layer not in valid_layers:
                        layer = MemoryLayer.EPISODIC.value
                    ids_g, vecs_g = groups.setdefault((sid, layer), ([], []))
                    ids_g.append(int(mid))
                    vecs_g.append([float(x) for x in vec])
                for (sid, layer), (ids_g, vecs_g) in groups.items():
                    try:
                        store.add(
                            ids_g, vecs_g,
                            session_id=sid,
                            layer=MemoryLayer(layer),
                            fingerprint=fp,
                        )
                    except Exception as exc:  # noqa: BLE001
                        # 只把失败的那一组记为待补建，不影响同批其它组
                        self._mark_unindexed(ids_g)
                        logger.warning(
                            f"[Memory] Milvus 写入失败，{len(ids_g)} 条待补建 "
                            f"(session={sid}, layer={layer}): {type(exc).__name__}"
                        )
        self._stat_writes += len(ids)
        # C-03：裁剪改为 await，异常不丢
        await self.__prune_if_needed()
        return ids

    async def add_memories(self, memories: List[Memory]) -> List[int]:
        if not memories:
            return []
        return await self._run_on_worker(lambda: self.__add_memories_write(memories))

    async def add_memory(
        self, memory: Memory, vector: Any = None, importance: float = 0.0
    ) -> int:
        if importance:
            memory.importance = importance
        ids = await self.add_memories([memory])
        return int(ids[0]) if ids else 0

    async def add_compressed_memory(self, memory: CompressedMemory) -> None:
        async def _write() -> None:
            assert self._sqlite is not None
            await self._sqlite.add_compressed_memory(memory)

        await self._run_on_worker(_write)

    # ---------- 检索 ----------

    async def retrieve_memory(
        self,
        query_vector: Sequence[float],
        limit: int = 10,
        session_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """语义检索：**服务端先按 session/layer/fingerprint 过滤再 ANN**。"""
        k = max(int(limit), 1)

        async def _search() -> List[Dict[str, Any]]:
            assert self._sqlite is not None
            self._stat_searches += 1
            store = self._vector()
            if store is None:
                logger.debug("[Memory] 向量后端不可用，dense 通道为空")
                return []
            try:
                from ..domain.layers import layers_for_query

                hits = store.search(
                    list(query_vector),
                    session_id=str(session_id),
                    layers=list(layers_for_query(explicit_recall=False)),
                    top_k=min(k * 4, 100),
                    fingerprint=self._fingerprint(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] Milvus 检索失败: {type(exc).__name__}")
                return []
            if not hits:
                return []
            ids = [int(mid) for mid, _score in hits]
            score_map = {int(mid): float(score) for mid, score in hits}
            # 二次 scope 校验：向量库是外部系统，不能假设它一定守约
            records = await self._sqlite.get_records(ids, session_id=str(session_id))
            marks = await self._load_tombstones()
            now = datetime.now()
            results: List[Dict[str, Any]] = []
            for row in records:
                mid = int(row["id"])
                enriched = dict(row)
                enriched["score"] = float(score_map.get(mid, 0.0))
                enriched["similarity"] = float(score_map.get(mid, 0.0))
                enriched["computed_score"] = utils.compute_memory_score(
                    simillarity=float(score_map.get(mid, 0.0)),
                    now=now,
                    last_access_time=datetime.fromtimestamp(
                        float(row.get("last_access_time") or 0.0)
                    ),
                    importance=float(row.get("importance") or 0.0),
                    decay_rate=0.001,
                )
                results.append(enriched)
            results.sort(
                key=lambda x: float(x.get("computed_score", x.get("score", 0.0))),
                reverse=True,
            )
            top = results[:k]
            before = len(top)
            if marks:
                top = integrity.filter_resurrected(top, marks)
                if len(top) != before:
                    logger.warning(
                        f"[Memory] 检索结果剔除 {before - len(top)} 条命中墓碑的记忆"
                    )
            if top:
                await self._sqlite.reinforce(
                    [int(x["id"]) for x in top], self.reinforce_boost
                )
            return top

        return await self._run_on_worker(_search)

    async def get_long_term(
        self, session_id: str = "default", query: str = "", limit: int = 20
    ) -> List[Dict[str, Any]]:
        if not str(query or "").strip():
            return []
        vec = await self._embed_text(str(query))
        return await self.retrieve_memory(
            query_vector=vec, limit=limit, session_id=session_id
        )

    async def candidates(
        self,
        session_id: str = "default",
        *,
        layers: Sequence[str] = (),
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """给 `MemoryRanker` 的 scope 内候选（SQL 侧先过滤）。"""
        async def _query() -> List[Dict[str, Any]]:
            assert self._sqlite is not None
            return await self._sqlite.scoped_candidates(
                str(session_id), layers=list(layers), limit=int(limit)
            )

        return await self._run_on_worker(_query)

    async def get_detailed(
        self, session_id: str = "default", limit: int = 20
    ) -> List[Dict[str, Any]]:
        async def _query() -> List[Dict[str, Any]]:
            assert self._sqlite is not None
            rows = await self._sqlite.get_recent(str(session_id), max(1, int(limit)))
            rows.reverse()
            return rows

        return await self._run_on_worker(_query)

    async def get_short_term(
        self, session_id: str = "default", limit: int = 100
    ) -> List[Dict[str, Any]]:
        async def _query() -> List[Dict[str, Any]]:
            assert self._sqlite is not None
            boundary = (
                datetime.now().timestamp()
                - timedelta(days=self.short_term_days).total_seconds()
            )
            rows = await self._sqlite.get_recent(
                str(session_id), max(int(limit) * 4, int(limit))
            )
            rows = [
                x for x in rows if float(x.get("created_at", 0.0)) >= boundary
            ][: max(1, int(limit))]
            rows.reverse()
            return rows

        return await self._run_on_worker(_query)

    async def get_compressed(
        self,
        session_id: str = "default",
        short_first: bool = True,
        limit: int = 24,
    ) -> List[CompressedMemory]:
        async def _query() -> List[CompressedMemory]:
            assert self._sqlite is not None
            rows = await self._sqlite.get_compressed(
                session_id=str(session_id), limit=max(1, int(limit)) * 4
            )
            # B1-05 复活闸门：压缩摘要由原文生成，引用了已删记忆的
            # 整条排除。C-06：blocked 统一转成 str 再比较。
            marks = await self._load_tombstones()
            if marks:
                deleted_ids = {int(t.memory_id) for t in marks}
                comp_rows = await self._sqlite.compressed_rows(
                    session_id=str(session_id)
                )
                _kept, verdicts = integrity.filter_compressed(
                    comp_rows, deleted_ids
                )
                blocked = {str(v.row_id) for v in verdicts if not v.injectable}
                if blocked:
                    before = len(rows)
                    rows = [r for r in rows if str(r.id) not in blocked]
                    logger.warning(
                        f"[Memory] 排除 {before - len(rows)} 条引用已删记忆的压缩摘要"
                    )
            boundary = (
                datetime.now().timestamp()
                - timedelta(days=self.short_term_days).total_seconds()
            )
            # 修正：旧实现把"近期"放进 long_rows、"远期"放进 short，
            # 正好反了，导致 short_first=True 实际优先返回过期摘要。
            short, long_rows = [], []
            for row in rows:
                (short if float(row.created_at) >= boundary else long_rows).append(row)
            ordered = short + long_rows if short_first else long_rows + short
            return ordered[: max(1, int(limit))]

        return await self._run_on_worker(_query)

    # ---------- 衰减 / 删除 ----------

    async def __prune_if_needed(self) -> None:
        if self._sqlite is None:
            return
        overflow = await self._sqlite.count_rows() - self.max_records
        if overflow <= 0:
            return
        targets = await self._sqlite.lowest_ranked(overflow)
        if not targets:
            return
        await self._sqlite.delete_memories(targets)
        store = self._vector()
        if store is not None:
            try:
                # 容量裁剪不是隐私删除：按 id 清向量即可，不写墓碑
                for offset in range(0, len(targets), 256):
                    store.remove(targets[offset:offset + 256], session_id="")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 裁剪向量清理失败: {type(exc).__name__}")

    async def decay_now(self) -> None:
        async def _decay() -> None:
            assert self._sqlite is not None
            await self._sqlite.decay_importance(self.decay_rate)
            await self.__prune_if_needed()

        await self._run_on_worker(_decay)

    async def delete_memory(self, memory_id: str, *, session_id: str = "default") -> None:
        target = int(memory_id)

        async def _delete() -> None:
            assert self._sqlite is not None
            # 墓碑 + 删行由仓储层单事务完成
            await self._sqlite.delete_memories_tombstoned(
                [target], session_id=str(session_id)
            )

        await self._run_on_worker(_delete)
        store = self._vector()
        if store is not None:
            try:
                store.remove([target], session_id=str(session_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 删除向量失败（墓碑已生效）: {type(exc).__name__}")
        try:
            audit.record(
                audit.Action.MEMORY_DELETE.value,
                resource=audit.Resource(
                    type=audit.ResourceType.MEMORY.value,
                    id=str(target), count=1,
                ),
                decision=audit.Decision.ALLOW.value,
                result=audit.Result.SUCCESS.value,
                source=audit.Source.API.value,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _load_tombstones(self) -> List[integrity.Tombstone]:
        assert self._sqlite is not None
        try:
            rows = await self._sqlite.active_tombstones()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Memory] 读取墓碑失败，删除保护降级: {exc}")
            return []
        out = []
        for row in rows:
            item = integrity.Tombstone.from_dict(row)
            if item is not None:
                out.append(item)
        return out

    # ---------- 诊断 ----------

    async def health_report(self) -> Dict[str, Any]:
        """B1-04：SQLite ↔ Milvus 对齐诊断（纯 id 集合比对）。"""
        async def _diag() -> Dict[str, Any]:
            assert self._sqlite is not None
            snap = await self._sqlite.alignment_snapshot()
            store = self._vector()
            vector_ids: List[int] = []
            index_dim = 0
            vector_error = ""
            backend_available = store is not None
            if store is None:
                vector_error = "向量后端不可用"
            else:
                try:
                    stats = store.stats() or {}
                    index_dim = int(stats.get("dim", 0) or 0)
                    vector_ids = list(store.list_ids(
                        session_id=str(snap.get("session_id", "") or "")
                    ))
                except Exception as exc:  # noqa: BLE001
                    vector_error = type(exc).__name__
                    backend_available = False
            health = integrity.analyze_alignment(
                memory_ids=snap["memory_ids"],
                vector_ids=vector_ids,
                unindexed=list(dict.fromkeys(self._unindexed)),
                index_dim=index_dim,
                expected_dim=int(self.embedding_dim),
                backend_available=backend_available,
            )
            report = health.as_dict()
            report["embedding"] = (
                self._rebuild_plan.as_dict() if self._rebuild_plan else {}
            )
            report["vector_error"] = vector_error
            report["writes"] = self._stat_writes
            report["searches"] = self._stat_searches
            return report

        return await self._run_on_worker(_diag)

    async def stats(self) -> Dict[str, Any]:
        async def _stats() -> Dict[str, Any]:
            assert self._sqlite is not None
            return {
                "records": await self._sqlite.count_rows(),
                "writes": self._stat_writes,
                "searches": self._stat_searches,
                "unindexed": len(set(self._unindexed)),
                "backend": "sqlite+milvus",
            }

        return await self._run_on_worker(_stats)
