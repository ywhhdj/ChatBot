"""目标工作区（沙盒）权限模型与敏感内容脱敏。

用户在工作区选择器里指定一个目录，并授予三档之一：

| 档位 | 读 | 写 | 删 | 执行 |
|---|---|---|---|---|
| `READ_ONLY`    | ✓ | ✗ | ✗ | ✗ |
| `WRITABLE`     | ✓ | ✓ | ✗ | ✗ |
| `UNRESTRICTED` | ✓ | ✓ | ✓ | ✓ |

**只读可以读任意文件**，但有一条不可让渡的例外：
apikey / 密钥 / 签名相关文件，或内容里含这些东西，
交给 AI 之前一律脱敏。只有用户**明确确认**（`allow_sensitive=True` + 一次
显式确认动作）才允许看原文，且该次确认会进轨迹日志。

为什么"完全放开"也不是真的无边界
──────────────────────────────
轨迹日志（`logger/trail.py`）记录 AI 自己做过什么。
允许 AI 删轨迹 = 允许嫌疑人烧掉监控录像。
所以删除保护是**两层**：

1. **物理隔离**：轨迹文件根本不在工作区目录内（放在应用数据目录），
   AI 的文件操作路径永远解析不到它；
2. **策略硬拦截**：`UNRESTRICTED` 下对轨迹路径的删除/截断/清空
   依旧返回 `DENY`，且这个判定不读任何配置、不可被覆盖。

只做第 2 条是不够的——将来有人改了策略就失效了；
只做第 1 条也不够——AI 可能通过别的通道（命令执行）摸到绝对路径。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

from ..utils.file.atomic import is_within

# ─────────────────────────────────────────────────────────────
# 权限
# ─────────────────────────────────────────────────────────────


class WorkspaceMode(str, Enum):
    READ_ONLY = "read_only"
    WRITABLE = "writable"
    UNRESTRICTED = "unrestricted"


class Operation(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXEC = "exec"


#: 各档位允许的操作。写死在一处，避免散落各处比较字符串。
_PERMISSIONS: Dict[WorkspaceMode, FrozenSet[Operation]] = {
    WorkspaceMode.READ_ONLY: frozenset({Operation.READ}),
    WorkspaceMode.WRITABLE: frozenset({Operation.READ, Operation.WRITE}),
    WorkspaceMode.UNRESTRICTED: frozenset({
        Operation.READ, Operation.WRITE, Operation.DELETE, Operation.EXEC,
    }),
}


class DenyReason(str, Enum):
    """拒绝原因。稳定低基数，进审计与轨迹。"""

    OK = "ok"
    NO_WORKSPACE = "no_workspace"
    OUTSIDE_ROOT = "outside_root"
    SYMLINK_ESCAPE = "symlink_escape"
    MODE_DENIED = "mode_denied"
    TRAIL_PROTECTED = "trail_protected"
    INVALID_PATH = "invalid_path"
    NOT_A_FILE = "not_a_file"


@dataclass(frozen=True)
class AccessVerdict:
    allowed: bool = False
    reason: DenyReason = DenyReason.OK
    path: str = ""
    operation: str = ""
    #: 是否需要先对内容脱敏
    scrub_required: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value,
            "path": self.path,
            "operation": self.operation,
            "scrub_required": self.scrub_required,
        }


@dataclass(frozen=True)
class Workspace:
    """一个被选中的目标工作区。frozen：切换用 `replace()` 派生新对象。"""

    root: str = ""
    mode: WorkspaceMode = WorkspaceMode.READ_ONLY
    #: 是否允许把敏感原文交给 AI。**默认 False**，
    #: 且必须由 `confirm_sensitive_exposure()` 显式翻开。
    allow_sensitive: bool = False
    #: 用户显式确认的记录 id（进轨迹，便于事后追责）
    confirmation_id: str = ""

    def resolved_root(self) -> str:
        return os.path.realpath(os.path.abspath(self.root))

    def with_confirmation(self, confirmation_id: str) -> "Workspace":
        return replace(self, allow_sensitive=True, confirmation_id=str(confirmation_id))

    def without_confirmation(self) -> "Workspace":
        return replace(self, allow_sensitive=False, confirmation_id="")


#: 未选择工作区的空对象
NO_WORKSPACE = Workspace()


# ─────────────────────────────────────────────────────────────
# 路径边界
# ─────────────────────────────────────────────────────────────


def resolve_in(workspace: Workspace, path: str) -> Tuple[Optional[str], DenyReason]:
    """把用户/AI 给的路径解析成绝对路径，并确认仍在工作区内。

    必须 `realpath`：**符号链接**是路径逃逸最常见的手段 ——
    `root/link -> /etc` 在字符串上看起来完全在 root 内。
    """
    if not workspace.root:
        return None, DenyReason.NO_WORKSPACE
    if not path or "\x00" in str(path):
        return None, DenyReason.INVALID_PATH

    root = workspace.resolved_root()
    candidate = os.path.realpath(os.path.abspath(str(path)))
    if not os.path.isabs(candidate):
        return None, DenyReason.INVALID_PATH

    if not is_within(root, candidate):
        # 区分"本来就在外面"和"指向外面的软链"，便于告警定位
        lexical = os.path.abspath(str(path))
        if is_within(root, lexical) and not is_within(root, candidate):
            return None, DenyReason.SYMLINK_ESCAPE
        return None, DenyReason.OUTSIDE_ROOT
    return candidate, DenyReason.OK


def check(
    workspace: Workspace,
    path: str,
    operation: Operation,
) -> AccessVerdict:
    """判定一次访问。**纯函数**，不改任何状态。

    `scrub_required` 恒为 True，除非工作区里带有效确认标记 ——
    读操作永远走脱敏，这是默认安全，不需要调用方记得加。
    """
    op = operation if isinstance(operation, Operation) else Operation(str(operation))
    resolved, reason = resolve_in(workspace, path)
    if resolved is None:
        return AccessVerdict(False, reason, str(path), op.value)

    # 轨迹保护：任何档位、任何操作路径都不放开删除/截断/清空
    if op in (Operation.DELETE, Operation.WRITE) and _is_trail_path(resolved):
        return AccessVerdict(
            False, DenyReason.TRAIL_PROTECTED, resolved, op.value
        )

    if op not in _PERMISSIONS.get(workspace.mode, frozenset()):
        return AccessVerdict(
            False, DenyReason.MODE_DENIED, resolved, op.value
        )

    if op == Operation.READ and not os.path.isfile(resolved):
        return AccessVerdict(
            False, DenyReason.NOT_A_FILE, resolved, op.value
        )

    return AccessVerdict(
        allowed=True,
        reason=DenyReason.OK,
        path=resolved,
        operation=op.value,
        scrub_required=not workspace.allow_sensitive,
    )


def _is_trail_path(path: str) -> bool:
    """轨迹文件路径识别。由 trail 模块提供权威判定，这里做无依赖兜底。

    写成函数而不是常量集合：轨迹目录可能随配置变化，
    硬编码一串名字迟早会漏。
    """
    try:
        from ..logger.trail import is_trail_path

        return is_trail_path(path)
    except Exception:  # noqa: BLE001
        normalized = str(path).replace("\\", "/").lower()
        return "/trail/" in normalized or normalized.endswith(".trail")


# ─────────────────────────────────────────────────────────────
# 敏感识别与脱敏
# ─────────────────────────────────────────────────────────────

REDACTED = "[REDACTED:secret]"

#: 文件名片段：命中即视为**敏感文件**（整文件不直接给 AI）
SENSITIVE_NAME_TOKENS: FrozenSet[str] = frozenset({
    "api_key", "apikey", "secret", "password", "passwd", "credential",
    "private_key", "privatekey", "id_rsa", "id_dsa", "id_ecdsa",
    "signature", "signing", "keystore", "token", "auth", ".env",
})

#: 敏感扩展名
SENSITIVE_SUFFIXES: FrozenSet[str] = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx",
})

#: 内容模式。命中即替换该片段。
_CONTENT_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("pem_private_key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.S,
    )),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("hex_signature", re.compile(r"\b[0-9a-fA-F]{64,}\b")),
    ("assigned_secret", re.compile(
        r"(?im)^\s*(?:api[_-]?key|apikey|secret|password|passwd|token|"
        r"access[_-]?key|private[_-]?key|signature|client[_-]?secret|"
        r"authorization|bearer)\s*[:=]\s*(?P<q>['\"]?)(?P<v>[^\s'\"#,;]{4,})(?P=q)\s*$"
    )),
    ("bearer_header", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}")),
)


class Sensitivity(str, Enum):
    NONE = "none"
    #: 文件名/扩展名命中 —— 整文件不给原文
    FILE = "file"
    #: 内容里含敏感片段 —— 逐段替换
    CONTENT = "content"


@dataclass(frozen=True)
class ScrubResult:
    text: str
    sensitivity: Sensitivity = Sensitivity.NONE
    #: 命中的类型（低基数，不记原文）
    findings: Tuple[str, ...] = ()
    #: 替换次数
    redacted: int = 0
    #: 是否因为文件名命中而整段拒绝
    blocked: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sensitivity": self.sensitivity.value,
            "findings": list(self.findings),
            "redacted": self.redacted,
            "blocked": self.blocked,
        }


def classify_name(path: str) -> bool:
    """文件名本身是否敏感。"""
    name = os.path.basename(str(path)).lower()
    suffix = os.path.splitext(name)[1]
    if suffix in SENSITIVE_SUFFIXES:
        return True
    return any(token in name for token in SENSITIVE_NAME_TOKENS)


def scrub_text(text: str, *, allow_sensitive: bool = False) -> ScrubResult:
    """把文本里的密钥/签名片段替换掉。**纯函数**。

    `allow_sensitive=True` 只在用户明确确认后由调用方传入；
    此时仍返回 `findings`，让轨迹日志能记下"这次看了什么类型"，
    只是不替换内容 —— **确认不是无痕**。
    """
    if text is None:
        return ScrubResult("")
    original = str(text)
    if allow_sensitive:
        kinds, _ = _scan(original)
        return ScrubResult(
            original,
            Sensitivity.CONTENT if kinds else Sensitivity.NONE,
            kinds, 0, False,
        )

    findings: List[str] = []
    redacted = 0
    out = original

    for kind, pattern in _CONTENT_PATTERNS:
        if kind == "assigned_secret":
            def _repl(m: "re.Match") -> str:
                return m.group(0).replace(m.group("v"), REDACTED)
            out, n = pattern.subn(_repl, out)
        else:
            out, n = pattern.subn(REDACTED, out)
        if n:
            findings.append(kind)
            redacted += n

    return ScrubResult(
        out,
        Sensitivity.CONTENT if findings else Sensitivity.NONE,
        tuple(sorted(set(findings))),
        redacted,
        False,
    )


def _scan(text: str) -> Tuple[Tuple[str, ...], int]:
    kinds: List[str] = []
    total = 0
    for kind, pattern in _CONTENT_PATTERNS:
        n = len(pattern.findall(text))
        if n:
            kinds.append(kind)
            total += n
    return tuple(sorted(set(kinds))), total


def _trail(action: Any, **kwargs: Any) -> None:
    """写轨迹。轨迹写入失败绝不能影响业务判定。"""
    try:
        from ..logger import trail

        trail.record(action, **kwargs)
    except Exception:  # noqa: BLE001
        pass


def _root_label(root: str) -> str:
    """路径标签：目录名 + 短 hash。

    不把完整绝对路径写进日志 —— 路径常含用户名、盘符、公司目录结构，
    属于隐私（SecurityAndAuditDesign §6：默认不记录不必要的绝对路径）。
    """
    import hashlib

    base = os.path.basename(os.path.abspath(str(root))) or "root"
    digest = hashlib.sha256(os.path.abspath(str(root)).encode("utf-8")).hexdigest()[:8]
    return f"{base}#{digest}"


def read_for_ai(
    workspace: Workspace,
    path: str,
    *,
    encoding: str = "utf-8",
    max_bytes: int = 512 * 1024,
) -> Tuple[str, AccessVerdict, ScrubResult]:
    """AI 读工作区文件的**唯一安全入口**。

    三件事一次做完：路径边界 → 权限判定 → 脱敏。
    调用方不需要（也不应该）自己拼这三步，漏任何一步都会泄密。

    敏感文件名命中时返回占位文本而不是原文（除非工作区带确认标记），
    并且 `blocked=True`，让轨迹日志能记下"这次有人试图读密钥文件"。
    """
    verdict = check(workspace, path, Operation.READ)
    if not verdict.allowed:
        _trail(
            "file.read",
            source="workspace.read",
            actor="ai",
            target=os.path.basename(str(path)),
            decision="deny",
            result="denied",
            reason_code=verdict.reason.value,
            metadata={"operation": "read"},
        )
        return "", verdict, ScrubResult("")

    if classify_name(verdict.path) and verdict.scrub_required:
        _trail(
            "sensitive.blocked",
            source="workspace.read",
            actor="ai",
            target=os.path.basename(verdict.path),
            decision="deny",
            result="denied",
            reason_code="sensitive_filename",
            metadata={"workspace": _root_label(workspace.root)},
        )
        return (
            f"{REDACTED} 该文件被识别为密钥/签名相关文件，内容未提供给 AI。",
            verdict,
            ScrubResult("", Sensitivity.FILE, ("sensitive_filename",), 1, True),
        )

    try:
        with open(verdict.path, "rb") as fh:
            raw = fh.read(max_bytes + 1)
    except OSError:
        return "", verdict, ScrubResult("")
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode(encoding, errors="replace")
    if truncated:
        text += "\n[TRUNCATED]"

    result = scrub_text(text, allow_sensitive=not verdict.scrub_required)
    _trail(
        "sensitive.exposed" if not verdict.scrub_required else "file.read",
        source="workspace.read",
        actor="ai",
        target=os.path.basename(verdict.path),
        decision="allow",
        result="ok",
        metadata={
            "workspace": _root_label(workspace.root),
            "findings": list(result.findings),
            "redacted": result.redacted,
            "confirmed": not verdict.scrub_required,
        },
    )
    return text if not verdict.scrub_required else result.text, verdict, result


# ─────────────────────────────────────────────────────────────
# 当前工作区（单例，由 UI 的选择器切换）
# ─────────────────────────────────────────────────────────────


class WorkspaceRegistry:
    """当前工作区。切换必须走这里，便于统一发轨迹事件。"""

    def __init__(self) -> None:
        import threading

        self._lock = threading.RLock()
        self._current: Workspace = NO_WORKSPACE

    def current(self) -> Workspace:
        with self._lock:
            return self._current

    def select(
        self,
        root: str,
        mode: WorkspaceMode = WorkspaceMode.READ_ONLY,
    ) -> Workspace:
        with self._lock:
            self._current = Workspace(
                root=os.path.abspath(str(root)),
                mode=mode if isinstance(mode, WorkspaceMode)
                else WorkspaceMode(str(mode)),
                allow_sensitive=False,
                confirmation_id="",
            )
            _trail(
                "workspace.select",
                source="ui.workspace_selector",
                actor="user",
                target=_root_label(self._current.root),
                decision="allow",
                result="ok",
                metadata={"mode": self._current.mode.value},
            )
            return self._current

    def confirm_sensitive_exposure(self, confirmation_id: str) -> Workspace:
        """用户显式确认后允许看原文。**必须由 UI 的确认动作调用**。"""
        with self._lock:
            self._current = self._current.with_confirmation(confirmation_id)
            _trail(
                "sensitive.exposed",
                source="ui.confirmation",
                actor="user",
                target=_root_label(self._current.root),
                decision="allow",
                result="ok",
                metadata={"confirmation_id": str(confirmation_id)[:32]},
            )
            return self._current

    def revoke(self) -> Workspace:
        with self._lock:
            self._current = self._current.without_confirmation()
            return self._current

    def clear(self) -> None:
        with self._lock:
            self._current = NO_WORKSPACE


_workspace = WorkspaceRegistry()


def get_workspace() -> Workspace:
    return _workspace.current()


def select_workspace(root: str, mode: WorkspaceMode = WorkspaceMode.READ_ONLY) -> Workspace:
    return _workspace.select(root, mode)


def confirm_sensitive_exposure(confirmation_id: str) -> Workspace:
    return _workspace.confirm_sensitive_exposure(confirmation_id)


def clear_workspace() -> None:
    _workspace.clear()
