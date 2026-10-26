#获取电脑设备CPU,GPU等信息
import ctypes
import ctypes
import json
from pathlib import Path
import sys
from typing import Optional
from fastapi import APIRouter

from ...response import ApiResponse, success
from ...dto import DeviceInfoData

router = APIRouter(prefix="/device",tags=["device"])

def _load_lib() -> ctypes.CDLL:
    """按平台查找动态库，兼容 PyInstaller / Nuitka 打包"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent

    if sys.platform == "win32":
        names = ["perf_native.dll"]
    elif sys.platform == "darwin":
        names = ["libperf_native.dylib", "perf_native.dylib"]
    else:
        names = ["libperf_native.so", "perf_native.so"]

    for name in names:
        p = base / name
        if p.exists():
            return ctypes.CDLL(str(p))
    # 兜底：让系统去 PATH 里找
    return ctypes.CDLL(names[0])

_info:Optional[DeviceInfoData]=None

@router.get("/info", response_model=ApiResponse[DeviceInfoData])
def device_info():
    global _info
    if _info:
        return success(_info)
    _lib = _load_lib()
    buf = ctypes.create_string_buffer(4096)
    _ = _lib.detect_performance_buf(buf, len(buf))
    _info = DeviceInfoData(**json.loads(buf.value.decode("utf-8")))
    return success(_info)
