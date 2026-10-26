"""用户输入上下文（单例，跨事件循环安全）"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional
from uuid import uuid4

from ..models import MessageContext, Role


class _LoopAwareLock:
    """按事件循环惰性创建的 asyncio.Lock（C1 / CD1）。

    - 首次 await 时绑定当前 running loop
    - 若后续在另一个 loop 上使用，自动换成该 loop 专属的锁
    - 没有 running loop 时（纯同步上下文）退化为 threading.Lock
    """

    def __init__(self) -> None:
        self._locks: Dict[int, asyncio.Lock] = {}
        self._guard = threading.Lock()

    def _current_loop_key(self) -> Optional[int]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        return id(loop)

    def _get_async_lock(self, key: int) -> asyncio.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def __aenter__(self):
        key = self._current_loop_key()
        if key is None:
            raise RuntimeError("[UserContext] 只能在有运行中事件循环的线程里 await 本锁")
        await self._get_async_lock(key).acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        key = self._current_loop_key()
        if key is not None:
            lock = self._locks.get(key)
            if lock is not None and lock.locked():
                lock.release()
        return False


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
        self._messages: Deque[MessageContext] = deque(maxlen=self.max_message * 2)
        self._memory_system = None
        self.__lock = _LoopAwareLock()
        self._initialized = True

    # ---------- 记忆系统 ----------

    async def init_memory_async(
        self,
        session_id: Optional[str] = None,
        llm_client: Any = None,
        is_db: bool = False,
    ) -> None:
        """可等待的记忆初始化"""
        from ..memory.main import HybridMemorySystem

        if self._memory_system is not None:
            return
        self._memory_system = HybridMemorySystem(
            llm_client=llm_client,
            user_is_database=is_db
        )
        await self.build_memory_messages(session_id=session_id or "default", query="")

    def get_current_messages(self) -> List[Dict[str, str]]:
        """给 LLM 用的近期消息（role/content 形态）。"""
        messages: List[Dict[str, str]] = []
        for item in self._messages:
            if item.role in (Role.USER, Role.ASSISTANT):
                messages.append({
                    "role": item.role, 
                    "content": item.content
                })
        return messages

    def get_memory_snippets(self) -> List[Dict[str, str]]:
        """给 PromptBuilder 用的记忆片段（title/content 形态，C2）。"""
        snippets: List[Dict[str, str]] = []
        for item in self._messages:
            if item.role == Role.SYSTEM:
                snippets.append({"title": "上下文", "content": item.content})
        return snippets

    def clear_messages(self) -> None:
        self._messages.clear()

    def find_cached_reply(self, content: str) -> Optional[MessageContext]:
        for item in reversed(self._messages):
            if item.role == Role.ASSISTANT and item.content == content:
                return item
        return None

    # ---------- 记忆注入 ----------

    async def build_memory_messages(self, session_id: str = "default", query: str = "") -> None:
        if self._memory_system is None:
            return
        layers = await self._memory_system.get_memory_layers(
            query=query,
            session_id=session_id,
            detail_top_k=8,
            summary_limit=8,
            is_query_detailed_items=bool(query),
        )
        for label, key in [("短期记忆", "short_term"), ("长期记忆", "long_term")]:
            value = layers.get(key)
            if value:
                await self.add_message(
                    Role.SYSTEM,
                    f"{label}:\n{value}",
                    source="memory",
                    session_id=session_id,
                    compress=False,
                )
        detailed = layers.get("detailed") or []
        if detailed:
            lines = [str(item.get("content", ""))[:180] for item in detailed if item.get("content")]
            if lines:
                await self.add_message(
                    Role.SYSTEM,
                    "相关详细记忆:\n" + "\n".join(f"- {line}" for line in lines[:8]),
                    source="memory",
                    session_id=session_id,
                    compress=False,
                )

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
        now = datetime.now().timestamp()
        tokens = self._estimate_tokens(content)

        async with self.__lock:
            self._messages.append(MessageContext(
                id=self.__next_id(),
                timestamp=now,
                role=str(role),
                content=content[:2000],
                session_id=session_id or "default",
                tokens=tokens,
                metadata={"source": source},
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
            ))
            self.__remove_adjacent_duplicates()
            if self._memory_system is not None:
                self._memory_system.note_new_message()
            if compress and self._memory_system is not None:
                try:
                    compressed = await self._memory_system.maybe_compress_context(
                        self._messages,
                        callback=self.compressed_callback,
                    )
                    if compressed is not None:
                        self._messages = deque(compressed, maxlen=self.max_message * 2)
                except Exception as exc:
                    print(f"[UserContext] compress failed: {exc}")

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
        """可等待的关闭"""
        async with self.__lock:
            if self._memory_system is not None:
                try:
                    await self._memory_system.close_with_context(self._messages)
                except Exception as exc:
                    print(f"[UserContext] close memory failed: {exc}")
            self._messages.clear()

    def close_sync(self) -> None:
        """退出流程用：无 loop 时安全关闭。"""
        if self._memory_system is None:
            self._messages.clear()
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(self.close_async())
            except Exception as exc:
                print(f"[UserContext] close failed: {exc}")
            return
        raise RuntimeError("[UserContext] 当前线程有事件循环，请用 await close_async()")

    # ---------- 内部 ----------

    def __next_id(self) -> str:
        return f"{int(datetime.now().timestamp() * 1000)}_{uuid4().hex[:6]}"

    def __remove_adjacent_duplicates(self) -> None:
        """只去掉相邻重复项"""
        unique: Deque[MessageContext] = deque(maxlen=self.max_message * 2)
        prev_key: Optional[tuple] = None
        for item in self._messages:
            key = (str(item.role), item.content)
            if key == prev_key:
                continue
            prev_key = key
            unique.append(item)
        self._messages = unique


userContext = UserContext()
