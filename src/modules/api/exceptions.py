"""API 层异常定义。

README 目录里 `modules/api/exceptions.py` 独立成文件，
而此前 `ApiError` 直接写在 `response.py` 里 —— 这里按目录归位，
`response.py` 再 re-export，保证既有 `from ..response import ApiError` 仍然可用。

设计要点
────────
`ApiError` 继承 `HTTPException`：既能 `raise` 让 FastAPI 立刻返回，
又能被 `install_exception_handlers` 捕获后转成统一信封 ——
失败响应的 body 与成功响应同构，前端只需判 `ok`。
"""

from __future__ import annotations
from typing import Any, Optional

from fastapi import HTTPException, status

# 错误码（与 api文档.md 0.2 一致）
CODE_OK = 200
CODE_BAD_REQUEST = 1001
CODE_NOT_FOUND = 1002
CODE_CONFLICT = 1003
CODE_NOT_INITIALIZED = 2001
CODE_TIMEOUT = 2002
CODE_INTERNAL = 3001
CODE_MAIN_THREAD_BUSY = 3002

CODE_TO_HTTP = {
    CODE_OK: status.HTTP_200_OK,
    CODE_BAD_REQUEST: status.HTTP_400_BAD_REQUEST,
    CODE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    CODE_CONFLICT: status.HTTP_409_CONFLICT,
    CODE_NOT_INITIALIZED: status.HTTP_503_SERVICE_UNAVAILABLE,
    CODE_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    CODE_INTERNAL: status.HTTP_500_INTERNAL_SERVER_ERROR,
    CODE_MAIN_THREAD_BUSY: status.HTTP_503_SERVICE_UNAVAILABLE,
}

MESSAGES = {
    CODE_OK: "ok",
    CODE_BAD_REQUEST: "参数校验失败",
    CODE_NOT_FOUND: "资源不存在",
    CODE_CONFLICT: "状态冲突",
    CODE_NOT_INITIALIZED: "依赖未初始化",
    CODE_TIMEOUT: "处理超时",
    CODE_INTERNAL: "内部异常",
    CODE_MAIN_THREAD_BUSY: "主线程忙，请稍后重试",
}


class ApiError(HTTPException):
    """业务异常。由全局 handler 转成信封形式的 JSONResponse。"""

    def __init__(
        self,
        message: str,
        code: int = CODE_BAD_REQUEST,
        http_status: Optional[int] = None,
        data: Any = None,
    ) -> None:
        self.code = code
        self.api_message = message
        self.data = data
        super().__init__(
            status_code=http_status or CODE_TO_HTTP.get(code, status.HTTP_400_BAD_REQUEST),
            detail=message,
        )

    # ---- 常用构造器 ----

    @classmethod
    def bad_request(cls, message: str = "参数校验失败", data: Any = None) -> "ApiError":
        return cls(message, CODE_BAD_REQUEST, data=data)

    @classmethod
    def not_found(cls, what: str) -> "ApiError":
        return cls(f"{what} 不存在", CODE_NOT_FOUND)

    @classmethod
    def conflict(cls, message: str) -> "ApiError":
        return cls(message, CODE_CONFLICT)

    @classmethod
    def not_initialized(cls, what: str, reason: Optional[str] = None) -> "ApiError":
        msg = f"{what} 未初始化"
        if reason:
            msg = f"{msg}: {reason}"
        return cls(msg, CODE_NOT_INITIALIZED)

    @classmethod
    def timeout(cls, what: str) -> "ApiError":
        return cls(f"{what} 超时", CODE_TIMEOUT)

    @classmethod
    def internal(cls, message: str) -> "ApiError":
        return cls(message, CODE_INTERNAL)

    @classmethod
    def main_thread_busy(cls) -> "ApiError":
        return cls(MESSAGES[CODE_MAIN_THREAD_BUSY], CODE_MAIN_THREAD_BUSY)


class ApiValidationError(ApiError):
    """请求体校验失败（语义同 1001，但便于调用方单独捕获）。"""

    def __init__(self, message: str = "参数校验失败", data: Any = None) -> None:
        super().__init__(message, CODE_BAD_REQUEST, data=data)


class ServiceUnavailableError(ApiError):
    """依赖未就绪（2001）：LLM / TTS / 技能沙盒等未初始化。"""

    def __init__(self, what: str, reason: Optional[str] = None) -> None:
        super().__init__(
            f"{what} 未初始化" + (f": {reason}" if reason else ""),
            CODE_NOT_INITIALIZED,
        )
