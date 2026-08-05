from __future__ import annotations
from typing import Any, Dict, List, Optional

from ..manager.task.decorator import async_task_scheduler
from ..routes.models import RouteType
from ..logger import logger
from ..manager.service.manager import service_manager
from .services.exceute import CommandExecutor, ResultFormatter
from .services.formatter import CommandParser, CommandValidator
from .services.models import CommandData, CommandResult, CommandStatus, OrchestrationConfig, OrchestrationState
from .skills.manager import ExternalSkillManager


class ServiceOrchestrator:
    """Prompt-command orchestrator for service calls and skills."""

    def __init__(
        self,
        config: Optional[OrchestrationConfig] = None,
    ) -> None:
        self._sm = service_manager
        self._config: Dict[str, Any] = {
            "max_rounds": 5,
            "exec_mode": "sequential",
            "stop_on_fatal": False,
            "external_skill_dir": "skills",
        }
        if config:
            self._config.update(config)
        self._parser = CommandParser()
        self._validator = CommandValidator(service_manager)
        self._executor = CommandExecutor(service_manager, mode=self._config["exec_mode"])
        self._skills = ExternalSkillManager()
        self._state = OrchestrationState()
        self._current_messages: List[Dict[str, str]] = []


    @async_task_scheduler
    async def run_raw_commands(self, command_text: str) -> Dict[str, Any]:
        commands = self._parser.parse(command_text)
        results = await self._execute_commands(commands)
        return {
            "success": all(item["ok"] for item in results) if results else False,
            "results": results,
            "summary": ResultFormatter.to_summary(results),
        }

    def _build_system_prompt(self, recent_context: List[Dict[str, str]]):
        from ..config.builder import PromptBuilder
        tools = service_manager.get_tools()
        skill_prompt = self._skills.build_prompt()
        return PromptBuilder.build(
            character=None,
            route=RouteType.TOOL_CALL,
            user_input="",
            tool_prompt=PromptBuilder.build_commands_prompt(tools),
            skill_prompt=skill_prompt,
            recent_context=recent_context,
        )

    def _extract_commands(self, text: str) -> tuple[str, List[CommandData]]:
        text_lines: List[str] = []
        commands: List[CommandData] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if CommandParser._looks_like_command(stripped):
                command = CommandParser._parse_line(stripped)
                if command:
                    commands.append(command)
                    continue
            text_lines.append(line)
        return "\n".join(text_lines).strip(), commands

    async def _execute_commands(self, commands: List[CommandData]) -> List[CommandResult]:
        results: List[CommandResult] = []
        service_commands: List[CommandData] = []
        service_indices: List[int] = []
        for command in commands:
            if command["service"] == "skill":
                started_result = await self._execute_skill_command(command)
                results.append(started_result)
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

        if service_commands:
            validated = self._validator.validate(service_commands)
            executed = await self._executor.execute(service_commands, validated)
            for index, result in zip(service_indices, executed):
                results[index] = result
        return results

    async def _execute_skill_command(self, command: CommandData) -> CommandResult:
        import time

        started = time.perf_counter()
        name = str(command["params"].get("name", ""))
        try:
            data = await self._skills.execute_skill(name, command["params"])
            return CommandResult(
                ok=bool(data.get("ok")),
                service="skill",
                method="run",
                status=CommandStatus.SUCCESS.value if data.get("ok") else CommandStatus.ERROR.value,
                data=data,
                error=None if data.get("ok") else data.get("error"),
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

    # async def _generate_final_message(self, messages: List[Dict[str, str]], results: List[CommandResult]) -> str:
    #     try:
    #         return await self._llm(messages + [{
    #             "role": "user",
    #             "content": "命令已经执行完毕，请用一句自然友好的话告诉用户结果。\n" + ResultFormatter.to_prompt(results),
    #         }])
    #     except Exception:
    #         return ResultFormatter.to_summary(results)

    def get_audit_result(self) -> Dict[str, Any]:
        return {
            "rounds": self._state.round,
            "history": self._state.history,
            "all_results": [item for row in self._state.history for item in row["results"]],
            "stop_reason": self._state.stop_reason,
            "messages": self._current_messages,
        }
