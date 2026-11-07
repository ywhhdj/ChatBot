"""受限代码沙盒"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import math
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Set

DEFAULT_ALLOWED_MODULES = {
    "base64", "collections", "datetime", "decimal", "enum", "fractions",
    "functools", "hashlib", "itertools", "json", "math", "random", "re",
    "statistics", "string", "time", "typing", "uuid",
}

DEFAULT_BLOCKED_MODULES = {
    "asyncio", "builtins", "ctypes", "cffi", "glob", "http", "importlib",
    "marshal", "mmap", "multiprocessing", "os", "pathlib", "pickle",
    "requests", "shelve", "shutil", "signal", "socket", "ssl", "subprocess",
    "sys", "tempfile", "threading", "urllib",
}

DEFAULT_BLOCKED_NAMES = {
    "__builtins__", "__import__", "__subclasses__", "__globals__", "__mro__",
    "compile", "delattr", "dir", "eval", "exec", "getattr", "globals",
    "input", "locals", "open", "setattr", "vars",
}


@dataclass
class SandboxConfig:
    max_execution_time: float = 5.0
    max_output_size: int = 100 * 1024
    allowed_modules: Set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_MODULES))
    blocked_modules: Set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_MODULES))
    blocked_names: Set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_NAMES))


class CodeValidator:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    def validate(self, code: str) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(f"语法错误: {exc}") from exc

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._validate_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    raise ValueError("禁止使用相对导入")
                if node.level and node.level > 0:
                    raise ValueError("禁止使用相对导入")
                self._validate_module(node.module)
            elif isinstance(node, ast.Name) and node.id in self.config.blocked_names:
                raise ValueError(f"禁止使用名称: {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError(f"禁止访问内部属性: {node.attr}")
            elif isinstance(node, ast.Call):
                call_name = self._call_name(node)
                if call_name in self.config.blocked_names:
                    raise ValueError(f"禁止调用: {call_name}")

    def _validate_module(self, module_name: str) -> None:
        root = module_name.split(".", 1)[0]
        if root in self.config.blocked_modules or root not in self.config.allowed_modules:
            raise ValueError(f"禁止导入模块: {module_name or '(空)'}")

    def _call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""


class _Timeout(Exception):
    """沙盒内部超时（由 watchdog 线程注入异常）。"""


class RestrictedCodeExecutor:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self.validator = CodeValidator(self.config)
        self._safe_modules = self.__build_safe_modules()

    # ---------- 模块注入（C83） ----------

    def __build_safe_modules(self) -> Dict[str, Any]:
        """把 DEFAULT_ALLOWED_MODULES 里声明允许的模块**真正**注入 globals。"""
        import base64 as _base64
        import collections as _collections
        import datetime as _datetime
        import decimal as _decimal
        import enum as _enum
        import fractions as _fractions
        import functools as _functools
        import hashlib as _hashlib
        import itertools as _itertools
        import json as _json
        import statistics as _statistics
        import string as _string
        import uuid as _uuid
        import typing as _typing

        modules: Dict[str, Any] = {
            "base64": _base64,
            "collections": _collections,
            "datetime": _datetime,
            "decimal": _decimal,
            "enum": _enum,
            "fractions": _fractions,
            "functools": _functools,
            "hashlib": _hashlib,
            "itertools": _itertools,
            "json": _json,
            "math": math,
            "random": random,
            "re": re,
            "statistics": _statistics,
            "string": _string,
            "time": time,
            "typing": _typing,
            "uuid": _uuid,
        }
        # 只保留配置允许且未被屏蔽的
        return {
            name: mod
            for name, mod in modules.items()
            if name in self.config.allowed_modules
            and name not in self.config.blocked_modules
        }

    def _safe_import(self, name: str, globals=None, locals=None, fromlist=(), level=0):
        """受限的 __import__：只能拿到预置的安全模块。"""
        if level and level > 0:
            raise ImportError("禁止使用相对导入")
        root = name.split(".", 1)[0]
        if root in self.config.blocked_modules:
            raise ImportError(f"禁止导入模块: {name}")
        if root in self._safe_modules:
            return self._safe_modules[root]
        raise ImportError(f"模块不可用: {name}")

    def _safe_builtins(self) -> Dict[str, Any]:
        allowed = {
            "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
            "int", "isinstance", "len", "list", "map", "max", "min", "pow",
            "print", "range", "repr", "round", "set", "sorted", "str", "sum",
            "tuple", "zip",
        }
        safe = {name: getattr(builtins, name) for name in allowed if hasattr(builtins, name)}
        safe["__import__"] = self._safe_import
        return safe

    # ---------- 执行 ----------

    async def execute(self, code: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """C85/C86：跑在**专用**线程池，并用看门狗线程中断死循环。

        `asyncio.wait_for(to_thread(...))` 无法真正终止线程，
        这里改为：worker 线程里用 `threading.Timer` 向目标线程
        `ctypes.PyThreadState_SetAsyncExc` 注入异常；若注入失败
        （例如卡在 C 扩展里），至少把线程标记为 daemon 并放弃等待，
        不让它拖垮整个池。
        """
        try:
            loop = _current_loop()
        except RuntimeError:
            # 没有运行中 loop（纯同步调用场景）时直接执行
            return self.execute_sync(code, context or {})
        return await loop.run_in_executor(
            _get_sandbox_executor(),
            lambda: self.execute_sync(code, context or {}),
        )

    def execute_sync(self, code: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        started = time.time()
        try:
            self.validator.validate(code)

            # C84：把 context 合并进 globals，而不是单独传 locals。
            # exec 的 locals 在函数/推导式内部不可见，这是经典陷阱 ——
            # 技能代码里定义函数后访问 params 会 NameError。
            globals_dict: Dict[str, Any] = {
                "__builtins__": self._safe_builtins(),
                **self._safe_modules,
            }
            globals_dict.update(context or {})
            # 结果约定：技能可以把返回值写进 result
            globals_dict.setdefault("result", None)

            output = io.StringIO()
            finished = threading.Event()

            def _runner() -> None:
                try:
                    with contextlib.redirect_stdout(output):
                        exec(compile(code, "<skill-sandbox>", "exec"), globals_dict)
                finally:
                    finished.set()

            worker = threading.Thread(target=_runner, daemon=True, name="SkillSandbox")
            worker.start()
            worker.join(timeout=self.config.max_execution_time)

            if worker.is_alive():
                # C85：线程仍活着 = 超时。注入异常尝试唤醒，失败也继续（daemon 线程不阻退出）
                self.__interrupt(worker)
                return {
                    "ok": False,
                    "error": f"沙盒执行超时（>{self.config.max_execution_time}s）",
                    "elapsed_ms": int((time.time() - started) * 1000),
                }

            stdout = output.getvalue()
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[: self.config.max_output_size] + "..."
            return {
                "ok": True,
                "data": globals_dict.get("result"),
                "stdout": stdout,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": int((time.time() - started) * 1000),
            }

    @staticmethod
    def __interrupt(thread: threading.Thread) -> None:
        """尽力向目标线程注入异常（无法保证成功，但比什么都不做强）。"""
        try:
            import ctypes

            tid = thread.ident
            if tid is None:
                return
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid), ctypes.py_object(_Timeout)
            )
        except Exception:
            pass


def _current_loop():
    import asyncio

    return asyncio.get_running_loop()


# ── 沙盒专用线程池（C86）────────────────────────────────────────────
# 不用 asyncio.to_thread 的默认池：技能是长耗时任务，占满默认池后
# 进程内所有 to_thread（含不相关的文件 IO）都会排队。
_sandbox_executor = None
_sandbox_executor_lock = threading.Lock()


def _get_sandbox_executor():
    global _sandbox_executor
    if _sandbox_executor is None:
        with _sandbox_executor_lock:
            if _sandbox_executor is None:
                from concurrent.futures import ThreadPoolExecutor

                _sandbox_executor = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="SkillSandbox"
                )
    return _sandbox_executor


