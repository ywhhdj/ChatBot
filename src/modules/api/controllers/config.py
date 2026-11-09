"""配置接口：读取、局部更新、重载、持久化、字段说明。

对应 api文档.md 第 2 节。

注意：配置对象是 pydantic 模型，**直接 `setattr` 不会触发校验**。
这里用 `update_from_dict()` 走模型自己的合并逻辑，保证类型正确。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from ..requests import ConfigPatchRequest, ConfigSaveRequest
from ..response import ApiError, ApiResponse, success
from .._common import mask_config, safe_dict

router = APIRouter(prefix="/config", tags=["config"])

# section 名称 -> AppConfig 属性名
SECTIONS = {
    "web": "web",
    "log": "log",
    "network": "network",
    "sqlite": "sqlite",
    "llm": "llm",
    "tts": "tts",
    "asr": "asr",
    "skills": "skills",
}

SECRET_KEYS = ("api_key", "token", "secret", "password")


def _config_obj():
    from ...config import get_config

    return get_config()


def _section_to_dict(name: str, raw: bool = False) -> Dict[str, Any]:
    config = _config_obj()
    attr = SECTIONS.get(name)
    if attr is None:
        raise ApiError.not_found(f"配置段 {name}")
    obj = getattr(config, attr, None)
    if obj is None:
        raise ApiError.not_found(f"配置段 {name}")
    data = safe_dict(obj) if not hasattr(obj, "to_dict") else obj.to_dict()
    return data if raw else mask_config(data, SECRET_KEYS)


@router.get("", response_model=ApiResponse[Dict[str, Any]])
async def get_config_api(
    section: Optional[str] = Query(None, description="只取某个配置段"),
    raw: bool = Query(False, description="true 时返回 api_key 等敏感字段原值"),
) -> ApiResponse[Dict[str, Any]]:
    """读取完整配置，或 `?section=llm` 读取单段。"""
    if section:
        return success(_section_to_dict(section, raw))

    data: Dict[str, Any] = {}
    for name in SECTIONS:
        try:
            data[name] = _section_to_dict(name, raw)
        except ApiError:
            continue
    return success(data)


@router.patch("/{section}", response_model=ApiResponse[Dict[str, Any]])
async def patch_section(
    section: str,
    payload: ConfigPatchRequest = Body(default=None),
    values: Optional[Dict[str, Any]] = Body(default=None),
) -> ApiResponse[Dict[str, Any]]:
    """局部更新配置段。

    两种写法等价：
      - `{"values": {"model": "deepseek-v4"}}`
      - 直接 `{"model": "deepseek-v4"}`
    """
    body: Dict[str, Any] = {}
    if payload is not None and payload.values:
        body.update(payload.values)
    if values:
        body.update(values)
    if not body:
        raise ApiError.bad_request("没有需要更新的字段")

    attr = SECTIONS.get(section)
    if attr is None:
        raise ApiError.not_found(f"配置段 {section}")

    config = _config_obj()
    obj = getattr(config, attr, None)
    if obj is None:
        raise ApiError.not_found(f"配置段 {section}")

    update = getattr(obj, "update_from_dict", None)
    if update is None:
        raise ApiError.internal(f"配置段 {section} 不支持更新")

    unknown = [k for k in body if not hasattr(obj, k)]
    if unknown:
        raise ApiError.bad_request(f"未知字段: {', '.join(unknown)}")

    update(body)
    return success(_section_to_dict(section, raw=False))


@router.post("/reload", response_model=ApiResponse[Dict[str, Any]])
async def reload() -> ApiResponse[Dict[str, Any]]:
    """从配置文件重新加载（丢弃当前内存中的修改）。"""
    from ...config import reload_config

    try:
        reload_config()
    except Exception as e:
        raise ApiError.internal(f"重载失败: {e}")

    data = {name: _section_to_dict(name, False) for name in SECTIONS}
    return success(data, message="配置已重载")


@router.post("/save", response_model=ApiResponse[Dict[str, Any]])
async def save(payload: Optional[ConfigSaveRequest] = None) -> ApiResponse[Dict[str, Any]]:
    """持久化到配置文件。文件 IO 走线程池，不占 Web loop。"""
    import asyncio

    from ...config import save_config

    path = (payload.file_path if payload else None) or ""
    try:
        await asyncio.to_thread(save_config, path)
    except Exception as e:
        raise ApiError.internal(f"保存失败: {e}")
    return success({"file_path": path or "config.json"}, message="配置已保存")


@router.get("/schema", response_model=ApiResponse[Dict[str, Any]])
async def schema(
    section: Optional[str] = Query(None, description="只取某段的字段说明"),
) -> ApiResponse[Dict[str, Any]]:
    """字段说明，供设置页自动生成表单。"""
    config = _config_obj()

    def one(name: str) -> List[Dict[str, Any]]:
        obj = getattr(config, SECTIONS[name], None)
        if obj is None:
            return []
        fn = getattr(obj, "get_ui_config_items", None)
        if fn is None:
            return []
        items = fn() or []
        out = []
        for item in items:
            item = dict(item)
            if item.get("name") in SECRET_KEYS:
                item["value"] = "***"
            out.append(item)
        return out

    if section:
        if section not in SECTIONS:
            raise ApiError.not_found(f"配置段 {section}")
        return success({section: one(section)})

    return success({
        name: one(name) 
        for name in SECTIONS
    })