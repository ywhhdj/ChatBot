"""工具执行安全策略

为什么单独一个模块
──────────────────
策略判定是**纯函数**：输入"服务声明了什么 + 命令要调什么 + 参数长什么样"，
输出 allow/deny 与稳定 reason_code。它不该知道命令怎么执行、结果怎么格式化。
拆出来后可以脱离执行器单测，也便于把同一套规则复用到
REST / WebSocket / Qt bridge（SecurityAndAuditDesign §3）。

三条硬约束（来自 SecurityAndAuditDesign §3）
────────────────────────────────────────────
1. **LLM 产出意图而非授权**：模型说什么都不构成权限。
   确定性执行层必须自己检查身份、权限、参数和业务状态。
2. **deny by default**：方法必须出现在服务声明的 tools 里才可调用。
   "方法存在"不等于"允许调用" —— 这是本模块要堵的最主要缺口。
3. **shell / 未隔离语言默认拒绝**：即使声明了也不放行，
   除非显式授予 `DANGEROUS` 且策略开关打开。

reason_code 的稳定性
────────────────────
低基数、稳定、不含自由文本。调用方可以拿它做计数与告警，
所以绝不能把用户输入的片段拼进 code —— 那是日志注入的入口。
需要给人看的细节放 `message`，且已经过长度截断。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from ...security.workspace import command_verdict

#: 唯一允许进程执行的服务 id。其余服务即使声明 EXEC 也不放行。
SHELL_SERVICE_ID = "shell"

# ─────────────────────────────────────────────────────────────
# 能力
# ─────────────────────────────────────────────────────────────


class Capability(str, Enum):
    """命令可能涉及的副作用类别。

    取自服务声明，不来自模型输出。一个方法可声明多个。
    """

    #: 只读，无副作用
    READ = "read"
    #: 修改本机状态（配置、服务开关）
    WRITE = "write"
    #: 访问网络
    NETWORK = "network"
    #: 读写文件系统
    FILESYSTEM = "filesystem"
    #: 执行外部进程 / 任意代码。**默认禁用**
    EXEC = "exec"
    #: 触及凭据、密钥、存档等敏感资源
    SENSITIVE = "sensitive"


#: 默认允许的能力。EXEC 不在其中 —— shell/脚本默认拒绝（验收标准）。
DEFAULT_ALLOWED_CAPABILITIES: FrozenSet[Capability] = frozenset({
    Capability.READ,
    Capability.WRITE,
    Capability.NETWORK,
    Capability.FILESYSTEM,
    Capability.SENSITIVE,
})

#: 需要显式放行的能力（策略开关 + 方法声明同时具备才通过）
DANGEROUS_CAPABILITIES: FrozenSet[Capability] = frozenset({Capability.EXEC})


# ─────────────────────────────────────────────────────────────
# 决策
# ─────────────────────────────────────────────────────────────


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ReasonCode(str, Enum):
    """稳定低基数的拒绝/通过理由。**不含自由文本**。"""

    OK = "ok"
    #: 服务未注册
    SERVICE_NOT_REGISTERED = "service_not_registered"
    #: 服务存在但方法不在声明的 tools 里（deny by default）
    METHOD_NOT_DECLARED = "method_not_declared"
    #: 服务根本没声明 tools，无法判定意图
    SERVICE_UNDECLARED = "service_undeclared"
    #: 命中 shell/脚本/执行类黑名单
    EXEC_FORBIDDEN = "exec_forbidden"
    #: 声明了需要显式放行的能力，但策略未开
    CAPABILITY_NOT_GRANTED = "capability_not_granted"
    #: 参数超出大小/数量/深度限制
    PARAM_TOO_LARGE = "param_too_large"
    #: 参数含危险形态（路径穿越等）
    PARAM_UNSAFE = "param_unsafe"
    #: shell 命令命中危险动词 / 拼接 / 逃逸形态
    COMMAND_FORBIDDEN = "command_forbidden"


@dataclass(frozen=True)
class PolicyVerdict:
    """策略判定结果。frozen：判定完成后不该被中途改写。"""

    decision: Decision
    reason_code: ReasonCode
    #: 给人看的说明。已截断，不含用户输入原文。
    message: str = ""
    #: 该命令实际生效的超时（秒）
    timeout_s: float = 0.0

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "message": self.message,
            "timeout_s": self.timeout_s,
        }


def allow(timeout_s: float, message: str = "") -> PolicyVerdict:
    return PolicyVerdict(Decision.ALLOW, ReasonCode.OK, message, timeout_s)


def deny(code: ReasonCode, message: str = "") -> PolicyVerdict:
    return PolicyVerdict(Decision.DENY, code, message, 0.0)


# ─────────────────────────────────────────────────────────────
# 策略配置
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolPolicy:
    """工具执行策略。frozen：运行期不应被请求内容改写（§9 验收项）。"""

    #: 单条命令默认超时（秒）。0 = 不限（不推荐）。
    default_timeout_s: float = 30.0
    #: 声明了 EXEC 的方法是否放行。**默认 False**
    allow_exec: bool = False
    #: 允许的能力集合
    allowed_capabilities: FrozenSet[Capability] = DEFAULT_ALLOWED_CAPABILITIES
    #: 服务未声明 tools 时是否放行。
    #: 迁移期可临时打开，但必须留下日志痕迹（见 `warn_undeclared`）。
    allow_undeclared_service: bool = False
    #: 是否对 shell 服务的 command 参数做纯函数粗筛。**默认 True**
    inspect_shell_command: bool = True
    #: 单个字符串参数最大字符数
    max_param_str_len: int = 4000
    #: 单个数组参数最大元素数
    max_param_list_len: int = 200
    #: 参数最大嵌套深度
    max_param_depth: int = 6
    #: 单条命令参数总个数上限
    max_param_count: int = 50
    #: 结果序列化后的最大字符数（超出截断，见 exceute.py）
    max_result_chars: int = 8000

    def with_exec_allowed(self, value: bool) -> "ToolPolicy":
        return replace(self, allow_exec=value)

    def with_timeout(self, seconds: float) -> "ToolPolicy":
        return replace(self, default_timeout_s=max(0.0, float(seconds)))


#: 默认策略。改这里要同步 PLAN.md 与 SecurityAndAuditDesign 的验收清单。
DEFAULT_POLICY = ToolPolicy()


# ─────────────────────────────────────────────────────────────
# 危险形态识别
# ─────────────────────────────────────────────────────────────

#: 方法名中命中即视为"执行类"。**不看参数、不看模型怎么说**。
#: 用子串匹配而非精确匹配：真实代码里这类方法名形态很多
#: （`run_shell` / `execCommand` / `powershell_run`）。
#:
#: 刻意**不含裸 `sh`**：它会误杀 show / flush / push / hash / dashboard
#: 这类完全无害的方法。shell 语义由 `shell` / `bash` / `zsh` 覆盖。
_EXEC_METHOD_TOKENS: Tuple[str, ...] = (
    "shell",
    "exec",
    "eval",
    "spawn",
    "subprocess",
    "popen",
    "system",
    "bash",
    "zsh",
    "powershell",
    "cmd",
    "command",
    "script",
    "runtime",
)

#: 显式白名单：含上面 token 但确实安全的方法（避免误杀）。
#: `run` 同时是 shell 服务的方法名 —— 真正的准入在 ShellService 内部完成。
_EXEC_METHOD_ALLOWLIST: FrozenSet[str] = frozenset({
    "error",   # 内置 error 命令
    "run",     # skill.run 与 shell.run，均走受控执行
})

#: 参数值中出现的路径穿越形态。
_TRAVERSAL_TOKENS: Tuple[str, ...] = ("..\\", "../", "~/", "%2e%2e", "..%2f")


def looks_like_exec(service: str, method: str) -> bool:
    """方法名是否像执行类命令。"""
    if method.lower() in _EXEC_METHOD_ALLOWLIST:
        return False
    lowered = method.lower()
    return any(token in lowered for token in _EXEC_METHOD_TOKENS)


def _contains_traversal(value: str) -> bool:
    lowered = value.lower()
    return any(t in lowered for t in _TRAVERSAL_TOKENS)


# ─────────────────────────────────────────────────────────────
# 参数检查
# ─────────────────────────────────────────────────────────────


def inspect_params(
    params: Mapping[str, Any],
    policy: ToolPolicy = DEFAULT_POLICY,
) -> Optional[ReasonCode]:
    """检查参数规模与危险形态。通过返回 None。

    为什么要在执行前查：prompt injection 最常见的载荷就是
    "让模型把一个巨大或带 `../` 的参数塞进工具调用"。
    执行层不能假设参数是良性。
    """
    if len(params) > policy.max_param_count:
        return ReasonCode.PARAM_TOO_LARGE

    for value in params.values():
        code = _inspect_value(value, policy, depth=1)
        if code is not None:
            return code
    return None


def _inspect_value(value: Any, policy: ToolPolicy, depth: int) -> Optional[ReasonCode]:
    if depth > policy.max_param_depth:
        return ReasonCode.PARAM_TOO_LARGE

    if isinstance(value, str):
        if len(value) > policy.max_param_str_len:
            return ReasonCode.PARAM_TOO_LARGE
        # 只查"看起来像路径"的字符串：过短或明显是自然语言的不查，
        # 避免把用户正常聊天内容误判为穿越尝试。
        if _contains_traversal(value):
            return ReasonCode.PARAM_UNSAFE
        return None

    if isinstance(value, (list, tuple)):
        if len(value) > policy.max_param_list_len:
            return ReasonCode.PARAM_TOO_LARGE
        for item in value:
            code = _inspect_value(item, policy, depth + 1)
            if code is not None:
                return code
        return None

    if isinstance(value, dict):
        if len(value) > policy.max_param_list_len:
            return ReasonCode.PARAM_TOO_LARGE
        for item in value.values():
            code = _inspect_value(item, policy, depth + 1)
            if code is not None:
                return code
        return None

    return None


# ─────────────────────────────────────────────────────────────
# 声明解析
# ─────────────────────────────────────────────────────────────


def _service_tools(service: Any) -> Any:
    """取服务声明的工具集合。

    现行 `BaseService` 子类实现 `get_tools()` 返回 `List[ToolFunction]`；
    早期代码只读 `tools` 属性。两种形态都要兼容，否则所有服务都会被
    判成 `SERVICE_UNDECLARED`（工具链整体不可用）。
    """
    tools = getattr(service, "tools", None)
    if tools is not None:
        return tools
    getter = getattr(service, "get_tools", None)
    if callable(getter):
        try:
            return getter()
        except Exception:  # noqa: BLE001
            return None
    return None


def declared_methods(service: Any) -> Optional[List[str]]:
    """服务声明的可调用方法名列表。

    返回 None 表示该服务**完全没有声明** tools —— 与"声明了但为空列表"
    是两回事：前者无法判定意图（deny），后者是"明确什么都不能调"（deny）。
    两种都拒绝，但 reason_code 不同，便于运维区分。
    """
    tools = _service_tools(service)
    if tools is None:
        return None
    names: List[str] = []
    if isinstance(tools, dict):
        names.extend(str(k) for k in tools.keys())
    elif isinstance(tools, (list, tuple)):
        for item in tools:
            if isinstance(item, dict):
                name = item.get("name") or item.get("method")
            else:
                name = getattr(item, "name", None) or getattr(item, "method", None)
            if name:
                names.append(str(name))
    return names


def method_capabilities(service: Any, method: str) -> FrozenSet[Capability]:
    """方法声明的能力。未声明时按 READ 处理（最小权限）。"""
    cfg = _find_method_config(service, method)
    if not cfg:
        return frozenset({Capability.READ})

    raw: Any = None
    if isinstance(cfg, dict):
        raw = cfg.get("capabilities") or cfg.get("capability")
    else:
        raw = getattr(cfg, "capabilities", None) or getattr(cfg, "capability", None)

    if raw is None:
        return frozenset({Capability.READ})
    if isinstance(raw, str):
        raw = [raw]

    out = set()
    for item in raw or []:
        try:
            out.add(Capability(str(item).strip().lower()))
        except ValueError:
            # 未知能力名不忽略 —— 保守当作需要显式放行的能力，
            # 否则拼错的 "exce" 会悄悄退化成放行。
            out.add(Capability.EXEC)
    return frozenset(out)


def _find_method_config(service: Any, method: str) -> Any:
    """兼容 dict / list / 对象三种 tools 形态（与 formatter.CommandValidator 一致）。"""
    tools = _service_tools(service)
    if not tools:
        return None
    if isinstance(tools, dict):
        return tools.get(method)
    if isinstance(tools, (list, tuple)):
        for item in tools:
            if isinstance(item, dict):
                name = item.get("name") or item.get("method")
            else:
                name = getattr(item, "name", None) or getattr(item, "method", None)
            if name == method:
                return item
    return None


# ─────────────────────────────────────────────────────────────
# 主判定
# ─────────────────────────────────────────────────────────────


def evaluate(
    service: Any,
    service_name: str,
    method: str,
    params: Mapping[str, Any],
    policy: ToolPolicy = DEFAULT_POLICY,
) -> PolicyVerdict:
    """判定一条命令能否执行。**纯函数，无 IO、无全局状态**。

    顺序是有讲究的：先判"是否声明"（deny by default），
    再判"是否执行类"，最后判参数 —— 这样 reason_code 总能指向
    最根本的那个原因，而不是被参数问题掩盖了权限问题。
    """
    if service is None:
        return deny(ReasonCode.SERVICE_NOT_REGISTERED, f"服务未注册: {service_name}")

    # 1) 执行类：不论声明与否，先过黑名单
    if looks_like_exec(service_name, method):
        caps = method_capabilities(service, method)
        if not (policy.allow_exec and Capability.EXEC in caps):
            return deny(
                ReasonCode.EXEC_FORBIDDEN,
                f"{service_name}.{method} 属于执行类能力，默认禁用",
            )

    # 2) deny by default：方法必须在声明里
    declared = declared_methods(service)
    if declared is None:
        if not policy.allow_undeclared_service:
            return deny(
                ReasonCode.SERVICE_UNDECLARED,
                f"服务 {service_name} 未声明可调用工具，默认拒绝",
            )
    elif method not in declared:
        return deny(
            ReasonCode.METHOD_NOT_DECLARED,
            f"{method} 不在服务 {service_name} 声明的工具内",
        )

    # 3) 能力是否在允许集合内
    #
    # 注意与第 1 步的一致性：`allow_exec=True` 必须同时把 EXEC 加进
    # 有效能力集合，否则第 1 步刚放行、第 3 步又拒绝，策略自相矛盾，
    # 且调用方无法判断到底该改哪个开关。
    effective = set(policy.allowed_capabilities)
    if policy.allow_exec:
        effective.add(Capability.EXEC)

    caps = method_capabilities(service, method)
    forbidden = caps - effective
    if forbidden & DANGEROUS_CAPABILITIES:
        return deny(
            ReasonCode.CAPABILITY_NOT_GRANTED,
            f"{service_name}.{method} 需要未授予的能力: exec",
        )
    if forbidden:
        return deny(
            ReasonCode.CAPABILITY_NOT_GRANTED,
            f"{service_name}.{method} 能力不在允许集合内",
        )

    # 4) shell 命令粗筛。执行层（ShellService）会再做一次完整的
    # 平台映射、白名单与工作区边界判定；这里只是不让明显的危险命令
    # 走到起子进程那一步，同时让拒绝原因在策略层就可计数告警。
    if service_name == SHELL_SERVICE_ID and policy.inspect_shell_command:
        verdict = command_verdict(str(params.get("command", "") or ""))
        if not verdict.allowed:
            return deny(ReasonCode.COMMAND_FORBIDDEN, verdict.message)

    # 5) 参数规模与危险形态
    code = inspect_params(params, policy)
    if code is not None:
        return deny(code, "参数超出安全限制或含不安全形态")

    return allow(policy.default_timeout_s)
