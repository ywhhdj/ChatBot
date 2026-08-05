from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any, List

from .models import CommandData, CommandResult, CommandStatus


class CommandExecutor:
    def __init__(self, service_manager: Any, mode: str = "sequential"):
        self._sm = service_manager
        self._mode = mode

    async def execute(
        self,
        commands: List[CommandData],
        validated: List[CommandResult],
    ) -> List[CommandResult]:
        runnable = [
            (index, cmd)
            for index, (cmd, check) in enumerate(zip(commands, validated))
            if check["status"] == CommandStatus.PENDING.value
        ]
        results: List[CommandResult] = list(validated)
        if self._mode == "concurrent":
            executed = await asyncio.gather(*(self._invoke(cmd) for _, cmd in runnable))
            for (index, _), result in zip(runnable, executed):
                results[index] = result
            return results
        for index, cmd in runnable:
            results[index] = await self._invoke(cmd)
        return results

    async def _invoke(self, cmd: CommandData) -> CommandResult:
        service_name = cmd["service"]
        method_name = cmd["method"]
        params = dict(cmd["params"])
        position_args = params.pop("_args", None)
        started = time.perf_counter()
        try:
            service = self._sm.get_service(service_name)
            method = getattr(service, method_name)
            if inspect.iscoroutinefunction(method):
                data = await method(*(position_args or []), **params)
            else:
                data = method(*(position_args or []), **params)
            return CommandResult(
                ok=True,
                service=service_name,
                method=method_name,
                status=CommandStatus.SUCCESS.value,
                data=data,
                error=None,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=cmd["raw"],
            )
        except Exception as exc:
            return CommandResult(
                ok=False,
                service=service_name,
                method=method_name,
                status=CommandStatus.ERROR.value,
                data=None,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=cmd["raw"],
            )


class ResultFormatter:
    @staticmethod
    def to_prompt(results: List[CommandResult]) -> str:
        lines = ["## 命令执行结果"]
        for index, result in enumerate(results, 1):
            lines.append(f"{index}. {result['raw']} -> {result['status']}")
            if result["ok"]:
                lines.append(f"返回: {ResultFormatter._truncate(str(result['data']))}")
            else:
                lines.append(f"错误: {result['error']}")
        return "\n".join(lines)

    @staticmethod
    def to_json(results: List[CommandResult]) -> str:
        return json.dumps(results, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def to_summary(results: List[CommandResult]) -> str:
        total = len(results)
        ok = sum(1 for item in results if item["ok"])
        fail = total - ok
        if fail == 0:
            return f"全部 {total} 条命令执行成功"
        return f"{total} 条命令中 {ok} 成功, {fail} 失败"

    @staticmethod
    def _truncate(text: str, limit: int = 200) -> str:
        return text if len(text) <= limit else text[:limit] + f"... (截断, 共 {len(text)} 字符)"
