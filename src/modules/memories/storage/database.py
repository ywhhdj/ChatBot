"""记忆元数据仓储（SQLite 权威源）。

**向量检索不在这里**：唯一的生产后端是 `memory/vector/` 的 Milvus 适配器。
本模块只负责事实/情节/摘要、强度、时钟、墓碑、指纹等权威数据，
以及给对齐诊断提供 id 集合。FAISS 与 `faiss_id_map` 已彻底移除。

设计约束
────────
* SQLite 是**权威**：Milvus 索引可随时从这里的正文重建；
* 所有写操作都经 `AsyncSqlite` 的显式 commit / `transaction()`；
  （旧实现全部不提交，conn.close() 时静默回滚 —— 见 `database/sqlite.py`）
* 所有查询**先按 session 过滤**，绝不返回全局集合再让上层过滤；
* 不导入 numpy / pymilvus，保持仓储层可独立测试。
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ...logger import logger
from ...runtime import RuntimePath
from .. import integrity
from ..database.sqlite import AsyncSqlite
from .models import CompressedMemory, Memory, TimeRange


#: `memories` 表全部可写列（与 resources/defaults/memory.sql 一致）。
MEMORY_COLUMNS: tuple[str, ...] = (
    "session_id", "role", "source", "content", "importance",
    "access_count", "last_access_time", "created_at", "updated_at",
    "tokens", "metadata",
    # schema v2 分层字段
    "layer", "kind", "confidence", "valid_from", "valid_until",
    "source_ids", "embedding_version", "supersedes", "conflict_group",
    "pinned", "derived_from", "covered_by_summary",
)


def _json(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def _row(row: Any) -> Dict[str, Any]:
    """把 sqlite3.Row 转成 dict，并解析 JSON 列。"""
    out = dict(row)
    for key in ("metadata", "source_ids", "supersedes", "derived_from"):
        if key in out:
            out[key] = _loads(out.get(key), {} if key == "metadata" else [])
    return out


class MemoryRepository(AsyncSqlite):
    """记忆元数据仓储。类名不再带向量库名 —— 它只管元数据。"""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.db_path = str(db_path)
        if not hasattr(self, "_MemoryRepository__is_init"):
            self.__is_init = False

    # ---------- 初始化 ----------

    async def _init_db(self) -> None:
        if self.__is_init:
            return
        # 用项目 resource 里的 schema；它是唯一权威 DDL。
        await self.execute_sql_file(RuntimePath.get_sql_file_path())
        from ..migrations import MemoryMigrator

        try:
            report = await self.transaction(
                lambda conn: MemoryMigrator(conn, batch_size=500).migrate().as_dict()
            )
            if isinstance(report, dict) and report.get("warnings"):
                logger.warning(f"[MemoryRepo] 迁移告警: {report['warnings'][:3]}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[MemoryRepo] schema 迁移未完成: {type(exc).__name__}")
        self.__is_init = True

    # ---------- 写入 ----------

    @staticmethod
    def _memory_values(r: Memory) -> tuple:
        meta = dict(r.metadata or {})
        layer = str(meta.get("layer", "") or "")
        return (
            str(r.session_id or "default"),
            str(r.role),
            str(r.source or "text"),
            str(r.content or ""),
            float(r.importance if r.importance is not None else 1.0),
            int(r.access_count or 0),
            float(r.last_access_time or r.created_at),
            float(r.created_at),
            float(r.updated_at or r.created_at),
            int(r.tokens or 0),
            _json(meta),
            layer or "episodic",
            str(meta.get("kind", "") or "fact"),
            float(meta.get("confidence", 0.5) or 0.5),
            float(meta.get("valid_from", 0.0) or 0.0),
            meta.get("valid_until"),
            _json(meta.get("source_ids", [])),
            str(meta.get("embedding_version", "") or ""),
            _json(meta.get("supersedes", [])),
            str(meta.get("conflict_group", "") or ""),
            1 if meta.get("pinned") else 0,
            _json(meta.get("derived_from", [])),
            1 if meta.get("covered_by_summary") else 0,
        )

    async def add_memories(self, rows: List[Memory]) -> List[int]:
        """批量插入并返回**真实自增 id**。

        旧实现用 `last_insert_rowid() - n + 1` 反推，在删除/回滚/
        并发插入后必然错配，且向量会挂到错误的 memory_id 上。
        现在走单事务逐条收集 `lastrowid`。
        """
        if not rows:
            return []
        columns = ",".join(MEMORY_COLUMNS)
        placeholders = ",".join("?" for _ in MEMORY_COLUMNS)
        sql = f"INSERT INTO memories ({columns}) VALUES ({placeholders})"
        ids = await self.insert_batch_returning_ids(
            sql, [self._memory_values(r) for r in rows]
        )
        # 同步补强度行：S0 由层策略与重要度决定，避免"新记忆没有强度"
        from ..domain.layers import policy_of
        from ..domain.strength import initial_stability

        pairs = []
        for mid, r in zip(ids, rows):
            layer = str((r.metadata or {}).get("layer", "") or "episodic")
            stability = initial_stability(
                policy_of(layer).layer, float(r.importance or 0.4)
            )
            pairs.append((
                int(mid), stability, float(r.created_at) / 86400.0,
                float(r.importance or 0.4), 0.0,
            ))
        if pairs:
            await self.transaction(lambda conn: conn.executemany(
                "INSERT OR IGNORE INTO memory_strength("
                "memory_id, stability, last_reinforced_day, importance, salience) "
                "VALUES(?,?,?,?,?)", pairs
            ))
        return ids

    async def add_compressed_memory(self, row: CompressedMemory) -> None:
        start, end = row.time_range.start, row.time_range.end
        await self.insert("compressed_memories").set_fields([
            "id", "session_id", "original_ids", "compressed_content",
            "summary", "created_at", "range_start", "range_end", "metadata",
        ]).add((
            str(row.id),
            str(row.session_id or "default"),
            json.dumps(list(row.original_ids), ensure_ascii=False),
            str(row.compressed_content),
            str(row.summary or ""),
            float(row.created_at),
            float(start.timestamp()),
            float(end.timestamp()),
            _json(row.metadata),
        )).save()

    # ---------- 读取（全部先按 session 过滤） ----------

    async def get_records(
        self, memory_ids: Sequence[int], *, session_id: str = ""
    ) -> List[Dict[str, Any]]:
        if not memory_ids:
            return []
        selector = self.select("memories").where_in("id", [int(i) for i in memory_ids])
        if session_id:
            selector = selector.where({"session_id": str(session_id)})
        rows = await selector.query()
        return [_row(r) for r in (rows or [])]

    async def get_recent(
        self, session_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        rows = await (self.select("memories")
                      .where({"session_id": str(session_id)})
                      .order_by("created_at", "DESC")
                      .limit(int(limit))
                      .query())
        return [_row(r) for r in (rows or [])]

    async def scoped_candidates(
        self,
        session_id: str,
        *,
        layers: Sequence[str] = (),
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """给 `MemoryRanker` 的候选集。**scope 在 SQL 里过滤**。

        只取检索需要的字段，不取大段正文之外的东西；强度表 LEFT JOIN
        一次拿齐，避免 ranker 逐条再查（B2-04 检索预算）。
        """
        # LEFT JOIN 强度表一次拿齐，避免 ranker 逐条再查（B2-04）。
        # 基类链式构造器没有 join，这里直接用参数化原生 SQL。
        where_layers = ""
        params: List[Any] = [str(session_id)]
        if layers:
            placeholders = ",".join("?" for _ in layers)
            where_layers = f" AND m.layer IN ({placeholders})"
            params.extend(str(x) for x in layers)
        params.append(int(limit))
        sql = (
            "SELECT m.id, m.session_id, m.content, m.role, m.created_at, "
            "m.importance, m.confidence, m.layer, m.pinned, m.valid_until, "
            "m.covered_by_summary, s.stability, s.last_reinforced_day, s.state "
            "FROM memories m LEFT JOIN memory_strength s ON s.memory_id = m.id "
            f"WHERE m.session_id = ?{where_layers} "
            "ORDER BY m.created_at DESC LIMIT ?"
        )
        rows = await self._execute(sql, tuple(params))
        return [_row(r) for r in (rows or [])]

    async def get_compressed(
        self, session_id: str, limit: int = 24
    ) -> List[CompressedMemory]:
        rows = await (self.select("compressed_memories")
                      .where({"session_id": str(session_id)})
                      .order_by("created_at", "DESC")
                      .limit(int(limit))
                      .query())
        out: List[CompressedMemory] = []
        for r in (rows or []):
            out.append(CompressedMemory(
                id=str(r["id"]),
                session_id=str(r["session_id"]),
                original_ids=list(_loads(r["original_ids"], [])),
                compressed_content=str(r["compressed_content"]),
                summary=str(r["summary"]),
                created_at=float(r["created_at"]),
                time_range=TimeRange(
                    start=datetime.fromtimestamp(float(r["range_start"])),
                    end=datetime.fromtimestamp(float(r["range_end"])),
                ),
                metadata=dict(_loads(r["metadata"], {})),
            ))
        return out

    # ---------- 更新 ----------

    async def reinforce(self, memory_ids: Sequence[int], boost: float) -> None:
        if not memory_ids:
            return
        now = float(datetime.now().timestamp())
        await self.update("memories").set({
            "importance": f"importance + {float(boost)}",
            "access_count": "access_count + 1",
            "last_access_time": now,
        }).where_in("id", [int(i) for i in memory_ids]).execute()

    async def decay_importance(
        self,
        decay_rate: float,
        min_importance: float = 0.0,
        memory_ids: Optional[Sequence[int]] = None,
    ) -> None:
        updater = self.update("memories").set({
            "importance": f"MAX({float(min_importance)}, importance * {float(decay_rate)})",
        })
        if memory_ids:
            updater = updater.where_in("id", [int(i) for i in memory_ids])
        await updater.execute()

    async def count_rows(self, session_id: str = "") -> int:
        selector = self.select("memories").set_fields(["COUNT(1) AS c"])
        if session_id:
            selector = selector.where({"session_id": str(session_id)})
        rows = await selector.query()
        return int(rows[0]["c"]) if rows else 0

    async def lowest_ranked(
        self, n: int, session_id: str = ""
    ) -> List[int]:
        """容量裁剪候选。**只返回 memory_id**（向量侧按 id 删即可）。"""
        if n <= 0:
            return []
        params: List[Any] = []
        where = ""
        if session_id:
            where = "WHERE session_id = ?"
            params.append(str(session_id))
        params.append(int(n))
        rows = await self._execute(
            f"SELECT id FROM memories {where} "
            "ORDER BY importance ASC, last_access_time ASC LIMIT ?",
            tuple(params),
        )
        return [int(r["id"]) for r in (rows or [])]

    # ---------- 删除 ----------

    async def delete_memories(self, memory_ids: Sequence[int]) -> int:
        """容量裁剪删除。**不写墓碑**（隐私删除才写，见下）。

        返回删掉的行数，供调用方同步清理 Milvus 向量。
        """
        ids = [int(i) for i in (memory_ids or [])]
        if not ids:
            return 0
        return int(await self.delete("memories").where_in("id", ids).execute())

    async def delete_memories_tombstoned(
        self,
        memory_ids: Sequence[int],
        *,
        session_id: str = "default",
        reason: str = "user",
        now: float = 0.0,
    ) -> int:
        """隐私删除：写墓碑 + 删行，**单事务原子**。

        顺序必须是"先读正文算摘要 → 写墓碑 → 删行"。行删掉之后
        就再也拿不到内容，墓碑只能退化成仅 id 的弱匹配，而弱匹配
        会误杀快照恢复后复用了同一 id 的新记忆（B1-05）。
        """
        ids = [int(i) for i in (memory_ids or [])]
        if not ids:
            return 0
        ts = float(now or datetime.now().timestamp())
        sid = str(session_id or "default")
        placeholders = ",".join("?" for _ in ids)

        def _work(conn):
            rows = conn.execute(
                f"SELECT id, session_id, content FROM memories "
                f"WHERE id IN ({placeholders})", tuple(ids)
            ).fetchall()
            digests = {
                int(r["id"]): (
                    str(r["session_id"] or sid),
                    integrity.content_digest(str(r["content"] or "")),
                )
                for r in rows
            }
            written = 0
            for mid in ids:
                owner, digest = digests.get(mid, (sid, ""))
                conn.execute(
                    "INSERT OR IGNORE INTO memory_tombstones("
                    "memory_id, session_id, digest, deleted_at, reason) "
                    "VALUES(?,?,?,?,?)",
                    (mid, owner, digest, ts, str(reason or "user")),
                )
                written += 1
            conn.execute(
                f"DELETE FROM memories WHERE id IN ({placeholders})", tuple(ids)
            )
            return written

        return int(await self.transaction(_work))

    async def active_tombstones(
        self, session_id: str = "", limit: int = 5000
    ) -> List[Dict[str, Any]]:
        selector = (self.select("memory_tombstones")
                    .set_fields(["memory_id", "session_id", "digest",
                                 "deleted_at", "reason"])
                    .limit(int(limit)))
        if session_id:
            selector = selector.where({"session_id": str(session_id)})
        return [dict(r) for r in (await selector.query() or [])]

    async def purge_tombstones(self, cutoff_ts: float) -> int:
        """清理早于 cutoff 的墓碑，返回**实际删除行数**。

        旧实现固定返回 0，调用方无法知道清理有没有生效。
        """
        return int(await self.delete("memory_tombstones").where_raw(
            "deleted_at < ?", float(cutoff_ts)
        ).execute())

    # ---------- embedding 指纹 ----------

    async def get_embedding_fingerprint(self) -> Optional[Dict[str, Any]]:
        rows = await self.select("embedding_meta").where({"id": 1}).query()
        return dict(rows[0]) if rows else None

    async def set_embedding_fingerprint(
        self, *, provider: str, model: str, dim: int, version: str = "1"
    ) -> str:
        fp = integrity.EmbeddingFingerprint(
            provider=str(provider or ""), model=str(model or ""),
            dim=int(dim or 0), version=str(version or "1"),
        )
        now = float(datetime.now().timestamp())

        def _work(conn):
            conn.execute("DELETE FROM embedding_meta WHERE id = 1")
            conn.execute(
                "INSERT INTO embedding_meta("
                "id, provider, model, dim, version, digest, updated_at) "
                "VALUES(1,?,?,?,?,?,?)",
                (fp.provider, fp.model, fp.dim, fp.version,
                 fp.digest(), now),
            )
            return fp.digest()

        return str(await self.transaction(_work))

    # ---------- 对齐诊断（B1-04，Milvus 版） ----------

    async def alignment_snapshot(
        self, *, session_id: str = "", limit: int = 200_000
    ) -> Dict[str, Any]:
        """取出做对齐诊断需要的 id 集合。

        只取 id，不取正文 —— 诊断报告进日志，不能带私人内容（§6）。
        Milvus 侧的 id 由调用方注入 `analyze_alignment(vector_ids=...)`,
        这里不再维护任何"本地 id 映射表"。
        """
        params: List[Any] = []
        where = ""
        if session_id:
            where = "WHERE session_id = ?"
            params.append(str(session_id))
        params.append(int(limit))
        rows = await self._execute(
            f"SELECT id FROM memories {where} LIMIT ?", tuple(params)
        )
        return {
            "memory_ids": [int(r["id"]) for r in (rows or [])],
            "session_id": str(session_id or ""),
        }

    async def compressed_rows(
        self, session_id: str = "", limit: int = 2000
    ) -> List[Dict[str, Any]]:
        selector = (self.select("compressed_memories")
                    .set_fields(["id", "session_id", "original_ids", "created_at"])
                    .limit(int(limit)))
        if session_id:
            selector = selector.where({"session_id": str(session_id)})
        return [dict(r) for r in (await selector.query() or [])]
