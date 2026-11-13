"""受控 shell 服务：工作区内的常规命令执行。

这是**唯一**被允许的进程执行入口。三层确定性检查，任何一层都不信任模型文本：

1. `security/workspace` —— 工作区档位、cwd 边界、路径参数 `realpath` 复验；
2. `shell/commands.plan_command` —— 平台方言归一 + 白名单 + 危险命令拒绝；
3. 进程资源限制 —— 净化环境、超时、输出字节上限、结果脱敏。

模型直接写命令原文（`cd docs` / `ls -la` / `mkdir report`），
不需要 `shell --command` 之类包装；解析由 `core/tools/services/formatter.py` 完成。
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import ShellConfig
from ...core.pipeline.models import ToolFunction, ToolFunctionParameters
from ...keys import ServiceKeys
from ...logger import logger
from ...security import (
    DenyReason,
    Operation,
    WorkspaceBoundaryError,
    check,
    ensure_workspace,
    resolve_command_path,
    resolve_in,
    scrub_text,
    service_output_dir,
)
from ..base import BaseService, ServiceState
from ..manager import Service
from .commands import clean_environment, plan_command, shell_spec

_ARG_RE = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')


@Service(id=ServiceKeys.SHELL)
class ShellService(BaseService):
    """工作区内命令执行（注册为服务 id `shell`）。"""

    name = "命令行"
    description = "工作区内的受控 shell 命令（浏览/定位/读写文件，删除与危险命令一律拒绝）"

    def __init__(
        self,
        shell: str = "",
        timeout: float = 30.0,
        max_output_bytes: int = 65536,
        allow_dangerous_commands: bool = False,
        cwd_scope: str = "workspace",
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.shell = str(shell or "")
        self.config= ShellConfig(
            timeout=max(1.0, float(timeout or 30.0)),
            max_output_bytes=max(1024, int(max_output_bytes or 65536)),
            allow_dangerous_commands=allow_dangerous_commands,
            cwd_scope=(
            cwd_scope if cwd_scope in ("workspace", "service_output") else "workspace"
        ),
        )
        self.timeout = max(1.0, float(timeout or 30.0))
        self.max_output_bytes = max(1024, int(max_output_bytes or 65536))
        # 保留字段：删除/破坏类命令是硬约束，不因配置放开。
        self.allow_dangerous_commands = bool(allow_dangerous_commands)
        self.cwd_scope = (
            cwd_scope if cwd_scope in ("workspace", "service_output") else "workspace"
        )
        self._cwd_lock = threading.RLock()
        self._cwd: Optional[str] = None
        # 构造尚未启动，状态交给 ServiceManager 管理。
        self.running = False
        self.set_status()

    # ---------- 状态 ----------

    def set_status(self) -> None:
        super().set_status(ServiceState.RUNNING if self.running else ServiceState.STOPPED)

    def start(self, *args: Any, **kwargs: Any) -> Any:
        self.running = True
        self.set_status()
        return True

    def stop(self, *args: Any, **kwargs: Any) -> Any:
        self.running = False
        self.set_status()
        return True

    def close(self, *args: Any, **kwargs: Any) -> Any:
        return self.stop()

    # ---------- 工具声明 ----------

    def get_tools(self) -> List[ToolFunction]:
        return [
            ToolFunction(
                name="run",
                description=(
                    "在工作区内执行常规 shell 命令：cd/ls/dir/pwd/mkdir/md/"
                    "cat/type/head/tail/cp/copy/mv/move/echo/tree 等。"
                    "删除(rm/del/rd)、提权、任意解释器、管道与重定向一律拒绝。"
                ),
                parameters=ToolFunctionParameters(
                    type="object",
                    properties={
                        "command": {
                            "type": "string",
                            "description": (
                                "命令原文，直接写 cd docs、ls -la、mkdir report；"
                                "不要加 shell 前缀，也不要用 --command 包装"
                            ),
                        },
                        "cwd": {
                            "type": "string",
                            "description": "可选：工作区内的相对目录",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "可选超时（秒）",
                        },
                    },
                    required=["command"],
                ),
            )
        ]

    # ---------- 内部辅助 ----------

    @staticmethod
    def _record(action: str, decision: str, result: str, **meta: Any) -> None:
        """低基数留痕：只记 program / 原因码，绝不记命令原文与输出正文。"""
        try:
            from ...logger import trail

            trail.record(
                action,
                source="service.shell",
                actor="ai",
                decision=decision,
                result=result,
                metadata=meta,
            )
        except Exception:  # noqa: BLE001
            pass

    def _fail(
        self,
        message: str,
        reason: str,
        started: float,
        program: str = "",
    ) -> Dict[str, Any]:
        self._record("shell.exec", "deny", "denied", reason_code=reason, program=program)
        logger.warning(f"[Shell] 命令被拒绝: {reason} ({program or 'unknown'})")
        return {
            "ok": False,
            "program": program,
            "error": message,
            "reason": reason,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "cwd": "",
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    @staticmethod
    def _relative(root: str, path: str) -> str:
        try:
            rel = os.path.relpath(path, root)
            return "." if rel == "." else rel.replace("\\", "/")
        except Exception:  # noqa: BLE001
            return ""

    def _cap(self, text: str) -> str:
        raw = str(text or "").encode("utf-8", errors="replace")
        if len(raw) <= self.max_output_bytes:
            return str(text or "")
        return (
            raw[: self.max_output_bytes].decode("utf-8", errors="replace")
            + "\n[TRUNCATED]"
        )

    @staticmethod
    def _argument_tokens(raw: str) -> List[str]:
        """取命令参数里"看起来像路径"的 token，跳过选项。"""
        parts = raw.split(None, 1)
        if len(parts) < 2:
            return []
        out: List[str] = []
        for token in _ARG_RE.findall(parts[1]):
            value = token.strip().strip('"').strip("'")
            if not value or value.startswith("-"):
                continue
            out.append(value)
        return out

    def _resolve_cwd(self, ws: Any, cwd: Optional[str]) -> str:
        """解析本次执行目录，并确保仍在工作区内。"""
        root = ws.resolved_root()
        base = self._cwd or root

        if cwd:
            resolved, reason = resolve_command_path(ws, base, str(cwd))
            if resolved is None:
                raise WorkspaceBoundaryError("cwd 越界", reason)
            if not os.path.isdir(resolved):
                raise WorkspaceBoundaryError("cwd 不存在", DenyReason.INVALID_PATH)
            return resolved

        if self._cwd:
            resolved, reason = resolve_in(ws, self._cwd)
            if resolved is None or not os.path.isdir(resolved):
                # 工作区切换后旧 cwd 失效，回到根目录，不静默沿用
                with self._cwd_lock:
                    self._cwd = None
            else:
                return resolved

        if self.cwd_scope == "service_output":
            return service_output_dir(ServiceKeys.SHELL)
        return root

    # ---------- 执行 ----------

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """执行一条命令，返回结构化结果。

        `cd` 不启动子进程（子进程改 cwd 无法回传），只更新会话内 cwd；
        后续命令在同一 `ShellService` 实例上沿用该目录。
        """
        started = time.perf_counter()
        raw = str(command or "").strip()
        if not raw:
            return self._fail("空命令", DenyReason.COMMAND_DENIED.value, started)

        try:
            ws = ensure_workspace()
        except WorkspaceBoundaryError as exc:
            return self._fail(str(exc), exc.reason.value, started)

        try:
            base = self._resolve_cwd(ws, cwd)
        except WorkspaceBoundaryError as exc:
            return self._fail(str(exc), exc.reason.value, started)

        access = check(ws, base, Operation.WRITE)
        if not access.allowed:
            return self._fail("工作区不允许写入", access.reason.value, started)

        plan = plan_command(raw)
        if not plan.allowed:
            return self._fail(plan.message, plan.reason, started, plan.program)

        # 逐个路径参数做 realpath 边界复验：绝对路径越界、`../`、
        # 指向工作区外的符号链接都会在这里被拦下。
        first_resolved: Optional[str] = None
        for token in self._argument_tokens(raw):
            resolved, reason = resolve_command_path(ws, base, token)
            if resolved is None:
                return self._fail(
                    "路径参数越过工作区边界",
                    reason.value,
                    started,
                    plan.program,
                )
            if first_resolved is None:
                first_resolved = resolved

        elapsed = lambda: int((time.perf_counter() - started) * 1000)

        if plan.program == "cd":
            if first_resolved is None or not os.path.isdir(first_resolved):
                return self._fail(
                    "cd 目标不存在或不是目录",
                    DenyReason.NOT_A_FILE.value,
                    started,
                    "cd",
                )
            with self._cwd_lock:
                self._cwd = first_resolved
            self._record("shell.cd", "allow", "ok", program="cd")
            return {
                "ok": True,
                "program": "cd",
                "cwd": self._relative(ws.resolved_root(), first_resolved),
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "error": None,
                "reason": "ok",
                "elapsed_ms": elapsed(),
            }

        limit = float(timeout) if timeout and float(timeout) > 0 else self.timeout
        spec = shell_spec(override=self.shell)
        argv = [spec.executable, *spec.prefix, plan.native_command]

        try:
            proc = subprocess.run(
                argv,
                cwd=base,
                env=clean_environment(),
                capture_output=True,
                timeout=limit,
                shell=False,
                text=True,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return self._fail(f"命令超时（{limit:.0f}s）", "timeout", started, plan.program)
        except OSError as exc:
            return self._fail(
                f"shell 不可用: {type(exc).__name__}",
                "shell_unavailable",
                started,
                plan.program,
            )

        # 输出上限 + 敏感脱敏：stdout/stderr 也视为不可信外部内容
        stdout = scrub_text(self._cap(proc.stdout or ""), allow_sensitive=False).text
        stderr = scrub_text(self._cap(proc.stderr or ""), allow_sensitive=False).text
        ok = proc.returncode == 0
        self._record(
            "shell.exec", "allow", "ok" if ok else "failure",
            program=plan.program, exit_code=proc.returncode,
        )

        return {
            "ok": ok,
            "program": plan.program,
            "cwd": self._relative(ws.resolved_root(), base),
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "error": None if ok else f"命令退出码 {proc.returncode}",
            "reason": "ok" if ok else "exit_nonzero",
            "elapsed_ms": elapsed(),
        }
