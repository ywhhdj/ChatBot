"""系统接口：健康检查、应用信息、运行统计、手动 GC。

对应 api文档.md 第 1 节。
"""

from __future__ import annotations

import platform
import sys
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from ..requests import GcRequest
from ..dto import (
    GcData,
    HealthData,
    InfoData,
    StatsData,
)
from ..response import ApiResponse, success
from .._common import get_schedular, schedular_running, to_thread

router = APIRouter(prefix="/system", tags=["system"])

_STARTED_AT = time.time()


def _schedular_stats() -> Dict[str, Any]:
    try:
        s = get_schedular()
        status = s.status or {}
        pending = 0
        tasks = s.tasks or {}
        for t in tasks.values():
            st = t.status
            if st in ("pending", "running"):
                pending += 1
        return {
            "running": schedular_running(),
            "pending": pending,
            "running_tasks": pending,
            "submitted": status.get("submitted", 0),
            "done": status.get("completed", 0),
            "failed": status.get("failed", 0),
            "streams": len(getattr(s, "_streams", {}) or {}),
        }
    except Exception:
        return {"running": False, "pending": 0, "running_tasks": 0}


def _main_thread_stats() -> Dict[str, Any]:
    try:
        from ...ui.dispatcher import get_main_thread_dispatcher

        d = get_main_thread_dispatcher()
        queue = getattr(d, "_queue", None)
        size = 0
        try:
            size = queue.qsize() # type:ignore
        except Exception:
            pass
        return {
            "ready": True,
            "queue": size
        }
    except Exception:
        return {
            "ready": False,
            "queue": 0
        }


def _memory_stats() -> Dict[str, Any]:
    try:
        from ...memory.main import HybridMemorySystem

        sysm = HybridMemorySystem.instance()
        # 单例未初始化时不要触发 __init__（会建立 embedding / 后端）
        if not getattr(sysm, "_initialized", False):
            return {"ready": False, "records": 0}
        storage = getattr(sysm, "storage", None)
        records = 0
        try:
            memories = getattr(storage, "memories", None)
            if memories is not None:
                records = len(memories)
        except Exception:
            pass
        return {
            "ready": True,
            "records": records
        }
    except Exception:
        return {
            "ready": False,
            "records": 0
        }


def _services_stats() -> Dict[str, Any]:
    try:
        from ...manager.service.manager import service_manager

        infos = service_manager.get_all_service_infos() or []
        running = sum(
            1 for i in infos if str(i.get("state", "")).lower().endswith("running")
        )
        return {"total": len(infos), "running": running}
    except Exception:
        return {"total": 0, "running": 0}


@router.get("/health", response_model=ApiResponse[HealthData])
async def health() -> ApiResponse[HealthData]:
    """健康检查：Web / 调度器 / 主线程 / 记忆 / 服务。"""
    from ..server import get_web

    try:
        web = get_web()
        web_info = {
            "ready": web.is_ready,
            "host": getattr(web, "host", "") or "",
            "port": getattr(web, "port", 0) or 0,
        }
    except Exception:
        web_info = {"ready": True, "host": "", "port": 0}

    sched = _schedular_stats()
    main_thread = _main_thread_stats()
    memory = _memory_stats()
    services = _services_stats()

    degraded = []
    if not sched.get("running"):
        degraded.append("scheduler")
    if not main_thread.get("ready"):
        degraded.append("main_thread")
    if not memory.get("ready"):
        degraded.append("memory")

    status = "healthy" if not degraded else ("degraded" if len(degraded) < 3 else "unhealthy")

    return success(
        HealthData(
            status=status,
            web=web_info,
            scheduler=sched,
            main_thread=main_thread,
            memory=memory,
            services=services,
        )
    )


@router.get("/info", response_model=ApiResponse[InfoData])
async def info() -> ApiResponse[InfoData]:
    """应用信息：版本、路径、运行时。"""
    from ...config import get_config
    from ...runtime import RuntimePath

    try:
        config = get_config()
        log_dir = str(config.log.log_dir)
    except Exception:
        log_dir = ""

    try:
        data_dir = str(RuntimePath.get_user_data_path(""))
    except Exception:
        data_dir = ""

    adapters: Dict[str, Any] = {}
    try:
        from ...manager.pipeline import PipelineManager

        pm = PipelineManager.__new__(PipelineManager)
        if getattr(pm, "_initialized", False):
            adapters = pm.get_pipeline_all_configs() or {}
    except Exception:
        pass

    return success(
        InfoData(
            version="0.1.0",
            config_path=str(getattr(RuntimePath, "CONFIG_PATH", "")),
            data_dir=data_dir,
            log_dir=log_dir,
            python=sys.version.split()[0],
            adapters={k: list(v.keys()) for k, v in adapters.items()} if isinstance(adapters, dict) else {},
        )
    )


@router.get("/stats", response_model=ApiResponse[StatsData])
async def stats() -> ApiResponse[StatsData]:
    """运行统计：日志、调度器、WebSocket、记忆。"""
    log_stats: Dict[str, Any] = {}
    try:
        from ...logger import get_logger

        log_stats = get_logger().get_stats() or {}
    except Exception:
        pass

    ws_stats: Dict[str, Any] = {}
    try:
        from ...manager.websocket.manager import get_websocket_manager

        mgr = get_websocket_manager()
        conns = getattr(mgr, "active_connections", None) or {}
        ws_stats = {"connections": len(conns)}
    except Exception:
        ws_stats = {"connections": 0}

    mem = _memory_stats()
    sched = _schedular_stats()

    return success(
        StatsData(
            uptime_sec=round(time.time() - _STARTED_AT, 3),
            log=log_stats,
            scheduler=sched,
            websocket=ws_stats,
            memory={
                "records": mem.get("records", 0),
            },
        )
    )


@router.post("/gc", response_model=ApiResponse[GcData])
async def gc(payload: Optional[GcRequest] = None) -> ApiResponse[GcData]:
    """触发一次清理：记忆衰减 + 排空日志/记忆写入。

    GC 涉及文件 IO 与可能的模型调用，全部走线程池，不占 Web loop。
    """
    payload = payload or GcRequest()
    result = GcData()

    if payload.decay:
        try:
            from ...memory.main import HybridMemorySystem

            sysm = HybridMemorySystem.instance()
            if sysm and getattr(sysm, "_initialized", False):
                await sysm.decay_now()
                result.decay = True
        except Exception as e:
            from ...logger import logger

            logger.warning(f"[API] gc decay failed: {e}")

    if payload.flush_log:
        try:
            from ...logger import get_logger

            def _flush():
                for h in get_logger().handlers:
                    flush = getattr(h, "flush", None)
                    if flush:
                        flush()

            await to_thread(_flush)
            result.log_flushed = True
        except Exception:
            pass

    if payload.flush_memory:
        try:
            from ...memory.main import HybridMemorySystem

            sysm = HybridMemorySystem.instance()
            if sysm and getattr(sysm, "_initialized", False):
                await sysm.flush_background(timeout=5.0)
                result.memory_flushed = True
        except Exception:
            pass

    return success(result)


@router.get("/ping")
async def ping() -> ApiResponse[str]:
    """最简探活（不查任何子系统）。"""
    return success("pong")