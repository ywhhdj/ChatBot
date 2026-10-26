"""审计接口（TD9–TD13）。

界面初始化时一次性拿到"能调什么"，用于构建 UI 树：

    GET /api/audit/tree   服务 → 方法 → 参数（带运行状态）
    GET /api/audit/tools  扁平列表，给下拉框 / 自动补全

数据来源是各服务的 `get_tools()`（已是 `ToolFunction`），
不再需要前端一个个试。
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from .._common import to_thread
from ..dto import (
    AuditServiceData,
    AuditTreeData,
)
from ..response import ApiResponse, success

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _tool_to_audit(service: str, tool: Any) -> Dict[str, Any]:
    """兼容 ToolFunction 对象与 dict 两种形态。"""
    if hasattr(tool, "to_audit_dict"):
        d = tool.to_audit_dict()
    elif isinstance(tool, dict):
        d = dict(tool)
    else:
        return {}
    return {
        "service": service,
        "method": str(d.get("name", "") or ""),
        "label": str(d.get("description", "") or d.get("name", "")),
        "parameters": d.get("parameters") or {},
        "required": list(d.get("required") or []),
    }


def _collect() -> Dict[str, Any]:
    from ...manager.service.manager import service_manager

    services: List[Dict[str, Any]] = []
    total = 0
    try:
        for service_id in service_manager.services.keys():
            try:
                svc = service_manager.get_service(service_id)
                info = service_manager.get_service_info(service_id) or {}
            except Exception:  # noqa: BLE001
                continue
            tools_raw = []
            try:
                tools_raw = svc.get_tools() or []
            except Exception:  # noqa: BLE001
                tools_raw = []
            tools = []
            for t in tools_raw:
                d = _tool_to_audit(str(getattr(svc, "name", service_id)), t)
                if d.get("method"):
                    tools.append(d)
            total += len(tools)
            services.append({
                "id": str(service_id),
                "name": str(getattr(svc, "name", service_id) or service_id),
                # TD12：运行状态。注意 S1 之前状态存在类属性上，
                # 一个服务启动所有服务都变 RUNNING —— 已修。
                "running": str(info.get("state", "")).lower() == "running",
                "tools": tools,
            })
    except Exception:  # noqa: BLE001
        pass
    total += len(tools)

    return {
        "services": services, 
        "total_tools": total
    }


# --------------------------------------------------------------------------
# 处理函数（供网关复用）
# --------------------------------------------------------------------------

async def tree() -> ApiResponse[AuditTreeData]:
    data = await to_thread(_collect)
    return success(AuditTreeData(
        services=[AuditServiceData(**s) for s in data["services"]],
        total_tools=int(data["total_tools"]),
    ))


async def tools() -> ApiResponse[Dict[str, Any]]:
    """TD11：扁平版。"""
    data = await to_thread(_collect)
    flat: List[Dict[str, Any]] = []
    for svc in data["services"]:
        for t in svc.get("tools", []):
            flat.append(t)
    flat.extend(data["skills"])
    return success({"tools": flat, "total": len(flat)})


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------

@router.get("/tree", response_model=ApiResponse[AuditTreeData])
async def _tree() -> ApiResponse[AuditTreeData]:
    return await tree()


@router.get("/tools", response_model=ApiResponse[Dict[str, Any]])
async def _tools() -> ApiResponse[Dict[str, Any]]:
    return await tools()
