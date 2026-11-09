"""结构化审计事件

设计约束
────────
* 只记动作 / 资源 ID / 计数 / 稳定原因码，不记正文、prompt、密钥；
  metadata 统一做脱敏、截断、键数上限与换行注入防护；
* 事件不可变（frozen dataclass），字段见 ``AuditEvent.to_dict()``；
* **审计失败绝不影响业务**：sink 异常、日志异常、缓冲满都只计数；
* 缓冲有界（``MAX_BUFFERED``），提供 dropped 计数；
* 只依赖标准库，可在没有 pydantic / Rust 内核的环境里独立导入。

"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

SCHEMA_VERSION = "1.0"
SCRUBBED = "[REDACTED]"
MAX_METADATA_KEYS = 24
MAX_BUFFERED = 512
MAX_VALUE_CHARS = 200

#: 键名命中即把值整体替换为 SCRUBBED（大小写/连字符不敏感）。
_SECRET_KEYS = frozenset({
    "api_key", "apikey", "token", "access_token", "user_token",
    "password", "passwd", "secret", "secret_key", "secret_value",
    "client_secret", "access_key", "authorization", "cookie",
    "credential", "credentials", "private_key",
})
_SECRET_SUFFIXES = ("_key", "_token", "_secret", "_password", "_credential")

#: 这些键只记长度 + 短 hash，不记内容（私人对话 / prompt / 工具正文）。
_PRIVATE_KEYS = frozenset({
    "content", "message", "messages", "text", "body", "prompt",
    "response", "answer", "transcript", "audio", "image", "raw",
})


class Action(str, Enum):
    CONFIG_CHANGE = "config.change"
    SECRET_CHANGE = "secret.change"
    MEMORY_DELETE = "memory.delete"
    MEMORY_GC_APPLY = "memory.gc_apply"
    MEMORY_RETENTION = "memory.retention"
    MEMORY_PIN = "memory.pin"
    MEMORY_REVIVE = "memory.revive"
    SNAPSHOT_PUBLISH = "snapshot.publish"
    SNAPSHOT_RESTORE = "snapshot.restore"
    TASK_FINISH = "task.finish"
    TOOL_INVOKE = "tool.invoke"
    TOOL_DENIED = "tool.denied"
    TOOL_BUDGET_EXHAUSTED = "tool.budget_exhausted"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class Result(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class Source(str, Enum):
    API = "api"
    UI = "ui"
    TASK = "task"
    RECOVERY = "recovery"
    SERVICE = "service"


class ResourceType(str, Enum):
    MEMORY = "memory"
    SAVE = "save"
    TOOL = "tool"
    CONFIG = "config"
    FILE = "file"


def _as_str(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "")


@dataclass(frozen=True)
class Resource:
    """只带不透明 ID 与计数，绝不携带正文。"""

    type: str = ""
    id: str = ""
    count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"type": _as_str(self.type)}
        if self.id:
            out["id"] = str(self.id)[:MAX_VALUE_CHARS]
        if self.count:
            out["count"] = int(self.count)
        return out


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    ts: float
    action: str
    request_id: str = ""
    session_id: str = ""
    parent_request_id: str = ""
    task_id: str = ""
    resource: Dict[str, Any] = field(default_factory=dict)
    decision: str = Decision.ALLOW.value
    result: str = Result.SUCCESS.value
    reason_code: str = ""
    source: str = Source.API.value
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ts": self.ts,
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "parent_request_id": self.parent_request_id,
            "task_id": self.task_id,
            "action": self.action,
            "resource": dict(self.resource or {}),
            "decision": self.decision,
            "result": self.result,
            "reason_code": self.reason_code,
            "source": self.source,
            "metadata": dict(self.metadata or {}),
        }


# --------------------------------------------------------------------------
# 脱敏
# --------------------------------------------------------------------------

def _is_secret_key(key: Any) -> bool:
    name = str(key or "").strip().lower().replace("-", "_")
    if not name:
        return False
    # secret_name 只记"改了哪个密钥"，是有意义的低基数信息，不能抹掉
    if name in ("secret_name", "key_name", "credential_name"):
        return False
    if name in _SECRET_KEYS:
        return True
    return name.endswith(_SECRET_SUFFIXES)


def _digest(value: str) -> Dict[str, Any]:
    raw = str(value)
    return {
        "len": len(raw),
        "sha256": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16],
    }


def _safe_value(key: Any, value: Any) -> Any:
    """单个 metadata 值：密钥抹除 → 正文哈希化 → 换行替换 → 长度截断。"""
    name = str(key or "")
    if value is None:
        return None
    if _is_secret_key(name):
        return SCRUBBED
    if not isinstance(value, (str, int, float, bool)):
        # 嵌套结构整体降级，避免把任意对象 / 正文塞进审计日志
        return _digest(str(value)[:MAX_VALUE_CHARS * 4])
    text = str(value)
    if name.lower() in _PRIVATE_KEYS and text:
        return _digest(text)
    if "\n" in text or "\r" in text:
        # 换行可伪造整条日志行；整值替换而不是"只删换行"
        return {**_digest(text), "reason": "newline_rejected"}
    if len(text) > MAX_VALUE_CHARS:
        return text[:MAX_VALUE_CHARS] + "…[truncated]"
    return value


def _sanitize_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    out: Dict[str, Any] = {}
    kept = 0
    skipped = 0
    for key, value in metadata.items():
        if kept >= MAX_METADATA_KEYS:
            skipped += 1
            continue
        safe_key = str(key)[:64].replace("\n", "_").replace("\r", "_")
        out[safe_key] = _safe_value(key, value)
        kept += 1
    if skipped:
        out["_truncated_keys"] = skipped
    return out


# --------------------------------------------------------------------------
# 事件构造 / 分发
# --------------------------------------------------------------------------

def build_event(
    action: Any,
    *,
    request_id: str = "",
    session_id: str = "",
    parent_request_id: str = "",
    task_id: str = "",
    resource: Optional[Resource] = None,
    decision: Any = Decision.ALLOW,
    result: Any = Result.SUCCESS,
    reason_code: str = "",
    source: Any = Source.API,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    """构造一条不可变审计事件。不写日志、不分发，便于离线校验。"""
    return AuditEvent(
        event_id=uuid.uuid4().hex,
        ts=time.time(),
        action=_as_str(action),
        request_id=str(request_id or "")[:MAX_VALUE_CHARS],
        session_id=str(session_id or "")[:MAX_VALUE_CHARS],
        parent_request_id=str(parent_request_id or "")[:MAX_VALUE_CHARS],
        task_id=str(task_id or "")[:MAX_VALUE_CHARS],
        resource=resource.to_dict() if isinstance(resource, Resource) else {},
        decision=_as_str(decision) or Decision.ALLOW.value,
        result=_as_str(result) or Result.SUCCESS.value,
        # 原因码严格低基数：只留 ASCII 字母数字 / 点 / 下划线
        reason_code="".join(
            ch for ch in str(reason_code or "")
            if ch.isascii() and (ch.isalnum() or ch in "._-")
        )[:64],
        source=_as_str(source) or Source.API.value,
        metadata=_sanitize_metadata(metadata),
        schema_version=SCHEMA_VERSION,
    )


_lock = threading.RLock()
_buffer: "deque[Dict[str, Any]]" = deque(maxlen=MAX_BUFFERED)
_dropped = 0
_sinks: List[Callable[[AuditEvent], Any]] = []


def _log_event(event: AuditEvent) -> None:
    """审计事件走独立结构化日志通道；日志不可用也不能影响业务。"""
    try:
        from . import logger as _logger_instance  # noqa: F401  (logger/__init__.py)

        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        try:
            _logger_instance.info(f"[AUDIT] {line}")
        except AttributeError:
            # 某些部署把 logger 换成包而非实例时，退回标准 logging
            import logging

            logging.getLogger("audit").info("[AUDIT] %s", line)
    except Exception:  # noqa: BLE001
        pass


def emit(event: AuditEvent) -> AuditEvent:
    """写入有界缓冲并分发给所有 sink。任何 sink 失败都被吞掉。"""
    global _dropped
    payload = event.to_dict()
    with _lock:
        if len(_buffer) >= MAX_BUFFERED:
            _dropped += 1
        _buffer.append(payload)
        sinks = list(_sinks)
    _log_event(event)
    for sink in sinks:
        try:
            sink(event)
        except Exception:  # noqa: BLE001
            pass
    return event


def record(action: Any, **kwargs: Any) -> AuditEvent:
    """构造 + 分发。即使 sink 全部失败也返回事件对象。"""
    try:
        event = build_event(action, **kwargs)
    except Exception:  # noqa: BLE001 - 审计绝不把异常抛回业务
        event = AuditEvent(
            event_id=uuid.uuid4().hex,
            ts=time.time(),
            action=_as_str(action),
        )
    return emit(event)


def register_sink(fn: Callable[[AuditEvent], Any]) -> None:
    if callable(fn):
        with _lock:
            _sinks.append(fn)


def clear_sinks() -> None:
    with _lock:
        _sinks.clear()


def reset() -> None:
    """清空缓冲 / 计数 / sink，供测试与热重载使用。"""
    global _dropped
    with _lock:
        _buffer.clear()
        _dropped = 0
        _sinks.clear()


def recent(limit: int = 20) -> List[Dict[str, Any]]:
    n = max(0, min(int(limit or 0), MAX_BUFFERED))
    with _lock:
        rows = list(_buffer)
    return [dict(row) for row in rows[-n:][::-1]] if n else []


def stats() -> Dict[str, Any]:
    with _lock:
        return {
            "buffered": len(_buffer),
            "dropped": _dropped,
            "sinks": len(_sinks),
            "max_buffered": MAX_BUFFERED,
            "schema_version": SCHEMA_VERSION,
        }


__all__ = [
    "Action", "Decision", "Result", "Source", "ResourceType", "Resource",
    "AuditEvent", "build_event", "emit", "record", "register_sink",
    "clear_sinks", "reset", "recent", "stats",
    "SCHEMA_VERSION", "SCRUBBED", "MAX_METADATA_KEYS", "MAX_BUFFERED",
]
