"""存档槽接口：列表、新建、切换、保存、加载、分区更新、与会话互同步。

对应 api文档.md 第 8 节。

`sections`：`characters` `ui` `chat_history` `achievements` `story`。
存档落盘涉及文件 IO，全部走线程池。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from ..dto import (
    SlotActionData,
    SlotInfoData,
    SlotListData,
    SlotMeta,
    SnapshotActionData,
)
from ..requests import (
    SlotCreateRequest,
    SlotSectionUpdateRequest,
    SlotSyncRequest,
    SnapshotRequest,
)
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/api/save", tags=["save"])


def _sm():
    from ...manager.saves.manager import save_slot_manager

    return save_slot_manager


def _field(payload: Any, name: str, default: Any = None) -> Any:
    """HTTP 通道拿到 pydantic 模型，桌面网关通道拿到 dict。"""
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _slot_info(slot: Any) -> SlotInfoData:
    meta: Dict[str, Any] = {}
    raw = getattr(slot, "meta", None)
    if raw is not None:
        meta = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw or {})
    fields = getattr(SlotMeta, "model_fields", {})
    return SlotInfoData(
        id=str(getattr(slot, "id", "") or ""),
        name=str(getattr(slot, "name", "") or ""),
        meta=SlotMeta(**{k: str(v or "") for k, v in meta.items() if k in fields}),
    )


# --------------------------------------------------------------------------
# SV16：处理函数（供网关复用，桌面端与 Web 同一份）
# --------------------------------------------------------------------------

async def all_slots() -> ApiResponse[SlotListData]:
    """列出全部存档"""
    sm = _sm()
    items = await to_thread(sm.list_metadata)
    current = await to_thread(sm.get_current_slot)
    current_id = str(getattr(current, "id", "") or "") if current else ""
    return success(SlotListData(
        total=len(items),
        slots=[SlotInfoData(**{
            k: v for k, v in m.items()
            if k in ("id", "name")
        }, meta=SlotMeta(**{
            k: str(v or "") for k, v in m.items()
            if k in getattr(SlotMeta, "model_fields", {})
        })) for m in items],
        current=current_id,
    ))


@router.get("/slots", response_model=ApiResponse[SlotListData])
async def list_slots() -> ApiResponse[SlotListData]:
    return await all_slots()


@router.post("/slots", response_model=ApiResponse[SlotInfoData])
async def create_slot(payload: SlotCreateRequest) -> ApiResponse[SlotInfoData]:
    """新建存档槽。"""
    sm = _sm()
    name = str(_field(payload, "name", "") or "")
    slot_id = _field(payload, "slot_id", None)
    try:
        slot = await to_thread(sm.create_slot, name, slot_id)
    except ValueError as exc:
        raise ApiError.bad_request(str(exc)) from exc
    return success(_slot_info(slot), message="存档已创建")


@router.get("/slots/{slot_id}", response_model=ApiResponse[SlotInfoData])
async def get_slot(slot_id: str) -> ApiResponse[SlotInfoData]:
    slot = _sm().get_slot(slot_id)
    if slot is None:
        raise ApiError.not_found(f"存档 {slot_id}")
    return success(_slot_info(slot))


@router.delete("/slots/{slot_id}", response_model=ApiResponse[SlotActionData])
async def delete_slot(slot_id: str) -> ApiResponse[SlotActionData]:
    sm = _sm()
    ok = await to_thread(sm.delete_slot, slot_id)
    if not ok:
        raise ApiError.not_found(f"存档 {slot_id}")
    return success(SlotActionData(id=slot_id, ok=True), message="存档已删除")


@router.post("/slots/{slot_id}/toggle", response_model=ApiResponse[SlotActionData])
async def toggle_slot(slot_id: str) -> ApiResponse[SlotActionData]:
    sm = _sm()
    ok = await to_thread(sm.toggle_slot, slot_id)
    if not ok:
        raise ApiError.not_found(f"存档 {slot_id}")
    return success(SlotActionData(id=slot_id, ok=True), message=f"已切换到存档 {slot_id}")


@router.post("/slots/{slot_id}/save", response_model=ApiResponse[SlotActionData])
async def save_slot(slot_id: str) -> ApiResponse[SlotActionData]:
    sm = _sm()
    ok = await to_thread(sm.save_slot, slot_id)
    if not ok:
        raise ApiError.not_found(f"存档 {slot_id}")
    return success(SlotActionData(id=slot_id, ok=True), message="存档已保存")


@router.post("/slots/{slot_id}/load", response_model=ApiResponse[SlotActionData])
async def load_slot(slot_id: str) -> ApiResponse[SlotActionData]:
    sm = _sm()
    ok = await to_thread(sm.load_slot, slot_id)
    if not ok:
        raise ApiError.not_found(f"存档 {slot_id}")
    return success(SlotActionData(id=slot_id, ok=True), message="存档已加载")


# --------------------------------------------------------------------------
# 前端 save.ts 已有调用、此前后端未注册的三条
# --------------------------------------------------------------------------

@router.put("/slots/{slot_id}/section", response_model=ApiResponse[Dict[str, Any]])
async def update_section(
    slot_id: str,
    payload: SlotSectionUpdateRequest,
) -> ApiResponse[Dict[str, Any]]:
    """局部更新存档分区。

    body: `{"data": {"chat_history": {...}, "ui": {...}}}`。
    `slot_id` 以路径参数为准，忽略 body 里的同名字段，避免越权改别的槽。
    """
    sm = _sm()
    if sm.get_slot(slot_id) is None:
        raise ApiError.not_found(f"存档 {slot_id}")
    raw = _field(payload, "data", None)
    if not isinstance(raw, dict) or not raw:
        raise ApiError.bad_request("data 不能为空，格式 {section_name: value}")
    updated: List[str] = []
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ApiError.bad_request(f"分区 {name} 的值必须是对象")
        ok = await to_thread(sm.put_section, name, value, slot_id)
        if not ok:
            raise ApiError.internal(f"分区 {name} 写入失败")
        updated.append(name)
    return success({"id": slot_id, "updated": updated, "ok": True}, message="分区已更新")


@router.post("/slots/sync", response_model=ApiResponse[Dict[str, Any]])
async def sync_from_sessions(
    payload: Optional[SlotSyncRequest] = None,
) -> ApiResponse[Dict[str, Any]]:
    """会话 → 存档：把会话与消息写进当前槽。"""
    sm = _sm()
    session_id = str(_field(payload, "session_id", "") or "")
    ok = await to_thread(sm.sync_from_sessions, session_id)
    if not ok:
        raise ApiError.internal("会话同步失败（当前存档不可用）")
    return success({"ok": True, "session_id": session_id or "*"}, message="会话已同步到存档")


@router.post("/slots/restore", response_model=ApiResponse[Dict[str, Any]])
async def restore_to_sessions() -> ApiResponse[Dict[str, Any]]:
    """存档 → 会话：从当前槽恢复会话与消息（只读存档）。"""
    sm = _sm()
    result = await to_thread(sm.restore_to_sessions)
    return success(result, message=f"已恢复 {result.get('restored', 0)} 个会话")


# ─────────────────── Snapshot revision（api.md §7 P2） ───────────────────
def _coordinator():
    """取存档组合根；未由应用层显式装配时返回稳定 2001，不假造成功。"""
    import sqlite3

    try:
        from ...manager.saves.coordinator import get_save_coordinator
        from ...runtime import RuntimePath

        sm = _sm()
        root = str(
            getattr(sm, "root", "")
            or RuntimePath.get_user_data_path("snapshots")
        )
        db = RuntimePath.get_user_data_path("memory") / "memories.db"

        def conn_factory():
            return sqlite3.connect(
                str(db), timeout=5.0, check_same_thread=False
            )

        return get_save_coordinator(
            save_manager=sm, root=root, conn_factory=conn_factory
        )
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized(
            "存档组合根", "SaveCoordinator 依赖未由应用层注入"
        )


def _snapshot_data(action: str, p: SnapshotRequest, raw: Any) -> SnapshotActionData:
    data = dict(raw) if isinstance(raw, dict) else {}
    return SnapshotActionData(
        ok=bool(data.get("ok", data.get("success", action in ("preview", "graph", "status")))),
        slot_id=str(data.get("slot_id", p.slot_id) or ""),
        revision=str(data.get("revision", p.revision) or ""),
        action=action,
        code=str(data.get("code", "") or ""),
        raw=data,
    )


def _snapshot_payload(payload: Any) -> SnapshotRequest:
    return payload if isinstance(payload, SnapshotRequest) else (
        SnapshotRequest.model_validate(payload or {})
    )


async def snapshot(payload: SnapshotRequest) -> ApiResponse[SnapshotActionData]:
    """创建不可变 Snapshot revision（stage → validate → publish）。"""
    p = _snapshot_payload(payload)
    try:
        raw = await to_thread(
            _coordinator().snapshot,
            p.slot_id,
            trigger=p.trigger,
            label=p.label,
            branch_id=p.branch_id,
        )
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized("存档组合根", "快照创建失败")
    return success(_snapshot_data("snapshot", p, raw), message="快照已创建")


async def snapshot_status() -> ApiResponse[SnapshotActionData]:
    """恢复事务、自动存档与调度器 gate 的当前状态。"""
    try:
        raw = await to_thread(_coordinator().status)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized("存档组合根", "状态查询失败")
    return success(_snapshot_data("status", SnapshotRequest(), raw))


async def snapshot_graph(
    slot_id: str = "",
) -> ApiResponse[SnapshotActionData]:
    """revision DAG（parent_revision / branch_id）。"""
    try:
        raw = await to_thread(_coordinator().graph, slot_id)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized("存档组合根", "DAG 查询失败")
    return success(_snapshot_data("graph", SnapshotRequest(slot_id=slot_id), raw))


async def snapshot_preview(
    slot_id: str = "",
    revision: str = "",
) -> ApiResponse[SnapshotActionData]:
    """恢复预演：只读、无副作用（Preview → Prepare → Commit → Verify）。"""
    try:
        raw = await to_thread(_coordinator().preview, slot_id, revision)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized("存档组合根", "恢复预演失败")
    return success(
        _snapshot_data("preview", SnapshotRequest(slot_id=slot_id, revision=revision), raw),
        message="恢复预演完成（未改动运行态）",
    )


async def snapshot_restore(payload: SnapshotRequest) -> ApiResponse[SnapshotActionData]:
    """恢复事务：失败自动 rollback，墓碑优先于旧快照。"""
    p = _snapshot_payload(payload)
    try:
        raw = await to_thread(
            _coordinator().restore,
            p.slot_id,
            p.revision,
            branch_id=p.branch_id,
            label=p.label,
        )
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError.not_initialized("存档组合根", "恢复事务失败")
    data = _snapshot_data("restore", p, raw)
    return success(data, message="恢复事务已完成" if data.ok else "恢复事务已回滚")
