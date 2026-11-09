"""快捷键映射接口：查询、录制校验、修改、批量修改、恢复默认。

前端负责热键**录制交互**（KeyboardEvent 捕获与设置页 UI），后端负责
动作白名单、规范化、保留键/冲突校验、持久化和设备侧重载。
契约见 `docs/HotkeyFrontendContract.md`。

所有写操作走线程池：`atomic_write_json` 是文件 IO，不占 Web loop。
"""

from __future__ import annotations

from typing import Any, Optional

from ..dto import HotkeyListData, HotkeyValidateData
from ..requests import (
    HotkeyBatchUpdateRequest,
    HotkeyResetRequest,
    HotkeyUpdateRequest,
    HotkeyValidateRequest,
)
from ..response import ApiError, ApiResponse, success
from .._common import to_thread


def _registry():
    from ...devices.hotkeys import get_hotkey_registry

    return get_hotkey_registry()


def _field(payload: Any, name: str, default: Any = None) -> Any:
    """HTTP 通道是 pydantic 模型，桌面网关通道是 dict。"""
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _as_api_error(exc: Exception) -> ApiError:
    from ...devices.hotkeys import HotkeyError

    if isinstance(exc, HotkeyError):
        code = exc.code
        message = exc.message
    else:
        code, message = "internal", str(exc)
    data = {"code": code}
    data.update(getattr(exc, "extra", {}) or {})
    if code in ("conflict", "stale_revision"):
        return ApiError.conflict(message or code)
    if code == "persist_failed" or code == "internal":
        return ApiError.internal(message or code)
    if code == "unknown_action":
        return ApiError.not_found(message or code)
    return ApiError.bad_request(message or code, data=data)


async def list_hotkeys() -> ApiResponse[HotkeyListData]:
    """当前映射 + 动作元数据 + 保留组合 + revision。"""
    reg = _registry()
    data = await to_thread(reg.describe)
    return success(HotkeyListData(**data))


async def validate_hotkey(
    payload: HotkeyValidateRequest,
) -> ApiResponse[HotkeyValidateData]:
    """录制中实时校验（不落盘）。

    前端每捕获一个组合就调一次：`action` 传正在编辑的动作，用于排除自身冲突。
    """
    combo = str(_field(payload, "combo", "") or "")
    action = str(_field(payload, "action", "") or "")
    result = _registry().validate(combo, action)
    return success(HotkeyValidateData(**result))


async def update_hotkey(
    action: str,
    payload: HotkeyUpdateRequest,
) -> ApiResponse[HotkeyListData]:
    """修改单个热键。`revision` 用于乐观并发，不匹配返回 409。"""
    combo = str(_field(payload, "combo", "") or "")
    revision = _field(payload, "revision", None)
    try:
        out = await to_thread(_registry().set_binding, action, combo, revision)
    except Exception as exc:  # noqa: BLE001 - 统一转成业务错误信封
        raise _as_api_error(exc) from exc
    return success(HotkeyListData(**out["registry"]), message="热键已更新")


async def update_hotkeys(
    payload: HotkeyBatchUpdateRequest,
) -> ApiResponse[HotkeyListData]:
    """批量修改（设置页「保存全部」）：全量校验通过才一次写盘。"""
    bindings = _field(payload, "bindings", None)
    revision = _field(payload, "revision", None)
    try:
        out = await to_thread(_registry().set_many, bindings, revision)
    except Exception as exc:  # noqa: BLE001
        raise _as_api_error(exc) from exc
    return success(HotkeyListData(**out["registry"]), message="热键已保存")


async def reset_hotkeys(
    payload: Optional[HotkeyResetRequest] = None,
) -> ApiResponse[HotkeyListData]:
    """恢复默认映射。"""
    revision = _field(payload, "revision", None)
    try:
        out = await to_thread(_registry().reset, revision)
    except Exception as exc:  # noqa: BLE001
        raise _as_api_error(exc) from exc
    return success(HotkeyListData(**out["registry"]), message="已恢复默认热键")
