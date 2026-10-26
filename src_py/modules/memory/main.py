"""混合记忆系统（main.py）。

修复对应清单：C108 C109 C110 C111 C112

C108 **高频压缩**（最严重）：
    ```python
    if len(context) % self.config.compress_every_n_messages != 0:
        return context
    ```
    触发条件基于"当前消息总数是否为 N 的倍数"。
    而 `UserContext._messages` 是 `deque(maxlen=max_message*2)` —— **满了之后
    len 恒定不变**。于是 len 一旦落在 N 的倍数上，之后**每加一条消息都会触发一次压缩**。
    压缩会调用 LLM（15s 超时），等于每轮对话都额外跑一次大模型。

    改为基于"距上次压缩新增了多少条"的计数器，与 deque 长度解耦。

C109 `asyncio.create_task(self.persist_context_detail(context))` ——
    **fire-and-forget**：任务引用没有保存，可能被 GC 回收；
    抛出的异常无人处理（"Task exception was never retrieved"）。
    改为保存引用集合 + done 回调记录异常。

C110 `MemoryConfig(...)` 用 `min(30, int(compress_min_size))` 之类强行夹取，
    但形参默认值（5 / 50）与 `MemoryConfig` 的默认值（200 / 1000）差了一个量级，
    调用方不显式传参时行为完全不同。改为默认 None，未传时用 config 的默认值。

C111 `close_with_context` 里 `except Exception: await self.persist_context_detail(...)`
    捕获过宽且没有日志；`shutdown()` 失败会让退出流程卡住。

C112 `self._instance = self` 多余（__new__ 已保证单例），且 `system_info`
    在多次构造间被重置（虽然 __init__ 有守卫，但守卫只挡 _initialized）。
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Optional, Set, TypedDict, Union

from ..events import on_event_class, types
from ..logger import logger
from ..models import Role,MessageContext
from . import utils
from .compression import ContextCompressor
from .config import MemoryConfig
from .managers import EmbeddingManager, MemoryBackendManager
from .storage.models import CompressedMemory, Memory
from .token import TokenCalculator

class MemoryContext(TypedDict):
    short_term: str
    long_term: str
    detailed: Optional[list[dict[str, Any]]]


class SystemInfo(TypedDict):
    compressed_count: int


@on_event_class([
    (types.AppEventType.ManagerEventType.MEMORY_STOP, "shutdown"),
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
    
    @classmethod
    def instance(cls):
        return cls._instance

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        compress_min_size: Optional[int] = None,
        embedding_adapter: Any = None,
        user_is_database: bool = False,
        db_path: Optional[str] = None,
        index_path: Optional[str] = None,
        max_records: Optional[int] = None,
        short_term_days: Optional[int] = None,
        compress_every_n_messages: Optional[int] = None,
        compress_batch_size: Optional[int] = None,
    ) -> None:
        if self._initialized:
            return

        base = MemoryConfig()
        base.ensure_parent_dirs()

        self.config = MemoryConfig(
            compress_min_size=max(1, int(
                compress_min_size 
                if compress_min_size is not None else base.compress_min_size
            )),
            user_is_database=user_is_database,
            db_path=db_path or base.db_path,
            index_path=index_path or base.index_path,
            max_records=max(100, int(max_records if max_records is not None
                                      else base.max_records)),
            short_term_days=max(1, int(
                short_term_days
                if short_term_days is not None else base.short_term_days
            )),
            compress_every_n_messages=max(1, int(
                compress_every_n_messages
                if compress_every_n_messages is not None else base.compress_every_n_messages
            )),
            compress_batch_size=max(1, int(
                compress_batch_size
                if compress_batch_size is not None
                else base.compress_batch_size
            ))
        )

        self.embedding_manager = EmbeddingManager(dim=self.config.embedding_dim)
        self.backend_manager = MemoryBackendManager(
            user_is_database=user_is_database,
            db_path=self.config.db_path,
            index_path=self.config.index_path,
            embedding_dim=self.config.embedding_dim,
            max_records=self.config.max_records,
            embedding_manager=self.embedding_manager,
        )
        self.storage = self.backend_manager.storage
        self.compression_manager = ContextCompressor(llm_client)
        self.token_calculator = TokenCalculator()
        self.system_info: SystemInfo = {"compressed_count": 0}

        # 压缩节流计数器（与 deque 长度解耦）
        self.__since_last_compress = 0
        self.__bg_tasks: Set[asyncio.Task] = set()
        self.__closing = False

        self.init_embedding_provider(embedding_adapter)
        self._initialized = True

    def init_embedding_provider(self, adapter: Any = None) -> None:
        self.embedding_manager.init_adapter(adapter)

    def calculate_tokens(self, text: str) -> int:
        return self.token_calculator.extract_tokens(text or "")

    # ---------- 后台任务（C109） ----------

    def __track(self, coro) -> None:
        try:
            task = asyncio.ensure_future(coro)
        except RuntimeError:
            # 没有运行中 loop（例如纯同步退出路径），直接放弃后台持久化
            logger.debug("[Memory] 无运行中事件循环，跳过后台持久化")
            return
        self.__bg_tasks.add(task)
        task.add_done_callback(self.__on_bg_done)

    def __on_bg_done(self, task: asyncio.Task) -> None:
        self.__bg_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(f"[Memory] 后台记忆任务失败: {exc}")

    # ---------- 压缩 ----------

    async def __compress_context_and_update(
        self,
        context: deque[MessageContext],
        callback: Optional[Callable[[list[Any]], Any]] = None,
    ) -> deque[MessageContext]:
        if len(context) < self.config.compress_min_size:
            return context
        messages = list(context)
        targets: list[MessageContext] = []
        for m in messages:
            if str(m.role) in {Role.USER, Role.ASSISTANT, Role.TOOL} and not (
                m.metadata or {}
            ).get("is_compressed_summary"):
                targets.append(m)
        if len(targets) < self.config.compress_min_size:
            return context

        batch = targets[: self.config.compress_batch_size]
        try:
            compressed = await self.compression_manager.compress_context(batch)
        except Exception as exc:
            # C111：压缩失败不能打断对话主流程
            logger.warning(f"[Memory] 压缩失败，保留原上下文: {exc}")
            return context

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
            try:
                persisted = add_compressed(compressed_memory)
                if asyncio.iscoroutine(persisted):
                    await persisted
            except Exception as exc:
                logger.warning(f"[Memory] 压缩记忆落盘失败: {exc}")

        removed = set(compressed.original_ids)
        updated = deque((m for m in context if m.id not in removed), maxlen=context.maxlen)
        summary_text = (
            f"[Compressed Context]\n{compressed.summary or compressed.compressed_content[:260]}"
        )
        updated.appendleft(
            MessageContext(
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
        # C108：压缩完成，计数器归零
        self.__since_last_compress = 0

        if callback is not None:
            try:
                result = callback([compressed])
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning(f"[Memory] 压缩回调失败: {exc}")
        return updated

    def note_new_message(self) -> None:
        """每追加一条消息调用一次，用于压缩节流计数。

        由 UserContext 在 add_message 成功后调用；
        若调用方不调用，退化为按长度判断（见 maybe_compress_context）。
        """
        self.__since_last_compress += 1 # 新增消息数计数器

    async def maybe_compress_context(
        self,
        context: deque[MessageContext],
        callback: Optional[Callable[[list[Any]], Any]] = None,
    ) -> deque[MessageContext]:
        threshold = self.config.compress_every_n_messages
        # 兼容未调用 note_new_message 的场景：用长度做兜底判断
        pending = max(self.__since_last_compress, 0)
        if pending == 0:
            if len(context) < threshold:
                return context
            pending = len(context)

        if pending < threshold or len(context) < self.config.compress_min_size:
            return context

        # C109：持久化改为受跟踪的后台任务
        self.__track(self.persist_context_detail(context))
        return await self.__compress_context_and_update(context, callback=callback)

    # ---------- 记忆读写 ----------

    async def add_memories(self, memories: list[Memory]) -> list[int]:
        return await self.storage.add_memories(memories)

    async def __list_session_memories(self, session_id: str = "default") -> list[dict[str, Any]]:
        rows = await self.storage.get_short_term(session_id=session_id, limit=self.config.max_records)
        rows.sort(key=lambda x: float(x.get("created_at", 0.0)))
        return rows

    def __format_rows(self, rows: list[dict[str, Any]], max_items: int = 10) -> str:
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
            created_at = datetime.fromtimestamp(
                float(row.get("created_at", utils.now()))
            ).strftime("%Y-%m-%d")
            lines.append(f"[{created_at}] ({role}) {text}")
        return "\n".join(lines[-max_items:])

    async def get_short_term_summary(self, session_id: str = "default", limit: int = 10) -> str:
        rows = await self.__list_session_memories(session_id=session_id)
        boundary = datetime.now() - timedelta(days=self.config.short_term_days)
        selected = [
            row for row in rows
            if datetime.fromtimestamp(float(row.get("created_at", utils.now()))) >= boundary
        ]
        return self.__format_rows(selected, max_items=limit)

    async def get_long_term_summary(self, session_id: str = "default", limit: int = 12) -> str:
        get_compressed = getattr(self.storage, "get_compressed", None)
        if callable(get_compressed):
            try:
                chunks = await get_compressed(
                    session_id=session_id, short_first=False, limit=limit * 2
                ) # type: ignore
                texts = [f"- {x.summary or x.compressed_content[:180]}" for x in chunks[:limit]]
                return "\n".join(texts)
            except Exception as exc:
                logger.warning(f"[Memory] 读取压缩记忆失败: {exc}")
        rows = await self.__list_session_memories(session_id=session_id)
        boundary = datetime.now() - timedelta(days=self.config.short_term_days)
        selected = [
            row for row in rows
            if datetime.fromtimestamp(float(row.get("created_at", utils.now()))) < boundary
        ]
        return self.__format_rows(selected, max_items=limit)

    async def retrieve_memory(
        self, query: str, session_id: str = "default", top_k: int = 20
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []
        get_detailed = getattr(self.storage, "get_detailed", None)
        if callable(get_detailed):
            try:
                rows = await get_detailed(session_id=session_id, limit=max(top_k * 2, 20)) # type: ignore
                q = query.lower()
                ranked = sorted(
                    rows,
                    key=lambda x: (
                        q in str(x.get("content", "")).lower(),
                        float(x.get("created_at", 0.0)),
                    ),
                    reverse=True,
                ) 
                return ranked[:top_k]
            except Exception as exc:
                logger.warning(f"[Memory] 检索详细记忆失败: {exc}")
        try:
            return await self.storage.get_long_term(session_id=session_id, query=query, limit=top_k)
        except Exception as exc:
            logger.warning(f"[Memory] 长期记忆检索失败: {exc}")
            return []

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
        detailed = None
        if is_query_detailed_items and query:
            detailed = await self.retrieve_memory(
                query=query, session_id=session_id, top_k=detail_top_k
            )
        return {"short_term": short_summary, "long_term": long_summary, "detailed": detailed}

    async def persist_context_detail(
        self, context: Union[list[MessageContext], deque[MessageContext]]
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
            try:
                await self.add_memories(payload)
            except Exception as exc:
                logger.warning(f"[Memory] 上下文持久化失败: {exc}")

    # ---------- 关闭 ----------

    async def flush_background(self, timeout: float = 5.0) -> None:
        if not self.__bg_tasks:
            return
        tasks = list(self.__bg_tasks)
        try:
            await asyncio.wait(tasks, timeout=timeout)
        except Exception:
            pass

    async def close_with_context(self, context: Optional[deque[MessageContext]] = None) -> None:
        if self.__closing:
            return
        self.__closing = True
        try:
            if context is not None:
                try:
                    new_context = await self.__compress_context_and_update(context)
                    await self.persist_context_detail(list(new_context))
                except Exception as exc:
                    logger.warning(f"[Memory] 退出前压缩失败，直接落盘: {exc}")
                    await self.persist_context_detail(list(context))
        finally:
            await self.flush_background()
            await self.shutdown()

    async def decay_now(self) -> None:
        await self.storage.decay_now()

    async def shutdown(self) -> None:
        try:
            await self.backend_manager.close()
        except Exception as exc:
            logger.warning(f"[Memory] 关闭存储失败: {exc}")
