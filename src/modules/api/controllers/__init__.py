"""控制器集合：路由由 endpoints.json 驱动生成。

WebSocket 路由不在这里——`websocket` 用 FastAPI 的 WebSocket API，
loader 只负责 HTTP。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..loader import get_loader


def all_routers() -> list[APIRouter]:
    return [get_loader().build_router()]


def register_all_routers(app, prefix: str = "/api") -> None:
    router = get_loader().build_router()
    # 去重：迁移期 controller 里可能还保留旧的 router
    src = get_loader().build_router()
    existing = {
        (r.path, m)
        for r in app.routes
        if hasattr(r, "path") and hasattr(r, "methods")
        for m in (r.methods or [])
    }
    sub = APIRouter()
    for route in src.routes:
        methods = list(route.methods or []) # type: ignore
        normalized = f"{prefix}{route.path}" # type: ignore
        if any((normalized, m) in existing for m in methods):
            from ...logger import logger
            logger.warning(f"[API] 跳过重复路由: {methods} {route.path}") # type: ignore
            continue
        sub.routes.append(route)
        for m in methods:
            existing.add((normalized, m))
    app.include_router(sub, prefix=prefix)