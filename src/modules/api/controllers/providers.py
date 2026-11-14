"""供应商适配器接口：查看可选 provider、切换、关闭"""

from __future__ import annotations
import asyncio
import uuid
from typing import Dict, Optional,Any
from fastapi import Query

from ..dto import DownloadStartData, ProviderStatusData,AdapterInfo, SwitchResultData
from ..requests import ProviderDownloadRequest,ProviderSwitchRequest
from ..response import success, ApiError, CODE_BAD_REQUEST, CODE_NOT_FOUND,ApiResponse
from ...logger import logger
from .._common import mask_config, to_thread
from ...providers.manager import provider_manager
from ...providers.adapters.registry import SECRET_KEYS

#: 正在下载的任务：key=(capability, provider, model_id)，value=task_id
_download_inflight: Dict[tuple, str] = {}
_download_lock = asyncio.Lock()

_SECRET_KEYS = tuple(sorted(SECRET_KEYS))


def _manager():
    from ...providers.manager import provider_manager

    pm = provider_manager
    try:
        if not pm.get_pipeline_all_configs():
            pm.load_config()
    except Exception:  # noqa: BLE001
        pm.load_config()
    return pm

async def list_describe() -> ApiResponse[Dict[str, Any]]:
    """列出所有能力、可选 providers、当前 providers / 模型与累计用量。"""
    described = _manager().describe()
    out: Dict[str, Any] = {}
    for key, info in (described.get("adapters") or {}).items():
        out[key] = {
            **AdapterInfo(
                type=key,
                providers=list(info.get("providers") or []),
                current=info.get("current"),
            ).model_dump(),
            "model": info.get("model"),
            "initialized": info.get("initialized"),
            "usage": info.get("usage") or {},
        }
    return success({
        "adapters": out,
        "warnings": described.get("warnings") or [],
    })


async def list_providers(adapter: str) -> ApiResponse[Dict[str, Any]]:
    """某能力下的 provider 列表（含 label / deployment / 模型清单）。"""
    pm = _manager()
    at = adapter
    names = list(pm.get_valid_providers(at) or [])
    providers = []
    for name in names:
        meta = pm.get_provider_meta(at, name) or {}
        providers.append({
            "name": name,
            "label": (meta.get("meta") or {}).get("label", name),
            "deployment": meta.get("deployment"),
            "models": [m.get("id") for m in (meta.get("models") or [])],
            "available": meta.get("available"),
        })
    return success({
        "type": at,
        "providers": providers,
        "names": names,
        "total": len(names),
    })

async def get_provider(
    adapter: str,
    provider: str,
    model_id: Optional[str] = Query(None, description="指定模型；缺省用第一个模型"),
) -> ApiResponse[Dict[str, Any]]:
    pm = _manager()
    at = adapter
    cfg = pm.get_provider_config(at, provider, model_id)
    if cfg is None:
        raise ApiError.not_found(f"provider {at}/{provider}")
    meta = pm.get_provider_meta(at, provider) or {}
    data = mask_config(dict(cfg), _SECRET_KEYS)
    return success({
        "type": at,
        "name": provider,
        "config": data,
        "meta": meta.get("meta") or {},
        "models": meta.get("models") or [],
        "selected_model": cfg.get("model"),
        "available": meta.get("available"),
        "warnings": meta.get("warnings") or [],
    })


async def switch(
    adapter: str,
    payload: ProviderSwitchRequest,
) -> ApiResponse[SwitchResultData]:
    """切换 provider（可指定 model_id 与配置覆盖）"""
    pm = _manager()
    at = adapter

    if not pm.validate_provider(at, payload.provider):
        valid = list(pm.get_valid_providers(at) or [])
        raise ApiError.bad_request(
            f"provider {payload.provider} 不适用于 {at}，可选: {', '.join(valid)}"
        )

    result = await to_thread(
        pm.switch_adapter, at, payload.provider, payload.config, payload.model_id
    )
    data = result if isinstance(result, dict) else {}
    if not data.get("success"):
        errors = data.get("errors") or ["切换失败"]
        raise ApiError.internal("; ".join(str(e) for e in errors))

    return success(
        SwitchResultData(
            success=True,
            type=data.get("type", at),
            name=data.get("name", payload.provider),
            model=data.get("model"),
            config=mask_config(dict(data.get("config") or {}), _SECRET_KEYS),
        ),
        message=f"{at} 已切换到 {payload.provider}",
    )



async def stop_adapter(adapter: str) -> ApiResponse[Dict[str, Any]]:
    """释放当前 provider 的模型/连接，但保留能力门面，之后仍可切回。"""
    pm = _manager()
    at = adapter
    stopped = await to_thread(pm.stop_provider, at)
    return success(
        {
            "type": at,
            "stopped": bool(stopped)
        },
        message=f"{at} 已关闭" if stopped else f"{at} 没有运行中的 provider",
    )

async def all_configs() -> ApiResponse[Dict[str, Any]]:
    """所有能力的供应商元数据（describe 结果本身不含凭据）。"""
    pm = _manager()
    data = pm.get_pipeline_all_configs() or {}
    masked: Dict[str, Any] = {}
    for capability, providers in data.items():
        if not isinstance(providers, dict):
            masked[capability] = providers
            continue
        masked[capability] = {
            name: mask_config(cfg, _SECRET_KEYS) if isinstance(cfg, dict) else cfg
            for name, cfg in providers.items()
        }
    return success(masked)



async def status(
    adapter: str,
    provider: str,
    model_id: Optional[str] = None,
) -> ApiResponse[ProviderStatusData]:
    """单个 provider 完整状态，含本地模型文件状态。"""
    data = provider_manager.get_provider_status(adapter, provider, model_id)
    if data is None:
        raise ApiError(
            code= CODE_NOT_FOUND,
            message=f"provider {provider} 不存在或不适用于 {adapter}",
        )
    return success(ProviderStatusData(**data))


async def download_model(
    adapter: str,
    provider: str,
    payload: ProviderDownloadRequest,
) -> ApiResponse[DownloadStartData]:
    """触发本地模型下载。进度走 WebSocket DOWNLOAD_MODEL 事件。"""
    # 解析 model_id：缺省取 spec 的默认模型
    mg = _manager()
    status = mg.get_provider_status(adapter, provider, payload.model_id)
    if status is None:
        raise ApiError(
            code=CODE_NOT_FOUND,
            message=f"provider {provider} 不存在或不适用于 {adapter}",
        )
    if not status.get("download"):
        raise ApiError(
            code=CODE_BAD_REQUEST,
            message=f"{adapter}/{provider} 不是本地 provider，无需下载",
        )
    model_id = status.get("selected_model")

    # 已安装且未 force → 直接返回
    if not payload.force and status["download_status"].get("installed"):
        raise ApiError(
            code=CODE_BAD_REQUEST,
            message=f"{adapter}/{provider} 模型已安装，传 force=true 可强制重下",
        )

    key = (adapter, provider, model_id)
    async with _download_lock:
        existing = _download_inflight.get(key)
        if existing:
            return success(DownloadStartData(
                task_id=existing, capability=adapter,
                provider=provider, model_id=model_id, status="running",
            ))
        task_id = uuid.uuid4().hex[:16]
        _download_inflight[key] = task_id

    async def _run() -> None:
        try:
            await mg.download_model(
                adapter,
                provider, 
                model_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[Download] {adapter}/{provider} 失败: {exc}")
        finally:
            async with _download_lock:
                _download_inflight.pop(key, None)

    asyncio.create_task(_run())

    return success(DownloadStartData(
        task_id=task_id, 
        capability=adapter,
        provider=provider,
        model_id=model_id,
        status="started",
    ))