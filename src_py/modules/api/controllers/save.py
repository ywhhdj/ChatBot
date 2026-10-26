"""存档槽接口：列表、新建、切换、保存、加载、分区更新、与会话互同步。

对应 api文档.md 第 8 节。

`sections`：`characters` `ui` `chat_history` `achievements` `story`。
存档落盘涉及文件 IO，全部走线程池。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dto import (
    SlotActionData,
    SlotInfoData,
    SlotListData,
    SlotMeta,
)
from ..requests import (
    SlotCreateRequest,
    SlotSectionUpdateRequest,
    SlotSyncRequest,
)
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/api/save", tags=["save"])



# --------------------------------------------------------------------------
# SV16：处理函数（供网关复用，桌面端与 Web 同一份）
# --------------------------------------------------------------------------

async def all_slots() -> ApiResponse[SlotListData]:
    """列出全部存档"""
    sm = _sm()
    items = sm.list_metadata()
    current_id = sm._current_slot_id
    return success(SlotListData(
        total=len(items), 
        slots=[SlotInfoData(**m) for m in items],
        current=current_id,
    ))


def _sm():
    from ...manager.saves.manager import save_slot_manager

    return save_slot_manager


def _iso(value: Any) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat(timespec="seconds")
    except Exception:
        return str(value)



@router.get("/slots", response_model=ApiResponse[SlotListData])
async def list_slots() -> ApiResponse[SlotListData]:
    return await all_slots()


@router.post("/slots", response_model=ApiResponse[SlotInfoData])
async def create_slot(payload: SlotCreateRequest) -> ApiResponse[SlotInfoData]:
    """新建存档槽。"""
    sm = _sm()
    slot = await to_thread(sm.create_slot, payload.name, payload.slot_id)
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

