"""服务编排器：把 LLM 产出的命令文本解析、校验、执行并汇总。"""

from __future__ import annotations
import hashlib
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...logger import logger
from ...services.manager import service_manager
from ..routes.models import RouteType
from .policy import ToolPolicy, DEFAULT_POLICY, evaluate as evaluate_policy
from ..context.assembly import ToolBudgetState, NO_TOOLS
from .services.exceute import CommandExecutor, ResultFormatter
from .services.formatter import CommandParser, CommandValidator, SHELL_SERVICE_ID
from .services.models import (
    CommandData,
    CommandResult,
    CommandStatus,
    OrchestrationState,
)
from .model import OrchestrationConfig
from .skills.manager import ExternalSkillManager


def _tool_call_id(command: Any) -> str:
    if not isinstance(command, dict):
        return uuid.uuid4().hex[:12]
    raw = f"{command.get('service','')}.{command.get('method','')}|{command.get('raw','')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _result_to_tool_item(
    result: Dict[str, Any],
    label: str,
    item_id: str = ""
) -> Dict[str, Any]:
    """CommandResult -> ToolCallItem（TD3）。"""
    status = result.get("status") or ("success" if result.get("ok") else "error")
    return {
        "id": item_id or _tool_call_id(result),
        "service": result.get("service", ""),
        "method": result.get("method", ""),
        "raw": result.get("raw", ""),
        "status": status,
        "params": {},
        "result": result.get("data"),
        "error": result.get("error") or "",
        "elapsedMs": int(result.get("elapsed_ms", 0) or 0),
        "label": label,
    }


class CLTTool:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "CLTTool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        config: Optional[OrchestrationConfig] = None,
        policy: Optional[ToolPolicy] = None,
    ) -> None:
        self._sm = service_manager
        self.config: OrchestrationConfig = {
            "skill_dir": "skills",
            "max_tool_calls": 10,
            "exec_mode": "sequential",
            "stop_on_fatal": False,
        }
        if config:
            self.config.update(config)
        self._parser = CommandParser()
        self._validator = CommandValidator(service_manager)
        #: 执行安全策略。默认 deny-by-default + 禁用执行类。
        self._policy: ToolPolicy = policy or DEFAULT_POLICY
        self._executor = CommandExecutor(
            service_manager, mode=self.config.get("exec_mode"), policy=self._policy
        )
        self._skills = ExternalSkillManager(skill_dir=Path(self.config.get("skill_dir")))
        self._state = OrchestrationState()
        self._ensure_shell_service()

        #: 单轮最大工具调用次数，-1 = 无上限。
        self.max_tool_calls: int = int(self.config.get("max_tool_calls", -1))
        self._tool_listener: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._current_messages: List[Dict[str, Any]] = []
        #: 策略判定留痕。只存 service/method/决策/原因码，
        #: **不存参数与返回正文**（SecurityAndAuditDesign §5）。
        self._policy_decisions: List[Dict[str, Any]] = []
        #: 本轮工具额度状态。动态装配据此决定是否切"强制总结"阶段。
        self._budget_state: ToolBudgetState = NO_TOOLS

    def _ensure_shell_service(self) -> None:
        """确保 shell 兜底服务已注册"""
        try:
            if self._sm.is_registered(SHELL_SERVICE_ID):
                return
            from ...services.shell.service import ShellService

            ShellService()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[Orchestrator] shell 服务注册失败: {type(exc).__name__}"
            )

    def set_policy(self, policy: ToolPolicy) -> None:
        """替换执行策略（如切换到更严格的远程模式）。"""
        self._policy = policy
        self._executor = CommandExecutor(
            self._sm, mode=self.config.get("exec_mode"), policy=policy
        )

    def set_tool_listener(self, listener: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
        """注册工具生命周期回调。

        `listener(event, item)`，event 为 `start` / `end`。
        """
        self._tool_listener = listener

    def _emit_tool(self, event: str, item: Dict[str, Any]) -> None:
        if self._tool_listener is None:
            return
        try:
            self._tool_listener(event, item)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Orchestrator] tool listener error: {exc}")

    def _label_for(self, service: str, method: str) -> str:
        """TD3：人话标题。

        `ServiceManager.get_tools()` 返回的是
        `[{"service": name, "tools": [ToolFunction, ...]}]`，
        需要下钻一层才能拿到方法描述。
        """
        try:
            entries = self._sm.get_tools()
        except Exception:  # noqa: BLE001
            return f"{service}.{method}"
        for entry in entries or []:
            if isinstance(entry, dict):
                tools = entry.get("tools") or []
            else:
                tools = getattr(entry, "tools", None) or []
            for t in tools or []:
                name = getattr(t, "name", None) or (
                    t.get("name") if isinstance(t, dict) else None)
                desc = getattr(t, "description", None) or (
                    t.get("description") if isinstance(t, dict) else None
                )
                if name == method and desc:
                    return str(desc)
        return f"{service}.{method}"

    def get_tools(self) -> List[Dict[str, Any]]:
        return self._sm.get_tools()

    # ---------- 执行 ----------

    async def _run(self, text: str) -> Dict[str, Any]:
        try:
            service_names = list(self._sm.services.keys())
        except Exception:  # noqa: BLE001
            service_names = []
        commands = self._parser.parse(text, service_names)
        round_results = await self._execute_commands(commands)
        results = round_results
        self._state.history.append({
            "input": text,
            "results": round_results,
        })
        self._state.last_results = round_results

        if not self._state.stop_reason:
            self._state.stop_reason = "命令执行完毕"

        return {
            "success": all(item.get("ok") for item in results) if results else False,
            "results": results,
            "summary": ResultFormatter.to_summary(results),
            "rounds": self._state.round,
            "stop_reason": self._state.stop_reason,
            #: 动态装配需要知道额度是否打满。此前截断是**静默**的：
            #: 上层只看到"执行了 N 条"，无从得知还有 M 条被丢掉，
            #: 于是模型继续输出命令、用户以为任务还在跑。
            "budget": self._budget_state.as_dict(),
        }

    @property
    def budget_state(self) -> ToolBudgetState:
        """本轮工具额度状态（供动态装配读取）。"""
        return self._budget_state

    async def run_raw_commands_async(self, text: str) -> Dict[str, Any]:
        """可等待版本
        调用方在协程里应优先用这个方法：
        `await orch.run_raw_commands_async(text)`
        """
        return await self._run(text)

    def run_raw_commands(self, text: str):
        """调度器版本：提交到任务调度器，返回 TaskReference"""
        from ..native.decorator import async_task_scheduler
        @async_task_scheduler
        async def _task():
            return await self._run(text)
        return _task()

    async def _execute_commands(self, commands: List[CommandData]) -> List[CommandResult]:
        limit: int = self.max_tool_calls
        requested = len(commands)
        skipped: List[CommandData] = []
        if limit >= 0 and len(commands) > limit:
            skipped = list(commands[limit:])
            commands = list(commands[:limit])
            for cmd in skipped:
                self._emit_tool("end", {
                    "id": _tool_call_id(cmd),
                    "service": cmd.get("service", ""),
                    "method": cmd.get("method", ""),
                    "raw": cmd.get("raw", ""),
                    "status": "skipped",
                    "params": dict(cmd.get("params", {}) or {}),
                    "result": None,
                    "error": f"超出单轮最大工具调用次数 {limit}，未执行",
                    "elapsedMs": 0,
                    "label": self._label_for(cmd.get("service", ""), cmd.get("method", "")),
                })
            logger.warning(
                f"[Orchestrator] 单轮命令 {len(commands) + len(skipped)} 条"
                f"超过上限 {limit}，截断 {len(skipped)} 条"
            )

        # 额度状态在本轮开始时落地，供动态装配在总结阶段读取。
        self._budget_state = ToolBudgetState(
            limit=limit,
            used=len(commands),
            requested=requested,
            skipped=len(skipped),
        )

        results: List[CommandResult] = []
        service_commands: List[CommandData] = []
        service_indices: List[int] = []

        for command in commands:
            if command["service"] == "skill":
                results.append(await self._execute_skill_command(command))
            elif command["service"] == "error":
                # error 命令不进执行器，直接记为失败
                validated = self._validator.validate([command])
                results.extend(validated)
            else:
                service_indices.append(len(results))
                service_commands.append(command)
                results.append(CommandResult(
                    ok=False,
                    service=command["service"],
                    method=command["method"],
                    status=CommandStatus.PENDING.value,
                    data=None,
                    error=None,
                    elapsed_ms=0,
                    raw=command["raw"],
                ))

        # TD6：执行前发 start（前端立刻能看到"正在调用…"卡片）
        for cmd in service_commands:
            self._emit_tool("start", {
                "id": _tool_call_id(cmd),
                "service": cmd.get("service", ""),
                "method": cmd.get("method", ""),
                "raw": cmd.get("raw", ""),
                "status": "running",
                "params": dict(cmd.get("params", {}) or {}),
                "result": None,
                "error": "",
                "elapsedMs": 0,
                "label": self._label_for(cmd.get("service", ""), cmd.get("method", "")),
            })

        if service_commands:
            validated = self._validator.validate(service_commands)
            validated = self._apply_policy(service_commands, validated)
            executed = await self._executor.execute(service_commands, validated)
            for index, result in zip(service_indices, executed):
                results[index] = result
                # 执行完发 end（同一 id，前端增量更新同一张卡）
                self._emit_tool("end", _result_to_tool_item(
                    dict(result),
                    self._label_for(
                        result.get("service", ""),
                        result.get("method", "")
                    ),
                    _tool_call_id(
                        service_commands[service_indices.index(index)]
                        if index in service_indices else {}
                    ),
                ))
        return results

    def _apply_policy(
        self,
        commands: List[CommandData],
        validated: List[CommandResult],
    ) -> List[CommandResult]:
        """把通过参数校验的命令再过一遍安全策略。

        为什么不在 `CommandValidator` 里一起做
        ──────────────────────────────────────
        校验回答"这条命令**格式对不对**"（服务存在吗、参数齐吗）；
        策略回答"**允不允许**调"。两件事混在一起，
        就没法单独回答"这条是被格式拦下的还是被权限拦下的"——
        而 SecurityAndAuditDesign §5 要求拒绝也要可追踪。

        被拒绝的命令记为 SKIPPED（不是 ERROR）：
        它没有执行，不该算作"执行失败"。
        """
        out: List[CommandResult] = list(validated)
        for index, (cmd, result) in enumerate(zip(commands, validated)):
            if result.get("status") != CommandStatus.PENDING.value:
                continue

            service_name = cmd.get("service", "")
            method_name = cmd.get("method", "")
            try:
                service = self._sm.get_service(service_name)
            except Exception:  # noqa: BLE001
                service = None

            verdict = evaluate_policy(
                service=service,
                service_name=service_name,
                method=method_name,
                params=cmd.get("params", {}) or {},
                policy=self._policy,
            )

            # 审计留痕：拒绝也要能查到原因（§5 成功/失败/拒绝均可追踪）
            self._policy_decisions.append({
                "service": service_name,
                "method": method_name,
                "decision": verdict.decision.value,
                "reason_code": verdict.reason_code.value,
            })

            if verdict.allowed:
                continue

            # B1-08：被拒绝的调用单独发事件。与正常调用分开是为了
            # 让"被拒"可被计数告警——混在成功事件里就会被淹没。
            self._record_denial(service_name, method_name, verdict.reason_code.value)

            logger.warning(
                f"[Orchestrator] 命令被策略拒绝: {service_name}.{method_name} "
                f"({verdict.reason_code.value}) {verdict.message}"
            )
            out[index] = CommandResult(
                ok=False,
                service=service_name,
                method=method_name,
                status=CommandStatus.SKIPPED.value,
                data=None,
                error=f"安全策略拒绝 [{verdict.reason_code.value}]: {verdict.message}",
                elapsed_ms=0,
                raw=cmd.get("raw", ""),
            )
        return out

    @staticmethod
    def _record_denial(service: str, method: str, reason_code: str) -> None:
        """拒绝留痕：优先写 audit 事件，模块不可用时退化为结构化日志。

        只记 service / method / 稳定原因码，不记参数与返回正文。
        原实现直接调用未导入的 `audit.record(...)`，会在拒绝路径上抛
        NameError，把"被安全策略拦下"变成 500。
        """
        try:
            from ...logger import audit

            audit.record(
                audit.Action.TOOL_DENIED,
                resource=audit.Resource(
                    type=audit.ResourceType.TOOL.value,
                    id=f"{service}.{method}",
                ),
                decision=audit.Decision.DENY,
                result=audit.Result.FAILURE,
                reason_code=reason_code,
                source=audit.Source.TASK,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                f"[Orchestrator] 工具拒绝留痕: {service}.{method} ({reason_code})"
            )

    async def _execute_skill_command(self, command: CommandData) -> CommandResult:
        started = time.perf_counter()
        params = dict(command.get("params", {}) or {})
        skill_id = str(params.get("id", "") or "").strip()
        if not skill_id:
            return CommandResult(
                ok=False,
                service="skill",
                method="run",
                status=CommandStatus.ERROR.value, data=None,
                error='skill 命令缺少 --id 参数（应为: skill --id <id> --des "..."）',
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=command.get("raw", ""),
            )
        try:
            data = await self._skills.execute_skill(skill_id, params)
            if isinstance(data, dict):
                ok = bool(data.get("ok"))
                error = None if ok else data.get("error")
            else:
                ok = data is not None
                error = None if ok else "技能未返回结果"
                data = {
                    "ok": ok,
                    "data": data
                }
            return CommandResult(
                ok=ok,
                service="skill",
                method="run",
                status=CommandStatus.SUCCESS.value if ok else CommandStatus.ERROR.value,
                data=data,
                error=error,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=command["raw"],
            )
        except Exception as exc:
            logger.warning(f"Skill execution failed: {exc}")
            return CommandResult(
                ok=False,
                service="skill",
                method="run",
                status=CommandStatus.ERROR.value,
                data=None,
                error=str(exc),
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=command["raw"],
            )

    # ---------- 审计 ----------

    def get_audit_result(self) -> Dict[str, Any]:
        return {
            "rounds": self._state.round,
            "history": self._state.history,
            "all_results": [
                item for row in self._state.history for item in row.get("results", [])
            ],
            "stop_reason": self._state.stop_reason,
            "messages": self._current_messages,
            #: 策略判定记录。供审计事件消费，
            #: 只含低基数 reason_code，不含正文。
            "policy_decisions": list(self._policy_decisions),
        }

    def reset_state(self) -> None:
        self._state = OrchestrationState()
        self._current_messages = []
        self._policy_decisions = []
