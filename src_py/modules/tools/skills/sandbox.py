from __future__ import annotations

import ast
import asyncio
import builtins
import contextlib
import io
import math
import random
import re
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
                self._validate_module(node.module or "")
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
            raise ValueError(f"禁止导入模块: {module_name}")

    def _call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""


class RestrictedCodeExecutor:
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self.validator = CodeValidator(self.config)
        self._safe_modules = {
            "json": __import__("json"),
            "math": math,
            "random": random,
            "re": re,
            "time": time,
        }

    async def execute(self, code: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return await asyncio.wait_for(
            asyncio.to_thread(self.execute_sync, code, context or {}),
            timeout=self.config.max_execution_time + 0.5,
        )

    def execute_sync(self, code: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        started = time.time()
        try:
            self.validator.validate(code)
            output = io.StringIO()
            globals_dict = {
                "__builtins__": self._safe_builtins(),
                **self._safe_modules,
            }
            locals_dict = dict(context or {})
            with contextlib.redirect_stdout(output):
                exec(compile(code, "<skill-sandbox>", "exec"), globals_dict, locals_dict)
            stdout = output.getvalue()
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[: self.config.max_output_size] + "..."
            return {
                "ok": True,
                "data": locals_dict.get("result", locals_dict.get("_sandbox_result")),
                "stdout": stdout,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        except asyncio.TimeoutError:
            raise TimeoutError("沙盒执行超时")
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "elapsed_ms": int((time.time() - started) * 1000),
            }

    def _safe_builtins(self) -> Dict[str, Any]:
        allowed = {
            "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
            "int", "isinstance", "len", "list", "map", "max", "min", "pow",
            "print", "range", "repr", "round", "set", "sorted", "str", "sum",
            "tuple", "zip", "True", "False", "None",
        }
        return {name: getattr(builtins, name) for name in allowed if hasattr(builtins, name)}
