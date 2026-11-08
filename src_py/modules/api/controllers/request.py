"""普通请求"""
from ..response import ApiError, ApiResponse, success
from ...runtime import RuntimePath

STREAM_TIMEOUT = 600.0

def folder(type: str):
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