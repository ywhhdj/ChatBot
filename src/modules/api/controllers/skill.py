"""技能接口：列表、详情、扫描、启用/停用、安装/卸载、校验、执行、提示词"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from ..requests import SkillExecuteRequest
from ..dto import SkillExecuteData, SkillInfoData, SkillListData
from ..response import ApiError, ApiResponse, success
from .._common import to_thread
from ...core.tools.skills.manager import DEFAULT_MAX_RESULT_CHARS, cap_skill_result

router = APIRouter(prefix="/skill", tags=["skill"])

EXEC_TIMEOUT = 30.0
MAX_RESULT_CHARS = DEFAULT_MAX_RESULT_CHARS


def _manager():
    from ...core.tools.skills.manager import ExternalSkillManager

    return ExternalSkillManager()


def _exec_type_value(skill: Any) -> str:
    value = getattr(skill, "exec_type", "none")
    return str(getattr(value, "value", value) or "none")


def _is_supported(skill: Any) -> bool:
    """Skill 只有 `supported` 属性（PYTHON 类型），没有 `executable`。"""
    supported = getattr(skill, "supported", None)
    if isinstance(supported, bool):
        return supported
    return _exec_type_value(skill) == "python"


def _info(skill_id: str, skill: Any) -> SkillInfoData:
    exec_type = _exec_type_value(skill)
    executable = _is_supported(skill)
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


def _audit_execute(
    skill_id: str,
    ok: bool,
    elapsed_ms: int,
    *,
    error_type: str = "",
    stdout_bytes: int = 0,
    truncated: bool = False,
) -> None:
    """执行留痕。只记低基数元数据，**不记 params / 返回正文 / stdout 内容**。"""
    try:
        from ...logger import audit

        audit.record(
            audit.Action.TOOL_INVOKE,
            resource=audit.Resource(
                type=audit.ResourceType.TOOL.value, id=str(skill_id)
            ),
            decision=audit.Decision.ALLOW,
            result=audit.Result.SUCCESS if ok else audit.Result.FAILURE,
            source=audit.Source.API,
            metadata={
                "phase": "skill.execute",
                "ok": bool(ok),
                "error_type": str(error_type or "")[:32],
                "elapsed_ms": int(elapsed_ms),
                "stdout_bytes": int(stdout_bytes),
                "truncated": bool(truncated),
            },
        )
    except Exception:  # noqa: BLE001 - 审计绝不把异常抛回业务
        pass


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
    except Exception:  # noqa: BLE001
        pass

    return success(
        SkillListData(skills=items, total=len(items), pending=pending)
    )


@router.get("/prompt", response_model=ApiResponse[Dict[str, Any]])
async def prompt() -> ApiResponse[Dict[str, Any]]:
    """给 LLM 的技能提示词（只含已启用技能）。"""
    mgr = _manager()
    try:
        from ...core.context.prompt import PromptBuilder

        text = PromptBuilder.build_skill_prompt(
            mgr.list_skills(active_only=True) or {}
        )
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
    """完整目录扫描 + 索引重建（文件 IO，走线程池）。

    原实现只 `load_index()` —— 新增的 SKILL.md 永远发现不了。
    """
    mgr = _manager()
    report = await to_thread(mgr.reload)
    return success(dict(report or {}), message="技能目录已重扫，索引已重建")


@router.post("/rescan", response_model=ApiResponse[Dict[str, Any]])
async def rescan() -> ApiResponse[Dict[str, Any]]:
    """`/skill/reload` 的语义化别名：同一套真扫描实现。"""
    mgr = _manager()
    report = await to_thread(mgr.rescan)
    return success(dict(report or {}), message="技能目录已重扫")


@router.post("/install", response_model=ApiResponse[Dict[str, Any]])
async def install(skill_id: str = "") -> ApiResponse[Dict[str, Any]]:
    """登记安装：把技能目录里已有的 SKILL.md 纳入索引，状态为待审批。

    `skill_id` 作为 query 参数；desktop bridge 的平铺 payload 也会绑定同名键。
    """
    sid = str(skill_id or "").strip()
    if not sid:
        raise ApiError.bad_request("缺少 skill_id")
    mgr = _manager()
    report = await to_thread(mgr.install_skill, sid)
    if not isinstance(report, dict) or not report.get("ok"):
        raise ApiError.bad_request(
            str((report or {}).get("error") or "技能安装失败")
        )
    return success(report, message=f"技能 {sid} 已登记，待审批启用")


@router.delete("/{skill_id}/uninstall", response_model=ApiResponse[Dict[str, Any]])
async def uninstall(
    skill_id: str, remove_files: bool = False
) -> ApiResponse[Dict[str, Any]]:
    """卸载登记；`remove_files=True` 才删目录（默认保留用户文件）。"""
    mgr = _manager()
    report = await to_thread(mgr.uninstall_skill, skill_id, remove_files=remove_files)
    if not isinstance(report, dict) or not report.get("ok"):
        raise ApiError.not_found(f"技能 {skill_id}")
    return success(report, message=f"技能 {skill_id} 已卸载")


@router.post("/{skill_id}/validate", response_model=ApiResponse[Dict[str, Any]])
async def validate(skill_id: str) -> ApiResponse[Dict[str, Any]]:
    """校验元数据 / 参数 schema / 代码 AST 白名单。只读，不改状态。"""
    mgr = _manager()
    report = await to_thread(mgr.validate_skill, skill_id)
    return success(dict(report or {}), message="技能校验完成")


@router.post("/{skill_id}/activate", response_model=ApiResponse[SkillInfoData])
async def activate(skill_id: str) -> ApiResponse[SkillInfoData]:
    """启用技能（激活时补载代码，审批状态一并清除并回写索引）。"""
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

    执行体跑在 `to_thread` + 沙盒线程（受 `SandboxConfig.max_execution_time`
    限制），外层再以 `EXEC_TIMEOUT` 封顶；返回体按 `MAX_RESULT_CHARS` 封顶。
    """
    mgr = _manager()
    skill = mgr.get_skill(skill_id)
    if skill is None:
        raise ApiError.not_found(f"技能 {skill_id}")

    if not _is_supported(skill):
        exec_type = _exec_type_value(skill)
        reason = (
            "shell 技能暂不支持执行，请改用 python 沙盒实现"
            if exec_type == "shell"
            else f"技能类型 {exec_type} 不支持执行"
        )
        raise ApiError.not_initialized(f"技能 {skill_id}", reason)

    if not getattr(skill, "active", False):
        raise ApiError.conflict(f"技能 {skill_id} 未启用")

    params = (payload.params if payload else None) or {}
    started = time.perf_counter()

    try:
        # 同步入口：调度器 / to_thread 拿到的永远是 dict，不是 coroutine。
        result = await asyncio.wait_for(
            to_thread(mgr.execute_skill_sync, skill_id, params),
            timeout=EXEC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _audit_execute(
            skill_id, False, int((time.perf_counter() - started) * 1000),
            error_type="TimeoutError",
        )
        raise ApiError.timeout(f"技能 {skill_id}")
    except Exception as e:  # noqa: BLE001
        _audit_execute(
            skill_id, False, int((time.perf_counter() - started) * 1000),
            error_type=type(e).__name__,
        )
        raise ApiError.internal(f"技能执行失败: {e}")

    data = cap_skill_result(result, MAX_RESULT_CHARS)
    ok = bool(data.get("ok", False))
    _audit_execute(
        skill_id,
        ok,
        int((time.perf_counter() - started) * 1000),
        error_type="" if ok else str(data.get("error") or "").split(":", 1)[0][:32],
        stdout_bytes=len(str(data.get("stdout") or "")),
        truncated=bool(data.get("truncated")),
    )
    return success(
        SkillExecuteData(
            id=skill_id,
            ok=ok,
            result=data if ok else None,
            error=None if ok else str(data.get("error") or "执行失败"),
        )
    )
