"""日志接口：级别、统计、近期记录、强制落盘。"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional
from fastapi import APIRouter, Query

from ..dto import LogAppendData, LoggerLevelData, LoggerStatsData, LogRecordData
from ..requests import LogAppendRequest, LoggerLevelRequest
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/logger", tags=["logger"])

RECENT_CAPACITY = 200
LOG_APPEND_MAX = 100
MESSAGE_MAX = 4000
STACK_MAX = 12000

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
# 前端 LogLevel -> 后端 logging 级别
LEVEL_ALIASES = {
    "log": "INFO", "trace": "DEBUG", "debug": "DEBUG", "info": "INFO",
    "warn": "WARNING", "warning": "WARNING", "error": "ERROR",
    "critical": "CRITICAL", "fatal": "CRITICAL",
}
LOG_APPEND_FIELDS = frozenset({
    "level", "message", "source", "timestamp", "log_name", "metadata", "stack_trace",
})


class _RecentLogHandler(logging.Handler):
    """只做一件事：把最近 N 条日志留在内存里供 REST 查询。"""

    def __init__(self, capacity: int = RECENT_CAPACITY) -> None:
        super().__init__(level=logging.DEBUG)
        self._lock = threading.Lock()
        self._buf: Deque[Dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "level": record.levelname,
                "message": self.format(record),
                "source": getattr(record, "source", "backend"),
                "ts": record.created,
            }
            if record.exc_info and record.exc_info != (None, None, None):
                import traceback

                entry["stack_trace"] = "".join(
                    traceback.format_exception(*record.exc_info)
                )[:12000]
            with self._lock:
                self._buf.append(entry)
        except Exception:
            pass

    def recent(self, limit: int = 100, level: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._buf)
        if level:
            wanted = level.upper()
            items = [i for i in items if i.get("level", "").upper() == wanted]
        return items[-limit:] if limit > 0 else items

    def add_entry(self, entry: Dict[str, Any]) -> None:
        """前端转发日志直接入环形缓冲，不再回到 console（防回环）。"""
        with self._lock:
            self._buf.append(entry)


_recent_handler: Optional[_RecentLogHandler] = None
_recent_lock = threading.Lock()


def _get_logger():
    from ...logger import get_logger

    return get_logger()


def _ensure_recent_handler() -> _RecentLogHandler:
    """幂等地把环形缓冲挂到应用 logger 上，且能自愈外部 init 造成的解绑。"""
    global _recent_handler
    log = _get_logger()
    root = logging.getLogger(log.app_name)
    with _recent_lock:
        handler = _recent_handler
        if handler is None:
            handler = _RecentLogHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            _recent_handler = handler
        if handler not in root.handlers:
            root.addHandler(handler)
    return handler


async def append_log(payload: LogAppendRequest) -> ApiResponse[LogAppendData]:
    """接收前端 LogForwarder 批量日志（api.md §4.3 / §7 P1）。

    约束：数组上限 100 条、字段白名单、正文/堆栈限长、级别归一；
    `no_frontend_push=true` 时不向前端广播 GET_LOG 事件，避免日志回环。
    """
    records = payload.records if isinstance(payload, LogAppendRequest) else []
    total = len(records)
    if total > LOG_APPEND_MAX:
        raise ApiError.bad_request(f"单次最多 {LOG_APPEND_MAX} 条日志，收到 {total} 条")

    handler = _ensure_recent_handler()
    log = _get_logger()
    accepted = 0
    dropped = 0
    for item in records:
        if not isinstance(item, dict):
            dropped += 1
            continue
        clean = {k: v for k, v in item.items() if k in LOG_APPEND_FIELDS}
        message = str(clean.get("message", "") or "")[:MESSAGE_MAX]
        if not message.strip():
            dropped += 1
            continue
        raw_level = str(clean.get("level", "INFO") or "INFO").upper()
        level = LEVEL_ALIASES.get(raw_level.lower(), raw_level)
        if level not in LEVELS:
            level = "INFO"
        entry = {
            "level": level,
            "message": message,
            "source": str(clean.get("source", "frontend") or "frontend"),
            "ts": clean.get("timestamp") or "",
            "log_name": str(clean.get("log_name", "web_console") or "web_console"),
        }
        stack = str(clean.get("stack_trace", "") or "")[:STACK_MAX]
        if stack:
            entry["stack_trace"] = stack
        handler.add_entry(entry)
        try:
            # 只走文件/控制台，不 emit GET_LOG 事件（no_frontend_push）
            await to_thread(log.log, log.get_logging_level(level), message)
        except Exception:  # noqa: BLE001
            dropped += 1
            continue
        accepted += 1

    return success(
        LogAppendData(
            accepted=accepted, dropped=dropped, total=total,
            no_frontend_push=payload.no_frontend_push if isinstance(payload, LogAppendRequest) else True,
        ),
        message=f"已接收 {accepted} 条日志",
    )

async def get_level() -> ApiResponse[LoggerLevelData]:
    """当前日志级别（统一返回大写，内部以小写规范值存储）。"""
    log = _get_logger()
    level = log.current_level()
    return success(LoggerLevelData(level=level, levels=LEVELS))

async def set_level(payload: LoggerLevelRequest) -> ApiResponse[LoggerLevelData]:
    """设置日志级别 `{"level": "DEBUG"}`。大小写不敏感，兼容 bridge dict。"""
    body = payload if isinstance(payload, LoggerLevelRequest) else (
        LoggerLevelRequest.model_validate(payload or {})
    )
    raw = str(body.level or "").upper()
    raw = LEVEL_ALIASES.get(raw.lower(), raw)
    if raw not in LEVELS:
        raise ApiError.bad_request(f"级别 {raw} 无效，可选: {', '.join(LEVELS)}")

    log = _get_logger()

    def _apply() -> None:
        # 门面方法同时更新 log_level、底层 logging.Logger 与所有 handler 级别
        log.set_level(raw)

    await to_thread(_apply)
    return success(
        LoggerLevelData(level=raw, levels=LEVELS),
        message=f"日志级别已设为 {raw}",
    )

async def list_levels() -> ApiResponse[Dict[str, Any]]:
    return success({"levels": LEVELS})

async def stats() -> ApiResponse[LoggerStatsData]:
    """日志统计：各级别条数、丢弃数、队列长度、文件与消费者状态。"""
    log = _get_logger()
    try:
        data = log.get_stats() or {}
    except Exception:
        data = {}

    by_level = data.get("by_level") or data.get("levels") or {}
    return success(
        LoggerStatsData(
            total=int(data.get("total", 0) or 0),
            dropped=int(data.get("dropped", 0) or 0),
            queue=int(data.get("queue", 0) or 0),
            file_enabled=bool(data.get("file_enabled", False)),
            by_level={str(k).upper(): int(v) for k, v in dict(by_level).items()},
            console_enabled=bool(data.get("console_enabled", True)),
            running=bool(data.get("running", False)),
            event_push_failures=int(data.get("event_push_failures", 0) or 0),
            handler_errors=int(data.get("handler_errors", 0) or 0),
        )
    )

async def records(
    limit: int = Query(100, ge=1, le=RECENT_CAPACITY),
    level: Optional[str] = Query(None, description="按级别过滤，如 ERROR"),
) -> ApiResponse[Dict[str, Any]]:
    """近期日志记录（内存环形缓冲，最多 200 条）。"""
    handler = _ensure_recent_handler()
    items = [
        LogRecordData(**item).model_dump()
        for item in handler.recent(limit=limit, level=level)
    ]
    return success({
        "records": items,
        "total": len(items),
        "capacity": RECENT_CAPACITY,
    })

async def flush() -> ApiResponse[Dict[str, Any]]:
    """强制提交当前批次并等待落盘完成。"""
    log = _get_logger()
    count = await to_thread(log.flush)
    return success({"flushed": count}, message="日志已落盘")
