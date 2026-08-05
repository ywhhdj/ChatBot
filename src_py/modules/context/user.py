from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Deque, Dict, List, Optional
from uuid import uuid4
from ..types.common import Role
from ..types.memory.context import Message

class SafeSessionContext:
    def __init__(self, session_id: str, max_history: int = 150):
        self.session_id = session_id
        self._lock = asyncio.Lock()
        self._history = deque(maxlen=max_history)
        self._closed = False

    async def add_interaction(
        self,
        user_msg: str,
        system_response: str,
        commands: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._closed:
            raise RuntimeError("Session already closed")
        async with self._lock:
            self._history.append({
                "timestamp": datetime.now().isoformat(),
                "user": user_msg[:500],
                "response": system_response[:1000],
                "commands": (commands or [])[:10],
                "metadata": metadata or {},
                "token_count": self._estimate_tokens(user_msg + system_response),
            })

    def _estimate_tokens(self, text: str) -> int:
        chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return int(chinese * 1.5 + (len(text) - chinese) * 0.33)

    def get_recent_history(self, n: int = 10) -> List[Dict[str, Any]]:
        return list(self._history)[-n:]

    async def cleanup(self) -> None:
        async with self._lock:
            self._closed = True
            self._history.clear()


class UserContext:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
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
        self._messages: Deque[Message] = deque(maxlen=self.max_message * 2)
        self._memory_system = None
        self.__lock = asyncio.Lock()
        self._initialized = True

    async def init_memory(
        self,
        session_id: Optional[str] = None,
        llm_client: Any = None,
        is_db: bool = False,
    ) -> None:
        from ..memory.main import HybridMemorySystem
        self._memory_system = HybridMemorySystem(llm_client=llm_client, user_is_database=is_db)
        await self.build_memory_messages(session_id=session_id or "default", query="")

    def get_current_messages(self):
        messgess=[]
        for item in reversed(self._messages):
            if item.role == Role.USER or item.role == Role.ASSISTANT:
                messgess.append({
                    "role": item.role,
                    "content": item.content,
                })
        return messgess

    def clear_messages(self) -> None:
        self._messages.clear()

    def find_cached_reply(self, content: str) -> Optional[Message]:
        for item in reversed(self._messages):
            if item.role == Role.ASSISTANT and item.content == content:
                return item
        return None

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
        tokens = self._memory_system.calculate_tokens(content) if self._memory_system else max(1, int(len(content) / 1.5))
        async with self.__lock:
            self._messages.append(Message(
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
            self.__remove_duplicates()
        if compress and self._memory_system is not None:
            self._messages = await self._memory_system.maybe_compress_context(
                self._messages,
                callback=self.compressed_callback,
            )

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
        await self.add_message(Role.ASSISTANT, content, source="tool", session_id=session_id, tool_calls=normalized)

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

    def __next_id(self) -> str:
        return f"{int(datetime.now().timestamp() * 1000)}_{uuid4().hex[:6]}"

    def __remove_duplicates(self) -> None:
        seen: set[tuple[str, str]] = set()
        unique: Deque[Message] = deque(maxlen=self.max_message * 2)
        for item in self._messages:
            key = (str(item.role), item.content)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        self._messages = unique
    from ..manager.task import decorator
    @decorator.async_task_scheduler
    async def close(self) -> None:
        if self._memory_system is not None:
            await self._memory_system.close_with_context(self._messages)
        self._messages.clear()
