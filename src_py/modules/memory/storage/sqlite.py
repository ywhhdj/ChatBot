from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import CoroutineType
from typing import Any, Callable, Optional
import numpy as np

from .base import _MemoryStorageBase
from .models import CompressedMemory, Memory
from .. import utils
from .database import FAISSMemory, SQLiteMemory

class _MemoryTask:
    def __init__(self, fn: Callable[[], Any], future: asyncio.Future) -> None:
        self.fn = fn
        self.future = future

class SQLiteFAISSStorage(_MemoryStorageBase):
    def __init__(
        self,
        embed_fn: Callable[[str, int], CoroutineType[Any,Any,np.ndarray]],
        thread_name: str = "MemoryWorker",
        db_path: str = "memory/memory.db",
        index_path: str = "memory/memory.faiss",
        embedding_dim: int = 384,
        max_records: int = 10000,
        decay_rate: float = 0.995,
        decay_interval_sec: int = 3600,
        reinforce_boost: float = 0.08,
        short_term_days: int = 2
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.index_path = index_path
        self.embedding_dim = embedding_dim
        self.max_records = max_records
        self.decay_rate = decay_rate
        self.decay_interval_sec = max(60, decay_interval_sec)
        self.reinforce_boost = reinforce_boost
        self.short_term_days = max(1, int(short_term_days))
        self.embed_fn = embed_fn

        self._sqlite: SQLiteMemory | None = None
        self._faiss: FAISSMemory | None = None
        self._task_queue: asyncio.Queue[_MemoryTask] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._last_decay_time: float = 0.0

    async def _embed_text(self, text: str) -> np.ndarray:
        vec = await self.embed_fn(text, self.embedding_dim)
        if vec.dtype != np.float32:
            vec = vec.astype(np.float32)
        return vec

    async def __initialize(self) -> None:
        if self._sqlite is None:
            self._sqlite = SQLiteMemory(self.db_path)
            await self._sqlite.connect()
            await self._sqlite._init_db()
        
        if self._faiss is None:
            self._faiss = FAISSMemory(self.embedding_dim, self.index_path)
            self._faiss.load_meta()
            max_faiss_id = await self._sqlite.max_faiss_id()
            self._faiss.set_next_faiss_id(max(self._faiss.next_faiss_id, max_faiss_id + 1))

    async def __worker_loop(self) -> None:
        await self.__initialize()
        last_decay = datetime.now()
        while not self._running or not self._task_queue.empty():
            try:
                    # 等待任务，超时后检查是否需要衰减
                get_task = asyncio.create_task(self._task_queue.get())
                time_until_decay = max(0.1, self.decay_interval_sec - (datetime.now() - last_decay).total_seconds())
                wait_decay = asyncio.create_task(asyncio.sleep(time_until_decay))
                
                done, pending = await asyncio.wait(
                    [get_task, wait_decay],
                    return_when=asyncio.FIRST_COMPLETED
                )

                if get_task in done:
                    task = get_task.result()
                    try:
                        # [修复] 异常吞没：确保正确处理 Lambda 返回的协程并捕获异常
                        res = task.fn()
                        result = await res if asyncio.iscoroutine(res) else res
                        
                        if task.future is not None and not task.future.done():
                            task.future.set_result(result)
                    except Exception as e:
                        import logging
                        logging.error(f"Worker task failed: {e}", exc_info=True)
                        if task.future is not None and not task.future.done():
                            task.future.set_exception(e)
                else:
                    get_task.cancel()
                now = datetime.now()
                if (now - last_decay).total_seconds() >= self.decay_interval_sec and self._sqlite is not None:
                    try:
                        asyncio.create_task(self._sqlite.decay_importance(self.decay_rate))
                        asyncio.create_task(self.__prune_if_needed())
                    except Exception:
                        pass
                    last_decay = now
            except asyncio.CancelledError:
                break

        if self._faiss is not None:
            self._faiss.save()
        if self._sqlite is not None:
            self._sqlite.__del__()

    async def _run_on_worker(self, fn: Callable[[], Any]) -> Any:
        future= asyncio.get_event_loop().create_future()
        await self._task_queue.put(_MemoryTask(fn=fn, future=future))
        return await future

    async def start(self) -> None:
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self.__worker_loop())

    async def close(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        # 保存FAISS索引
        if self._faiss:
            self._faiss.save()
        
        # 关闭数据库
        if self._sqlite:
            await self._sqlite.close()

    async def __prune_if_needed(self) -> None:
        """如果需要，删除最低排名的记录"""
        if not self._sqlite or not self._faiss:
            return
        total = await self._sqlite.count_rows()
        overflow = total - self.max_records
        if overflow <= 0:
            return
        targets = await self._sqlite.lowest_ranked(overflow)
        if not targets:
            return
        memory_ids = [x["memory_id"] for x in targets]
        faiss_ids = [x["faiss_id"] for x in targets]
        self._faiss.remove_ids(faiss_ids)
        await self._sqlite.delete_memories(memory_ids)

    async def add_memory(self, memory: Memory, vector: np.ndarray, importance: float = 0.0) -> list[int]:
        memory.importance = importance
        return await self.add_memories([memory])
    
    async def __add_memories_write(self, memories: list[Memory]) -> list[int]:
        vectors: list[np.ndarray] = [await self._embed_text(str(m.content).strip()) for m in memories]
        vec_array = np.vstack(vectors).astype(np.float32)
        assert self._sqlite is not None and self._faiss is not None
        ids = await self._sqlite.add_memories(memories)
        faiss_ids = self._faiss.add_vectors(vec_array)
        #交给后台线程处理，不阻塞主线程
        asyncio.create_task(self._sqlite.map_faiss_ids(zip(faiss_ids, ids)))
        asyncio.create_task(self.__prune_if_needed())
        return ids

    async def add_memories(self, memories: list[Memory]) -> list[int]:
        if not memories:
            return []
        return await self._run_on_worker(lambda: self.__add_memories_write(memories))

    async def add_compressed_memory(self, memory: CompressedMemory) -> None:
        async def _write() -> None:
            assert self._sqlite is not None
            await self._sqlite.add_compressed_memory(memory)
        await self._run_on_worker(_write)

    async def get_compressed(self, session_id: str = "default", short_first: bool = True, limit: int = 24) -> list[CompressedMemory]:
        async def _query() -> list[CompressedMemory]:
            assert self._sqlite is not None
            rows = await self._sqlite.get_compressed(session_id=session_id, limit=limit*4)
            boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
            short,long_rows=[],[]
            for row in rows:
                if float(row.created_at) >= boundary:
                    long_rows.append(row)
                else:
                    short.append(row)
            ordered = short + long_rows if short_first else long_rows + short
            return ordered[: max(1, int(limit))]
        return await self._run_on_worker(_query)

    async def get_detailed(self, session_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
        async def _query() -> list[dict[str, Any]]:
            assert self._sqlite is not None
            rows = await self._sqlite.get_recent(session_id, limit=max(1, int(limit)))
            rows.reverse()
            return rows
        return await self._run_on_worker(_query)

    async def retrieve_memory(self, query_vector: np.ndarray, limit: int = 10, session_id: str = "default") -> list[dict[str, Any]]:
        top_k = max(limit * 4, limit)

        async def _search() -> list[dict[str, Any]]:
            assert self._sqlite is not None and self._faiss is not None
            pairs = self._faiss.search(query_vector.astype(np.float32), top_k=top_k)
            if not pairs:
                return []
            # 批量获取所有ID
            faiss_ids = [x[0] for x in pairs]
            score_map = {fid: score for fid, score in pairs}

            id_map = await self._sqlite.get_memory_ids_by_faiss(faiss_ids)
            ordered_memory_ids = [id_map[fid] for fid in faiss_ids if fid in id_map]
            records = await self._sqlite.get_records(ordered_memory_ids)
            record_map = {int(r["id"]): r for r in records}

            now = datetime.now()
            results: list[dict[str, Any]] = []
            for faiss_id in faiss_ids:
                memory_id = id_map.get(faiss_id)
                if memory_id is None:
                    continue
                row = record_map.get(memory_id)
                if not row or row.get("session_id") != session_id:
                    continue
                score = utils.compute_memory_score(
                    simillarity=float(score_map.get(faiss_id, 0.0)),
                    now=now,
                    last_access_time=datetime.fromtimestamp(float(row["last_access_time"])),
                    importance=float(row["importance"]),
                    decay_rate=0.001,
                )
                row = dict(row)
                row["score"] = score
                results.append(row)

            results.sort(key=lambda x: float(x["score"]), reverse=True)
            top = results[:limit]
            if top:
                await self._sqlite.reinforce([int(x["id"]) for x in top], self.reinforce_boost)
            return top

        return await self._run_on_worker(_search)

    async def get_short_term(self, session_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        async def _query() -> list[dict[str, Any]]:
            assert self._sqlite is not None
            boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
            rows = await self._sqlite.get_recent(session_id, max(limit * 4, limit))
            rows = [x for x in rows if float(x.get("created_at", 0.0)) >= boundary]
            rows = rows[: max(1, int(limit))]
            rows.reverse()
            return rows
        return await self._run_on_worker(_query)

    async def get_long_term(self, session_id: str = "default", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        vec = await self._embed_text(query)
        vec = vec.astype(np.float32)
        return await self.retrieve_memory(query_vector=vec, limit=limit, session_id=session_id)

    async def decay_now(self) -> None:
        async def _decay() -> None:
            assert self._sqlite is not None
            await self._sqlite.decay_importance(self.decay_rate)
            await self.__prune_if_needed()
        await self._run_on_worker(_decay)
    
    async def __delete_memory(self, memory_id: list[int]) -> None:
        assert self._sqlite is not None and self._faiss is not None
        faiss_ids = await self._sqlite.get_faiss_ids_by_memory(memory_id)
        if faiss_ids:
            self._faiss.remove_ids(faiss_ids)
        await self._sqlite.delete_memories(memory_id)

    async def delete_memory(self, memory_id: str):
        target = int(memory_id)
        await self._run_on_worker(lambda: self.__delete_memory([target]))
