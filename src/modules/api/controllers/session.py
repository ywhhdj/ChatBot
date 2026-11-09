"""会话接口：列表、创建、切换、消息读写、落盘。

对应 api文档.md 第 7 节。

会话与"存档槽"是两套东西：会话是每轮对话的容器（`GameSaveManager`），
存档槽是完整快照（`SaveSlotManager`）。同步能力见 `/api/save/slots/sync`。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from ..dto import (
    MessageItem,
    MessageListData,
    SessionInfoData,
    SessionListData,
)
from ..requests import (
    FlushRequest,
    MessageAppendRequest,
    SessionCreateRequest,
)
from ..response import ApiError, ApiResponse, success
from .._common import to_thread

router = APIRouter(prefix="/session", tags=["session"])


def _gsm():
    from ... import runtime
    return runtime.manager.session_manager


def _info(sess: Any) -> SessionInfoData:
    messages = getattr(sess, "messages", None) or []
    metadata = getattr(sess, "metadata", None)
    if metadata is not None and hasattr(metadata, "__dict__"):
        metadata = dict(metadata.__dict__)
    return SessionInfoData(
        id=str(getattr(sess, "id", "")),
        name=str(getattr(sess, "name", "") or ""),
        character_id=str(getattr(sess, "character_id", "") or ""),
        created_at=float(getattr(sess, "created_at", 0.0) or 0.0),
        updated_at=float(getattr(sess, "updated_at", 0.0) or 0.0),
        message_count=len(messages),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


@router.get("", response_model=ApiResponse[SessionListData])
async def list_sessions() -> ApiResponse[SessionListData]:
    """会话列表。"""
    gsm = _gsm()
    raw = gsm.list() or []
    sessions = []
    for item in raw:
        sid = item.get("id") if isinstance(item, dict) else getattr(item, "id", "")
        sess = gsm.get(str(sid)) if sid else None
        if sess is None:
            if isinstance(item, dict):
                sessions.append(SessionInfoData(**{
                    k: v for k, v in item.items()
                    if k in SessionInfoData.model_fields
                }))
            continue
        sessions.append(_info(sess))

    current = gsm.get_current()
    return success(
        SessionListData(
            sessions=sessions,
            total=len(sessions),
            current=str(getattr(current, "id", "")) if current else None,
        )
    )


@router.post("", response_model=ApiResponse[SessionInfoData])
async def create_session(payload: SessionCreateRequest) -> ApiResponse[SessionInfoData]:
    """创建会话。"""
    gsm = _gsm()

    def _create():
        sess = gsm.create(payload.name, payload.character_id)
        gsm.switch(sess.id)
        return sess

    sess = await to_thread(_create)
    return success(_info(sess), message="会话已创建")


@router.get("/{session_id}", response_model=ApiResponse[SessionInfoData])
async def get_session(session_id: str) -> ApiResponse[SessionInfoData]:
    """会话详情。"""
    sess = _gsm().get(session_id)
    if sess is None:
        raise ApiError.not_found(f"会话 {session_id}")
    return success(_info(sess))


@router.delete("/{session_id}", response_model=ApiResponse[Dict[str, Any]])
async def delete_session(session_id: str) -> ApiResponse[Dict[str, Any]]:
    """删除会话（同时删除消息文件）。"""
    gsm = _gsm()
    if gsm.get(session_id) is None:
        raise ApiError.not_found(f"会话 {session_id}")
    await to_thread(gsm.delete, session_id)
    return success({"id": session_id, "deleted": True}, message="会话已删除")


@router.post("/{session_id}/switch", response_model=ApiResponse[SessionInfoData])
async def switch_session(session_id: str) -> ApiResponse[SessionInfoData]:
    """切换当前会话（会先保存前一个会话）。"""
    gsm = _gsm()
    if gsm.get(session_id) is None:
        raise ApiError.not_found(f"会话 {session_id}")
    await to_thread(gsm.switch, session_id)
    sess = gsm.get(session_id)
    return success(_info(sess), message=f"已切换到会话 {session_id}")


@router.get("/{session_id}/messages", response_model=ApiResponse[MessageListData])
async def messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=1000),
) -> ApiResponse[MessageListData]:
    """消息列表（按时间正序，取最近 N 条）。"""
    sess = _gsm().get(session_id)
    if sess is None:
        raise ApiError.not_found(f"会话 {session_id}")

    raw = list(getattr(sess, "messages", None) or [])
    items: List[MessageItem] = []
    for m in raw[-limit:]:
        if isinstance(m, dict):
            items.append(
                MessageItem(
                    role=str(m.get("role", "user") or "user"),
                    content=str(m.get("content", "") or ""),
                    timestamp=float(m.get("timestamp", 0.0) or 0.0),
                    source=str(m.get("source", "text") or "text"),
                )
            )
    return success(MessageListData(messages=items, total=len(items)))


@router.post("/{session_id}/messages", response_model=ApiResponse[Dict[str, Any]])
async def append_message(
    session_id: str,
    payload: MessageAppendRequest,
) -> ApiResponse[Dict[str, Any]]:
    """追加一条消息（不触发模型推理，仅写会话）。"""
    gsm = _gsm()
    if gsm.get(session_id) is None:
        raise ApiError.not_found(f"会话 {session_id}")
    if not payload.content:
        raise ApiError.bad_request("content 不能为空")

    await to_thread(
        gsm.append_message, session_id, payload.role, payload.content
    )
    return success({"id": session_id, "appended": True}, message="消息已追加")


@router.post("/flush", response_model=ApiResponse[Dict[str, Any]])
async def flush(payload: Optional[FlushRequest] = None) -> ApiResponse[Dict[str, Any]]:
    """强制落盘（不带 session_id 则全部）。"""
    gsm = _gsm()
    sid = payload.session_id if payload else None
    await to_thread(gsm.flush, sid)
    return success({"session_id": sid or "*"}, message="会话已落盘")
