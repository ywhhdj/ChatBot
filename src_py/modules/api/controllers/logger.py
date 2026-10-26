"""日志接口：级别读写、统计、近期记录、强制落盘。"""

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
    """幂等地把环形缓冲挂到应用 logger 上。"""
    global _recent_handler
    if _recent_handler is not None:
        return _recent_handler

    with _recent_lock:
        if _recent_handler is None:
            handler = _RecentLogHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            log = _get_logger()
            try:
                root = logging.getLogger(log.app_name)
                root.addHandler(handler)
            except Exception:
                pass
            _recent_handler = handler
    return _recent_handler


# @router.post("/append", response_model=ApiResponse[None])
# async def append_log(payload: list) -> ApiResponse[None]:
#     """追加日志。"""
#     log = _get_logger()
#     for item in payload:
#         log.log(log.get_logging_level(item.get("level", "INFO")), item.get("message", ""))
#     return success(message="日志已追加")


@router.get("/level", response_model=ApiResponse[LoggerLevelData])
async def get_level() -> ApiResponse[LoggerLevelData]:
    """当前日志级别。"""
    log = _get_logger()
    level = str(getattr(log, "log_level", "INFO") or "INFO").upper()
    return success(LoggerLevelData(level=level, levels=LEVELS))


@router.put("/level", response_model=ApiResponse[LoggerLevelData])
async def set_level(payload: Dict[str, Any]) -> ApiResponse[LoggerLevelData]:
    """设置日志级别 `{"level": "DEBUG"}`。

    同时更新底层 `logging.Logger` 与门面的 `log_level`，
    否则下次 `init()` 会把级别改回去。
    """
    raw = str((payload or {}).get("level", "") or "").upper()
    if raw not in LEVELS:
        raise ApiError.bad_request(f"级别 {raw} 无效，可选: {', '.join(LEVELS)}")

    log = _get_logger()

    def _apply() -> None:
        numeric = log.get_logging_level(raw)
        log.log_level = raw
        root = logging.getLogger(log.app_name)
        root.setLevel(numeric)
        for h in getattr(root, "handlers", []):
            try:
                h.setLevel(numeric)
            except Exception:
                pass
        handler_fn = getattr(log, "setLevel", None)
        if callable(handler_fn):
            try:
                handler_fn(numeric)
            except Exception:
                pass

    await to_thread(_apply)
    return success(LoggerLevelData(level=raw, levels=LEVELS), message=f"日志级别已设为 {raw}")


@router.get("/levels", response_model=ApiResponse[Dict[str, Any]])
async def list_levels() -> ApiResponse[Dict[str, Any]]:
    return success({"levels": LEVELS})


@router.get("/stats", response_model=ApiResponse[LoggerStatsData])
async def stats() -> ApiResponse[LoggerStatsData]:
    """日志统计：各级别条数、丢弃数、队列长度。"""
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
            by_level={str(k): int(v) for k, v in dict(by_level).items()},
        )
    )


@router.get("/records", response_model=ApiResponse[Dict[str, Any]])
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


@router.post("/flush", response_model=ApiResponse[Dict[str, Any]])
async def flush() -> ApiResponse[Dict[str, Any]]:
    """强制落盘当前批次。"""
    log = _get_logger()

    def _flush() -> int:
        count = 0
        for h in log.handlers:
            fn = getattr(h, "flush", None)
            if callable(fn):
                fn()
                count += 1
        return count

    count = await to_thread(_flush)
    return success({"flushed": count}, message="日志已落盘")