from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
from typing import Any, Callable, Optional
from numpy import ndarray, float32, allclose, linalg, array

from .base import MemoryStorageBase
from .models import CompressedMemory, Memory, MemoryStorgeData
from ...utils.file import read_text
from ...logger import logger
from .. import utils
from ...models import Role


def _row_to_payload(row) -> dict:
    """C158：`dataclasses.asdict()` 只能用于 **dataclass** 实例。

    而 MemoryStorgeData / CompressedMemory 都是 **pydantic BaseModel**，
    asdict 会直接抛：
        TypeError: asdict() should be called on dataclass instances
    这一段在检索、短期/长期记忆读取、落盘四处都有，
    等于"只要读记忆就崩"。改用 model_dump()。
    """
    try:
        payload = row.model_dump()
    except Exception:
        payload = dict(row.__dict__)
    payload.pop("vector", None)
    role = payload.get("role")
    if isinstance(role, Role):
        payload["role"] = role.value
    elif role is not None and not isinstance(role, str):
        payload["role"] = str(role)
    return payload


async def _await_coro(coro):
    return await coro


class MarkDownStorage(MemoryStorageBase):
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

        # C149：不在这里创建 asyncio.Lock()。
        # 它会被绑定到"创建时的事件循环"，而记忆系统跨 Web loop /
        # 调度器 loop 使用时会抛 "attached to a different loop"。
        # 改为惰性创建（首次使用时绑定当前 loop）。
        self._lock: Optional[asyncio.Lock] = None
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory-io")
        self.memories: list[MemoryStorgeData] = []
        self.compressed_memories: list[CompressedMemory] = []
        self.counter = 0
        self._file_positions: dict[str, int] = {}
        # C148：原实现 `self._pool.submit(self.__load_from_markdown)`。
        # __load_from_markdown 是 **async def**，submit 只是创建了协程对象
        # 然后丢在线程池里"执行"——协程体**一行都不会跑**，
        # 于是磁盘上的历史记忆**永远加载不进来**，还会打
        # "coroutine was never awaited" 警告。
        # 真正的加载放在 start() 里（由调用方 await）。
        self._bg_tasks: set = set()

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

    def _get_lock(self) -> asyncio.Lock:
        """惰性创建锁（C149）。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _track_bg(self, coro) -> None:
        """C151：跟踪后台任务，避免 fire-and-forget 被 GC + 异常丢失。"""
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:
            return
        self._bg_tasks.add(task)
        task.add_done_callback(self._on_bg_done)

    def _on_bg_done(self, task) -> None:
        self._bg_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(f"[Memory/Markdown] 后台任务失败: {exc}")

    async def _embed_text_async(self, text: str) -> ndarray:
        """C150：embed_fn 是 **async**（见 managers.MemoryBackendManager）。

        原实现是同步方法 `def _embed_text`，里面：
            vec = self.embed_fn(text, dim)     # 得到 coroutine
            if vec.dtype != float32: ...       # AttributeError!
        协程对象没有 .dtype —— 记忆写入/检索的第一步就直接崩。
        """
        vec = self.embed_fn(text, self.embedding_dim)
        if asyncio.iscoroutine(vec) or isinstance(vec, asyncio.Future):
            vec = await vec
        vec = array(vec, dtype=float32)
        return vec

    def _embed_text_sync(self, text: str) -> ndarray:
        """供线程池内同步调用（加载历史记录时使用）。"""
        import numpy as np

        fn = self.embed_fn
        try:
            vec = fn(text, self.embedding_dim)
        except TypeError:
            vec = fn(text) # type: ignore
        if asyncio.iscoroutine(vec) or isinstance(vec, asyncio.Future):
            # 在没有 loop 的线程里，建一个独立 loop 跑完
            loop = asyncio.new_event_loop()
            try:
                vec = loop.run_until_complete(vec)
            finally:
                loop.close()
        return np.asarray(vec, dtype=np.float32)
    
    async def start(self) -> None:
        if not self._loaded:
            await self.__load_from_markdown()
            self._loaded = True

    async def __load_from_markdown(self) -> None:
        detail_files = list(self.memory_dir.glob("*_detail_memory.md"))
        compressed_files = list(self.memory_dir.glob("*_compressed_memory.md"))
        # 在线程池中并行读取所有文件
        loop = asyncio.get_running_loop()
        async def read_file(path: Path) -> tuple[str, str, list[str]]:
            """读取单个文件"""
            content = await loop.run_in_executor(
                self._pool,
                lambda: read_text(path, encoding="utf-8")
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
        # C174：向量不能在这里同步计算 ——
        # _embed_text_sync 在无 loop 的线程里会用 asyncio.run()，
        # 而 __load_from_markdown 本身就在事件循环里跑，
        # asyncio.run() 会抛 "cannot be called from a running event loop"，
        # 于是**整批历史记忆加载失败**（silent except 吞掉）。
        # 先只解析文本，最后统一批量 await 嵌入。
        pending: list[tuple[dict, str]] = []
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
                        pending.append((row, text))
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
        # C174：批量嵌入（并发，避免逐条 await 拖慢启动）
        if pending:
            try:
                vectors = await asyncio.gather(
                    *(self._embed_text_async(text) for _, text in pending),
                    return_exceptions=True,
                )
            except Exception:
                vectors = [None] * len(pending)
            for (row, text), vec in zip(pending, vectors):
                session_id = str(row.get("session_id", "default"))
                if isinstance(vec, BaseException) or vec is None:
                    logger.debug(f"[Memory/Markdown] 历史记录嵌入失败，跳过: {row.get('id')}")
                    continue
                temp_memories.append(
                    MemoryStorgeData(
                        id=str(row.get("id", "")),
                        session_id=session_id,
                        role=row.get("role", Role.USER),
                        source=str(row.get("source", "text")),
                        content=text,
                        importance=float(row.get("importance", 1.0)),
                        access_count=int(row.get("access_count", 0)),
                        last_access_time=float(row.get("last_access_time", utils.now())),
                        created_at=float(row.get("created_at", utils.now())),
                        updated_at=float(row.get("updated_at", utils.now())),
                        tokens=int(row.get("tokens", 0)),
                        vector=vec,
                        metadata=dict(row.get("metadata", {})),
                    )
                )
            # 已存在文件中的记录视为已持久化
            for m in temp_memories:
                m._persisted = True

        async with self._get_lock():
            self.counter = max(self.counter, counter)
            self.memories.extend(temp_memories)
            self.compressed_memories.extend(temp_compressed)

    async def __append_to_markdown(self, filepath: Path, new_lines: list[str]) -> None:
        """追加新行到 markdown 文件末尾"""
        if not new_lines:
            return
        loop = asyncio.get_running_loop()
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
        async with self._get_lock():
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
            payload = _row_to_payload(row)
            detail_lines.append(json.dumps(payload, ensure_ascii=False, default=str))
        
        compressed_lines = [json.dumps(_row_to_payload(row), ensure_ascii=False, default=str) for row in new_compressed]
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
        async with self._get_lock():
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
        loop = asyncio.get_running_loop()
        
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
        async with self._get_lock():
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
        self._track_bg(self.__persist_session_files(row.session_id))
        return mid

    async def add_memories(self, memories: list[Memory]) -> list[int]:
        ids: list[int] = []
        for m in memories:
            mid = await self.add_memory(m, await self._embed_text_async(str(m.content)), importance=float(m.importance or 1.0))
            ids.append(mid)
        return ids

    async def add_compressed_memory(self, memory: CompressedMemory) -> None:
        """C159：原实现在这里先 `memory._persisted = True` 再 append，
        而 __persist_session_files 筛选的是 `not m._persisted` ——
        刚被标记过的记录**永远不会被写进 markdown 文件**。
        压缩记忆（对话摘要）全部丢失，重启即没。
        """
        await self.start()
        async with self._get_lock():
            self.compressed_memories.append(memory)
        self._track_bg(self.__persist_session_files(memory.session_id or "default"))

    async def retrieve_memory(self, query_vector: ndarray, limit: int = 10, session_id: str = "default") -> list[dict[str, Any]]:
        await self.start()
        async with self._get_lock():
            rows = [m for m in self.memories if m.session_id == session_id]
        if not rows:
            return []
        loop = asyncio.get_running_loop()
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
                payload = _row_to_payload(row)
                payload["score"] = score
                scored.append(payload)
            
            scored.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
            return scored[: max(1, int(limit))]
        return await loop.run_in_executor(self._pool, _compute_similarity)

    async def get_short_term(self, session_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        await self.start()
        boundary = datetime.now().timestamp() - timedelta(days=self.short_term_days).total_seconds()
        async with self._get_lock():
            rows = [m for m in self.memories if m.session_id == session_id and float(m.created_at) >= boundary]
        rows.sort(key=lambda x: float(x.created_at), reverse=True)
        out = []
        for row in rows[: max(1, int(limit))]:
            out.append(_row_to_payload(row))
        out.reverse()
        return out

    async def get_long_term(self, session_id: str = "default", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        return await self.retrieve_memory(await self._embed_text_async(query), limit=limit, session_id=session_id)

    async def get_detailed(self, session_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        await self.start()
        async with self._get_lock():
            rows = [m for m in self.memories if m.session_id == session_id]
        rows.sort(key=lambda x: float(x.created_at), reverse=True)
        out: list[dict[str, Any]] = []
        for row in rows[: max(1, int(limit))]:
            out.append(_row_to_payload(row))
        out.reverse()
        return out

    async def get_compressed(self, session_id: str = "default", short_first: bool = True, limit: int = 24) -> list[CompressedMemory]:
        await self.start()
        async with self._get_lock():
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

    async def decay_now(self) -> None:
        """C153：原实现 `run_in_executor(self._pool, decay)`，
        decay 是 **async 函数**，丢进线程池只会得到一个从未被 await 的
        协程对象 —— 衰减一次都没执行过，而且返回的 Future 也没人 await。
        这里直接 await（记得 start() 已确保加载完成）。
        """
        await self.start()
        now = utils.now()
        cutoff = now - 24 * 3600  # 只处理24小时内的记录
        async with self._get_lock():
            updated_sessions = set()
            for row in self.memories:
                if float(row.last_access_time) < cutoff:
                    continue
                row.importance = max(0.0, float(row.importance) * self.decay_rate)
                row.updated_at = utils.now()
                updated_sessions.add(row.session_id)
        for session in updated_sessions:
            await self.__persist_session_files(session)

    async def delete_memory(self, memory_id: str) -> None:
        """C154：原实现先把 self.memories 清空，再遍历**已经空了的**列表重建，
        结果就是"删除一条 -> 全部记忆被清空"。
        """
        async with self._get_lock():
            self.memories = [
                row for row in self.memories if str(row.id) != str(memory_id)
            ]

    async def close(self) -> None:
        """C155：原实现用 `await asyncio.sleep(0.5)` "等"后台写入，
        这只是碰运气——写盘慢一点就丢数据。改为显式等待已跟踪的任务。
        """
        if self._closed:
            return
        self._closed = True

        if self._bg_tasks:
            try:
                await asyncio.wait(list(self._bg_tasks), timeout=5.0)
            except Exception as exc:
                logger.warning(f"[Memory/Markdown] 等待写盘超时: {exc}")
        self._pool.shutdown(wait=True)
