from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
from typing import Any, Callable
from numpy import ndarray,ndarray,float32,allclose,linalg,array

from .base import _MemoryStorageBase
from .models import CompressedMemory, Memory, MemoryStorgeData
from ...types.common import Role
from .. import utils

class MarkDownStorage(_MemoryStorageBase):
    def __init__(
        self,
        memory_dir: str,
        embed_fn: Callable[[str, int], ],
        max_size: int = 10000,
        embedding_dim: int = 384,
        decay_rate: float = 0.995,
        reinforce_boost: float = 0.08,
        short_term_days: int = 2,
    ) -> None:
        super().__init__()
        self._loaded = False
        self._closed = False
        self.max_size = max(100, int(max_size))
        self.embedding_dim = embedding_dim
        self.decay_rate = decay_rate
        self.reinforce_boost = reinforce_boost
        self.short_term_days = max(1, int(short_term_days))
        self.embed_fn = embed_fn
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self._lock = asyncio.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory-io")
        self.memories: list[MemoryStorgeData] = []
        self.compressed_memories: list[CompressedMemory] = []
        self.counter = 0
        self._file_positions: dict[str, int] = {}
        self._pool.submit(self.__load_from_markdown)

    def __session_file(self, session_id: str, suffix: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (session_id or "default"))
        return self.memory_dir / f"{safe}_{suffix}.md"

    def _detail_file(self, session_id: str) -> Path:
        return self.__session_file(session_id, "detail_memory")

    def _compressed_file(self, session_id: str) -> Path:
        return self.__session_file(session_id, "compressed_memory")

    def _short_file(self, session_id: str) -> Path:
        return self.__session_file(session_id, "short_term_memory")

    def _long_file(self, session_id: str) -> Path:
        return self.__session_file(session_id, "long_term_memory")

    # def _track(self, future: Future) -> None:
    #     self._futures.append(future)

    def _embed_text(self, text: str) -> ndarray:
        vec = self.embed_fn(text, self.embedding_dim)
        if vec.dtype != float32:
            vec = vec.astype(float32)
        return vec
    
    async def start(self) -> None:
        if not self._loaded:
            await self.__load_from_markdown()
            self._loaded = True

    async def __load_from_markdown(self) -> None:
        detail_files = list(self.memory_dir.glob("*_detail_memory.md"))
        compressed_files = list(self.memory_dir.glob("*_compressed_memory.md"))
        # 在线程池中并行读取所有文件
        loop = asyncio.get_event_loop()
        async def read_file(path: Path) -> tuple[str, str, list[str]]:
            """读取单个文件"""
            content = await loop.run_in_executor(
                self._pool,
                lambda: path.read_text(encoding="utf-8")
            )
            suffix = "_detail_memory.md" if "_detail_memory.md" in path.name else "_compressed_memory.md"
            session_id = path.name.replace(suffix, "")
            return session_id, suffix, content.splitlines()
        # 并行读取所有文件
        tasks = [read_file(f) for f in detail_files + compressed_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        temp_memories = []
        temp_compressed = []
        counter = self.counter
        # 处理结果
        for result in results:
            if isinstance(result, BaseException):
                continue
            session_id, suffix, lines = result
            if "_detail_memory.md" in suffix:
                for line in lines:
                    if not line.startswith("- "):
                        continue
                    try:
                        row = json.loads(line[2:])
                        text = str(row.get("content", ""))
                        counter = max(counter, int(row.get("id", 0) or 0))
                        temp_memories.append(
                            MemoryStorgeData(
                                id=str(row.get("id", "")),
                                session_id=str(row.get("session_id", session_id)),
                                role=row.get("role", Role.USER),
                                source=str(row.get("source", "text")),
                                content=text,
                                importance=float(row.get("importance", 1.0)),
                                access_count=int(row.get("access_count", 0)),
                                last_access_time=float(row.get("last_access_time", utils.now())),
                                created_at=float(row.get("created_at", utils.now())),
                                updated_at=float(row.get("updated_at", utils.now())),
                                tokens=int(row.get("tokens", 0)),
                                vector=self._embed_text(text),
                                metadata=dict(row.get("metadata", {})),
                                _persisted=True,
                            )
                        )
                    except Exception:
                        continue
            else:
                for line in lines:
                    if not line.startswith("- "):
                        continue
                    try:
                        row = json.loads(line[2:])
                        temp_compressed.append(
                            CompressedMemory(
                                id=str(row.get("id", "")),
                                session_id=str(row.get("session_id", session_id)),
                                original_ids=list(row.get("original_ids", [])),
                                compressed_content=str(row.get("compressed_content", "")),
                                summary=str(row.get("summary", "")),
                                created_at=float(row.get("created_at", utils.now())),
                                time_range=row.get(
                                    "time_range",
                                    {"start": datetime.now(), "end": datetime.now()},
                                ),
                                metadata=dict(row.get("metadata", {})),
                            )
                        )
                    except Exception:
                        continue
        async with self._lock:
            self.counter = max(self.counter, counter)
            self.memories.extend(temp_memories)
            self.compressed_memories.extend(temp_compressed)

    async def __append_to_markdown(self, filepath: Path, new_lines: list[str]) -> None:
        """追加新行到 markdown 文件末尾"""
        if not new_lines:
            return
        loop = asyncio.get_event_loop()
        def _write():
            mode = "a" if filepath.exists() else "w"
            with open(filepath, mode, encoding="utf-8") as f:
                if mode == "w":
                    session_id = filepath.stem.replace("_detail_memory", "")
                    f.write(f"# Detailed Memory ({session_id})\n\n")
                for line in new_lines:
                    f.write(f"- {line}\n")
        await loop.run_in_executor(self._pool, _write)

    async def __persist_session_files(self, session_id: str) -> None:
        async with self._lock:
            new_details = [m for m in self.memories if m.session_id == session_id and not m._persisted]
            new_compressed = [m for m in self.compressed_memories if m.session_id == session_id and not m._persisted]
            
            for m in new_details + new_compressed:
                m._persisted = True
                
            if not new_details and not new_compressed:
                return
            self._file_positions[session_id] = self._file_positions.get(session_id, 0) + len(new_details)

        # 锁外层处理耗时 JSON 和文件 IO
        detail_lines = []
        for row in new_details:
            payload = asdict(row)
            payload.pop("vector", None)
            if isinstance(payload.get("role"), Role):
                payload["role"] = payload["role"].value
            detail_lines.append(json.dumps(payload, ensure_ascii=False))
        
        compressed_lines = [json.dumps(asdict(row), ensure_ascii=False, default=str) for row in new_compressed]
        # 追加写入
        write_tasks = []
        if detail_lines:
            write_tasks.append(self.__append_to_markdown(self._detail_file(session_id), detail_lines))
        if compressed_lines:
            write_tasks.append(self.__append_to_markdown(self._compressed_file(session_id), compressed_lines))
        await asyncio.gather(*write_tasks)
        await self.__rewrite_summary_files(session_id)

    async def __rewrite_summary_files(self, session_id: str) -> None:
        """重写压缩记忆摘要文件"""
        async with self._lock:
            compressed = [m for m in self.compressed_memories if m.session_id == session_id]
        boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
        short_rows: list[CompressedMemory] = []
        long_rows: list[CompressedMemory] = []
        for row in compressed:
            created_at=float(row.created_at)
            if created_at < boundary:
                long_rows.append(row)
            else:
                short_rows.append(row)
        long_rows.sort(key=lambda x: float(x.created_at), reverse=True)
        loop = asyncio.get_event_loop()
        
        async def _write_summary(filepath: Path, title: str, rows: list, max_items: int):
            content = f"# {title}\n\n"
            content += "\n".join(
                f"- {x.summary or x.compressed_content[:120]}" 
                for x in rows[:max_items]
            )
            content += "\n"
            await loop.run_in_executor(
                self._pool,
                lambda: filepath.write_text(content, encoding="utf-8")
            )
        await asyncio.gather(
            _write_summary(self._short_file(session_id), "Short-Term Compressed", short_rows, 24),
            _write_summary(self._long_file(session_id), "Long-Term Compressed", long_rows, 48),
        )

    # def __submit_persist(self, session_id: str) -> None:
    #     self._track(self._pool.submit(self.__persist_session_files, session_id))

    async def add_memory(self, memory: Memory, vector: ndarray, importance: float = 0.0) -> int:
        await self.start()
        async with self._lock:
            self.counter += 1
            mid = self.counter
            row = MemoryStorgeData(
                id=str(mid),
                session_id=memory.session_id or "default",
                role=memory.role,
                source=memory.source or "text",
                content=str(memory.content),
                importance=float(memory.importance or importance or 1.0),
                access_count=int(memory.access_count or 0),
                last_access_time=float(memory.last_access_time or utils.now()),
                created_at=float(memory.created_at or utils.now()),
                updated_at=float(memory.updated_at or utils.now()),
                tokens=int(memory.tokens or 0),
                vector=vector.astype(float32),
                metadata=dict(memory.metadata or {})
            )
            self.memories.append(row)
            if len(self.memories) > self.max_size:
                self.memories.sort(key=lambda x: (float(x.importance), float(x.last_access_time)))
                self.memories = self.memories[-self.max_size :]
        asyncio.create_task(self.__persist_session_files(row.session_id))
        return mid

    async def add_memories(self, memories: list[Memory]) -> list[int]:
        ids: list[int] = []
        for m in memories:
            mid = await self.add_memory(m, self._embed_text(str(m.content)), importance=float(m.importance or 1.0))
            ids.append(mid)
        return ids

    async def add_compressed_memory(self, memory: CompressedMemory) -> None:
        await self.start()
        async with self._lock:
            memory._persisted = True
            self.compressed_memories.append(memory)
        asyncio.create_task(self.__persist_session_files(memory.session_id or "default"))

    async def retrieve_memory(self, query_vector: ndarray, limit: int = 10, session_id: str = "default") -> list[dict[str, Any]]:
        await self.start()
        async with self._lock:
            rows = [m for m in self.memories if m.session_id == session_id]
        if not rows:
            return []
        loop = asyncio.get_event_loop()
        # 向量化计算
        def _compute_similarity():
            vectors = array([r.vector for r in rows if r.vector is not None], dtype=float32)
            valid_indices = [i for i, r in enumerate(rows) if r.vector is not None]
            
            if len(vectors) == 0:
                return []
            
            # 批量余弦相似度
            query = query_vector.astype(float32).reshape(1, -1)
            similarities = (vectors @ query.T).flatten()  # 假设向量已归一化
            if not allclose(linalg.norm(vectors, axis=1), 1.0):
                norms = linalg.norm(vectors, axis=1)
                similarities = similarities / (norms + 1e-8)
            
            now = datetime.now()
            scored = []
            for idx, sim in zip(valid_indices, similarities):
                row = rows[idx]
                score = utils.compute_memory_score(
                    simillarity=float(sim),
                    now=now,
                    last_access_time=datetime.fromtimestamp(float(row.last_access_time)),
                    importance=float(row.importance),
                )
                payload = asdict(row)
                payload.pop("vector", None)
                payload["score"] = score
                if isinstance(payload.get("role"), Role):
                    payload["role"] = payload["role"].value
                scored.append(payload)
            
            scored.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
            return scored[: max(1, int(limit))]
        return await loop.run_in_executor(self._pool, _compute_similarity)

    async def get_short_term(self, session_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        await self.start()
        boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
        async with self._lock:
            rows = [m for m in self.memories if m.session_id == session_id and float(m.created_at) >= boundary]
        rows.sort(key=lambda x: float(x.created_at), reverse=True)
        out = []
        for row in rows[: max(1, int(limit))]:
            payload = asdict(row)
            payload.pop("vector", None)
            if isinstance(payload.get("role"), Role):
                payload["role"] = payload["role"].value
            out.append(payload)
        out.reverse()
        return out

    async def get_long_term(self, session_id: str = "default", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        return await self.retrieve_memory(self._embed_text(query), limit=limit, session_id=session_id)

    async def get_detailed(self, session_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        await self.start()
        async with self._lock:
            rows = [m for m in self.memories if m.session_id == session_id]
        rows.sort(key=lambda x: float(x.created_at), reverse=True)
        out: list[dict[str, Any]] = []
        for row in rows[: max(1, int(limit))]:
            payload = asdict(row)
            payload.pop("vector", None)
            if isinstance(payload.get("role"), Role):
                payload["role"] = payload["role"].value
            out.append(payload)
        out.reverse()
        return out

    async def get_compressed(self, session_id: str = "default", short_first: bool = True, limit: int = 24) -> list[CompressedMemory]:
        await self.start()
        async with self._lock:
            rows = [m for m in self.compressed_memories if m.session_id == session_id]
        boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
        short: list[CompressedMemory] = []
        long_rows: list[CompressedMemory] = []
        for row in rows:
            created_at=float(row.created_at)
            if created_at < boundary:
                long_rows.append(row)
            else:
                short.append(row)
        short.sort(key=lambda x: float(x.created_at), reverse=True)
        long_rows.sort(key=lambda x: float(x.created_at), reverse=True)
        ordered = short + long_rows if short_first else long_rows + short
        return ordered[: max(1, int(limit))]

    async def decay_now(self):
        async def decay() -> None:
            await self.start()
            now = utils.now()
            cutoff = now - 24 * 3600  # 只处理24小时内的记录
            async with self._lock:
                updated_sessions = set()
                for row in self.memories:
                    if float(row.last_access_time) < cutoff:
                        continue
                    row.importance = max(0.0, float(row.importance) * self.decay_rate)
                    row.updated_at = utils.now()
                    updated_sessions.add(row.session_id)
            for session in updated_sessions:
                await self.__persist_session_files(session)
        asyncio.get_event_loop().run_in_executor(self._pool, decay)

    async def delete_memory(self, memory_id: str) -> None:
        async with self._lock:
            self.memories=[]
            for row in self.memories:
                if str(row.id) == str(memory_id):
                    continue
                self.memories.append(row)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        
        # 等待所有待处理的写入完成
        await asyncio.sleep(0.5)
        self._pool.shutdown(wait=True)
