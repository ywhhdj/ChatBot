"""网关 op 注册：由 endpoints.json 驱动。"""
from __future__ import annotations

from ..logger import logger
from .loader import get_loader

_REGISTERED = False


def register_all() -> int:
    global _REGISTERED
    if _REGISTERED:
        return len(get_loader().specs)
    count = get_loader().register_gateway()
    _REGISTERED = True
    logger.info(f"[Gateway] 已注册 {count} 个 op")
    return count


__all__ = ["register_all"]