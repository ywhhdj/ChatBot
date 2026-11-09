"""日志接口：级别、统计、近期记录、强制落盘。"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional
from fastapi import APIRouter, Query

from ..dto import LoggerLevelData, LoggerStatsData, LogRecordData
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/logger", tags=["logger"])

RECENT_CAPACITY = 200

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


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


# @router.post("/append", response_model=ApiResponse[None])
# async def append_log(payload: list) -> ApiResponse[None]:
#     """追加日志。"""
#     log = _get_logger()
#     for item in payload:
#         log.log(log.get_logging_level(item.get("level", "INFO")), item.get("message", ""))
#     return success(message="日志已追加")

async def get_level() -> ApiResponse[LoggerLevelData]:
    """当前日志级别（统一返回大写，内部以小写规范值存储）。"""
    log = _get_logger()
    level = log.current_level()
    return success(LoggerLevelData(level=level, levels=LEVELS))

async def set_level(payload: Dict[str, Any]) -> ApiResponse[LoggerLevelData]:
    """设置日志级别 `{"level": "DEBUG"}`。大小写不敏感。"""
    body = payload if isinstance(payload, dict) else {}
    raw = str(body.get("level", "") or "").upper()
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
