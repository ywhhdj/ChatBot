from typing import Any, Dict, Optional
from fastapi import APIRouter

from ..response import ApiResponse, success
from ..dto import DeviceInfoData

def _detect_dict(refresh: bool = False) :
    try:
        import core as _core
        return dict(_core.detect_performance(refresh=refresh)) # type: ignore
    except Exception as exc:  # noqa: BLE001
        try:
            from ...logger import logger
            logger.debug(f"[device] Rust 内核不可用，回退 ctypes: {exc}")
        except Exception:  # noqa: BLE001
            raise exc


_info:Optional[DeviceInfoData]=None

def device_info(refresh: bool = False) -> ApiResponse[DeviceInfoData]:
    global _info
    if _info is not None and not refresh:
        return success(_info)
    _info = DeviceInfoData(**_detect_dict(refresh=refresh))
    return success(_info)

