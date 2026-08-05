import ast
from dataclasses import field
import re
from typing import List, Set, Tuple

from .restricted import SandboxConfig

ALLOWED_MODULES: Set[str] = field(default_factory=lambda: {
    "json",
    "math", 
    "random", 
    "datetime", 
    "time",
    "typing", 
    "collections", 
    "itertools", 
    "functools",
    "re", 
    "string", 
    "uuid", 
    "hashlib", 
    "base64",
    "copy", 
    "enum", 
    "decimal", 
    "fractions"
})

BLOCKED_MODULES: Set[str] = field(default_factory=lambda: {
    # 黑名单模块 - 危险操作
    "os", 
    "subprocess", 
    "sys", 
    "shutil", 
    "glob",
    "pickle", 
    "shelve", 
    "marshal", 
    "tempfile",
    "socket", 
    "ssl", 
    "http", 
    "urllib", 
    "requests",
    "ctypes", 
    "cffi", 
    "imp", 
    "importlib",
    "code", 
    "codeop", 
    "codecs",
    "pty", 
    "tty", 
    "termios",
    "multiprocessing", 
    "threading", 
    "_thread",
    "signal", 
    "mmap", 
    "fcntl",
    "builtins", 
    "__builtins__"
})

BLOCKED_KEYWORDS: Set[str] = field(default_factory=lambda: {
    "__import__", 
    "eval", 
    "exec", 
    "compile",
    "open", 
    "file", 
    "input", 
    "raw_input",
    "getattr", 
    "setattr", 
    "delattr",
    "globals", 
    "locals", 
    "vars", 
    "dir",
    "__subclasses__", 
    "__bases__", 
    "__mro__",
    "__code__", 
    "__globals__", 
    "__closure__"
})

DANGEROUS_PATTERNS: List[str] = [
    r'__import__\s*\(',
    r'eval\s*\(',
    r'exec\s*\(',
    r'compile\s*\(',
    r'open\s*\(',
    r'file\s*\(',
    r'subprocess\s*\.',
    r'os\.system\s*\(',
    r'os\.popen\s*\(',
    r'socket\s*\.',
    r'requests\s*\.',
    r'urllib\s*\.',
    r'ctypes\s*\.',
    r'multiprocessing\s*\.',
    r'threading\s*\.',
    r'pickle\.loads?\s*\(',
    r'marshal\.loads?\s*\(',
    r'base64\.b64decode\s*\(',
]

class CodeValidator:
    def __init__(
            self, 
            config: SandboxConfig
        ):
        self.config = config
        self._blocked_patterns = self._compile_blocked_patterns()
    
    def _compile_blocked_patterns(self) -> List[re.Pattern]:
        patterns = []
        # 黑名单关键字模式
        for kw in BLOCKED_KEYWORDS:
            patterns.append(re.compile(r'\b' + re.escape(kw) + r'\b'))
        # 危险模式
        for pattern in DANGEROUS_PATTERNS:
            patterns.append(re.compile(pattern, re.IGNORECASE))
        return patterns
    
    def validate_code(self, code: str) -> Tuple[bool, str]:
        """
        验证代码安全性
        
        Returns:
            (is_safe, error_message)
        """    
        # AST解析检查
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {str(e)}"
        
        # 3. 遍历AST节点检查
        for node in ast.walk(tree):
            # 检查import语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._is_module_allowed(alias.name):
                        return False, f"不允许导入模块: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if not self._is_module_allowed(module):
                    return False, f"不允许导入模块: {module}"
            # 检查函数调用
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in BLOCKED_KEYWORDS:
                    return False, f"不允许的函数调用: {func_name}"
        
        # 4. 正则检查黑名单模式
        for pattern in self._blocked_patterns:
            if pattern.search(code):
                return False, f"检测到危险代码模式: {pattern.pattern}"
        
        return True, ""
    
    def _is_module_allowed(self, module_name: str) -> bool:
        """检查模块是否在白名单中"""
        # 检查完整模块名
        if module_name in ALLOWED_MODULES:
            return True
        
        # 检查模块前缀
        for allowed in ALLOWED_MODULES:
            if module_name.startswith(allowed + "."):
                return True
        
        # 检查是否在黑名单中
        for blocked in BLOCKED_MODULES:
            if module_name == blocked or module_name.startswith(blocked + "."):
                return False
        return False
    
    def _get_call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""