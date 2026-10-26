"""Cython setup 脚本（供 `python cython_setup.py build_ext --inplace` 调用）。

B23：模块列表由环境变量 `CHATBOT_CYTHON_MODULES` 传入（逗号分隔），
    不再硬编码 —— 原列表里的 `router`、`devices` 在当前项目不存在。
B22：只编译自己的包，不碰第三方。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from setuptools import setup

EXCLUDE_PATTERNS = [
    "*/tests/*", "*/test_*.py", "*/_test.py",
    "*/__pycache__/*", "*/migrations/*", "*/conftest.py",
]

#: B22：绝不能 Cython 化
NEVER = {"ui", "core", "services", "api"}

raw = os.environ.get("CHATBOT_CYTHON_MODULES", "").strip()
if raw:
    packages = [p.strip() for p in raw.split(",") if p.strip()]
else:
    # 兜底：自动发现
    mods = Path("modules")
    packages = [
        f"modules.{d.name}"
        for d in sorted(mods.iterdir())
        if d.is_dir()
        and (d / "__init__.py").exists()
        and d.name not in NEVER
        and d.name != "__pycache__"
    ]

sources: list[str] = []
for pkg in packages:
    pkg_dir = Path(pkg.replace(".", "/"))
    if not pkg_dir.exists():
        print(f"⚠️  模块不存在，跳过: {pkg_dir}")
        continue
    short = pkg.split(".")[-1]
    if short in NEVER:
        print(f"⚠️  黑名单模块，跳过: {pkg}")
        continue
    for py in sorted(pkg_dir.rglob("*.py")):
        if py.name == "__init__.py" and py.parent.name in ("tests", "test"):
            continue
        sources.append(py.as_posix())

if not sources:
    print("❌ 没有找到可编译的源文件")
    sys.exit(1)

print(f"📦 待编译 {len(sources)} 个文件，来自 {len(packages)} 个包")

try:
    from Cython.Build import cythonize
except ImportError:
    print("❌ 未安装 Cython: pip install cython")
    sys.exit(1)

ext_modules = cythonize(
    sources,
    nthreads=os.cpu_count() or 4,
    exclude=EXCLUDE_PATTERNS,
    compiler_directives={
        "language_level": "3",
        "boundscheck": False,
        "wraparound": False,
        "initializedcheck": False,
        "cdivision": True,
        "profile": False,
        "emit_code_comments": False,
    },
    annotate=False,
)

setup(
    name="ChatBotOptimized",
    ext_modules=ext_modules,
)
