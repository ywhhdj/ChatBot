from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# 脚本自身 import 不依赖 cwd
BUILDER_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BUILDER_DIR.parent
if str(BUILDER_DIR) not in sys.path:
    sys.path.insert(0, str(BUILDER_DIR))

os.environ["CHATBOT_PROJECT_ROOT"] = r"D:\Project\ChatBot\src_py"

ENTRY_CANDIDATES = ("main.py", "app.py", "run.py")


def detect_project_root(start: Optional[Path] = None) -> Path:
    """向上探测项目根（同时含入口文件与 `modules/` 的那一层）。"""
    cur = (start or BUILDER_DIR).resolve()
    for _ in range(8):
        if (cur / "modules").is_dir() and any(
            (cur / e).is_file() for e in ENTRY_CANDIDATES
        ):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError(
        f"未能定位项目根：从 {BUILDER_DIR} 向上 8 级都没找到 "
        f"同时含 modules/ 与 {'/'.join(ENTRY_CANDIDATES)} 的目录。"
        "如需自定义，设置 CHATBOT_PROJECT_ROOT 环境变量。"
    )


_env_root = os.environ.get("CHATBOT_PROJECT_ROOT", "").strip()
PROJECT_ROOT = Path(_env_root).resolve() if _env_root else detect_project_root()

#: 入口文件（相对项目根）
DEFAULT_ENTRY = "main.py"
DEFAULT_OUTPUT_DIR = "dist"
DEFAULT_APP_NAME = "ChatBot"
DEFAULT_VERSION = "1.0.0"

RESOURCE_DIR = PROJECT_ROOT / "resources"
DOCS_DIR = PROJECT_ROOT / "docs"
RUST_DIR = PROJECT_ROOT / "native" / "rust"
STATIC_DIR = PROJECT_ROOT / "static"
SKILLS_DIR = PROJECT_ROOT / "skills"


# ─────────────────────────────────────────────────────────────
# 资源映射
# ─────────────────────────────────────────────────────────────

@dataclass
class ResourceSpec:
    """一条资源映射。

    `kind` 显式声明，不再靠路径前缀猜。

    * ``source``   —— Python 源码目录，走源码排除规则
    * ``resource`` —— 二进制/数据资源，保留 .dll/.so/.bin/.dylib
    """

    src: str                 # 相对 src_base 的路径
    dst: str                 # 相对 share/resources/ 的目标
    kind: str = "resource"   # source | resource
    base: str = "auto"       # auto | project | resources


# ─────────────────────────────────────────────────────────────
# 排除规则
# ─────────────────────────────────────────────────────────────

#: 复制 Python 源码时排除（源码目录不需要原生产物）
EXCLUDED_SOURCE_EXT = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".dylib",
    ".c", ".pyx", ".pyi", ".DS_Store", ".gitignore",
}

#: 复制资源时排除（**保留** .dll/.so/.dylib/.bin —— 原生依赖必须带上）
EXCLUDED_RESOURCE_EXT = {
    ".pyc", ".pyo", ".pyx", ".pyi", ".c", ".DS_Store", ".gitignore",
}

EXCLUDED_DIR_NAMES = {
    "schema", "__pycache__", ".git", ".pytest_cache",
    "__pyx_cache__", ".idea", ".vscode", ".mypy_cache", ".ruff_cache",
}

#: Cython 排除
CYTHON_EXCLUDE_PATTERNS = [
    "*/tests/*", "*/test_*.py", "*/_test.py", "*/__pycache__/*",
    "*/migrations/*", "*/conftest.py",
]

#: 这些包**绝不** Cython 化 —— 动态特性 / 原生扩展 / 第三方
CYTHON_NEVER = {
    "ui",        # PyQt6 + qtwebview2
    "core",      # Rust 绑定入口
    "services",  # 大量 setattr 动态包装（Service 装饰器）
    "api",       # gateway 依赖 get_type_hints()，B20
}

#: Cython 默认关闭
CYTHON_ENABLED_BY_DEFAULT = False

#: Nuitka 不追踪
NOFOLLOW_IMPORT_PATTERNS = [
    "*.tests", "*.test", "tests.*", "test_*",
    "pytest", "unittest", "setuptools", "pip", "IPython",
]

PYTHON_PATH = ""

#: 内置默认。存在 config.yaml 时以它为准。
DEFAULT_RESOURCE_SPECS: List[ResourceSpec] = [
    ResourceSpec("defaults", "defaults", "resource", "resources"),
    ResourceSpec("roles", "roles", "resource", "resources"),
    ResourceSpec("live2d", "models/live2d", "resource", "resources"),
    ResourceSpec("emotion", "models/emotion", "resource", "resources"),
    ResourceSpec("mediapipe", "models/mediapipe", "resource", "resources"),
    ResourceSpec("panddleOCR", "models/panddleOCR", "resource", "resources"),
    ResourceSpec("asr", "models/asr", "resource", "resources"),
    ResourceSpec("tts", "models/tts", "resource", "resources"),
    ResourceSpec("ocr", "models/ocr", "resource", "resources"),
    # browser/scripts 是 JS
    ResourceSpec("modules/services/browser/scripts", "scripts",
                 "resource", "project"),
    ResourceSpec("skills", "skills", "resource", "project"),
    ResourceSpec("static", "static", "resource", "project"),
]

def load_config():
    global DEFAULT_RESOURCE_SPECS, CYTHON_ENABLED_BY_DEFAULT, NOFOLLOW_IMPORT_PATTERNS, CYTHON_EXCLUDE_PATTERNS, CYTHON_NEVER, EXCLUDED_RESOURCE_EXT, EXCLUDED_DIR_NAMES, EXCLUDED_SOURCE_EXT, DEFAULT_ENTRY, DEFAULT_OUTPUT_DIR, DEFAULT_APP_NAME, DEFAULT_VERSION, PYTHON_PATH
    cfg = BUILDER_DIR / "config.yaml"
    if not cfg.exists():
        return
    import yaml
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    items = raw.get("resources") or []
    out: List[ResourceSpec] = []
    for it in items:
        out.append(
            ResourceSpec(
                src=str(it.get("src", "")),
                dst=str(it.get("dst", it.get("src", ""))),
                kind=str(it.get("kind", "resource")),
                base=str(it.get("base", "auto")),
            )
        )
    DEFAULT_RESOURCE_SPECS = out or list(DEFAULT_RESOURCE_SPECS)
    CYTHON_ENABLED_BY_DEFAULT = raw.get("cython_enabled_by_default", CYTHON_ENABLED_BY_DEFAULT)
    NOFOLLOW_IMPORT_PATTERNS = raw.get("nofollow_import_patterns", NOFOLLOW_IMPORT_PATTERNS)
    CYTHON_EXCLUDE_PATTERNS = raw.get("exclude_cython_patterns", CYTHON_EXCLUDE_PATTERNS)
    CYTHON_NEVER = set(raw.get("cython_never", CYTHON_NEVER))
    EXCLUDED_RESOURCE_EXT = raw.get("exclude_resource_ext", EXCLUDED_RESOURCE_EXT)
    EXCLUDED_DIR_NAMES = raw.get("exclude_dir_names", EXCLUDED_DIR_NAMES)
    EXCLUDED_SOURCE_EXT = raw.get("exclude_source_ext", EXCLUDED_SOURCE_EXT)
    DEFAULT_ENTRY = raw.get("entry", DEFAULT_ENTRY)
    DEFAULT_OUTPUT_DIR = raw.get("output", DEFAULT_OUTPUT_DIR)
    DEFAULT_APP_NAME = raw.get("app_name", DEFAULT_APP_NAME)
    DEFAULT_VERSION = raw.get("version", DEFAULT_VERSION)
    PYTHON_PATH = raw.get("python_path", PYTHON_PATH)


def get_resource_specs() -> List[ResourceSpec]:
    return list(DEFAULT_RESOURCE_SPECS)

# ─────────────────────────────────────────────────────────────
# 构建配置
# ─────────────────────────────────────────────────────────────

@dataclass
class BuildConfig:
    """一次构建的全部参数（版本号唯一真相源）。"""

    entry: str = DEFAULT_ENTRY
    output_dir: str = DEFAULT_OUTPUT_DIR
    app_name: str = DEFAULT_APP_NAME
    version: str = DEFAULT_VERSION
    debug: bool = False
    cython: bool = CYTHON_ENABLED_BY_DEFAULT
    rust: bool = True
    installer: bool = False
    deploy: bool = True
    force: bool = False            # B6：默认不 rmtree 输出目录
    only: Optional[str] = None     # B33
    dry_run: bool = False
    clean: bool = False
    jobs: int = field(default_factory=lambda: os.cpu_count() or 4)
    python_path: str = ""

    # ---- 派生路径 ----

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def entry_abs(self) -> Path:
        return PROJECT_ROOT / self.entry

    @property
    def entry_stem(self) -> str:
        """B24：Nuitka 产物名来自**入口文件名**，不是 app_name。"""
        return Path(self.entry).stem

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    @property
    def install_dir(self) -> Path:
        return self.output_path / self.app_name

    @property
    def dist_dir(self) -> Path:
        """B25：`<entry_stem>.dist`，不是 `<app_name>.dist`。"""
        return self.output_path / f"{self.entry_stem}.dist"

    @property
    def share_resources(self) -> Path:
        return self.install_dir / "share" / "resources"


def parse_args(argv: Optional[Sequence[str]] = None) -> BuildConfig:
    import argparse

    p = argparse.ArgumentParser(
        description="ChatBot 统一构建脚本（跨平台）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  py build.py --dry-run\n"
            "  py build.py --only rust\n"
            "  py build.py --cython --installer\n"
        ),
    )
    p.add_argument("--entry", default=DEFAULT_ENTRY)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--app-name", default=DEFAULT_APP_NAME)
    p.add_argument("--version", default=DEFAULT_VERSION)
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    p.add_argument("--cython", action="store_true",
                   help="启用 Cython 预编译（默认关闭，见 B19）")
    p.add_argument("--no-rust", action="store_true",
                   help="跳过 Rust 内核构建")
    p.add_argument("--installer", action="store_true")
    p.add_argument("--no-deploy", action="store_true",
                   help="只编译，不部署到标准目录")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="允许删除已存在的输出目录（B6）")
    p.add_argument("--only",
                   choices=["rust", "cython", "nuitka", "resources",
                            "deploy", "installer"],
                   help="只跑指定步骤（B33）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印计划，不执行")
    p.add_argument("--clean", action="store_true",
                   help="清理构建产物后退出")
    p.add_argument("-i", "--python-path", default=PYTHON_PATH,
                   help="指定 Python 解释器路径（默认环境变量）")
    a = p.parse_args(argv)

    return BuildConfig(
        entry=a.entry,
        output_dir=a.output_dir,
        app_name=a.app_name,
        version=a.version,
        debug=a.debug,
        cython=a.cython,
        rust=not a.no_rust,
        installer=a.installer,
        deploy=not a.no_deploy,
        force=a.force,
        only=a.only,
        dry_run=a.dry_run,
        clean=a.clean,
        jobs=a.jobs,
        python_path=a.python_path,
    )

load_config()