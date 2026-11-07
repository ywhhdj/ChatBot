"""用户输入上下文（单例门面 + session 分桶存储）。

改造说明（C0-02 / C0-04 / C0-05）
────────────────────────────────
本类曾是"进程单例 + 一条共享 deque"，读取时只按 role 过滤、不按 session 过滤，
Orchestrator 又正是用它构造 prompt —— 多会话交错时必然串线。

现在单例只保留**跨会话共享的东西**（记忆系统、压缩回调、配置），
消息本体全部下沉到 `ContextStore` 的 per-session 桶里：

    UserContext
        └── ContextStore
              ├── "default"  → deque + 自己的锁
              └── "<sid>"    → deque + 自己的锁

对外 API 保持不变，但每个读取接口都新增 `session_id`：
不传时**自动取当前 RequestContext 的会话**，而不是退回"全部会话"，
这样"忘记传"得到的是正确结果，而不是污染。

记忆注入（C0-04）
────────────────
原实现把记忆作为 SYSTEM 消息 append 进对话 deque：
每问一轮沉淀一条、随 deque 一起被压缩、还会作为"对话历史"再次进 prompt。
现在记忆是**每轮整体覆盖的瞬态片段**，不进对话窗口。
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ...models import MessageContext, Role
from .request import current as _current_request
from .store import DEFAULT_SESSION_ID, ContextStore, _normalize_session


class UserContext:
    """保存本轮与近期的用户/助手消息，并按需接入记忆系统。"""

    _instance = None
    _cls_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._cls_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        max_message: int = 20,
        compressed_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return
        self.max_message = max(20, int(max_message))
        self.compressed_callback = compressed_callback
        self._memory_system = None
        self._store = ContextStore(
            max_messages=self.max_message,
            token_estimator=self._estimate_tokens,
        )
        self._initialized = True

    # ---------- session 解析 ----------

    @property
    def store(self) -> ContextStore:
        return self._store

    @staticmethod
    def resolve_session(session_id: Optional[str] = None) -> str:
        """显式传入 > 当前 RequestContext > default。

        顺序很关键：宁可退回 default 这个**明确**的桶，
        也不能退回"所有会话"这个隐式全集。
        """
        if session_id:
            return _normalize_session(session_id)
        ctx = _current_request()
        if ctx is not None and ctx.session_id:
            return _normalize_session(ctx.session_id)
        return DEFAULT_SESSION_ID

    # ---------- 记忆系统 ----------

    async def init_memory_async(
        self,
        session_id: Optional[str] = None,
        llm_client: Any = None,
        is_db: bool = False,
    ) -> None:
        """可等待的记忆初始化"""
        from ...memory.main import HybridMemorySystem

        if self._memory_system is not None:
            return
        self._memory_system = HybridMemorySystem(
            llm_client=llm_client,
            user_is_database=is_db
        )
        await self.build_memory_messages(session_id=session_id or "default", query="")

    # ---------- 读取 ----------

    def get_current_messages(
        self,
        session_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """给 LLM 用的近期消息（role/content 形态）。

        **只返回该 session 的消息** —— 这是与旧实现的根本区别。
        """
        return self._store.get_dialogue(self.resolve_session(session_id), limit=limit)

    def get_memory_snippets(
        self,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """给 PromptBuilder 用的记忆片段（瞬态，每轮覆盖）。"""
        return self._store.get_memory_snippets(self.resolve_session(session_id))

    def get_messages(
        self,
        session_id: Optional[str] = None,
        roles: Optional[List[str]] = None,
    ) -> List[MessageContext]:
        """原始 MessageContext 列表（需要 id/token/工具信息时用这个）。"""
        return self._store.get_messages(self.resolve_session(session_id), roles=roles)

    def find_cached_reply(
        self,
        content: str,
        session_id: Optional[str] = None,
    ) -> Optional[MessageContext]:
        for item in reversed(self.get_messages(session_id)):
            if str(item.role) == Role.ASSISTANT and item.content == content:
                return item
        return None

    # ---------- 清理 ----------

    def clear_messages(self, session_id: Optional[str] = None) -> None:
        """只清指定会话（。同步签名保持兼容；真正的清理是无锁的。"""
        sid = self.resolve_session(session_id) if session_id else DEFAULT_SESSION_ID
        self._store._bucket(sid, create=False)  # noqa: SLF001 - 同模块内部
        bucket = self._store._sessions.get(sid)  # noqa: SLF001
        if bucket is not None:
            bucket.messages.clear()
            bucket.memory_snippets = []

    async def clear_session(self, session_id: Optional[str] = None) -> int:
        """异步清理指定会话（推荐入口，走锁）。"""
        sid = self.resolve_session(session_id) if session_id else DEFAULT_SESSION_ID
        return await self._store.clear(sid)

    # ---------- 记忆注入 ----------

    async def build_memory_messages(self, session_id: str = "default", query: str = "") -> None:
        """检索记忆并**整体覆盖**本轮片段。

        不再 append 进对话 deque：那段文本既不属于对话，也不该被压缩/回放（C0-04）。
        """
        if self._memory_system is None:
            return
        sid = _normalize_session(session_id)
        layers = await self._memory_system.get_memory_layers(
            query=query,
            session_id=sid,
            detail_top_k=8,
            summary_limit=8,
            is_query_detailed_items=bool(query),
        )
        snippets: List[Dict[str, Any]] = []
        for label, key in [("短期记忆", "short_term"), ("长期记忆", "long_term")]:
            value = layers.get(key)
            if value:
                snippets.append({"title": label, "content": str(value)})

        detailed = layers.get("detailed") or []
        lines = [str(item.get("content", ""))[:180] for item in detailed if item.get("content")]
        if lines:
            snippets.append({
                "title": "相关详细记忆",
                "content": "\n".join(f"- {line}" for line in lines[:8]),
            })

        self._store.set_memory_snippets(sid, snippets)

    # ---------- 写入 ----------

    async def add_message(
        self,
        role: str,
        content: str,
        source: str = "text",
        session_id: str = "default",
        tool_calls: Optional[list[dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        compress: bool = True,
    ) -> None:
        sid = _normalize_session(session_id)
        message = MessageContext(
            id=self.__next_id(),
            timestamp=datetime.now().timestamp(),
            role=str(role),
            content=content[:2000],
            session_id=sid,
            tokens=self._estimate_tokens(content),
            metadata={"source": source},
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )

        # 加锁只做"改状态"这一件事（微秒级），不做任何 IO
        await self._store.add(message)

        if self._memory_system is not None:
            self._memory_system.note_new_message()

        # 压缩可能调用 LLM —— 必须在锁外做，否则一条会话的慢活
        # 会堵住其他所有会话的写入（BackendDesign §3.6 / OptimizationPlan §8）
        if compress and self._memory_system is not None:
            await self.__maybe_compress(sid)

    async def __maybe_compress(self, session_id: str) -> None:
        snapshot = self._store.snapshot(session_id)
        if not snapshot:
            return
        try:
            compressed = await self._memory_system.maybe_compress_context( #type: ignore
                deque(snapshot, maxlen=self._store.max_messages * 2),
                callback=self.compressed_callback,
            )
        except Exception as exc:  # noqa: BLE001
            # 压缩失败不影响对话本身：只记日志，保留原明细
            from ...logger import logger

            logger.warning(f"[UserContext] compress failed: {exc}")
            return
        if compressed is not None:
            await self._store.replace_messages(session_id, compressed)

    def _estimate_tokens(self, content: str) -> int:
        if self._memory_system is not None:
            try:
                return int(self._memory_system.calculate_tokens(content))
            except Exception:
                pass
        return max(1, int(len(content) / 1.5))

    async def add_user_message(self, content: str, session_id: str = "default", source: str = "text") -> None:
        await self.add_message(Role.USER, content[:500], source=source, session_id=session_id)

    async def add_assistant_message(self, content: str, session_id: str = "default") -> None:
        await self.add_message(Role.ASSISTANT, content, source="llm", session_id=session_id)

    async def add_tool_calls_message(
        self,
        content: str,
        turn: int = 0,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        session_id: str = "default",
    ) -> None:
        normalized = []
        for index, tool_call in enumerate(tool_calls or []):
            function = tool_call.get("function", {})
            normalized.append({
                "id": tool_call.get("id", f"call_{turn}_{index}"),
                "type": tool_call.get("type", "function"),
                "function": {
                    "name": function.get("name", tool_call.get("name")),
                    "arguments": function.get("arguments", tool_call.get("arguments", "{}")),
                },
            })
        await self.add_message(
            Role.ASSISTANT,
            content,
            source="tool",
            session_id=session_id,
            tool_calls=normalized
        )

    async def add_tool_call_message(
        self,
        content: Any,
        turn: int = 0,
        tool_call: Optional[dict[str, Any]] = None,
        session_id: str = "default",
    ) -> None:
        tool_call = tool_call or {}
        await self.add_message(
            Role.TOOL,
            json.dumps(content, ensure_ascii=False, default=str),
            source="tool",
            session_id=session_id,
            tool_call_id=tool_call.get("id", f"call_{turn}_{tool_call.get('name', 'tool')}"),
        )

    # ---------- 关闭 ----------

    async def close_async(self) -> None:
        """可等待的关闭：逐个会话收尾，避免只清 default 而漏掉其他会话。"""
        if self._memory_system is not None:
            for sid in self._store.session_ids():
                try:
                    await self._memory_system.close_with_context(
                        deque(self._store.get_messages(sid),
                              maxlen=self._store.max_messages * 2)
                    )
                except Exception as exc:  # noqa: BLE001
                    from ...logger import logger

                    logger.warning(f"[UserContext] close memory failed({sid}): {exc}")
        await self._store.clear_all()

    def close_sync(self) -> None:
        """退出流程用：无 loop 时安全关闭。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(self.close_async())
            except Exception as exc:  # noqa: BLE001
                print(f"[UserContext] close failed: {exc}")
            return
        raise RuntimeError("[UserContext] 当前线程有事件循环，请用 await close_async()")

    def stats(self) -> Dict[str, Any]:
        return self._store.stats()

    # ---------- 内部 ----------

    @staticmethod
    def __next_id() -> str:
        return f"{int(datetime.now().timestamp() * 1000)}_{uuid4().hex[:6]}"


userContext = UserContext()
