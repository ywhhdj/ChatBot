"""工作区控制面：`security/workspace` 的对外 API。

所有服务产出与 shell 命令都受工作区约束。这里只暴露状态查询、
选择目录/档位、显式确认敏感原文暴露与撤销选择，不提供任意路径写入。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...security import (
    WorkspaceMode,
    clear_workspace,
    confirm_sensitive_exposure,
    describe_workspace,
    ensure_workspace,
    select_workspace,
)
from .._common import to_thread
from ..response import ApiError, ApiResponse, success

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceSelectRequest(BaseModel):
    root: str = Field(default="", description="工作区目录")
    mode: str = Field(default="writable", description="read_only / writable / unrestricted")


class WorkspaceConfirmRequest(BaseModel):
    confirmation_id: str = Field(default="", description="UI 显式确认动作产生的记录 id")


async def info() -> ApiResponse[Dict[str, Any]]:
    """当前工作区状态。不回显完整绝对路径（只给目录名 + 短 hash）。"""
    return success(await to_thread(describe_workspace))


async def select(payload: Optional[WorkspaceSelectRequest] = None) -> ApiResponse[Dict[str, Any]]:
    """选择工作区目录与权限档位。"""
    p = payload or WorkspaceSelectRequest()
    root = (p.root or "").strip()
    if not root:
        raise ApiError.bad_request("root 不能为空")
    try:
        mode = WorkspaceMode((p.mode or "writable").strip().lower())
    except ValueError:
        raise ApiError.bad_request("mode 必须是 read_only / writable / unrestricted")
    try:
        await to_thread(select_workspace, root, mode)
    except Exception as exc:  # noqa: BLE001
        raise ApiError.internal(f"选择工作区失败: {exc}")
    return success(describe_workspace(), message="工作区已选择")


async def confirm(payload: Optional[WorkspaceConfirmRequest] = None) -> ApiResponse[Dict[str, Any]]:
    """用户显式确认后才允许把敏感原文交给 AI；确认本身进轨迹。"""
    p = payload or WorkspaceConfirmRequest()
    cid = (p.confirmation_id or "").strip()
    if not cid:
        raise ApiError.bad_request("confirmation_id 不能为空")
    ensure_workspace()
    confirm_sensitive_exposure(cid)
    return success(describe_workspace(), message="敏感原文暴露已确认（本次会话有效）")


async def clear() -> ApiResponse[Dict[str, Any]]:
    """撤销选择，回到默认工作区。"""
    clear_workspace()
    ensure_workspace()
    return success(describe_workspace(), message="已恢复默认工作区")


# --------------------------------------------------------------------------
# HTTP 层只做参数绑定；逻辑全在上面，供网关复用
# --------------------------------------------------------------------------

@router.get("", response_model=ApiResponse[Dict[str, Any]])
async def _info() -> ApiResponse[Dict[str, Any]]:
    return await info()


@router.post("/select", response_model=ApiResponse[Dict[str, Any]])
async def _select(payload: WorkspaceSelectRequest) -> ApiResponse[Dict[str, Any]]:
    return await select(payload)


@router.post("/confirm", response_model=ApiResponse[Dict[str, Any]])
async def _confirm(payload: WorkspaceConfirmRequest) -> ApiResponse[Dict[str, Any]]:
    return await confirm(payload)


@router.delete("", response_model=ApiResponse[Dict[str, Any]])
async def _clear() -> ApiResponse[Dict[str, Any]]:
    return await clear()
