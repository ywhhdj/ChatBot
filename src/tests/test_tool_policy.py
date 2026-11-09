"""工具执行安全策略回归测试（B0-06 / SecurityAndAuditDesign §3、§9）。

只依赖标准库与 `tools/policy.py` 的纯函数，不启动服务、不注册真实服务。

运行：

    cd src_py && python -m pytest tests/test_tool_policy.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.core.tools.policy import (  # noqa: E402
    DEFAULT_POLICY,
    Capability,
    Decision,
    ReasonCode,
    ToolPolicy,
    evaluate,
    inspect_params,
    looks_like_exec,
    method_capabilities,
)
from modules.core.tools.services.exceute import CommandExecutor  # noqa: E402
from modules.core.tools.services.models import CommandStatus  # noqa: E402


# ─────────────────────────────────────────────────────────────
# 假服务
# ─────────────────────────────────────────────────────────────


class FakeService:
    """最小服务桩：只提供 tools 声明与若干方法。"""

    def __init__(self, tools=None):
        self.tools = tools

    def read_thing(self, name: str = "") -> str:
        return f"read:{name}"

    def run_shell(self, cmd: str = "") -> str:
        return f"shell:{cmd}"

    async def slow_read(self, seconds: float = 0.05) -> str:
        await asyncio.sleep(seconds)
        return "done"

    def block_forever(self) -> str:
        time.sleep(30)
        return "never"


def declared(tools) -> FakeService:
    return FakeService(tools)


# ─────────────────────────────────────────────────────────────
# deny by default
# ─────────────────────────────────────────────────────────────


def test_declared_method_is_allowed():
    svc = declared({"read_thing": {"required_args": []}})
    v = evaluate(svc, "demo", "read_thing", {"name": "x"})
    assert v.allowed
    assert v.reason_code == ReasonCode.OK


def test_undeclared_method_is_denied_even_if_it_exists():
    """方法存在 ≠ 允许调用。这是 B0-06 要堵的主要缺口。"""
    svc = declared({"read_thing": {}})
    assert hasattr(svc, "run_shell"), "方法确实存在，但仍应被拒绝"
    v = evaluate(svc, "demo", "run_shell", {})
    assert not v.allowed
    assert v.reason_code == ReasonCode.EXEC_FORBIDDEN


def test_service_without_tools_declaration_is_denied():
    svc = declared(None)
    v = evaluate(svc, "demo", "read_thing", {})
    assert not v.allowed
    assert v.reason_code == ReasonCode.SERVICE_UNDECLARED


def test_undeclared_service_can_be_opted_in_for_migration():
    svc = declared(None)
    policy = ToolPolicy(allow_undeclared_service=True)
    v = evaluate(svc, "demo", "read_thing", {}, policy=policy)
    assert v.allowed, "迁移期显式开启后应放行，但默认必须关闭"


def test_default_policy_denies_undeclared_services():
    assert DEFAULT_POLICY.allow_undeclared_service is False


# ─────────────────────────────────────────────────────────────
# 执行类默认拒绝
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method", [
    "run_shell", "exec_cmd", "eval_python", "spawn_process",
    "subprocess_run", "bash", "powershell", "run_script",
])
def test_exec_like_methods_are_forbidden_by_default(method):
    svc = declared({method: {}})
    v = evaluate(svc, "demo", method, {})
    assert not v.allowed
    assert v.reason_code == ReasonCode.EXEC_FORBIDDEN


def test_exec_allowed_only_when_declared_and_enabled():
    svc = declared({"run_shell": {"capabilities": ["exec"]}})
    # 只声明、不开开关 → 拒绝
    assert not evaluate(svc, "demo", "run_shell", {}).allowed
    # 开开关且声明了 exec → 放行
    v = evaluate(svc, "demo", "run_shell", {}, policy=ToolPolicy(allow_exec=True))
    assert v.allowed


def test_builtin_run_is_not_mistaken_for_exec():
    """`run` 是 skill.run，走受控沙盒，不应被黑名单误杀。"""
    assert not looks_like_exec("skill", "run")
    assert not looks_like_exec("error", "error")


@pytest.mark.parametrize("method", ["show", "flush", "push", "hash", "dashboard"])
def test_harmless_methods_are_not_mistaken_for_exec(method):
    """黑名单不能误杀含 `sh` / `cmd` 子串的无害方法。"""
    assert not looks_like_exec("demo", method)


# ─────────────────────────────────────────────────────────────
# 能力
# ─────────────────────────────────────────────────────────────


def test_unknown_capability_is_treated_as_dangerous():
    """拼错的能力名不能悄悄退化成放行 —— 保守当作 exec。"""
    svc = declared({"m": {"capabilities": ["exce"]}})
    caps = method_capabilities(svc, "m")
    assert Capability.EXEC in caps


def test_undeclared_capability_defaults_to_read():
    svc = declared({"m": {}})
    assert method_capabilities(svc, "m") == frozenset({Capability.READ})


# ─────────────────────────────────────────────────────────────
# 参数
# ─────────────────────────────────────────────────────────────


def test_oversized_string_param_is_denied():
    assert inspect_params({"k": "x" * (DEFAULT_POLICY.max_param_str_len + 1)}) == \
        ReasonCode.PARAM_TOO_LARGE


def test_oversized_list_param_is_denied():
    big = list(range(DEFAULT_POLICY.max_param_list_len + 1))
    assert inspect_params({"k": big}) == ReasonCode.PARAM_TOO_LARGE


def test_deeply_nested_param_is_denied():
    node: object = "leaf"
    for _ in range(DEFAULT_POLICY.max_param_depth + 3):
        node = {"child": node}
    assert inspect_params({"k": node}) == ReasonCode.PARAM_TOO_LARGE


def test_path_traversal_is_denied():
    assert inspect_params({"path": "../../etc/passwd"}) == ReasonCode.PARAM_UNSAFE
    assert inspect_params({"path": "..\\windows\\system32"}) == ReasonCode.PARAM_UNSAFE


def test_normal_params_pass():
    assert inspect_params({"name": "你好", "count": 3}) is None


# ─────────────────────────────────────────────────────────────
# reason_code 稳定性
# ─────────────────────────────────────────────────────────────


def test_reason_code_never_contains_user_text():
    """拒绝原因必须是低基数常量，不能把用户输入拼进 code（§5）。"""
    svc = declared({"read_thing": {}})
    payload = "恶意";  # 任意用户输入
    v = evaluate(svc, "demo", "read_thing", {"p": "../" + payload})
    assert v.reason_code == ReasonCode.PARAM_UNSAFE
    assert payload not in v.reason_code.value
    assert v.reason_code.value.isascii()


# ─────────────────────────────────────────────────────────────
# 执行器：超时与输出上限
# ─────────────────────────────────────────────────────────────


class FakeSM:
    def __init__(self, svc):
        self._svc = svc

    def get_service(self, name):
        return self._svc


def cmd(service="demo", method="block_forever", params=None, raw="raw"):
    return {"service": service, "method": method, "params": params or {}, "raw": raw}


async def test_executor_timeout_is_reported():
    svc = FakeService({"block_forever": {}})
    ex = CommandExecutor(FakeSM(svc), policy=ToolPolicy(default_timeout_s=0.2))
    result = await ex._invoke(cmd())
    assert result["ok"] is False
    assert result["status"] == CommandStatus.ERROR.value
    assert "超时" in (result["error"] or "")


async def test_executor_caps_large_result():
    svc = FakeService({"read_thing": {}})
    svc.read_thing = lambda name="": "x" * 5000
    ex = CommandExecutor(FakeSM(svc), policy=ToolPolicy(max_result_chars=200))
    result = await ex._invoke(cmd(method="read_thing"))
    assert result["ok"] is True
    assert len(str(result["data"])) < 5000
    assert "截断" in str(result["data"])


async def test_executor_passes_normal_result_through():
    svc = FakeService({"read_thing": {}})
    ex = CommandExecutor(FakeSM(svc), policy=ToolPolicy(max_result_chars=8000))
    result = await ex._invoke(cmd(method="read_thing", params={"name": "abc"}))
    assert result["ok"] is True
    assert result["data"] == "read:abc"


async def test_async_method_is_awaited_not_returned_as_coroutine():
    svc = FakeService({"slow_read": {}})
    ex = CommandExecutor(FakeSM(svc), policy=ToolPolicy(default_timeout_s=5))
    result = await ex._invoke(cmd(method="slow_read", params={"seconds": 0.01}))
    assert result["ok"] is True
    assert result["data"] == "done", "协程方法必须被 await，不能把协程对象当结果"
