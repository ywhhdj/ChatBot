from __future__ import annotations
from datetime import datetime
import json
import os
import pickle
from typing import Any, Iterable, Sequence
import faiss
from numpy import ndarray,float32,array,int64,arange,empty
import orjson

from ....database.sqlite import AsyncSqlite
from .models import CompressedMemory, Memory,TimeRange
from ...runtime import RuntimePath

class SQLiteMemory(AsyncSqlite):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    async def _init_db(self) -> None:
        if self.__is_init:
            return
        sql_path = RuntimePath.get_sql_file_path()
        await self.execute_sql_file(sql_path)
        self.__is_init = True

    async def add_memories(self, rows: list[Memory]) -> list[int]:
        if not rows:
            return []
        inserter = self.insert("memories").set_fields([
            "session_id",
            "role",
            "source",
            "content",
            "importance",
            "access_count",
            "last_access_time",
            "created_at",
            "updated_at",
            "tokens",
            "metadata"
        ])
        for r in rows:
            metadata_str = orjson.dumps(r.metadata or {}).decode("utf-8")
            inserter.add_batch((
                str(r.session_id or "default"),
                str(r.role),
                str(r.source or "text"),
                str(r.content or ""),
                float(r.importance or 1.0),
                int(r.access_count or 0),
                float(r.last_access_time or r.created_at),
                float(r.created_at),
                float(r.updated_at or r.created_at),
                int(r.tokens or 0),
                metadata_str,
            ))
        await inserter.save_batch()
        lastrowid = await self.get_lastrowid()
        start = lastrowid - len(rows) + 1 if lastrowid else 1
        return list(range(int(start), int(start) + len(rows)))

    async def add_compressed_memory(self, row: CompressedMemory) -> None:
        start = row.time_range.get("start")
        end = row.time_range.get("end")
        start_ts = start.timestamp()
        end_ts = end.timestamp()
        await self.insert("compressed_memories").set_fields([
            "id",
            "session_id",
            "original_ids",
            "compressed_content",
            "summary",
            "created_at",
            "range_start",
            "range_end",
            "metadata"
        ]).add((
            row.id,
            row.session_id or "default",
            json.dumps(list(row.original_ids), ensure_ascii=False),
            str(row.compressed_content),
            str(row.summary or ""),
            float(row.created_at),
            float(start_ts),
            float(end_ts),
            json.dumps(row.metadata or {}, ensure_ascii=False)
        )).save()

    async def get_compressed(self, session_id: str, limit: int = 24) -> list[CompressedMemory]:
        query_rows=await self.select("compressed_memories").set_fields([
            "id",
            "session_id",
            "original_ids",
            "compressed_content",
            "summary",
            "created_at",
            "range_start",
            "range_end",
            "metadata"
        ]).where({
            "session_id": session_id
        }).order_by("created_at", "DESC").limit(int(limit)).query()
        rows: list[CompressedMemory] = []
        if query_rows:
            for r in query_rows:
                rows.append(
                    CompressedMemory(
                        id=str(r["id"]),
                        session_id=str(r["session_id"]),
                        original_ids=list(json.loads(r["original_ids"] or "[]")),
                        compressed_content=str(r["compressed_content"]),
                        summary=str(r["summary"]),
                        created_at=float(r["created_at"]),
                        time_range=TimeRange(
                            start=datetime.fromtimestamp(float(r["range_start"])),
                            end=datetime.fromtimestamp(float(r["range_end"])),
                        ),
                        metadata=dict(json.loads(r["metadata"] or "{}")),
                    )
                )
        return rows

    async def map_faiss_ids(self, pairs: Iterable[tuple[int, int]]) -> None:
        await self.insert("faiss_id_map").set_fields([
            "faiss_id",
            "memory_id"
        ]).add_batch([(int(fid), int(mid)) for fid, mid in pairs]).save_batch()

    async def get_memory_ids_by_faiss(self, faiss_ids: Sequence[int]) -> dict[int, int]:
        if not faiss_ids:
            return {}
        placeholders = ",".join("?" for _ in faiss_ids)
        query =await self.select("faiss_id_map").set_fields([
            "faiss_id",
            "memory_id"
        ]).where_in("faiss_id", faiss_ids).query() # type: ignore
        if not query:
            return {}
        return {int(r["faiss_id"]): int(r["memory_id"]) for r in query}

    async def get_records(self, memory_ids: Sequence[int]) -> list[dict[str, Any]]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" for _ in memory_ids)
        query =await self.select("memory").where_in("id", memory_ids).query() # type: ignore
        out = []
        if query:
            for r in query:
                row = dict(r)
                row["metadata"] = json.loads(row.get("metadata") or "{}")
                out.append(row)
        return out

    async def get_recent(self, session_id: str, limit: int) -> list[dict[str, Any]]:
        query = await self.select("memory").set_fields([
            "id",
            "session_id",
            "role",
            "source",
            "content",
            "importance",
            "access_count",
            "last_access_time",
            "created_at",
            "updated_at",
            "tokens",
            "metadata"
        ]).where({
            "session_id": session_id
        }).order_by("created_at", "DESC").limit(int(limit)).query() # type: ignore
        out = []
        if query:
            for r in query:
                row = dict(r)
                row["metadata"] = json.loads(row.get("metadata") or "{}")
                out.append(row)
        return out

    async def reinforce(self, memory_ids: Sequence[int], boost: float) -> None:
        if not memory_ids:
            return
        await self.update("memories").set({
            "boost": f"boost + {float(boost)}",
            "access_count": f"access_count + 1",
        }).where_in("id", memory_ids).save() # type: ignore

    async def decay_importance(self, memory_ids: Sequence[int], decay_rate: float, min_importance: float = 0.0) -> None:
        await self.update("memories").set({
            "importance": f"MAX({float(min_importance)}, importance * {float(decay_rate)})",
        }).where_in("id", memory_ids).save() # type: ignore

    async def count_rows(self) -> int:
        query = await self.select("memories").set_fields([
            "COUNT(1) AS c"
        ]).query()
        if not query:
            return 0
        return int(query[0]["c"]) if query else 0

    async def lowest_ranked(self, n: int) -> list[dict[str, int]]:
        if n <= 0:
            return []
        query = await self.select("memories").set_fields([
            "id",
            "importance",
            "last_access_time"
        ]).order_by("importance", "ASC").order_by("last_access_time", "ASC").limit(int(n)).query() # type: ignore
        if not query:
            return []
        return [{
            "memory_id": int(r["memory_id"]), 
            "faiss_id": int(r["faiss_id"])
        } for r in query]

    async def delete_memories(self, memory_ids: Sequence[int]) -> None:
        if not memory_ids:
            return
        await self.delete("memories").where_in("id", memory_ids).delete_batch() # type: ignore

    async def max_faiss_id(self) -> int:
        query = await (self.select("faiss_id_map")
                    .set_fields(["COALESCE(MAX(faiss_id), -1) AS m"])
                    .query())
        if query and len(query) > 0:
            return int(query[0]["m"])
        return -1

    async def get_faiss_ids_by_memory(self, memory_ids: Sequence[int]) -> list[int]:
        if not memory_ids:
            return []
        query = await self.select("faiss_id_map").set_fields([
            "faiss_id"
        ]).where_in("memory_id", memory_ids).query() # type: ignore
        if not query:
            return []
        return [int(r["faiss_id"]) for r in query]


class FAISSMemory:
    def __init__(self, dim: int, index_path: str, max_top_k: int = 100) -> None:
        self.dim = dim
        self.index_path = index_path
        self.map_path = f"{index_path}.id_map"
        os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
            if not isinstance(self.index, faiss.IndexIDMap2):
                self.index = faiss.IndexIDMap2(self.index)
        else:
            base = faiss.IndexFlatIP(dim)
            self.index = faiss.IndexIDMap2(base)
        self._next_faiss_id = 0
        self._distance_buffer = empty((1, max_top_k), dtype=float32)
        self._index_buffer = empty((1, max_top_k), dtype=int64)

    @property
    def next_faiss_id(self) -> int:
        return self._next_faiss_id

    def set_next_faiss_id(self, value: int) -> None:
        self._next_faiss_id = max(0, int(value))

    def add_vectors(self, vectors: ndarray) -> list[int]:
        if vectors.size == 0:
            return []
        if vectors.dtype != float32:
            vectors = vectors.astype(float32)
        faiss.normalize_L2(vectors)
        n = vectors.shape[0]
        ids = arange(self._next_faiss_id, self._next_faiss_id + n, dtype=int64)
        self.index.add_with_ids(vectors, ids)
        self._next_faiss_id += n
        return [int(x) for x in ids.tolist()]

    def search(self, query: ndarray, top_k: int) -> list[tuple[int, float]]:
        if self.index.ntotal == 0:
            return []
        if query.dtype != float32:
            query = query.astype(float32)
        query = query.reshape(1, -1)
        faiss.normalize_L2(query)
        if top_k > self._distance_buffer.shape[1]:
            self._distance_buffer = empty((1, int(top_k)), dtype=float32)
            self._index_buffer = empty((1, int(top_k)), dtype=int64)
        
        # 预分配输出数组
        scores = empty((1, int(top_k)), dtype=float32)
        ids = empty((1, int(top_k)), dtype=int64)
        self.index.search(query, int(top_k), scores, ids)  # 注意第一个参数是 n=1
        
        out: list[tuple[int, float]] = []
        for idx, score in zip(ids[0].tolist(), scores[0].tolist()):
            if idx < 0:
                continue
            out.append((int(idx), float(score)))
        return out

    def remove_ids(self, faiss_ids: Sequence[int]) -> None:
        if not faiss_ids:
            return
        self.index.remove_ids(array([int(x) for x in faiss_ids], dtype=int64))  # type: ignore

    def save(self) -> None:
        faiss.write_index(self.index, self.index_path)
        with open(self.map_path, "wb") as f:
            pickle.dump({"next_faiss_id": self._next_faiss_id}, f)

    def load_meta(self) -> None:
        if not os.path.exists(self.map_path):
            return
        with open(self.map_path, "rb") as f:
            data = pickle.load(f)
        self._next_faiss_id = int(data.get("next_faiss_id", self._next_faiss_id))
