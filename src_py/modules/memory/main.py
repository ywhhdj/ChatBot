from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Optional, TypedDict, Union

from ..events import on_event_class, types
from ..types.memory.context import MemoryContext, Message
from .storage.models import CompressedMemory, Memory
from ..types.common import Role
from . import utils
from .compression import ContextCompressor
from .managers import EmbeddingManager, MemoryBackendManager
from .token import TokenCalculator


class SystemInfo(TypedDict):
    compressed_count: int

@on_event_class([
    (types.AppEventType.ManagerEventType.MEMORY_STOP,"shutdown"),
])
class HybridMemorySystem:
    _instance = None
    _lock = Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        compress_min_size: int = 5, # 压缩最小消息数
        embedding_adapter= None,
        user_is_database: bool = False,
        db_path: str = "memory/memory.db",
        index_path: str = "memory/memory.faiss",
        max_records: int = 10000,
        short_term_days: int = 2,
        compress_every_n_messages: int = 5, # 每n条消息压缩一次
        compress_batch_size: int = 50
    ) -> None:
        """
        HybridMemorySystem is a memory system that combines long-term memory storage with short-term memory storage.
        It uses a hybrid approach where short-term memory is stored in memory and long-term memory is stored in a database.
        This allows for efficient storage of short-term memory while preserving long-term memory.
        Parameters:
            llm_client:LLM客户端,用于压缩上下文
            compress_min_size:压缩上下文最小消息数
            embedding_adapter:嵌入适配器
            user_is_database:用户是否为数据库用户
            db_path:数据库路径
            index_path:索引路径
            embedding_dim:嵌入维度
            max_records:最大记录数
            short_term_days:短时间记忆天数
            compress_every_n_messages:每n条消息压缩一次
            compress_batch_size:压缩批次大小
        """

        if self._initialized:
            return
        self._instance = self
        from .config import MemoryConfig
        self.config=MemoryConfig(
            compress_min_size=min(30, int(compress_min_size)),
            user_is_database=user_is_database,
            db_path=db_path,
            index_path=index_path,
            max_records=max(100, int(max_records)),
            short_term_days=max(1, int(short_term_days)),
            compress_every_n_messages= min(300, int(compress_every_n_messages)),
            compress_batch_size=max(200, int(compress_batch_size)),
        )
        self.embedding_manager = EmbeddingManager(dim=384)
        self.backend_manager = MemoryBackendManager(
            user_is_database=user_is_database,
            db_path=db_path,
            index_path=index_path,
            embedding_dim=384,
            max_records=max_records,
            embedding_manager=self.embedding_manager,
        )
        self.storage = self.backend_manager.storage
        self.compression_manager = ContextCompressor(llm_client)
        self.token_calculator = TokenCalculator()
        self.system_info: SystemInfo = {"compressed_count": 0}
        self.init_embedding_provider(embedding_adapter)
        self._initialized = True

    def init_embedding_provider(self, adapter= None):
        self.embedding_manager.init_adapter(adapter)

    def calculate_tokens(self, text: str) -> int:
        return self.token_calculator.extract_tokens(text or "")

    async def __compress_context_and_update(
        self,
        context: deque[Message],
        callback: Optional[Callable[[list[Any]], Any]] = None,
    ) -> deque[Message]:
        if len(context) < self.config.compress_min_size:
            return context
        messages = list(context)
        targets: list[Message] = []
        for m in messages:
            if str(m.role) in {Role.USER, Role.ASSISTANT, Role.TOOL} and not (m.metadata or {}).get("is_compressed_summary"):
                targets.append(m)
        if len(targets) < self.config.compress_min_size:
            return context
        batch = targets[: self.config.compress_batch_size]
        compressed = await self.compression_manager.compress_context(batch)
        created_at = datetime.now().timestamp()
        compressed_memory = CompressedMemory(
            id=compressed.id,
            original_ids=list(compressed.original_ids),
            compressed_content=compressed.compressed_content,
            summary=compressed.summary,
            created_at=created_at,
            session_id=compressed.session_id or batch[0].session_id,
            time_range=compressed.time_range,
            metadata=dict(compressed.metadata or {}),
        )

        add_compressed = getattr(self.storage, "add_compressed_memory", None)
        if callable(add_compressed):
            persisted = add_compressed(compressed_memory)
            if asyncio.iscoroutine(persisted):
                await persisted

        removed = set(compressed.original_ids)
        updated = deque((m for m in context if m.id not in removed), maxlen=context.maxlen)
        summary_text = f"[Compressed Context]\n{compressed.summary or compressed.compressed_content[:260]}"
        updated.appendleft(
            Message(
                id=f"compressed_{compressed.id}",
                content=summary_text,
                timestamp=created_at,
                role=Role.SYSTEM,
                session_id=batch[0].session_id,
                tokens=self.calculate_tokens(summary_text),
                metadata={
                    "is_compressed_summary": True,
                    "compressed_id": compressed.id,
                },
            )
        )

        self.system_info["compressed_count"] += 1
        if callback is not None:
            result = callback([compressed])
            if asyncio.iscoroutine(result):
                await result
        return updated

    async def maybe_compress_context(
        self,
        context: deque[Message],
        callback: Optional[Callable[[list[Any]], Any]] = None,
    ) -> deque[Message]:
        if len(context) < self.config.compress_every_n_messages:
            return context
        if len(context) % self.config.compress_every_n_messages != 0:
            return context
        asyncio.create_task(self.persist_context_detail(context))
        return await self.__compress_context_and_update(context, callback=callback)

    async def add_memories(self, memories: list[Memory]) -> list[int]:
        return await self.storage.add_memories(memories)

    async def __list_session_memories(self, session_id: str = "default") -> list[dict[str, Any]]:
        rows = await self.storage.get_short_term(session_id=session_id, limit=self.config.max_records)
        rows.sort(key=lambda x: float(x.get("created_at", 0.0)))
        return rows

    def __format_rows(
        self,
        rows: list[dict[str, Any]],
        max_items: int = 10
    ) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for row in rows:
            text = " ".join(str(row.get("content", "")).split())
            if not text:
                continue
            norm = text.lower()
            if norm in seen:
                continue
            seen.add(norm)
            if len(text) > 160:
                text = text[:157] + "..."
            role = str(row.get("role", "memory"))
            created_at = datetime.fromtimestamp(float(row.get("created_at", utils.now()))).strftime("%Y-%m-%d")
            lines.append(f"[{created_at}] ({role}) {text}")
        return "\n".join(lines[-max_items:])

    async def get_short_term_summary(
        self, 
        session_id: str = "default", 
        limit: int = 10
    ) -> str:
        rows = await self.__list_session_memories(session_id=session_id)
        boundary = datetime.now() - timedelta(days=self.config.short_term_days)
        selected=[]
        for row in rows:
            if datetime.fromtimestamp(float(row.get("created_at", utils.now()))) >= boundary:
                selected.append(row)
        return self.__format_rows(selected, max_items=limit)

    async def get_long_term_summary(
        self, 
        session_id: str = "default", 
        limit: int = 12
    ) -> str:
        get_compressed = self.storage.get_compressed
        if callable(get_compressed):
            chunks = await self.storage.get_compressed(session_id=session_id, short_first=False, limit=limit * 2)
            texts = [f"- {x.summary or x.compressed_content[:180]}" for x in chunks[:limit]]
            return "\n".join(texts)
        rows = await self.__list_session_memories(session_id=session_id)
        boundary = datetime.now() - timedelta(days=self.config.short_term_days)
        selected=[]
        for row in rows:
            if datetime.fromtimestamp(float(row.get("created_at", utils.now()))) < boundary:
                selected.append(row)
        return self.__format_rows(selected, max_items=limit)

    async def retrieve_memory(self, query: str, session_id: str = "default", top_k: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        get_detailed =  self.storage.get_detailed
        if callable(get_detailed):
            rows = await get_detailed(session_id=session_id, limit=max(top_k * 2, 20))
            q = query.lower()
            ranked = sorted(
                rows,
                key=lambda x: (q in str(x.get("content", "")).lower(), float(x.get("created_at", 0.0))),
                reverse=True,
            )
            return ranked[:top_k]
        return await self.storage.get_long_term(session_id=session_id, query=query, limit=top_k)

    async def get_memory_layers(
        self,
        query: str = "",
        session_id: str = "default",
        detail_top_k: int = 12,
        summary_limit: int = 12,
        is_query_detailed_items: bool = True,
    ) -> MemoryContext:
        short_summary = await self.get_short_term_summary(session_id=session_id, limit=summary_limit)
        long_summary = await self.get_long_term_summary(session_id=session_id, limit=summary_limit)
        if is_query_detailed_items:
            detailed = await self.retrieve_memory(query=query or "", session_id=session_id, top_k=detail_top_k)
        else:
            detailed = None
        return {"short_term": short_summary, "long_term": long_summary, "detailed": detailed}

    async def persist_context_detail(
        self, 
        context: Union[list[Message], deque[Message]]
    ) -> None:
        if not context:
            return
        if isinstance(context, deque):
            context = list(context)
        payload: list[Memory] = []
        for msg in context:
            if str(msg.role) not in {Role.USER, Role.ASSISTANT, Role.TOOL}:
                continue
            payload.append(
                Memory(
                    id=str(msg.id),
                    session_id=msg.session_id or "default",
                    role=str(msg.role),
                    source=str(msg.metadata.get("source", "text")) if msg.metadata else "text",
                    content=msg.content,
                    tokens=int(msg.tokens or 0),
                    importance=1.0,
                    access_count=0,
                    last_access_time=float(msg.timestamp),
                    created_at=float(msg.timestamp),
                    updated_at=float(msg.timestamp),
                    metadata=dict(msg.metadata or {}),
                )
            )
        if payload:
            await self.add_memories(payload)

    async def close_with_context(
        self, 
        context: Optional[deque[Message]] = None
    ) -> None:
        if context is not None and len(context) >= self.config.compress_min_size:
            try:
                new_context = await self.__compress_context_and_update(context)
                await self.persist_context_detail(list(new_context))
            except Exception:
                await self.persist_context_detail(list(context))
        await self.shutdown()

    async def decay_now(self) -> None:
        await self.storage.decay_now()

    async def shutdown(self) -> None:
        await self.storage.close()
