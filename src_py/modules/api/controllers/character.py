"""角色接口：列表、当前角色、切换、增删改、运行时状态、预设模板。

对应 api文档.md 第 9 节。

角色对象同时被 Web 线程（API）与主线程（UI）访问，
管理器内部用 `RLock` 保护，API 层只做读写 + 序列化。
"""

from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter

from ..dto import (
    CharacterAttributesData,
    CharacterInfoData,
    CharacterListData,
    CharacterStateData,
)
from ..requests import (
    CharacterCreateRequest,
    CharacterStateUpdateRequest,
    CharacterUpdateRequest,
)
from ..response import ApiError, ApiResponse, success

router = APIRouter(prefix="/character", tags=["character"])


def _mgr():
    from ... import runtime

    return runtime.manager.character_manager


def _attributes_of(char: Any) -> CharacterAttributesData:
    a = getattr(char, "attributes", None)
    if a is None:
        return CharacterAttributesData()

    def s(field: str, default: str = "") -> str:
        return str(getattr(a, field, default) or default)

    def lst(field: str) -> List[str]:
        value = getattr(a, field, None) or []
        return [str(x) for x in value]

    return CharacterAttributesData(
        name=s("name"),
        title=s("title"),
        nickname_for_user=s("nickname_for_user"),
        personality=s("personality"),
        background=s("background"),
        speech_style=s("speech_style"),
        catchphrases=lst("catchphrases"),
        rules=lst("rules"),
        topics_allowed=lst("topics_allowed"),
        topics_forbidden=lst("topics_forbidden"),
        affection_level=int(getattr(a, "affection_level", 50) or 50),
        mood=s("mood", "平静"),
        random_words=lst("random_words"),
        action_verbs=lst("action_verbs"),
        emotion_adjectives=lst("emotion_adjectives"),
    )


def _state_of(char: Any) -> CharacterStateData:
    st = getattr(char, "state", None)
    if st is None:
        return CharacterStateData()
    return CharacterStateData(
        mood=int(getattr(st, "mood", 4) or 4),
        affection=int(getattr(st, "affection", 50) or 50),
        total_messages=int(getattr(st, "total_messages", 0) or 0),
        total_tasks=int(getattr(st, "total_tasks", 0) or 0),
        last_interaction=float(getattr(st, "last_interaction", 0.0) or 0.0),
        pending_tasks=len(getattr(st, "pending_tasks", None) or []),
    )


def _info(char: Any) -> CharacterInfoData:
    status = "idle"
    st = getattr(char, "state", None)
    if st is not None and getattr(st, "status", None) is not None:
        value = getattr(st.status, "value", st.status)
        status = str(value)
    return CharacterInfoData(
        id=str(getattr(char, "id", "")),
        name=str(getattr(char, "name", "") or ""),
        status=status,
        attributes=_attributes_of(char),
        state=_state_of(char),
    )


@router.get("", response_model=ApiResponse[CharacterListData])
async def list_characters() -> ApiResponse[CharacterListData]:
    """角色列表。"""
    mgr = _mgr()
    chars = [_info(c) for c in mgr.list_characters()]
    return success(
        CharacterListData(
            characters=chars,
            total=len(chars),
            current=mgr.current_id
        )
    )


@router.get("/presets", response_model=ApiResponse[Dict[str, Any]])
async def presets() -> ApiResponse[Dict[str, Any]]:
    """可用预设模板。"""
    from ...characters import presets as _p

    names: List[Dict[str, Any]] = []
    for attr in dir(_p):
        if not attr.startswith("create_"):
            continue
        if attr in ("create_custom",):
            continue
        fn = getattr(_p, attr)
        if not callable(fn):
            continue
        try:
            char = fn()
            names.append({"id": char.id, "name": char.name, "factory": attr}) # type: ignore
        except Exception:
            continue

    emotion_map = getattr(_p, "emotion_map", {}) or {}
    return success({
        "presets": names,
        "emotion_map": emotion_map
    })


@router.get("/current", response_model=ApiResponse[CharacterInfoData])
async def current() -> ApiResponse[CharacterInfoData]:
    """当前角色。"""
    char = _mgr().get_current()
    if char is None:
        raise ApiError.not_found("当前角色（角色注册表为空）")
    return success(_info(char))


@router.get("/{character_id}", response_model=ApiResponse[CharacterInfoData])
async def get_character(character_id: str) -> ApiResponse[CharacterInfoData]:
    """角色详情。"""
    char = _mgr().get(character_id)
    if char is None:
        raise ApiError.not_found(f"角色 {character_id}")
    return success(_info(char))


@router.post("", response_model=ApiResponse[CharacterInfoData])
async def create_character(payload: CharacterCreateRequest) -> ApiResponse[CharacterInfoData]:
    """创建角色。"""
    mgr = _mgr()
    if payload.id and mgr.get(payload.id) is not None:
        raise ApiError.conflict(f"角色 {payload.id} 已存在")

    char = mgr.create(**payload.model_dump(exclude_none=True))
    return success(_info(char), message=f"角色 {char.id} 已创建")


@router.put("/{character_id}", response_model=ApiResponse[CharacterInfoData])
async def update_character(
    character_id: str,
    payload: CharacterUpdateRequest,
) -> ApiResponse[CharacterInfoData]:
    """更新角色属性（只传要改的字段）。"""
    mgr = _mgr()
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise ApiError.bad_request("没有需要更新的字段")

    char = mgr.update(character_id, **data)
    if char is None:
        raise ApiError.not_found(f"角色 {character_id}")
    return success(_info(char), message="角色已更新")


@router.delete("/{character_id}", response_model=ApiResponse[Dict[str, Any]])
async def delete_character(character_id: str) -> ApiResponse[Dict[str, Any]]:
    """删除角色。"""
    if not _mgr().remove(character_id):
        raise ApiError.not_found(f"角色 {character_id}")
    return success({"id": character_id, "deleted": True}, message="角色已删除")


@router.post("/{character_id}/switch", response_model=ApiResponse[CharacterInfoData])
async def switch_character(character_id: str) -> ApiResponse[CharacterInfoData]:
    """切换当前角色。"""
    mgr = _mgr()
    if not mgr.switch(character_id):
        raise ApiError.not_found(f"角色 {character_id}")
    char = mgr.get(character_id)
    return success(_info(char), message=f"已切换到角色 {character_id}")


@router.get("/{character_id}/state", response_model=ApiResponse[CharacterStateData])
async def get_state(character_id: str) -> ApiResponse[CharacterStateData]:
    """运行时状态（心情 / 好感 / 消息数）。"""
    char = _mgr().get(character_id)
    if char is None:
        raise ApiError.not_found(f"角色 {character_id}")
    return success(_state_of(char))


@router.post("/{character_id}/state", response_model=ApiResponse[CharacterStateData])
async def update_state(
    character_id: str,
    payload: CharacterStateUpdateRequest,
) -> ApiResponse[CharacterStateData]:
    """更新运行时状态 `{"mood": 17, "affection": 70}`。

    mood 取值见 `/api/character/presets` 返回的 `emotion_map`。
    """
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise ApiError.bad_request("没有需要更新的字段")

    char = _mgr().update_state(character_id, **data)
    if char is None:
        raise ApiError.not_found(f"角色 {character_id}")
    return success(_state_of(char), message="状态已更新")
