"""API 契约回归测试（B0-01 / B0-02 / B0-04 / B0-05）。

覆盖"协议与安全正确性"里几条可以脱离业务依赖验证的硬约束：

* 成功判定只有一个权威入口，200 与历史 0 得到相同结论（B0-01）
* `/api` 前缀不重复（B0-02）
* 500 不回传内部异常正文，request_id 被校验（B0-04 / B0-05）

运行：

    cd src_py && python -m pytest tests/test_api_contract.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from modules.api.exceptions import (  # noqa: E402
    CODE_INTERNAL,
    CODE_NOT_FOUND,
    CODE_OK,
    ApiError,
    is_success,
)
from modules.api.response import (  # noqa: E402
    install_exception_handlers,
    install_request_id_middleware,
    normalize_request_id,
    set_request_id,
)


# --------------------------------------------------------------------------
# B0-01：成功码唯一判定
# --------------------------------------------------------------------------

def test_success_code_is_single_source_of_truth():
    """后端写 200、旧 bridge 判 0 —— 两者必须得到同一个结论。"""
    assert is_success(CODE_OK) is True
    assert is_success(0) is True, "0 是历史别名，仍须判成功"
    assert is_success(1001) is False
    assert is_success("200") is True, "HTTP header/JSON 里可能是字符串"
    assert is_success(None) is False, "None 不能算成功"

    # ok 字段优先：即便 code 异常，布尔语义最稳
    assert is_success(CODE_OK, ok=False) is False
    assert is_success(1001, ok=True) is True


# --------------------------------------------------------------------------
# B0-05：request_id 校验
# --------------------------------------------------------------------------

def test_request_id_is_validated():
    """request_id 来自客户端，是不可信输入。"""
    assert normalize_request_id("abc123").startswith("abc123")
    # 换行会污染日志/响应头，控制字符同理
    assert not normalize_request_id("bad\nX-Injected: 1").startswith("bad")
    assert normalize_request_id(""), "空值也要换成可用的 id"
    assert len(normalize_request_id("x" * 200)) <= 64
    assert not normalize_request_id(None).startswith("None")


def test_set_request_id_returns_reset_token():
    """早期 set_request_id() 没有 return，调用方复位成 None。

    这是 gateway.call() 的 finally 里真实踩过的坑：
    `token = set_request_id(rid)` 拿到 None，复位后 request_id 变 None。
    """
    token = set_request_id("rid-1")
    assert token is not None, "必须返回可用于 reset 的 token"


# --------------------------------------------------------------------------
# B0-04：异常不外泄
# --------------------------------------------------------------------------

def _build_app() -> FastAPI:
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("泄露路径 /home/user/.env 与密钥 sk-TEST-SECRET")

    @app.get("/api/not-found-ish")
    def ok() -> dict:
        return {"ok": True}

    install_exception_handlers(app)
    return app


def test_unhandled_exception_is_sanitized():
    """500 只给稳定话术 + request_id，绝不回传异常正文。"""
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/api/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["ok"] is False
    assert body["code"] == CODE_INTERNAL
    assert "sk-TEST-SECRET" not in resp.text, "密钥不得出现在响应体"
    assert "/home/user/.env" not in resp.text, "绝对路径不得出现在响应体"
    assert body["request_id"], "要给 request_id 便于对日志"


def test_business_error_keeps_stable_message():
    """业务异常照常透出可读 message，但不带内部细节。"""
    app = FastAPI()
    install_request_id_middleware(app)

    @app.get("/api/bad")
    def bad() -> None:
        raise ApiError.bad_request("参数 x 必须是正整数")

    install_exception_handlers(app)
    resp = TestClient(app, raise_server_exceptions=False).get("/api/bad")

    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["message"] == "参数 x 必须是正整数"
    assert body["request_id"]


def test_not_found_returns_envelope_not_bare_detail():
    """/api 下的 404 也必须是信封，否则前端要写两套解析。"""
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/api/does-not-exist")

    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["code"] == CODE_NOT_FOUND
    assert "request_id" in body


def test_request_id_header_is_sanitized_and_echoed():
    client = TestClient(_build_app(), raise_server_exceptions=False)
    resp = client.get("/api/not-found-ish", headers={"X-Request-ID": "evil\nvalue"})
    rid = resp.headers.get("X-Request-ID", "")
    assert "\n" not in rid and "evil" not in rid, "脏 request_id 必须被替换"


def test_api_error_debug_field_never_in_body():
    """debug 只用于日志字段，不应出现在 error_body 里。"""
    from modules.api.response import error_body

    exc = ApiError(
        "内部异常", code=CODE_INTERNAL, debug="Traceback: /secret/path sk-xxx"
    )
    body = error_body(exc, "rid")
    assert "sk-xxx" not in str(body)
    assert exc.debug.endswith("sk-xxx"), "原始细节仍留在异常对象上供日志记录"


# --------------------------------------------------------------------------
# B0-02：路由前缀
# --------------------------------------------------------------------------

def test_no_duplicate_api_prefix():
    """/api/api/xxx 是最典型的注册事故：文档写 /api/save，实际却是 /api/api/save。"""
    try:
        from modules.api.controllers import find_duplicate_prefixes, route_inventory
    except Exception as exc:  # pragma: no cover - 依赖不全时跳过
        pytest.skip(f"controllers 依赖未就绪: {exc}")

    dup = find_duplicate_prefixes()
    assert dup == [], f"发现重复 /api 前缀: {dup}"

    paths = {item["path"] for item in route_inventory()}
    assert "/api/save/slots" in paths or any(
        p.startswith("/api/save") for p in paths
    ), "save 路由必须挂在 /api/save 下"
    assert not any(p.startswith("/api/api") for p in paths)
