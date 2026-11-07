"""兼容门面：把旧 `HybridMemorySystem` 调用委托给统一 `MemoryAPI`"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Deque, Dict, List, Optional, Set, TypedDict, Union

from ..events import on_event_class, types
from ..logger import logger
from ..models import MessageContext, Role
from .api import MemoryAPI, get_memory_api, reset_memory_api
from .compression import ContextCompressor
from .config import load_memory_config
from .storage.models import CompressedMemory, Memory
from .token import TokenCalculator


class MemoryContext(TypedDict):
    short_term: str
    long_term: str
    detailed: Optional[List[Dict[str, Any]]]


class SystemInfo(TypedDict):
    compressed_count: int


@on_event_class([
    (types.AppEventType.ManagerEventType.MEMORY_STOP, "shutdown"),
])
class HybridMemorySystem:
    _instance: Optional["HybridMemorySystem"] = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def instance(cls) -> Optional["HybridMemorySystem"]:
        return cls._instance

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        compress_min_size: Optional[int] = None,
        embedding_adapter: Any = None,
        user_is_database: bool = True,
        db_path: Optional[str] = None,
        max_records: Optional[int] = None,
        short_term_days: Optional[int] = None,
        compress_every_n_messages: Optional[int] = None,
        compress_batch_size: Optional[int] = None,
        index_path: Optional[str] = None,   # 已移除，仅吞掉避免 TypeError
        **_: Any,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        base = load_memory_config()
        if db_path:
            base.db_path = str(db_path)
        if max_records:
            base.max_records = int(max_records)
        if short_term_days:
            base.short_term_days = int(short_term_days)
        if compress_min_size:
            base.compress_min_size = int(compress_min_size)
        if compress_every_n_messages:
            base.compress_every_n_messages = int(compress_every_n_messages)
        if compress_batch_size:
            base.compress_batch_size = int(compress_batch_size)
        base.user_is_database = True   # 统一走 SQLite，不再有隐式 Markdown 回退

        # adapter 在构造时装配，不留到不可达代码里
        self.api: MemoryAPI = get_memory_api(
            config=base,
            llm_client=llm_client,
            embedding_adapter=embedding_adapter,
        )
        self.config = self.api.config
        self.storage = self.api.storage
        self.embedding_manager = self.api.embedding
        self.features = self.api.features
        self.kernel = self.api.kernel
        self.clock = self.api.clock

        self.compression_manager = ContextCompressor(llm_client)
        self.token_calculator = TokenCalculator()
        self.system_info: SystemInfo = {"compressed_count": 0}
        self.__since_last_compress = 0
        self.__bg_tasks: Set[asyncio.Task] = set()
        self.__closing = False
        # 必须显式置位：多个调用点用它判断系统是否可用
        self._initialized = True

    # ---------- 生命周期 ----------

    async def start(self) -> Dict[str, Any]:
        return await self.api.start()

    async def shutdown(self) -> None:
        await self.api.shutdown()

    def init_embedding_provider(self, adapter: Any = None) -> None:
        self.api.embedding.init_adapter(adapter)

    def ensure_vector_backend(self, fingerprint: str = "") -> Dict[str, Any]:
        return self.api.ensure_vector_backend()

    def memory_status(self) -> Dict[str, Any]:
        return self.api.status()

    def calculate_tokens(self, text: str) -> int:
        return self.token_calculator.extract_tokens(text or "")

    # ---------- 读（全部委托统一 API） ----------

    async def get_memory_layers(
        self,
        query: str = "",
        session_id: str = "default",
        detail_top_k: int = 12,
        summary_limit: int = 12,
        is_query_detailed_items: bool = True,
    ) :
        return await self.api.layers(
            session_id=session_id,
            query=query if is_query_detailed_items else "",
            detail_top_k=detail_top_k,
            summary_limit=summary_limit,
        )

    async def get_short_term_summary(
        self, session_id: str = "default", limit: int = 10
    ) -> str:
        return await self.api.short(session_id=session_id, limit=limit)

    async def get_long_term_summary(
        self, session_id: str = "default", limit: int = 12
    ) -> str:
        return await self.api.long(session_id=session_id, limit=limit)

    async def retrieve_memory(
        self, query: str, session_id: str = "default", top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """语义检索。旧实现用 `query in content` 子串匹配冒充语义检索，
        现在统一走 MemoryAPI 的多路召回 + Milvus 向量通道。"""
        result = await self.api.search(
            query, session_id=session_id, top_k=top_k
        )
        return result["items"]

    # ---------- 写 ----------

    async def add_memories(self, memories: List[Memory]) -> List[int]:
        return await self.api.add(memories)

    async def persist_context_detail(
        self, context: Union[List[MessageContext], Deque[MessageContext]]
    ) -> None:
        if not context:
            return
        payload: List[Memory] = []
        for msg in context:
            if str(msg.role) not in {Role.USER, Role.ASSISTANT, Role.TOOL}:
                continue
            meta = dict(msg.metadata or {})
            payload.append(Memory(
                id=str(msg.id),
                session_id=msg.session_id or "default",
                role=str(msg.role),
                source=str(meta.get("source", "text")),
                content=msg.content,
                tokens=int(msg.tokens or 0),
                importance=1.0,
                access_count=0,
                last_access_time=float(msg.timestamp),
                created_at=float(msg.timestamp),
                updated_at=float(msg.timestamp),
                metadata=meta,
            ))
        if payload:
            try:
                await self.api.add(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 上下文持久化失败: {type(exc).__name__}")

    # ---------- 压缩节流（C108） ----------

    def note_new_message(self) -> None:
        self.__since_last_compress += 1

    async def maybe_compress_context(
        self,
        context: Deque[MessageContext],
        callback: Optional[Callable[[List[Any]], Any]] = None,
    ) -> Deque[MessageContext]:
        threshold = int(self.config.compress_every_n_messages)
        pending = max(self.__since_last_compress, 0)
        if pending == 0:
            if len(context) < threshold:
                return context
            pending = len(context)
        if pending < threshold or len(context) < self.config.compress_min_size:
            return context
        self.__track(self.persist_context_detail(context))
        return await self.__compress_context_and_update(context, callback=callback)

    async def __compress_context_and_update(
        self,
        context: Deque[MessageContext],
        callback: Optional[Callable[[List[Any]], Any]] = None,
    ) -> Deque[MessageContext]:
        if len(context) < self.config.compress_min_size:
            return context
        targets = [
            m for m in context
            if str(m.role) in {Role.USER, Role.ASSISTANT, Role.TOOL}
            and not (m.metadata or {}).get("is_compressed_summary")
        ]
        if len(targets) < self.config.compress_min_size:
            return context
        batch = targets[: self.config.compress_batch_size]
        try:
            compressed = await self.compression_manager.compress_context(batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Memory] 压缩失败，保留原上下文: {exc}")
            return context
        created_at = datetime.now().timestamp()
        try:
            await self.api.add_compressed(CompressedMemory(
                id=compressed.id,
                original_ids=list(compressed.original_ids),
                compressed_content=compressed.compressed_content,
                summary=compressed.summary,
                created_at=created_at,
                session_id=compressed.session_id or batch[0].session_id,
                time_range=compressed.time_range,
                metadata=dict(compressed.metadata or {}),
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Memory] 压缩记忆落盘失败: {type(exc).__name__}")
        removed = set(compressed.original_ids)
        updated = deque(
            (m for m in context if m.id not in removed), maxlen=context.maxlen
        )
        summary_text = (
            f"[Compressed Context]\n"
            f"{compressed.summary or compressed.compressed_content[:260]}"
        )
        updated.appendleft(MessageContext(
            id=f"compressed_{compressed.id}",
            content=summary_text,
            timestamp=created_at,
            role=Role.SYSTEM,
            session_id=batch[0].session_id,
            tokens=self.calculate_tokens(summary_text),
            metadata={"is_compressed_summary": True,
                       "compressed_id": compressed.id},
        ))
        self.system_info["compressed_count"] += 1
        self.__since_last_compress = 0
        if callback is not None:
            try:
                result = callback([compressed])
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Memory] 压缩回调失败: {type(exc).__name__}")
        return updated

    # ---------- 后台任务 ----------

    def __track(self, coro) -> None:
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:
            return
        self.__bg_tasks.add(task)
        task.add_done_callback(self.__on_bg_done)

    def __on_bg_done(self, task: asyncio.Task) -> None:
        self.__bg_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(f"[Memory] 后台任务失败: {type(exc).__name__}")

    async def flush_background(self, timeout: float = 5.0) -> None:
        await self.api.flush(timeout=timeout)
        if self.__bg_tasks:
            try:
                await asyncio.wait(list(self.__bg_tasks), timeout=timeout)
            except Exception:  # noqa: BLE001
                pass

    async def decay_now(self) -> None:
        await self.api.decay()

    async def close_with_context(
        self, context: Optional[Deque[MessageContext]] = None
    ) -> None:
        if self.__closing:
            return
        self.__closing = True
        try:
            if context is not None:
                try:
                    new_context = await self.__compress_context_and_update(context)
                    await self.persist_context_detail(list(new_context))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[Memory] 退出前压缩失败，直接落盘: {exc}")
                    await self.persist_context_detail(list(context))
        finally:
            await self.flush_background()
            await self.api.shutdown()


def reset_hybrid_memory() -> None:
    """仅供测试：同时重置兼容壳与统一 API 单例。"""
    with HybridMemorySystem._lock:
        HybridMemorySystem._instance = None
    reset_memory_api()
