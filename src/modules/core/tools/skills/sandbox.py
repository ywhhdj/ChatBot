"""受限代码沙盒

返回结构（controller / ctl 都按此对齐）
──────────────────────────────────
    成功 {"ok": True, "data": ..., "stdout": str, "truncated": bool, "elapsed_ms": int}
    失败 {"ok": False, "error": str, "stdout": str, "truncated": bool, "elapsed_ms": int}
"""

from __future__ import annotations

import ast
import builtins
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

#: 沙盒逃逸常用的 frame / code / func 属性。AST 的 `__` 前缀检查挡不住
#: `f_globals` / `gi_frame` 这类不带下划线的名字。
_BLOCKED_ATTRS = frozenset({
    "f_builtins", "f_globals", "f_locals", "f_code", "f_back",
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code",
    "tb_frame", "func_globals", "func_code", "func_closure", "__closure__",
    "im_func", "im_self", "__self__", "__dict__", "__class__", "__bases__",
    "__code__", "__func__", "__wrapped__",
})

#: 以字符串形式传属性名的调用。`hasattr` 在安全内建里被放行，
#: 但 `hasattr(x, "__globals__")` 会绕过 AST 属性检查，故单独拦截。
_DYNAMIC_ACCESS_CALLS = frozenset({
    "hasattr", "getattr", "setattr", "delattr", "vars", "dir",
    "eval", "exec", "compile", "__import__", "input", "open",
})

#: 每个 worker 线程一份，绝不共享、绝不碰 sys.stdout。
_thread_state = threading.local()


@dataclass
class SandboxConfig:
    max_execution_time: float = 5.0
    max_output_size: int = 100 * 1024
    allowed_modules: Set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_MODULES))
    blocked_modules: Set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_MODULES))
    blocked_names: Set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_NAMES))


class _SandboxBuffer(io.StringIO):
    """有界 stdout：写入时即截断，超限后续直接丢弃。"""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = max(0, int(limit))
        self.truncated = False
        self._count = 0

    def write(self, text: str) -> int:
        if self.truncated or not text:
            return len(text)
        room = self.limit - self._count
        if room <= 0:
            self.truncated = True
            return len(text)
        if len(text) > room:
            super().write(text[:room])
            self._count += room
            self.truncated = True
        else:
            super().write(text)
            self._count += len(text)
        return len(text)


def _sandbox_print(
    *args: Any, 
    sep: str = " ", 
    end: str = "\n",
) -> None:
    """只写当前沙盒线程的缓冲；不在技能线程里时静默丢弃。

    `file` 参数被忽略：技能不能靠 `print(..., file=...)` 写任意文件。
    """
    buf = getattr(_thread_state, "buffer", None)
    if buf is None:
        return
    try:
        buf.write(str(sep or " ").join(str(a) for a in args) + str(end if end is not None else ""))
    except Exception:  # noqa: BLE001 - print 绝不能把技能线程带崩
        pass


def _dangerous_name(value: str, config: SandboxConfig) -> bool:
    text = str(value or "")
    return (
        text.startswith("__")
        or text in config.blocked_names
        or text in _BLOCKED_ATTRS
    )


def _sandbox_hasattr(obj: Any, name: Any, config: SandboxConfig) -> bool:
    """放行常用内建，但堵死动态访问内部属性的绕过路径。"""
    text = str(name or "")
    if _dangerous_name(text, config):
        return False
    return builtins.hasattr(obj, text)


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
                if node.module is None or (node.level and node.level > 0):
                    raise ValueError("禁止使用相对导入")
                self._validate_module(str(node.module))
            elif isinstance(node, ast.Name) and node.id in self.config.blocked_names:
                raise ValueError(f"禁止使用名称: {node.id}")
            elif isinstance(node, ast.Attribute):
                attr = str(node.attr or "")
                if attr.startswith("__"):
                    raise ValueError(f"禁止访问内部属性: {attr}")
                if attr in self.config.blocked_names or attr in _BLOCKED_ATTRS:
                    raise ValueError(f"禁止访问属性: {attr}")
            elif isinstance(node, ast.Call):
                self._validate_call(node)

    def _validate_call(self, node: ast.Call) -> None:
        call_name = self._call_name(node)
        if call_name in self.config.blocked_names:
            raise ValueError(f"禁止调用: {call_name}")
        # 动态调用（下标 / lambda / 调用返回值）无法静态判定，一律拒绝。
        if not isinstance(node.func, (ast.Name, ast.Attribute)):
            raise ValueError("禁止动态调用（只能直接调用具名函数）")
        # 字符串形态的内部属性名绕过：`hasattr(x, "__globals__")`。
        if call_name in _DYNAMIC_ACCESS_CALLS:
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and _dangerous_name(arg.value, self.config)
                ):
                    raise ValueError(f"禁止通过字符串访问内部名称: {arg.value}")

    def _validate_module(self, module_name: str) -> None:
        root = str(module_name or "").split(".", 1)[0]
        if root in self.config.blocked_modules or root not in self.config.allowed_modules:
            raise ValueError(f"禁止导入模块: {module_name or '(空)'}")

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""


class _Timeout(Exception):
    """沙盒内部超时（由看门狗注入到 worker 线程）。"""


class RestrictedCodeExecutor:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self.validator = CodeValidator(self.config)
        self._safe_modules = self.__build_safe_modules()

    # ---------- 模块注入 ----------

    def __build_safe_modules(self) -> Dict[str, Any]:
        """把 DEFAULT_ALLOWED_MODULES 里声明允许的模块真正注入 globals。"""
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
        return {
            name: mod
            for name, mod in modules.items()
            if name in self.config.allowed_modules
            and name not in self.config.blocked_modules
        }

    def _safe_import(self, name: str, globals=None, locals=None,
                     fromlist=(), level=0):
        """受限的 __import__：只能拿到预置的安全模块。"""
        if level and level > 0:
            raise ImportError("禁止使用相对导入")
        root = str(name or "").split(".", 1)[0]
        if root in self.config.blocked_modules:
            raise ImportError(f"禁止导入模块: {name}")
        if root in self._safe_modules:
            return self._safe_modules[root]
        raise ImportError(f"模块不可用: {name}")

    def _safe_builtins(self) -> Dict[str, Any]:
        allowed = {
            # 原有
            "abs", "all", "any", "bool", "dict", "enumerate", "filter",
            "float", "int", "isinstance", "len", "list", "map", "max", "min",
            "pow", "range", "repr", "round", "set", "sorted", "str", "sum",
            "tuple", "zip",
            # 正常技能会用到的纯计算内建
            "bytes", "chr", "ord", "divmod", "format", "iter", "next",
            "reversed", "slice", "complex", "frozenset", "hex", "oct", "bin",
            # 类定义 / 异常捕获必需
            "__build_class__", "object", "property", "staticmethod",
            "classmethod", "super",
            "Exception", "BaseException", "ValueError", "TypeError",
            "KeyError", "IndexError", "RuntimeError", "StopIteration",
            "AssertionError", "AttributeError", "ZeroDivisionError",
            "OverflowError", "NotImplementedError",
        }
        safe: Dict[str, Any] = {
            name: getattr(builtins, name)
            for name in allowed
            if hasattr(builtins, name)
        }
        # 替换 print：写线程局部缓冲，不碰 sys.stdout。
        safe["print"] = _sandbox_print
        # 放行 hasattr，但拦截危险属性名，避免绕过 AST 白名单。
        safe["hasattr"] = lambda obj, name: _sandbox_hasattr(obj, name, self.config)
        safe["__import__"] = self._safe_import
        return safe

    # ---------- 执行 ----------

    async def execute(
        self, code: str,
        context: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """跑在沙盒专用线程池；无运行 loop 时退化为同步执行。"""
        try:
            loop = _current_loop()
        except RuntimeError:
            return self.execute_sync(code, context or {})
        return await loop.run_in_executor(
            _get_sandbox_executor(),
            lambda: self.execute_sync(code, context or {}),
        )

    def execute_sync(self, code: str,
                     context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        started = time.time()
        try:
            self.validator.validate(code)

            # context 合并进 globals（exec 的 locals 在函数内不可见）。
            globals_dict: Dict[str, Any] = {
                "__builtins__": self._safe_builtins(),
                **self._safe_modules,
            }
            globals_dict.update(context or {})
            globals_dict.setdefault("result", None)

            buffer = _SandboxBuffer(self.config.max_output_size)
            outcome: Dict[str, Any] = {"error": None}
            finished = threading.Event()

            def _runner() -> None:
                _thread_state.buffer = buffer
                try:
                    try:
                        exec(compile(code, "<skill-sandbox>", "exec"), globals_dict)
                    except BaseException as exc:  # noqa: BLE001 - 失败必须回传
                        if isinstance(exc, _Timeout):
                            outcome["error"] = "沙盒执行超时（线程内中断）"
                        else:
                            outcome["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    _thread_state.buffer = None
                    finished.set()

            worker = threading.Thread(
                target=_runner, daemon=True, name="SkillSandbox"
            )
            worker.start()
            worker.join(timeout=self.config.max_execution_time)

            stdout = buffer.getvalue()
            elapsed = int((time.time() - started) * 1000)

            if worker.is_alive():
                # 注入异常唤醒；无法保证成功（可能卡在 C 扩展），
                # 但线程是 daemon，不拖垮进程，且本次明确判为失败。
                self.__interrupt(worker)
                worker.join(timeout=0.2)
                return {
                    "ok": False,
                    "error": (
                        outcome["error"]
                        or f"沙盒执行超时（>{self.config.max_execution_time}s）"
                    ),
                    "stdout": stdout,
                    "truncated": buffer.truncated,
                    "elapsed_ms": elapsed,
                }

            if outcome["error"] is not None:
                return {
                    "ok": False,
                    "error": str(outcome["error"]),
                    "stdout": stdout,
                    "truncated": buffer.truncated,
                    "elapsed_ms": elapsed,
                }

            # finished 由 worker 的 finally 无条件设置；防御性等待，
            # 避免极端调度下 outcome 尚未写回就被主线程读取。
            if not finished.is_set():
                finished.wait(timeout=0.1)

            return {
                "ok": True,
                "data": globals_dict.get("result"),
                "stdout": stdout,
                "truncated": buffer.truncated,
                "elapsed_ms": elapsed,
            }
        except Exception as exc:  # noqa: BLE001 - 校验/构造失败也是失败
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": int((time.time() - started) * 1000),
            }

    @staticmethod
    def __interrupt(thread: threading.Thread) -> None:
        """向目标线程注入 `_Timeout` **实例**；注入异常时复位线程状态。"""
        try:
            import ctypes

            tid = thread.ident
            if tid is None:
                return
            handle = ctypes.c_ulong(tid)
            injected = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                handle, ctypes.py_object(_Timeout())
            )
            # >1 表示注入到多个/异常线程状态，必须撤销，否则污染目标线程。
            if injected > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    handle, ctypes.py_object(None)
                )
        except Exception:  # noqa: BLE001
            pass


def _current_loop():
    import asyncio

    return asyncio.get_running_loop()


# ── 沙盒专用线程池 ─────────────────────────────────────────────
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
