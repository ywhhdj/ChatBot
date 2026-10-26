"""技能接口：列表、详情、重新扫描、启用/停用、执行、提示词。

对应 api文档.md 第 11 节。

两条来自需求的硬约束：
  * 命令文本只认 `--id`，`--name` 是无效参数（技能名可重复，id 才唯一）。
  * `shell` 类型**暂不支持执行**：可被识别、可见、可启用，但执行时明确返回不支持，
    不会静默当作"无脚本"跳过。
"""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from ..requests import SkillExecuteRequest
from ..dto import SkillExecuteData, SkillInfoData, SkillListData
from ..response import ApiError, ApiResponse, success
from .._common import run_in_scheduler, to_thread

router = APIRouter(prefix="/skill", tags=["skill"])

EXEC_TIMEOUT = 30.0


def _manager():
    from ...tools.skills.manager import ExternalSkillManager

    return ExternalSkillManager()


def _exec_type_value(skill: Any) -> str:
    value = getattr(skill, "exec_type", "none")
    return str(getattr(value, "value", value) or "none")


def _info(skill_id: str, skill: Any) -> SkillInfoData:
    exec_type = _exec_type_value(skill)
    executable = bool(getattr(skill, "executable", False))
    reason = ""
    if not executable:
        if exec_type == "shell":
            reason = "shell 技能暂不支持执行，请改用 python 沙盒实现"
        elif exec_type == "javascript":
            reason = "javascript 技能暂不支持执行"
        else:
            reason = "该技能没有可执行脚本"

    meta = getattr(skill, "metadata", None)
    return SkillInfoData(
        id=str(skill_id),
        name=str(getattr(meta, "name", "") or getattr(skill, "name", "") or ""),
        description=str(getattr(meta, "description", "") or ""),
        version=str(getattr(meta, "version", "") or ""),
        author=str(getattr(meta, "author", "") or ""),
        license=str(getattr(meta, "license", "") or ""),
        exec_type=exec_type,
        active=bool(getattr(skill, "active", False)),
        executable=executable,
        reason=reason,
    )


@router.get("", response_model=ApiResponse[SkillListData])
async def list_skills(
    active_only: bool = Query(False, description="只返回已启用技能"),
) -> ApiResponse[SkillListData]:
    """技能列表。"""
    mgr = _manager()
    raw = mgr.list_skills(active_only=active_only) or {}
    items: List[SkillInfoData] = []
    for skill_id in raw:
        skill = mgr.get_skill(str(skill_id))
        if skill is None:
            items.append(SkillInfoData(id=str(skill_id), name=str(raw[skill_id])))
            continue
        items.append(_info(skill_id, skill))

    pending: Dict[str, str] = {}
    try:
        pending = dict(mgr.get_pending_skills() or {})
    except Exception:
        pass

    return success(
        SkillListData(skills=items, total=len(items), pending=pending)
    )


@router.get("/prompt", response_model=ApiResponse[Dict[str, Any]])
async def prompt() -> ApiResponse[Dict[str, Any]]:
    """给 LLM 的技能提示词（只含已启用技能）。"""
    mgr = _manager()
    try:
        text = mgr.build_prompt()
    except Exception as e:
        raise ApiError.internal(f"构建技能提示词失败: {e}")
    return success({"prompt": str(text or "")})


@router.get("/{skill_id}", response_model=ApiResponse[SkillInfoData])
async def get_skill(skill_id: str) -> ApiResponse[SkillInfoData]:
    """技能详情。"""
    skill = _manager().get_skill(skill_id)
    if skill is None:
        raise ApiError.not_found(f"技能 {skill_id}")
    return success(_info(skill_id, skill))


@router.post("/reload", response_model=ApiResponse[Dict[str, Any]])
async def reload() -> ApiResponse[Dict[str, Any]]:
    """重新扫描技能目录并重建索引（文件 IO，走线程池）。"""
    mgr = _manager()

    def _reload() -> int:
        mgr.load_index()
        return len(mgr.list_skills() or {})

    count = await to_thread(_reload)
    return success({"total": int(count)}, message="技能索引已重建")


@router.post("/{skill_id}/activate", response_model=ApiResponse[SkillInfoData])
async def activate(skill_id: str) -> ApiResponse[SkillInfoData]:
    """启用技能。"""
    mgr = _manager()
    ok = await to_thread(mgr.activate_skill, skill_id)
    if not ok:
        raise ApiError.not_found(f"技能 {skill_id}")

    skill = mgr.get_skill(skill_id)
    return success(_info(skill_id, skill), message=f"技能 {skill_id} 已启用")


@router.post("/{skill_id}/deactivate", response_model=ApiResponse[SkillInfoData])
async def deactivate(skill_id: str) -> ApiResponse[SkillInfoData]:
    """停用技能。"""
    mgr = _manager()
    ok = await to_thread(mgr.deactivate_skill, skill_id)
    if not ok:
        raise ApiError.not_found(f"技能 {skill_id}")

    skill = mgr.get_skill(skill_id)
    return success(_info(skill_id, skill), message=f"技能 {skill_id} 已停用")


@router.post("/{skill_id}/execute", response_model=ApiResponse[SkillExecuteData])
async def execute(
    skill_id: str,
    payload: Optional[SkillExecuteRequest] = None,
) -> ApiResponse[SkillExecuteData]:
    """执行技能。

    执行体跑在沙盒线程（受 `SandboxConfig.max_execution_time` 限制），
    再由调度器 loop 驱动，不会占住 Web loop。
    """
    mgr = _manager()
    skill = mgr.get_skill(skill_id)
    if skill is None:
        raise ApiError.not_found(f"技能 {skill_id}")

    if not getattr(skill, "executable", False):
        exec_type = _exec_type_value(skill)
        reason = "shell 技能暂不支持执行，请改用 python 沙盒实现" if exec_type == "shell" \
            else f"技能类型 {exec_type} 不支持执行"
        raise ApiError.not_initialized(f"技能 {skill_id}", reason)

    if not getattr(skill, "active", False):
        raise ApiError.conflict(f"技能 {skill_id} 未启用")

    params = (payload.params if payload else None) or {}

    try:
        result = await run_in_scheduler(
            mgr.execute_skill, skill_id, params, timeout=EXEC_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise ApiError.timeout(f"技能 {skill_id}")
    except Exception as e:
        raise ApiError.internal(f"技能执行失败: {e}")

    data = result if isinstance(result, dict) else {}
    ok = bool(data.get("ok", False))
    return success(
        SkillExecuteData(
            id=skill_id,
            ok=ok,
            result=data if ok else None,
            error=None if ok else str(data.get("error", "执行失败")),
        )
    )