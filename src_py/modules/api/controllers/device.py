from typing import Any, Dict, Optional
from fastapi import APIRouter

from ..response import ApiResponse, success
from ..dto import DeviceInfoData

router = APIRouter(prefix="/device", tags=["device"])

def _detect_dict(refresh: bool = False) -> Dict[str, Any]:
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

@router.get("/info", response_model=ApiResponse[DeviceInfoData])
def device_info(refresh: bool = False):
    global _info
    if _info is not None and not refresh:
        return success(_info)
    _info = DeviceInfoData(**_detect_dict(refresh=refresh))
    return success(_info)

