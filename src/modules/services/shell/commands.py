"""平台命令映射与命令计划（纯判定，不执行任何进程）。

为什么把"系统差异"单独成文件
────────────────────────────
同一个意图在不同系统上写法不同：`dir` / `ls`、`type` / `cat`、
`copy` / `cp`、`del` / `rm`。模型输出的是它最熟悉的那一种，
执行层必须按 `sys.platform` 归一后再映射到本机原生命令，
而不是把 `ls` 原样丢给 `cmd.exe`。

两道判定不信任任何模型文本：
1. `security.workspace.command_verdict()` —— 平台无关的粗筛（危险动词、拼接、逃逸形态）；
2. 本文件的 `plan_command()` —— 平台方言归一 + 白名单 + 原生命令生成。

`ShellService` 在真正起子进程之前还会做一次 cwd / 路径参数边界复验。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

from ...security.workspace import (
    FORBIDDEN_COMMAND_TOKENS,
    DenyReason,
    command_verdict,
)

# ─────────────────────────────────────────────────────────────
# 平台
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShellPlatform:
    name: str
    executable: str
    prefix: Tuple[str, ...]
    path_sep: str


def current_platform() -> ShellPlatform:
    if sys.platform == "win32":
        return ShellPlatform("windows", "cmd.exe", ("/C",), "\\")
    if sys.platform == "darwin":
        return ShellPlatform("macos", "/bin/sh", ("-c",), "/")
    return ShellPlatform("linux", "/bin/sh", ("-c",), "/")


_ALLOWED_SHELL_OVERRIDES = frozenset({
    "cmd.exe", "powershell.exe", "/bin/sh", "/bin/bash", "sh", "bash",
})


def shell_spec(platform: Optional[str] = None, override: str = "") -> ShellPlatform:
    """返回 (可执行文件, 参数前缀)。配置覆盖只允许白名单内的 shell。"""
    if platform == "windows":
        plat = ShellPlatform("windows", "cmd.exe", ("/C",), "\\")
    elif platform in ("linux", "macos"):
        plat = ShellPlatform(str(platform), "/bin/sh", ("-c",), "/")
    else:
        plat = current_platform()

    if not override:
        return plat

    name = os.path.basename(str(override).replace("\\", "/")).lower()
    if name not in _ALLOWED_SHELL_OVERRIDES:
        raise ValueError(f"不允许的 shell 程序: {override!r}")
    if name == "cmd.exe":
        prefix = ("/C",)
    elif name == "powershell.exe":
        prefix = ("-NoProfile", "-NonInteractive", "-Command")
    else:
        prefix = ("-c",)
    return ShellPlatform(plat.name, str(override), prefix, plat.path_sep)


# ─────────────────────────────────────────────────────────────
# 方言归一
# ─────────────────────────────────────────────────────────────

_ALIAS_TO_CANONICAL: Dict[str, str] = {
    "dir": "ls",
    "type": "cat", 
    "more": "cat",
    "copy": "cp",
    "xcopy": "cp",
    "move": "mv", 
    "ren": "mv", 
    "rename": "mv",
    "md": "mkdir",
    "rd": "rmdir",
    "del": "rm", 
    "erase": "rm", 
    "unlink": "rm", 
    "shred": "rm",
    "cls": "clear",
    "chdir": "cd",
    "ver": "uname",
    "mkfs": "format",
}

#: 归一后允许执行的命令（POSIX 风格）。删除/破坏类一律不在此集合。
ALLOWED_CANONICAL: FrozenSet[str] = frozenset({
    "ls", "cd", "pwd", "tree", "find",
    "cat", "head", "tail", "wc", "grep", "sort", "uniq", "diff",
    "file", "stat", "du", "df", "basename", "dirname",
    "cp", "mv", "mkdir", "touch", "echo",
    "clear", "date", "time", "whoami", "hostname", "uname", "where",
})

#: 归一后 → 各平台原生程序名（未列出的保持 canonical）
_NATIVE: Dict[str, Dict[str, str]] = {
    "windows": {
        "ls": "dir", "cat": "type", "clear": "cls", "cp": "copy",
        "mv": "move", "pwd": "cd", "uname": "ver", "find": "findstr",
    },
    "linux": {
        "dir": "ls", "type": "cat", "copy": "cp", "xcopy": "cp",
        "move": "mv", "ren": "mv", "rename": "mv", "md": "mkdir",
        "cls": "clear", "chdir": "cd", "ver": "uname",
    },
    "macos": {
        "dir": "ls", "type": "cat", "copy": "cp", "xcopy": "cp",
        "move": "mv", "ren": "mv", "rename": "mv", "md": "mkdir",
        "cls": "clear", "chdir": "cd", "ver": "uname",
    },
}

#: Windows 下 `ls` → `dir` 时的常见 POSIX 选项映射。
#: 未列出的选项原样保留（最多是命令报参数错误，不会放宽权限）。
_WINDOWS_LS_OPTIONS: Dict[str, str] = {
    "-la": "/A",
    "-al": "/A",
    "-l": "/A",
    "-a": "/A",
    "-R": "/S",
    "-s": "/O:-S",
}

#: 语义无法等价映射的命令，直接拒绝而不是"执行了但结果不对"
_UNSUPPORTED_BY_PLATFORM: Dict[str, FrozenSet[str]] = {
    "windows": frozenset({
        "head", 
        "tail", 
        "wc", 
        "stat", 
        "du", 
        "df", 
        "file", 
        "basename",
        "dirname",
        "uniq",
        "diff",
        "touch",
        "grep",
    }),
    "linux": frozenset({"where"}),
    "macos": frozenset({"where"}),
}

_PROG_RE = re.compile(r'^\s*(?P<prog>"[^"]+"|\'[^\']+\'|\S+)(?P<rest>.*)$', re.S)


def _split_program(text: str) -> Tuple[str, str]:
    """取出程序名与**原样保留**的剩余部分。

    不重新拼装参数：引号、反斜杠、Windows 盘符都要原封不动交给 shell，
    重新 shlex 一遍反而会破坏路径。
    """
    match = _PROG_RE.match(str(text or ""))
    if not match:
        return "", ""
    return match.group("prog").strip("'\""), match.group("rest")


def _norm_program(program: str) -> str:
    name = os.path.basename(str(program).replace("\\", "/")).lower()
    if name.endswith((".exe", ".com", ".bat", ".cmd")):
        name = name.rsplit(".", 1)[0]
    return name


def canonical_of(program: str) -> str:
    name = _norm_program(program)
    return _ALIAS_TO_CANONICAL.get(name, name)


# ─────────────────────────────────────────────────────────────
# 命令计划
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CommandPlan:
    allowed: bool
    reason: str = DenyReason.OK.value
    program: str = ""          # canonical，低基数，可进日志
    native_command: str = ""   # 实际交给 shell 的文本
    message: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "allowed": str(self.allowed).lower(),
            "reason": self.reason,
            "program": self.program,
            "message": self.message,
        }


def _deny(reason: DenyReason, program: str, message: str) -> CommandPlan:
    return CommandPlan(False, reason.value, program, "", message)


def plan_command(
    text: str,
    *,
    platform: Optional[str] = None,
    allow_dangerous: bool = False,
) -> CommandPlan:
    """把一行模型命令变成可执行计划。**纯函数**。

    `allow_dangerous` 只影响粗筛；删除/破坏类命令在
    `FORBIDDEN_COMMAND_TOKENS` 中仍会被第二道判定拒绝 —— 这是硬约束，
    不因为配置或工作区档位放开。
    """
    raw = str(text or "").strip()
    if not raw:
        return _deny(DenyReason.COMMAND_DENIED, "", "空命令")

    verdict = command_verdict(raw, allow_dangerous=allow_dangerous)
    if not verdict.allowed:
        return CommandPlan(
            False, verdict.reason.value, verdict.program, "", verdict.message
        )

    program, rest = _split_program(raw)
    canonical = canonical_of(program)

    if canonical in FORBIDDEN_COMMAND_TOKENS:
        return _deny(
            DenyReason.COMMAND_DENIED, canonical,
            f"命令 {canonical} 属于删除/破坏/提权类，一律拒绝",
        )

    if canonical not in ALLOWED_CANONICAL:
        return _deny(
            DenyReason.COMMAND_DENIED, canonical,
            f"命令 {canonical} 不在允许列表内",
        )

    plat = shell_spec(platform)
    if canonical in _UNSUPPORTED_BY_PLATFORM.get(plat.name, frozenset()):
        return _deny(
            DenyReason.COMMAND_DENIED, canonical,
            f"命令 {canonical} 在 {plat.name} 上没有等价实现",
        )

    if plat.name == "windows" and canonical == "ls":
        for option, replacement in _WINDOWS_LS_OPTIONS.items():
            rest = re.sub(
                rf"(?<!\S){re.escape(option)}(?!\S)", replacement, rest
            )

    native = _NATIVE.get(plat.name, {}).get(canonical, canonical)
    return CommandPlan(
        True, DenyReason.OK.value, canonical, native + rest, ""
    )


# ─────────────────────────────────────────────────────────────
# 子进程环境
# ─────────────────────────────────────────────────────────────

_SENSITIVE_ENV_HINTS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL",
    "PRIVATE", "AUTH", "SESSION",
)
_REQUIRED_ENV_KEYS = (
    "PATH", "SystemRoot", "TEMP", "TMP", "TMPDIR", "USERPROFILE", "HOME",
    "LANG", "LC_ALL", "COMSPEC", "PATHEXT", "OS",
)


def clean_environment() -> Dict[str, str]:
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        if any(hint in key.upper() for hint in _SENSITIVE_ENV_HINTS):
            continue
        env[key] = value
    for key in _REQUIRED_ENV_KEYS:
        if key in os.environ and key not in env:
            env[key] = os.environ[key]
    env.setdefault("PATH", os.defpath)
    return env
