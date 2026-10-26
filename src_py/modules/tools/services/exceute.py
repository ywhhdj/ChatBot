"""命令执行器与结果格式化"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any, List, Optional

from .models import CommandData, CommandResult, CommandStatus

# 同步服务方法专用的执行器（懒创建，避免导入期建线程池）
_sync_executor = None
_executor_lock = None


def _get_sync_executor():
    """同步命令执行专用线程池。

    不用 `asyncio.to_thread` 的默认池：那个池容量是 min(32, cpu+4)，
    被长耗时的浏览器/OCR 操作占满后，进程内**所有** to_thread 调用
    （包括不相关的文件 IO）都会排队。
    """
    global _sync_executor, _executor_lock
    if _executor_lock is None:
        import threading

        _executor_lock = threading.Lock()
    if _sync_executor is None:
        with _executor_lock:
            if _sync_executor is None:
                from concurrent.futures import ThreadPoolExecutor

                _sync_executor = ThreadPoolExecutor(
                    max_workers=8, thread_name_prefix="CmdExec"
                )
    return _sync_executor


class CommandExecutor:
    def __init__(self, service_manager: Any, mode: str = "sequential"):
        self._sm = service_manager
        self._mode = mode if mode in ("sequential", "concurrent") else "sequential"

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

        if self._mode == "concurrent" and runnable:
            # C63：return_exceptions，单条炸掉不影响整批
            executed = await asyncio.gather(
                *(self._invoke(cmd) for _, cmd in runnable),
                return_exceptions=True,
            )
            for (index, cmd), result in zip(runnable, executed):
                results[index] = (
                    result if isinstance(result, dict)
                    else self._error_result(cmd, result)
                )
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
                # C62：同步方法丢到专用线程池，避免阻塞调度器 loop
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(
                    _get_sync_executor(),
                    lambda: method(*(position_args or []), **params),
                )

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
            return self._error_result(cmd, exc, started)

    @staticmethod
    def _error_result(cmd: CommandData, exc: Any, started: Optional[float] = None) -> CommandResult:
        if started is None:
            started = time.perf_counter()
        if isinstance(exc, BaseException) and not isinstance(exc, Exception):
            # CancelledError 之类要原样抛出，不能被吞成"执行失败"
            raise exc
        return CommandResult(
            ok=False,
            service=cmd["service"],
            method=cmd["method"],
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
            lines.append(f"{index}. {result.get('raw', '')} -> {result.get('status', '')}")
            if result.get("ok"):
                lines.append(f"返回: {ResultFormatter._truncate(str(result.get('data')))}")
            else:
                lines.append(f"错误: {result.get('error')}")
        return "\n".join(lines)

    @staticmethod
    def to_json(results: List[CommandResult]) -> str:
        return json.dumps(results, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def to_summary(results: List[CommandResult]) -> str:
        total = len(results)
        ok = sum(1 for item in results if item.get("ok"))
        fail = total - ok
        if total == 0:
            return "没有执行任何命令"
        if fail == 0:
            return f"全部 {total} 条命令执行成功"
        return f"{total} 条命令中 {ok} 成功, {fail} 失败"

    @staticmethod
    def _truncate(text: str, limit: int = 500) -> str:
        return text if len(text) <= limit else text[:limit] + f"... (截断, 共 {len(text)} 字符)"
