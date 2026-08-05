from __future__ import annotations
import platform
from typing import Any, Dict
import os

from fastapi import APIRouter

from ...runtime import RuntimePath
from ...utils import response

req_router=APIRouter()
from ...config import get_config
config = get_config()

@req_router.get("/open-folder")
def open_folder(folder_path: str):
    if not folder_path:
        return response.not_found("folderPath 参数缺失")
    folder_path = os.path.normpath(folder_path)
    if not folder_path.startswith(RuntimePath.PROJECT_PATH):
        return response.error(message="路径注入攻击")
    system = platform.system()
    try:
        if system == 'Windows':
            os.startfile(folder_path)   # 仅Windows有效
            return response.success(True)
        elif system == 'Linux':
            import subprocess
            subprocess.run(['xdg-open', folder_path])
            return response.success(True)
        else:
            return response.error(message="系统不支持")
    except Exception as e:
        return response.unknown_error(error=f"打开文件夹失败: {e}")

@req_router.put("/config/llm")
def llm_config(llm_config: Dict[str, Any]):
    provider = llm_config.get("provider") or ""
    model = llm_config.get("model") or ""
    api_key = llm_config.get("apiKey") or llm_config.get("API_KEY") or ""
    base_url = llm_config.get("apiBaseURL") or llm_config.get("BASE_URL") or ""
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model
    if api_key:
        config.llm.api_key = api_key
    if base_url:
        config.llm.base_url = base_url
    return response.success(True)

@req_router.get("/config/system")
def get_system_config():
    system={
        "log":config.log.to_dict(),
        "network":config.network.to_dict()
    }
    return response.success(system)


# @app.put("/config/system")
# def set_system_config(payload: Dict[str, Any]) -> ResponseData[bool]:
#     cfg["system"] = payload
#     return Response.success(True)

