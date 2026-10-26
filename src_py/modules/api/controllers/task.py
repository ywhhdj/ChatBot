"""任务接口：查询状态与结果、取消。

对应 api文档.md 第 12 节。

同步任务（阻塞 IO）**无法被强杀**：`cancel` 只是把任务标记为 cancelled
并唤醒等待方，真正卡在阻塞调用里的线程仍在运行，直到它自己返回。
这是 Python 的固有限制，业务侧对阻塞 IO 仍需自设超时。
"""
from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, Query

from ..dto import TaskStatusData
from ..response import ApiError, ApiResponse, success
from .._common import get_schedular

router = APIRouter(prefix="/task", tags=["task"])

# 内部状态 -> 对外状态（文档里用的是 done/failed/timeout）
_STATE_MAP = {
    "pending": "pending",
    "running": "running",
    "completed": "done",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _state(raw: Any) -> str:
    value = getattr(raw, "value", raw)
    return _STATE_MAP.get(str(value).lower(), str(value).lower())


@router.get("/{task_id}", response_model=ApiResponse[TaskStatusData])
async def get_task(
    task_id: str,
    wait: bool = Query(False, description="true 时阻塞等待任务完成"),
    timeout: float = Query(30.0, ge=0.1, le=600.0),
) -> ApiResponse[TaskStatusData]:
    """查询任务状态。`?wait=true` 时等待完成（最多 timeout 秒）。"""
    s = get_schedular()
    info = s.get_task_status(task_id)
    if info is None:
        raise ApiError.not_found(f"任务 {task_id}")

    result: Any = None
    error: Optional[str] = None

    state = _state(info.get("status"))
    if wait and state in ("pending", "running"):
        try:
            result = await s.get_task_result_async(task_id, timeout=timeout)
            info = s.get_task_status(task_id) or info
            state = _state(info.get("status"))
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            state = "timeout"

    if state == "failed":
        error = error or str(info.get("error") or "任务失败")
    elif state == "done" and result is None:
        try:
            result = s.get_task_result_async(task_id, timeout=0.1)
        except Exception:
            result = None

    return success(
        TaskStatusData(
            task_id=task_id,
            state=state,
            result=result,
            error=error,
        )
    )


@router.post("/{task_id}/cancel", response_model=ApiResponse[TaskStatusData])
async def cancel_task(task_id: str) -> ApiResponse[TaskStatusData]:
    """取消任务（尽力而为）。"""
    s = get_schedular()
    if s.get_task_status(task_id) is None:
        raise ApiError.not_found(f"任务 {task_id}")

    ok = s.cancel_task(task_id)
    info = s.get_task_status(task_id) or {}
    return success(
        TaskStatusData(
            task_id=task_id,
            state=_state(info.get("status")),
            error=None if ok else "任务已完成，无法取消",
        ),
        message="任务已取消" if ok else "任务已结束，未取消",
    )