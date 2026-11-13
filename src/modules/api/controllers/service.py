"""服务接口：列表、详情、工具定义、启停、配置读写、UI 描述。

本次修复
────────
* `start_service` 原先把"已注册"当作可启动条件、并在注册前读取服务状态，
  必然在首次启动时抛错；现改为未注册才注册、已运行才拒绝。
* 服务管理器导入改为正式路径 `modules.services.manager`。
* 补齐 `ppt` / `shell` 服务的注册分支。
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query

from ...keys import ServiceKeys

from ..requests import (
    ServiceConfigUpdateRequest,
    ServiceStartRequest,
)
from ..dto import (
    ServiceActionData,
    ServiceInfoData,
    ServiceListData,
    ServiceUIDescription,
    ToolData
)
from ..response import ApiError, ApiResponse, success
from .._common import state_name, to_thread

router = APIRouter(prefix="/service", tags=["service"])


def _sm():
    from ...services.manager import service_manager

    return service_manager


def _info_with_id(service_id: str) -> ServiceInfoData:
    sm = _sm()
    info = sm.get_service_info(service_id)
    if info is None:
        raise ApiError.not_found(f"服务 {service_id}")
    return ServiceInfoData(
        id=service_id,
        name=str(info.get("name", "") or ""),
        description=str(info.get("description", "") or ""),
        state=state_name(info.get("state")),
        main_thread=bool(info.get("main_thread", False)),
        config=info.get("config"),
    )


@router.get("", response_model=ApiResponse[ServiceListData])
async def list_services(
    running_only: bool = Query(False, description="只返回运行中的服务"),
) -> ApiResponse[ServiceListData]:
    """服务列表。"""
    sm = _sm()
    services = [_info_with_id(sid) for sid in (sm.services.keys() or [])]
    if running_only:
        services = [s for s in services if s.state == "running"]
    return success(ServiceListData(services=services, total=len(services)))


@router.get("/tools", response_model=ApiResponse[ToolData])
async def list_tools() -> ApiResponse[ToolData]:
    """所有服务暴露的工具定义（OpenAI function 格式）。"""
    sm = _sm()
    try:
        tools = sm.get_tools() or []
    except Exception as e:
        raise ApiError.internal(f"获取工具失败: {e}")
    return success(ToolData(
        services={"tools": tools},
        total=len(tools)
    ))


@router.get("/{service_id}", response_model=ApiResponse[ServiceInfoData])
async def get_service(service_id: str) -> ApiResponse[ServiceInfoData]:
    """单个服务详情。"""
    return success(_info_with_id(service_id))


@router.get("/{service_id}/tools", response_model=ApiResponse[ToolData])
async def service_tools(service_id: str) -> ApiResponse[ToolData]:
    """某个服务的工具定义。"""
    sm = _sm()
    if not sm.is_registered(service_id):
        raise ApiError.not_found(f"服务 {service_id}")
    try:
        tools = sm.get_service_tool(service_id)
    except Exception as e:
        raise ApiError.internal(f"获取工具失败: {e}")
    if isinstance(tools, list):
        items = tools
    else:
        items = [tools] if tools else []
    return success(ToolData(services={"tools": items}, total=len(items)))


@router.get("/{service_id}/ui", response_model=ApiResponse[ServiceUIDescription])
async def service_ui(service_id: str) -> ApiResponse[ServiceUIDescription]:
    """UI 描述，供前端生成控制面板。"""
    sm = _sm()
    try:
        desc = sm.get_ui_service_description(service_id)
    except Exception as e:
        raise ApiError.internal(f"获取 UI 描述失败: {e}")
    return success(ServiceUIDescription(**desc))


def register_service(service_id: str, payload: Optional[Dict[str, Any]] = None):
    """按需实例化并注册服务（`@Service` 装饰器在 __init__ 时完成注册）。"""
    sm = _sm()
    if service_id == ServiceKeys.BROWSER:
        from ...services.browser.browser import Browser
        sm.register_service(ServiceKeys.BROWSER, Browser(**(payload or {})))
    elif service_id == ServiceKeys.OBS:
        from ...services.obs.client import OBSClient
        sm.register_service(ServiceKeys.OBS, OBSClient(**(payload or {})))
    elif service_id == ServiceKeys.QQBOT:
        from ...services.qqbot.client import QQBotClient
        sm.register_service(ServiceKeys.QQBOT, QQBotClient(**(payload or {})))
    elif service_id == ServiceKeys.LIVE2D:
        from ...services.live2d.views import Live2DView
        sm.register_service(ServiceKeys.LIVE2D, Live2DView(**(payload or {})))
    elif service_id == ServiceKeys.SHELL:
        from ...services.shell.service import ShellService
        sm.register_service(ServiceKeys.SHELL, ShellService(**(payload or {})))
    elif service_id == ServiceKeys.PPT:
        from ...services.ppt.service import PptService
        # PptService 不接受任意关键字，配置从服务配置读取
        sm.register_service(ServiceKeys.PPT, PptService())
    else:
        raise ApiError.not_found(f"服务 {service_id}")


@router.post("/{service_id}/start", response_model=ApiResponse[ServiceActionData])
async def start_service(
    service_id: str,
    payload: Optional[ServiceStartRequest] = None,
) -> ApiResponse[ServiceActionData]:
    """启动服务。

    服务启动可能拉起线程 / 建立连接，放在线程池执行。
    兼容 desktop bridge 传入的 dict（契约适配层会转成 DTO）。
    """
    kwargs = (
        payload.kwargs
        if isinstance(payload, ServiceStartRequest)
        else (payload if isinstance(payload, dict) else None)
    ) or {}
    sm = _sm()
    if not sm.is_registered(service_id):
        register_service(service_id, kwargs)
    else:
        current = state_name(sm.get_service_state(service_id))
        if current == "running":
            raise ApiError.conflict(f"服务 {service_id} 已在运行")

    ok = await to_thread(sm.start_service, service_id, **kwargs)
    if not ok:
        raise ApiError.internal(f"服务 {service_id} 启动失败")

    return success(
        ServiceActionData(id=service_id, state="running"),
        message=f"服务 {service_id} 已启动",
    )


@router.post("/{service_id}/stop", response_model=ApiResponse[ServiceActionData])
async def stop_service(service_id: str) -> ApiResponse[ServiceActionData]:
    """停止服务。"""
    sm = _sm()
    if not sm.is_registered(service_id):
        raise ApiError.not_found(f"服务 {service_id}")

    await to_thread(sm.stop_service, service_id)
    return success(
        ServiceActionData(id=service_id, state=state_name(sm.get_service_state(service_id))),
        message=f"服务 {service_id} 已停止",
    )


@router.get("/{service_id}/config", response_model=ApiResponse[Dict[str, Any]])
async def get_config(service_id: str) -> ApiResponse[Dict[str, Any]]:
    """读取服务配置。"""
    sm = _sm()
    if not sm.is_registered(service_id):
        raise ApiError.not_found(f"服务 {service_id}")
    try:
        cfg = sm.get_service_config(service_id)
    except Exception as e:
        raise ApiError.internal(f"读取配置失败: {e}")
    if hasattr(cfg, "to_dict"):
        cfg = cfg.to_dict()
    return success({"id": service_id, "config": cfg})


@router.put("/{service_id}/config", response_model=ApiResponse[Dict[str, Any]])
async def update_config(
    service_id: str,
    payload: ServiceConfigUpdateRequest,
) -> ApiResponse[Dict[str, Any]]:
    """更新服务配置；service_id 以路径参数为准，忽略 body 里的同名字段。"""
    sm = _sm()
    body = (
        payload.config
        if isinstance(payload, ServiceConfigUpdateRequest)
        else dict(payload or {})
    )

    ok = await to_thread(
        sm.update_service_config, service_id, body or None
    )
    if not ok:
        raise ApiError.internal(f"服务 {service_id} 配置更新失败")

    cfg = sm.get_service_config(service_id)
    if hasattr(cfg, "to_dict"):
        cfg = cfg.to_dict()
    return success({
        "id": service_id,
        "config": cfg
    }, message="配置已更新")


# 应用服务配置需先保存配置，再停止服务，再启动服务
@router.put("/{service_id}/config/apply", response_model=ApiResponse[Dict[str, Any]])
async def apply_config(
    service_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> ApiResponse[Dict[str, Any]]:
    """应用服务配置。"""
    sm = _sm()
    if not sm.is_registered(service_id):
        raise ApiError.not_found(f"服务 {service_id}")
    try:
        cfg = sm.set_service_config(service_id, payload or {})
        await to_thread(sm.stop_service, service_id)
        await to_thread(sm.start_service, service_id)
    except Exception as e:
        raise ApiError.internal(f"应用配置失败: {e}")
    return success({
        "id": service_id,
        "config": cfg
    }, message="配置已应用")
