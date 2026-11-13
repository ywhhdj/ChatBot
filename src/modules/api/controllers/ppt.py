"""PPT 接口：模板 / 大纲 / 渲染 / 下载。

修复对应清单：K24 / K25 / K26

所有处理函数都注册成网关 op，桌面端（JS Bridge）与 Web 端（HTTP）
走的是同一份代码、返回同一个信封。
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter

from ..dto import (
    PptDownloadData,
    PptJobData,
    PptOutlineData,
    PptRenderData,
    PptTemplateListData,
)
from ..requests import PptOutlineRequest, PptRenderRequest
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/ppt", tags=["ppt"])


def _service():
    from ...services.ppt.service import PptService

    return PptService()


# --------------------------------------------------------------------------
# 模板
# --------------------------------------------------------------------------

async def templates() -> ApiResponse[PptTemplateListData]:
    """列出可用模板。"""
    svc = _service()
    items = svc.list_templates()
    return success(PptTemplateListData(total=len(items), templates=items))


# --------------------------------------------------------------------------
# 大纲
# --------------------------------------------------------------------------

async def outline(payload: Optional[PptOutlineRequest] = None) -> ApiResponse[PptOutlineData]:
    """生成结构化大纲（只出内容，不渲染文件）。"""
    p = payload or PptOutlineRequest(topic="")
    if not (p.topic or "").strip():
        raise ApiError.bad_request("topic 不能为空")

    svc = _service()
    deck = await to_thread(
        svc.outline,
        topic=p.topic,
        pages=p.pages,
        audience=p.audience,
        scenario=p.scenario,
        style=p.style,
        material=p.material,
        template_id=p.template_id or None,
    )
    return success(PptOutlineData(
        title=deck.title, subtitle=deck.subtitle,
        slide_count=len(deck.slides), deck=deck.to_dict(),
    ))


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
async def render(payload: Optional[PptRenderRequest] = None) -> ApiResponse[PptRenderData]:
    """提交生成任务"""
    p = payload or PptRenderRequest()
    if not (p.topic or "").strip():
        raise ApiError.bad_request("topic 不能为空")
    svc = _service()
    task_id = await to_thread(
        svc.submit_generate,
        topic=p.topic,
        pages=p.pages,
        template_id=p.template_id or None,
        style=p.style,
        material=p.material,
        file_name=p.file_name or None,
    )
    return success(PptRenderData(ok=True, task_id=task_id, message="任务已提交"))


async def render_async(
    payload: Optional[PptRenderRequest] = None,
) -> ApiResponse[PptRenderData]:
    """提交渲染后台任务（`/ppt/render` 的显式异步别名，api.md §7 P1）。

    两者共用同一实现、同一 DTO 与同一 `task_id` 语义；保留别名是为兼容
    旧前端 `renderAsync` 调用，不新建第二套任务队列。
    """
    return await render(payload)


async def job_status(task_id: str) -> ApiResponse[PptJobData]:
    svc = _service()
    st = await to_thread(svc.job_status, task_id)
    return success(PptJobData(**{
        "task_id": st.get("task_id", task_id),
        "state": st.get("state", "not_found"),
        "result": st.get("result") or {},
        "error": st.get("error", ""),
    }))


# --------------------------------------------------------------------------
# 下载
# --------------------------------------------------------------------------

async def download(file_name: str) -> ApiResponse[PptDownloadData]:
    """取回产出文件（K：交付可被程序取回）。

    小文件直接 base64 返回，桌面端无需 HTTP 下载。
    """
    name = os.path.basename(str(file_name or ""))
    if not name:
        raise ApiError.bad_request("file_name 不能为空")

    # 产出目录固定为 <workspace>/ppt/；文件名只接受 basename，
    # 并再经 security/workspace 做一次 realpath 边界复验。
    from ...security import WorkspaceBoundaryError, output_path

    try:
        path = output_path("ppt", name)
    except WorkspaceBoundaryError as exc:
        raise ApiError.bad_request(f"文件 {name} 不在允许的产出目录内: {exc.reason.value}")
    if not os.path.isfile(path):
        raise ApiError.not_found(f"文件 {name}")

    data = await to_thread(_read_b64, path)
    return success(PptDownloadData(
        file_name=name,
        file_path=path,
        size=os.path.getsize(path), 
        content_base64=data,
    ))


def _read_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")
