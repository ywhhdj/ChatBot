"""服务编排器：把 LLM 产出的命令文本解析、校验、执行并汇总。"""

from __future__ import annotations
import hashlib
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..logger import logger
from ..manager.service.manager import service_manager
from ..routes.models import RouteType
from .services.exceute import CommandExecutor, ResultFormatter
from .services.formatter import CommandParser, CommandValidator
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
    ) -> None:
        self._sm = service_manager
        self.config: OrchestrationConfig= {
            "skill_dir": "skills",
            "max_tool_calls": 10,
            "exec_mode": "sequential",
            "stop_on_fatal": False,
        }
        if config:
            self.config.update(config)
        self._parser = CommandParser()
        self._validator = CommandValidator(service_manager)
        self._executor = CommandExecutor(service_manager, mode=self.config.get("exec_mode"))
        self._skills = ExternalSkillManager(skill_dir=Path(self.config.get("skill_dir")))
        self._state = OrchestrationState()

        #: 单轮最大工具调用次数，-1 = 无上限。
        self.max_tool_calls: int = int(self.config.get("max_tool_calls", -1))
        self._tool_listener: Optional[Callable[[str, Dict[str, Any]], None]] = None
    
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
        """TD3：人话标题，如 `obs.switch_scene` -> "切换OBS场景"。"""
        try:
            tools = self._sm.get_tools()
        except Exception:  # noqa: BLE001
            return f"{service}.{method}"
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
        results: List[CommandResult] = []
        commands = self._parser.parse(text)
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
        }

    async def run_raw_commands_async(self, text: str) -> Dict[str, Any]:
        """可等待版本
        调用方在协程里应优先用这个方法：
        `await orch.run_raw_commands_async(text)`
        """
        return await self._run(text)

    def run_raw_commands(self, text: str):
        """调度器版本：提交到任务调度器，返回 TaskReference"""
        from ..core.native.decorator import async_task_scheduler
        @async_task_scheduler
        async def _task():
            return await self._run(text)
        return _task()

    async def _execute_commands(self, commands: List[CommandData]) -> List[CommandResult]:
        limit: int = self.max_tool_calls
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
            executed = await self._executor.execute(service_commands, validated)
            for index, result in zip(service_indices, executed):
                results[index] = result
                # 执行完发 end（同一 id，前端增量更新同一张卡）
                self._emit_tool("end", _result_to_tool_item(
                    result.__dict__, 
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
        }

    def reset_state(self) -> None:
        self._state = OrchestrationState()
        self._current_messages = []
