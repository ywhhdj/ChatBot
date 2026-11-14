"""普通请求"""
import platform
import subprocess
from typing import Any, Dict

from ..response import ApiError, ApiResponse, success
from ...runtime import RuntimePath

STREAM_TIMEOUT = 600.0

_FOLDERS = ("images", "roles", "memory", "workspace")
async def open_folder(type: str) -> ApiResponse[Dict[str, Any]]:
    """打开受支持的本地数据目录；type 必须命中白名单。"""
    if type not in _FOLDERS:
        raise ApiError.bad_request(f"不支持的目录类型 {type}，可选: {', '.join(_FOLDERS)}")
    from ...runtime import RuntimePath

    path = str(RuntimePath.get_user_data_path(type))
    system = platform.system().lower()
    try:
        if system == "windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif system == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        raise ApiError.internal("打开目录失败（系统文件管理器不可用）")
    return success({"type": type, "path": path, "opened": True})
    paths={
        "images":RuntimePath.get_user_data_path("images"),
        "roles":RuntimePath.get_user_data_path("roles"),
    }
    if type not in paths.keys():
        raise ApiError.bad_request("路径越界")
    #获取系统类型
    import platform
    platform_type = platform.system().lower()
    if platform_type == "windows":
        import os
        os.startfile(paths[type])
        return success()
    elif platform_type == "mac":
        import os
        os.system(f"open {paths[type]}")
        return success()
    elif platform_type == "linux":
        import os
        os.system(f"xdg-open {paths[type]}")
        return success()
    else:
        raise ApiError.bad_request("系统不支持")