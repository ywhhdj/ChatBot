"""API 控制器集合。

对外只暴露一个入口：`register_all_routers(app)`。
server.py 不再逐个 import，避免新增 controller 时忘记注册。

命名兼容：server.py 早期版本里用的是 `req_router` / `logger_router` /
`service_router` / `pipeline_router`，这里保留同名别名。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

def all_routers() -> List[APIRouter]:
    """全部业务路由（WebSocket 由 `controllers.websocket` 单独注册）"""
    from .character import router as character_router
    from .config import router as config_router
    from .logger import router as logger_router
    from .memory import router as memory_router
    from .pipline import router as pipeline_router
    from .request import router as req_router
    from .save import router as save_router
    from .service import router as service_router
    from .session import router as session_router
    from .skill import router as skill_router
    from .system import router as system_router
    from .task import router as task_router
    from .device import router as device_router
    from .ppt import router as ppt_router
    from .audit import router as audit_router
    return [
        system_router,
        config_router,
        pipeline_router,
        req_router,
        service_router,
        logger_router,
        session_router,
        save_router,
        character_router,
        memory_router,
        skill_router,
        task_router,
        device_router,
        ppt_router,
        audit_router,
    ]


def register_all_routers(app, prefix: str = "/api") -> None:
    for r in all_routers():
        app.include_router(r, prefix=prefix)
