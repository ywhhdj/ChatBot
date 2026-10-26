"""管道（适配器）接口：查看可选 provider、切换、关闭。

对应 api文档.md 第 3 节。

`switch_adapter` 内部会关闭旧适配器 + 初始化新 provider，
其中 `init_provider_client` 可能触发模型加载（OCR 尤其明显），
因此整个切换放在线程池执行，Web loop 不被占住。
"""
from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter, Query

from ..dto import AdapterInfo, SwitchResultData
from ..requests import PipelineSwitchRequest
from ..response import ApiError, ApiResponse, success
from .._common import mask_config, to_thread

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

SECRET_KEYS = ("api_key", "token", "secret", "password")


def _adapter_type(value: str):
    from ...pipeline.enum import AdapterType

    try:
        return AdapterType(value)
    except ValueError:
        valid = [e.value for e in AdapterType]
        raise ApiError.bad_request(f"适配器类型 {value} 无效，可选: {', '.join(valid)}")


def _manager():
    from ...manager.pipeline import pipeline_manager

    pm = pipeline_manager
    # 配置可能还没加载（PIPELINE_START 未触发），这里兜底加载一次
    if not (pm.get_pipeline_all_configs() or {}):
        try:
            pm.load_config()
        except Exception:
            pass
    return pm


@router.get("/adapters", response_model=ApiResponse[Dict[str, Any]])
async def list_adapters() -> ApiResponse[Dict[str, Any]]:
    """列出所有适配器类型、可选 provider 与当前 provider。"""
    from ...pipeline.enum import AdapterType

    pm = _manager()
    out: Dict[str, Any] = {}
    for adapter in AdapterType:
        key = adapter.value
        try:
            providers = list(pm.get_provider_names(_adapter_type(key)) or [])
        except Exception:
            providers = []
        current = None
        try:
            from ...pipeline.manager import LLM, TTS

            mapping = {"llm": LLM, "tts": TTS}
            cls = mapping.get(key)
            if cls is not None:
                inst = cls.__new__(cls)
                if getattr(inst, "_provider", None) is not None:
                    current = str(getattr(inst._provider, "name", "") or "")
        except Exception:
            pass
        out[key] = AdapterInfo(type=key, providers=providers, current=current).model_dump()
    return success({"adapters": out})


@router.get(
    "/adapters/{adapter}/providers", 
    response_model=ApiResponse[Dict[str, Any]]
)
async def list_providers(adapter: str) -> ApiResponse[Dict[str, Any]]:
    """某适配器类型下的 provider 列表。"""
    pm = _manager()
    at = _adapter_type(adapter)
    names = list(pm.get_provider_names(at) or [])
    return success({"type": adapter, "providers": names, "total": len(names)})


@router.get(
    "/adapters/{adapter}/providers/{provider}",
    response_model=ApiResponse[Dict[str, Any]],
)
async def get_provider(
    adapter: str,
    provider: str,
    raw: bool = Query(False, description="true 时返回敏感字段原值"),
) -> ApiResponse[Dict[str, Any]]:
    """单个 provider 的完整配置。"""
    pm = _manager()
    cfg = pm.get_provider_config(_adapter_type(adapter), provider)
    if not cfg:
        raise ApiError.not_found(f"provider {adapter}/{provider}")
    data = dict(cfg)
    if not raw:
        data = mask_config(data, SECRET_KEYS)
    return success({
        "type": adapter, 
        "name": provider,
        "config": data
    })


@router.post("/adapters/{adapter}/switch", response_model=ApiResponse[SwitchResultData])
async def switch(
    adapter: str,
    payload: PipelineSwitchRequest,
) -> ApiResponse[SwitchResultData]:
    """切换 provider。

    `config` 留空则使用配置文件中的默认配置。
    切换过程（关闭旧的 + 初始化新的）在线程池执行。
    """
    pm = _manager()
    at = _adapter_type(adapter)

    if not pm.validate_provider(at, payload.provider):
        valid = list(pm.get_provider_names(at) or [])
        raise ApiError.bad_request(
            f"provider {payload.provider} 不适用于 {adapter}，可选: {', '.join(valid)}"
        )

    result = await to_thread(pm.switch_adapter, at, payload.provider, payload.config)
    data = result if isinstance(result, dict) else {}

    if not data.get("success"):
        errors = data.get("errors") or ["切换失败"]
        raise ApiError.internal("; ".join(str(e) for e in errors))

    return success(
        SwitchResultData(
            success=True,
            type=data.get("type", adapter),
            name=data.get("name", payload.provider),
            config=mask_config(data.get("config") or {}, SECRET_KEYS),
        ),
        message=f"{adapter} 已切换到 {payload.provider}",
    )


@router.post("/adapters/{adapter}/stop", response_model=ApiResponse[Dict[str, Any]])
async def stop_adapter(adapter: str) -> ApiResponse[Dict[str, Any]]:
    """关闭当前适配器。"""
    pm = _manager()
    at = _adapter_type(adapter)
    await to_thread(pm.unregister, at.value)
    return success({"type": adapter, "stopped": True}, message=f"{adapter} 已关闭")


@router.get("/configs", response_model=ApiResponse[Dict[str, Any]])
async def all_configs(
    raw: bool = Query(False, description="true 时返回敏感字段原值"),
) -> ApiResponse[Dict[str, Any]]:
    pm = _manager()
    data = pm.get_pipeline_all_configs() or {}
    if raw:
        return success(data)

    masked: Dict[str, Any] = {}
    for adapter, providers in data.items():
        if not isinstance(providers, dict):
            masked[adapter] = providers
            continue
        masked[adapter] = {
            name: mask_config(cfg, SECRET_KEYS) if isinstance(cfg, dict) else cfg
            for name, cfg in providers.items()
        }
    return success(masked)