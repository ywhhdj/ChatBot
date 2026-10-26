"""统一响应信封 / 错误码 / 异常。

对应 `api文档.md` 第 0 节。

设计要点
────────
* 成功与失败**共用一套信封**，前端只判 `ok`，不必解析两种格式。
* 失败时 HTTP 状态码仍语义化（400/404/503…），body 依旧是信封。
* `request_id` 由中间件注入 `contextvar`，这里自动回填。
"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Generic, Optional, TypeVar

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .exceptions import (
    CODE_BAD_REQUEST as _CODE_BAD_REQUEST,
    CODE_CONFLICT as _CODE_CONFLICT,
    CODE_INTERNAL as _CODE_INTERNAL,
    CODE_MAIN_THREAD_BUSY as _CODE_MAIN_THREAD_BUSY,
    CODE_NOT_FOUND as _CODE_NOT_FOUND,
    CODE_NOT_INITIALIZED as _CODE_NOT_INITIALIZED,
    CODE_OK as _CODE_OK,
    CODE_TIMEOUT as _CODE_TIMEOUT,
    CODE_TO_HTTP as _CODE_TO_HTTP,
    MESSAGES as _MESSAGES,
)

T = TypeVar("T")

# --------------------------------------------------------------------------
# 错误码（api文档.md 0.2）
# --------------------------------------------------------------------------
CODE_OK = _CODE_OK
CODE_BAD_REQUEST = _CODE_BAD_REQUEST
CODE_NOT_FOUND = _CODE_NOT_FOUND
CODE_CONFLICT = _CODE_CONFLICT
CODE_NOT_INITIALIZED = _CODE_NOT_INITIALIZED
CODE_TIMEOUT = _CODE_TIMEOUT
CODE_INTERNAL = _CODE_INTERNAL
CODE_MAIN_THREAD_BUSY = _CODE_MAIN_THREAD_BUSY
CODE_TO_HTTP = _CODE_TO_HTTP
MESSAGES = _MESSAGES

# request_id 上下文（中间件注入，响应自动回填）
_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    rid = _request_id.get()
    return rid or new_request_id()

class Base(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

def sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


REQUEST_ID_HEADER = "X-Request-ID"

# --------------------------------------------------------------------------
# 信封
# --------------------------------------------------------------------------

class WebSocketAPIResponse(Base,Generic[T]):
    type: str
    ok: bool = True
    message: str = "ok"
    data: Optional[T] = None
    from_id: Optional[str] = None



class ApiResponse(Base, Generic[T]):
    """统一响应体。路由的 `response_model` 统一声明为 `ApiResponse[...]`。"""
    ok: bool = True
    code: int = CODE_OK
    message: str = "ok"
    data: Optional[T] = None
    request_id: str = Field(default_factory=get_request_id)
    ts: float = Field(default_factory=time.time)


def success(
    data: Any = None,
    message: str = "ok",
    code: int = CODE_OK,
    request_id: Optional[str] = None,
    ts: Optional[float] = None,
) -> ApiResponse:
    return ApiResponse(
        ok=True,
        code=code,
        message=message,
        data=data,
        request_id=request_id or get_request_id(),
        ts=ts or time.time(),
    )


# ApiError 已归入 `exceptions.py`（README 目录结构），
# 这里 re-export 以兼容既有 `from ..response import ApiError` 的写法。
from .exceptions import ApiError


def error_body(exc: ApiError, request_id: Optional[str] = None) -> dict:
    return {
        "ok": False,
        "code": exc.code,
        "message": exc.api_message,
        "data": exc.data,
        "request_id": request_id or get_request_id(),
        "ts": time.time(),
    }


def install_exception_handlers(app) -> None:
    """注册全局异常处理，保证任何错误都以信封返回。"""

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):  # noqa: ANN001
        rid = getattr(request.state, "request_id", None) or request.headers.get(
            REQUEST_ID_HEADER
        ) or get_request_id()
        return JSONResponse(status_code=exc.status_code, content=error_body(exc, rid))

    @app.exception_handler(HTTPException)
    async def _http_error_handler(request: Request, exc: HTTPException):  # noqa: ANN001
        rid = getattr(request.state, "request_id", None) or request.headers.get(
            REQUEST_ID_HEADER
        ) or get_request_id()
        # FastAPI 自身的 404/405 等没有 code，这里补一个语义码
        code = CODE_NOT_FOUND if exc.status_code == 404 else CODE_BAD_REQUEST
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "code": code,
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "data": None,
                "request_id": rid,
                "ts": time.time(),
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):  # noqa: ANN001
        rid = getattr(request.state, "request_id", None) or request.headers.get(
            REQUEST_ID_HEADER
        ) or get_request_id()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "ok": False,
                "code": CODE_INTERNAL,
                "message": f"{type(exc).__name__}: {exc}",
                "data": None,
                "request_id": rid,
                "ts": time.time(),
            },
        )


def install_request_id_middleware(app) -> None:
    """注入 request_id，并把 /api 下的 404/405 也改成信封。

    request_id：客户端自带则沿用，否则生成新的；同时回写到响应 header，
    方便把一次点击与服务端日志对上。

    为什么要在中间件里处理 404/405
    ──────────────────────────────
    Starlette 在**路由未匹配**时直接返回 `{"detail": "Not Found"}`，
    不抛 HTTPException、不经过 `exception_handler`。而 api文档.md 0.1
    承诺"所有 REST 接口返回同一结构" —— 前端若遇到一种裸 detail 响应，
    就得写两套解析逻辑。这里统一成信封。
    """

    @app.middleware("http")
    async def _request_id_mw(request: Request, call_next):  # noqa: ANN001, ANN202
        rid = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = rid
        token = _request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)

        response.headers[REQUEST_ID_HEADER] = rid

        path = request.url.path or ""
        if path.startswith("/api") and response.status_code in (
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ):
            return _not_found_envelope(path, response.status_code, rid)
        return response


def _not_found_envelope(path: str, http_status: int, request_id: str) -> JSONResponse:
    """把 Starlette 的裸 404/405 响应替换成统一信封。"""
    code = CODE_NOT_FOUND if http_status == status.HTTP_404_NOT_FOUND else CODE_BAD_REQUEST
    message = "接口不存在" if code == CODE_NOT_FOUND else "方法不被允许"
    return JSONResponse(
        status_code=http_status,
        content={
            "ok": False,
            "code": code,
            "message": f"{message}: {path}",
            "data": None,
            "request_id": request_id,
            "ts": time.time(),
        },
    )
