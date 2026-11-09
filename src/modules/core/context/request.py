"""请求上下文（C0-01）。

目标
────
一次请求涉及的 id、会话、角色、时限、取消信号，此前散落在各个函数参数里，
靠"调用方记得传"来保证正确。漏传一个 session_id 就会静默串线，且无从追溯。

`RequestContext` 把它们收成一个**不可变对象**，全链路显式传递：

    controller  →  application service  →  orchestrator  →  prompt builder

同时提供 contextvar 形式的"当前请求"，只用于**日志与兜底**，
不得作为业务分支的依据（后台任务里它可能是空的）。

为什么用 monotonic 做 deadline
──────────────────────────────
`time.time()` 会被系统改时间/NTP 校时影响，deadline 可能突然"提前"几小时。
超时判定一律用 `time.monotonic()`。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

DEFAULT_SESSION_ID = "default"

_current: ContextVar[Optional["RequestContext"]] = ContextVar(
    "request_context", default=None
)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}" if prefix else uuid.uuid4().hex[:16]


@dataclass(frozen=True)
class RequestContext:
    """一次请求的身份与边界。frozen：任何一环都不许偷偷改别人的上下文。"""

    request_id: str = field(default_factory=new_id)
    session_id: str = DEFAULT_SESSION_ID
    character_id: str = ""
    trace_id: str = ""
    #: monotonic 绝对时刻；None 表示不限时
    deadline: Optional[float] = None
    #: 协作式取消信号（同步线程无法强杀，只能协作退出）
    cancellation: Optional[asyncio.Event] = None
    source: str = "text"

    # ---------- 构造 ----------

    @classmethod
    def create(
        cls,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        character_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
        source: str = "text",
    ) -> "RequestContext":
        return cls(
            request_id=request_id or new_id(),
            session_id=str(session_id) if session_id else DEFAULT_SESSION_ID,
            character_id=str(character_id or ""),
            trace_id=str(trace_id or ""),
            deadline=(time.monotonic() + timeout) if timeout else None,
            # 不论有没有 deadline 都要能取消：调用方不该先判断
            # "这个请求设了超时吗" 才敢调 cancel()
            cancellation=asyncio.Event(),
            source=source,
        )

    def bind(self, **changes: Any) -> "RequestContext":
        """派生子上下文（换 session/角色/加超时），保留 request_id 与 trace。"""
        return replace(self, **changes)

    def with_timeout(self, timeout: float) -> "RequestContext":
        return replace(
            self,
            deadline=time.monotonic() + timeout,
            cancellation=self.cancellation or asyncio.Event(),
        )

    # ---------- 时限与取消 ----------

    def remaining(self) -> Optional[float]:
        """剩余秒数；不限时返回 None；已超时返回 0.0（不返回负数，避免误导）。"""
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

    def expired(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    def cancelled(self) -> bool:
        return bool(self.cancellation is not None and self.cancellation.is_set())

    def cancel(self) -> None:
        if self.cancellation is not None:
            self.cancellation.set()

    def raise_if_expired(self) -> None:
        """在长循环的每一步调用，把"跑太久"变成可解释的错误而不是挂死。"""
        if self.expired():
            from ...api.exceptions import ApiError, CODE_TIMEOUT

            raise ApiError.timeout("请求")

    # ---------- 序列化 ----------

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "character_id": self.character_id,
            "trace_id": self.trace_id,
            "source": self.source,
            "remaining": self.remaining(),
            "cancelled": self.cancelled(),
        }

    def log_prefix(self) -> str:
        """统一日志前缀，便于用 request_id 串起一整条链路（B1-08）。"""
        cid = f" ch={self.character_id}" if self.character_id else ""
        return f"[rid={self.request_id} sid={self.session_id}{cid}]"


# --------------------------------------------------------------------------
# contextvar 存取（仅用于日志/兜底）
# --------------------------------------------------------------------------

def set_current(ctx: Optional[RequestContext]) -> Any:
    return _current.set(ctx)


def reset_current(token: Any) -> None:
    try:
        _current.reset(token)
    except Exception:
        pass


def current() -> Optional[RequestContext]:
    return _current.get()


def current_or_create(**kwargs: Any) -> RequestContext:
    """拿不到就临时造一个——保证调用方永远不用判空。"""
    return _current.get() or RequestContext.create(**kwargs)
