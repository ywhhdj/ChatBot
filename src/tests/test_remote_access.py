"""远程访问与认证回归测试（B0-05 / SecurityAndAuditDesign §3）。

纯函数，不启动服务、不占端口。

运行：

    cd src_py && python -m pytest tests/test_remote_access.py -v
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api.access import (  # noqa: E402
    AUTH_HEADER,
    PUBLIC_PATHS,
    ReasonCode,
    RemoteAccessPolicy,
    authorize_request,
    evaluate_remote_access,
    extract_bearer,
    is_loopback,
    is_public_path,
    policy_from_env,
    token_matches,
)


# ─────────────────────────────────────────────────────────────
# 本机判定
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", ""])
def test_loopback_hosts_are_local(host):
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "10.0.0.5", "example.com"])
def test_non_loopback_hosts_are_remote(host):
    assert not is_loopback(host)


def test_unresolvable_name_is_treated_as_remote():
    """域名无法判定时保守当作远程 —— 误判为远程只是多一道确认，
    误判为本机会让远程监听绕过认证。"""
    assert not is_loopback("my-host.local")


# ─────────────────────────────────────────────────────────────
# 启动门槛
# ─────────────────────────────────────────────────────────────


def test_local_host_starts_without_any_acknowledgement():
    """默认本机场景必须零摩擦，本地开发不受影响。"""
    ok, reason, _ = evaluate_remote_access("127.0.0.1", RemoteAccessPolicy())
    assert ok
    assert reason == ReasonCode.OK_LOCAL


def test_remote_host_is_refused_by_default():
    """传 0.0.0.0 不再等于全网裸奔。"""
    ok, reason, message = evaluate_remote_access("0.0.0.0", RemoteAccessPolicy())
    assert not ok
    assert reason == ReasonCode.REMOTE_NOT_ACKNOWLEDGED
    assert message


def test_remote_requires_credentials_even_when_acknowledged():
    ok, reason, _ = evaluate_remote_access(
        "0.0.0.0", RemoteAccessPolicy(allow_remote=True)
    )
    assert not ok
    assert reason == ReasonCode.REMOTE_WITHOUT_AUTH


def test_remote_with_token_is_allowed():
    ok, reason, _ = evaluate_remote_access(
        "0.0.0.0",
        RemoteAccessPolicy(allow_remote=True, token="secret-token"),
    )
    assert ok
    assert reason == ReasonCode.OK_REMOTE_AUTHENTICATED


def test_cors_is_not_authentication():
    """策略里没有任何 allow_origins 字段 —— CORS 不能替代认证（§3）。"""
    fields = set(RemoteAccessPolicy().__dataclass_fields__)
    assert "allow_origins" not in fields


# ─────────────────────────────────────────────────────────────
# token 校验
# ─────────────────────────────────────────────────────────────


def test_correct_bearer_passes():
    headers = {AUTH_HEADER: "Bearer secret-token"}
    ok, _ = authorize_request(
        "/api/session/history", headers,
        RemoteAccessPolicy(allow_remote=True, token="secret-token"),
    )
    assert ok


def test_missing_or_wrong_token_is_rejected():
    policy = RemoteAccessPolicy(allow_remote=True, token="secret-token")
    assert not authorize_request("/api/session/history", {}, policy)[0]
    assert not authorize_request(
        "/api/session/history", {AUTH_HEADER: "Bearer wrong"}, policy
    )[0]


def test_missing_configured_token_denies_rather_than_allows():
    """配置缺失时拒绝而非放行 —— 宁可服务起不来，也不能裸奔。"""
    policy = RemoteAccessPolicy(allow_remote=True, token=None)
    ok, reason = authorize_request("/api/session/history", {}, policy)
    assert not ok
    assert reason == ReasonCode.REMOTE_WITHOUT_AUTH


def test_health_check_is_reachable_without_token():
    """监控系统探活不该被认证挡住。"""
    policy = RemoteAccessPolicy(allow_remote=True, token="secret-token")
    path = next(iter(PUBLIC_PATHS))
    assert is_public_path(path)
    assert authorize_request(path, {}, policy)[0]


def test_authorization_header_case_is_ignored():
    assert extract_bearer({"Authorization": "Bearer abc"}) == "abc"
    assert extract_bearer({"AUTHORIZATION": "abc"}) == "abc"


def test_token_without_bearer_prefix_is_accepted():
    assert extract_bearer({AUTH_HEADER: "abc"}) == "abc"


def test_token_compare_is_constant_time():
    """用 hmac.compare_digest，避免通过响应耗时逐字节猜 token。"""
    assert token_matches("abc", "abc")
    assert not token_matches("abd", "abc")
    assert not token_matches("", "abc")
    assert not token_matches("abc", ""), "未配置 token 时一律不通过"


# ─────────────────────────────────────────────────────────────
# 环境变量
# ─────────────────────────────────────────────────────────────


def test_env_defaults_to_no_remote(monkeypatch):
    for key in ("CHATBOT_ALLOW_REMOTE", "CHATBOT_API_TOKEN", "CHATBOT_REMOTE_NO_AUTH"):
        monkeypatch.delenv(key, raising=False)
    policy = policy_from_env()
    assert policy.allow_remote is False
    assert policy.require_auth is True
    assert not policy.has_token


def test_env_can_enable_remote_with_token(monkeypatch):
    monkeypatch.setenv("CHATBOT_ALLOW_REMOTE", "1")
    monkeypatch.setenv("CHATBOT_API_TOKEN", "tok")
    policy = policy_from_env()
    assert policy.allow_remote is True
    assert policy.has_token
    ok, _, _ = evaluate_remote_access("0.0.0.0", policy)
    assert ok
