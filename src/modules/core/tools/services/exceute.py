"""命令执行器与结果格式化"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any, List, Optional

from ..policy import ToolPolicy, DEFAULT_POLICY
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
    """命令执行器。

    B0-06：每条命令都有**超时**与**输出上限**。
    SecurityAndAuditDesign §8 明确要求"工具运行时间和 tool steps 有上限"——
    否则一个卡死的浏览器操作或无限循环的技能脚本会永久占用执行线程，
    而且 LLM 可以靠"多来几条慢命令"把整个池子拖死。
    """

    def __init__(
        self,
        service_manager: Any,
        mode: str = "sequential",
        policy: Optional[ToolPolicy] = None,
    ):
        self._sm = service_manager
        self._mode = mode if mode in ("sequential", "concurrent") else "sequential"
        self._policy = policy or DEFAULT_POLICY

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

    async def _invoke(
        self,
        cmd: CommandData,
        timeout_s: Optional[float] = None,
    ) -> CommandResult:
        """执行单条命令。

        `timeout_s` 由策略给出（见 `tools/policy.py`）；
        None 表示沿用策略默认值，0 表示不限。
        """
        service_name = cmd["service"]
        method_name = cmd["method"]
        params = dict(cmd["params"])
        position_args = params.pop("_args", None)
        started = time.perf_counter()

        limit = self._policy.default_timeout_s if timeout_s is None else float(timeout_s)

        try:
            service = self._sm.get_service(service_name)
            method = getattr(service, method_name)

            if inspect.iscoroutinefunction(method):
                # 协程方法：asyncio 超时能真正取消（前提是方法内部有 await 点）
                coro = method(*(position_args or []), **params)
                data = await self._with_timeout(coro, limit, service_name, method_name)
            else:
                # C62：同步方法丢到专用线程池，避免阻塞调度器 loop。
                #
                # 注意 asyncio.wait_for **杀不掉已提交到线程的任务** ——
                # 超时后线程仍在跑。这是刻意的取舍：强杀线程会留下
                # 半完成的副作用（写了一半的文件、锁没释放）。
                # 所以我们让命令自己跑完，只是不再等它，
                # 并在结果里如实标记 timeout（§9："取消/超时后资源释放，
                # 后台异常可追踪"靠日志而非假装终止）。
                loop = asyncio.get_running_loop()
                fut = loop.run_in_executor(
                    _get_sync_executor(),
                    lambda: method(*(position_args or []), **params),
                )
                data = await self._with_timeout(fut, limit, service_name, method_name)

            return CommandResult(
                ok=True,
                service=service_name,
                method=method_name,
                status=CommandStatus.SUCCESS.value,
                data=self._cap_result(data),
                error=None,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=cmd["raw"],
            )
        except asyncio.TimeoutError:
            return CommandResult(
                ok=False,
                service=service_name,
                method=method_name,
                status=CommandStatus.ERROR.value,
                data=None,
                error=f"命令超时（{limit:.0f}s），已放弃等待",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                raw=cmd["raw"],
            )
        except Exception as exc:
            return self._error_result(cmd, exc, started)

    @staticmethod
    async def _with_timeout(awaitable: Any, limit: float, service: str, method: str) -> Any:
        if limit <= 0:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=limit)

    def _cap_result(self, data: Any) -> Any:
        """输出上限（SecurityAndAuditDesign §8：最大 response body）。

        工具返回整个目录树、整篇网页或大文件时，若不加约束会直接
        灌进 prompt 与审计历史。这里在**执行层**就截断，
        而不是等格式化时才截 —— 后者意味着大对象已经在内存和历史里了。
        """
        limit = self._policy.max_result_chars
        if limit <= 0 or data is None:
            return data
        try:
            text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            return data
        if len(text) <= limit:
            return data
        head = text[:limit]
        note = f"... (结果已截断, 共 {len(text)} 字符)"
        return head + note

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
