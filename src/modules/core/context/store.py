"""按 session 分桶的上下文存储（C0-02 / C0-04 / C0-05）。

为什么要有这个文件
──────────────────
原 `UserContext` 是**进程级单例 + 一条共享 deque**：

* `get_current_messages()` 遍历整条 deque，只按 role 过滤，
  不按 `session_id` 过滤 —— 消息身上明明带着 session_id 却没人用；
* `Orchestrator` 正是拿这个结果去构造 prompt。

于是 A、B 两个会话交错对话时，A 的 prompt 里会混入 B 的历史。
这不是"理论上可能"，而是每次切换会话都必然发生，只是单会话手工测试看不出来。

本文件把"消息仓库"从单例里剥离成显式分桶：

    ContextStore
      ├── session "default" → deque + 自己的锁
      ├── session "abc"     → deque + 自己的锁
      └── ...

三条硬约束：

1. **读取必须带 session_id**：没有 session 作用域的读取接口一律不提供，
   从 API 上消灭"忘记过滤"这种错误。
2. **锁按 session 分片**：不同会话不会因一把全局锁互相串行
   （OptimizationPlan §8：ContextStore 使用 per-session lock）。
3. **记忆片段不进对话窗口**：记忆是每轮重算的**瞬态**输入，
   原实现把它作为 SYSTEM 消息 append 进 deque，于是每问一轮就多沉淀一条，
   越积越多且永不过期。这里单独存放、每轮整体覆盖。
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections import deque
from collections import OrderedDict
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
)

from ...models import MessageContext, Role

#: 参与"对话历史"的 role。SYSTEM 不在其中——它只作瞬态注入。
DIALOGUE_ROLES: Set[str] = {Role.USER, Role.ASSISTANT, Role.TOOL}

DEFAULT_SESSION_ID = "default"


def _normalize_session(session_id: Optional[str]) -> str:
    """空值一律落到 default，避免 None 成为一个"看不见的公共桶"。"""
    return str(session_id) if session_id else DEFAULT_SESSION_ID


def _estimate_tokens_fallback(content: str) -> int:
    """CJK 约 1 字 1 token，拉丁约 4 字符 1 token。"""
    if not content:
        return 0
    cjk = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff"
              or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af")
    return max(1, cjk + int((len(content) - cjk) / 4))


class _SessionLocks:
    """per-(loop, session) 锁。

    asyncio.Lock 不能跨事件循环复用，所以 key 里带上 running loop 的 id；
    没有 running loop 时（纯同步线程）退化为一把线程锁。
    """

    #: 防止 loop 反复重建导致锁表无限增长
    _MAX_KEYS = 512

    def __init__(self) -> None:
        self._async: "OrderedDict[tuple, asyncio.Lock]" = OrderedDict()
        self._sync = threading.RLock()
        self._guard = threading.Lock()

    @staticmethod
    def _key(session_id: str) -> Optional[tuple]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        return (id(loop), session_id)

    @contextlib.asynccontextmanager
    async def for_session(self, session_id: str) -> AsyncIterator[None]:
        key = self._key(session_id)
        if key is None:
            with self._sync:
                yield
            return

        with self._guard:
            lock = self._async.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._async[key] = lock
                # 简单的容量护栏：丢弃最久未用的锁
                while len(self._async) > self._MAX_KEYS:
                    self._async.popitem(last=False)
            else:
                self._async.move_to_end(key)

        async with lock:
            yield

    def drop(self, session_id: str) -> None:
        """会话被清空时，把它的锁一并回收。"""
        with self._guard:
            for key in [k for k in self._async if k[1] == session_id]:
                self._async.pop(key, None)


class _SessionBucket:
    """单个会话的消息桶。"""

    __slots__ = ("messages", "memory_snippets", "updated_at", "created_at", "lock")

    def __init__(self, max_messages: int) -> None:
        #: 桶级线程锁。原实现只有 asyncio.Lock（按 loop 分片），
        #: 同步线程里的写入与 async 写入互不互斥；读路径更是完全无锁，
        #: deque 在迭代时被 append 会直接抛 RuntimeError。
        self.lock = threading.RLock()
        self.messages: Deque[MessageContext] = deque(maxlen=max_messages)
        #: 每轮整体覆盖，不累积（C0-04）
        self.memory_snippets: List[Dict[str, Any]] = []
        now = time.monotonic()
        self.created_at = now
        self.updated_at = now

    def touch(self) -> None:
        self.updated_at = time.monotonic()


class ContextStore:
    """session 分桶的上下文存储。线程/协程安全。"""

    def __init__(
        self,
        max_messages: int = 40,
        max_sessions: int = 64,
        session_idle_ttl: float = 3600.0,
        token_estimator: Optional[Callable[[str], int]] = None,
    ) -> None:
        #: deque 里是"半个轮次"粒度（user+assistant），所以按 2 倍开
        self.max_messages = max(2, int(max_messages))
        self.max_sessions = max(1, int(max_sessions))
        self.session_idle_ttl = float(session_idle_ttl)
        self._token_estimator = token_estimator
        self._sessions: "OrderedDict[str, _SessionBucket]" = OrderedDict()
        self._locks = _SessionLocks()
        self._registry_guard = threading.RLock()

    # ---------- 桶管理 ----------

    def _bucket(self, session_id: str, *, create: bool = True) -> Optional[_SessionBucket]:
        key = _normalize_session(session_id)
        with self._registry_guard:
            bucket = self._sessions.get(key)
            if bucket is None and create:
                bucket = _SessionBucket(self.max_messages * 2)
                self._sessions[key] = bucket
                self._evict_if_needed()
            elif bucket is not None:
                self._sessions.move_to_end(key)
            return bucket

    def _evict_if_needed(self) -> None:
        """超容量时按 LRU 淘汰；default 会话永不被淘汰（它是兜底桶）。"""
        with self._registry_guard:
            if len(self._sessions) <= self.max_sessions:
                return
            now = time.monotonic()
            overflow = len(self._sessions) - self.max_sessions
            # 先淘汰确实空闲的；不够再按 LRU 淘汰。
            # 旧实现"没有 idle victim 就直接 return"，max_sessions 形同虚设，
            # 桶可以无限增长。default 是兜底桶，永不淘汰。
            idle = [
                sid for sid, b in self._sessions.items()
                if sid != DEFAULT_SESSION_ID
                and (now - b.updated_at) > self.session_idle_ttl
            ]
            victims = idle[:overflow]
            if len(victims) < overflow:
                lru = [
                    sid for sid in self._sessions
                    if sid != DEFAULT_SESSION_ID and sid not in victims
                ]
                victims += lru[: overflow - len(victims)]
            for sid in victims:
                self._sessions.pop(sid, None)
                self._locks.drop(sid)

    def session_ids(self) -> List[str]:
        with self._registry_guard:
            return list(self._sessions)

    # ---------- 读取（必须带 session） ----------

    def get_messages(
        self,
        session_id: str,
        roles: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
    ) -> List[MessageContext]:
        """取指定会话的消息。**不传 session_id 就没有结果**，没有全局视图。"""
        bucket = self._bucket(session_id, create=False)
        if bucket is None:
            return []
        wanted = {str(r) for r in roles} if roles is not None else None
        out: List[MessageContext] = []
        with bucket.lock:
            for item in bucket.messages:
                if wanted is not None and str(item.role) not in wanted:
                    continue
                out.append(item)
        if limit is not None and limit >= 0:
            out = out[-limit:]
        return out

    def get_dialogue(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """给 LLM 的近期对话（role/content 形态）。"""
        return [
            {"role": item.role, "content": item.content}
            for item in self.get_messages(session_id, roles=DIALOGUE_ROLES, limit=limit)
        ]

    def get_memory_snippets(self, session_id: str) -> List[Dict[str, Any]]:
        """本轮记忆片段（瞬态，每轮覆盖）。"""
        bucket = self._bucket(session_id, create=False)
        if bucket is None:
            return []
        with bucket.lock:
            return list(bucket.memory_snippets)

    def set_memory_snippets(self, session_id: str, snippets: Sequence[Dict[str, Any]]) -> None:
        """整体覆盖，而非追加 —— 避免历史上"每问一轮多沉淀一条"。"""
        bucket = self._bucket(session_id)
        if bucket is None:
            return
        with bucket.lock:
            bucket.memory_snippets = [dict(s) for s in snippets]
            bucket.touch()

    def clear_memory_snippets(self, session_id: str) -> None:
        bucket = self._bucket(session_id, create=False)
        if bucket is not None:
            with bucket.lock:
                bucket.memory_snippets = []

    # ---------- 写入 ----------

    def estimate_tokens(self, content: str) -> int:
        if self._token_estimator is not None:
            try:
                return int(self._token_estimator(content))
            except Exception:
                pass
        return _estimate_tokens_fallback(content)

    async def add(
        self,
        message: MessageContext,
        *,
        dedupe: bool = True,
    ) -> MessageContext:
        """写入一条消息。**同步部分**，不涉及任何慢 IO。"""
        session_id = _normalize_session(message.session_id)
        async with self._locks.for_session(session_id):
            bucket = self._bucket(session_id)
            if bucket is None:  # pragma: no cover - _bucket 恒返回
                return message
            with bucket.lock:
                bucket.messages.append(message)
                if dedupe:
                    self.__remove_adjacent_duplicates(bucket)
                bucket.touch()
        return message

    async def replace_messages(
        self,
        session_id: str,
        messages: Iterable[MessageContext],
    ) -> None:
        """整体替换（压缩完成后回写）。"""
        key = _normalize_session(session_id)
        async with self._locks.for_session(key):
            bucket = self._bucket(key)
            if bucket is None:
                return
            with bucket.lock:
                bucket.messages = deque(messages, maxlen=bucket.messages.maxlen)
                bucket.touch()

    def snapshot(self, session_id: str) -> List[MessageContext]:
        """取快照用于锁外处理（如压缩），避免持锁做慢活。"""
        return self.get_messages(session_id)

    async def clear(self, session_id: Optional[str] = None) -> int:
        """清空指定会话；不传则清空 default。**只清指定的那个**（C0-05）。"""
        if session_id is None:
            key = DEFAULT_SESSION_ID
        else:
            key = _normalize_session(session_id)
        async with self._locks.for_session(key):
            with self._registry_guard:
                bucket = self._sessions.pop(key, None)
            with (bucket.lock if bucket is not None else _NOOP_LOCK):
                removed = len(bucket.messages) if bucket else 0
                if bucket is not None:
                    bucket.messages.clear()
                    bucket.memory_snippets = []
            self._locks.drop(key)
        return removed

    async def clear_all(self) -> int:
        total = 0
        for sid in self.session_ids():
            total += await self.clear(sid)
        return total

    # ---------- 统计 ----------

    def stats(self) -> Dict[str, Any]:
        with self._registry_guard:
            return {
                "sessions": len(self._sessions),
                "max_sessions": self.max_sessions,
                "per_session": {
                    sid: {
                        "messages": len(b.messages),
                        "memory_snippets": len(b.memory_snippets),
                        "idle_seconds": round(time.monotonic() - b.updated_at, 1),
                    }
                    for sid, b in self._sessions.items()
                },
            }

    def clear_messages_sync(self, session_id: str) -> int:
        """同步清空消息（退出流程 / UI 清理用），走桶锁而不碰内部 deque。"""
        bucket = self._bucket(session_id, create=False)
        if bucket is None:
            return 0
        with bucket.lock:
            removed = len(bucket.messages)
            bucket.messages.clear()
            bucket.memory_snippets = []
            bucket.touch()
        return removed

    # ---------- 内部 ----------

    @staticmethod
    def __remove_adjacent_duplicates(bucket: _SessionBucket) -> None:
        """只去掉相邻重复项（保留"用户说了两遍"这种真实重复）。"""
        if len(bucket.messages) < 2:
            return
        unique: Deque[MessageContext] = deque(maxlen=bucket.messages.maxlen)
        prev_key: Optional[tuple] = None
        for item in bucket.messages:
            key = (str(item.role), item.content)
            if key == prev_key:
                continue
            prev_key = key
            unique.append(item)
        bucket.messages = unique


class _NoopLock:
    def __enter__(self): return self
    def __exit__(self, *exc): return False


_NOOP_LOCK = _NoopLock()

_store: Optional[ContextStore] = None
_store_lock = threading.Lock()


def get_context_store() -> ContextStore:
    """进程内共享的上下文存储（组合根可替换其内部实现）。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ContextStore()
    return _store
