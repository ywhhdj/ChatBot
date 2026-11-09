"""执行轨迹（低基数结构化留痕）"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict

_TRAIL_DIR_MARKERS = ("/trail/", "\\trail\\", "/audit/", "\\audit\\")
_TRAIL_SUFFIXES = (".trail", ".trail.jsonl", ".audit", ".audit.jsonl")

#: 只记这些键，任何正文 / 命令原文 / 输出都不进轨迹
_ALLOWED_KEYS = frozenset({
    "source", "actor", "decision", "result", "reason_code",
    "program", "service", "op", "service_id", "request_id",
    "session_id", "duration_ms", "status", "provider",
})


def is_trail_path(path: Any) -> bool:
    """轨迹/审计文件路径判定（大小写与分隔符不敏感）。"""
    raw = str(path or "").replace("\\", "/").lower()
    if not raw:
        return False
    if any(marker in raw for marker in _TRAIL_DIR_MARKERS):
        return True
    if raw.endswith(_TRAIL_SUFFIXES):
        return True
    basename = os.path.basename(raw)
    return basename in ("trail", "trail.jsonl", "audit.jsonl", "audit.log")


def _low_cardinality(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in _ALLOWED_KEYS:
        value = kwargs.get(key)
        if value is None:
            continue
        text = str(value)
        # 拒绝换行与控制字符，避免日志行注入
        if any(ch in text for ch in ("\n", "\r", "\x00")):
            text = text.replace("\n", "_").replace("\r", "_").replace("\x00", "")
        out[key] = text[:120]
    metadata = kwargs.get("metadata")
    if isinstance(metadata, dict):
        try:
            from .audit import _sanitize_metadata

            out["metadata"] = _sanitize_metadata(metadata)
        except Exception:  # noqa: BLE001
            out["metadata"] = {"keys": len(metadata)}
    return out


def record(action: Any, **kwargs: Any) -> Dict[str, Any]:
    """写一条轨迹，返回实际写入的字典（便于离线校验）。"""
    entry = {
        "ts": time.time(),
        "action": str(action or "")[:120].replace("\n", "_"),
        **_low_cardinality(kwargs),
    }
    try:
        from . import logger as _logger_instance

        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        try:
            _logger_instance.info(f"[TRAIL] {line}")
        except AttributeError:
            import logging

            logging.getLogger("trail").info("[TRAIL] %s", line)
    except Exception:  # noqa: BLE001
        pass
    return entry


__all__ = ["record", "is_trail_path"]
