"""Cython 预编译"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from ..config import (
    CYTHON_NEVER,
    EXCLUDED_DIR_NAMES,
    PROJECT_ROOT,
    BuildConfig,
)

SCRIPT = Path(__file__).with_name("cython_setup.py")


def discover_packages(root: Optional[Path] = None) -> List[str]:
    """自动发现 `modules/` 下的包，排除黑名单。
    `root` 可注入，便于测试 —— 不注入时用全局项目根。
    """
    mods = (root or PROJECT_ROOT) / "modules"
    if not mods.exists():
        return []
    out = []
    for d in sorted(mods.iterdir()):
        if not d.is_dir() or d.name in EXCLUDED_DIR_NAMES:
            continue
        if not (d / "__init__.py").exists():
            continue
        if d.name in CYTHON_NEVER:
            continue
        out.append(f"modules.{d.name}")
    return out

RUST_PACKAGE = "core"


def cleanup_previous(
    project_root: Path,
    log=print,
    packages: Optional[List[str]] = None,
) -> None:
    """清理上一轮 Cython 产物。
    **关键** —— 绝不能 `rglob("*.so")` 全删，那会误删
    Rust 内核产物 `chatbot_core.so`。
    这里只扫 `modules/` 下的包目录，并且跳过 Rust 模块名。
    """
    mods = project_root / "modules"
    if not mods.exists():
        return
    for cache in ("build", "__pyx_cache__"):
        for d in project_root.rglob(cache):
            if d.is_dir() and "rust" not in d.parts:
                shutil.rmtree(d, ignore_errors=True)

    removed = 0
    for pkg in (packages if packages is not None
                else discover_packages(project_root)):
        pkg_dir = project_root / pkg.replace(".", "/")
        if not pkg_dir.exists():
            continue
        for ext in (".pyd", ".so", ".dylib"):
            for f in pkg_dir.rglob(f"*{ext}"):
                # B15：Rust 产物不在 modules 下，但再兜一道
                if RUST_PACKAGE in f.name:
                    continue
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    if removed:
        log(f"  🗑  清理旧产物 {removed} 个（已跳过 Rust 内核）")


def build(cfg: BuildConfig, log=print) -> bool:
    if not cfg.cython:
        log("  ⏭  跳过 Cython（默认关闭，--cython 开启）")
        return False

    if shutil.which("cython") is None and not _cython_importable():
        log("  ⚠️  未安装 Cython，跳过（pip install cython）")
        return False

    packages = discover_packages()
    if not packages:
        log("  ⚠️  没有可编译的包，跳过")
        return False

    log(f"🔧 Cython 预编译 {len(packages)} 个包...")
    log(f"  排除（动态特性/原生扩展）: {', '.join(sorted(CYTHON_NEVER))}")

    if cfg.dry_run:
        log(f"  [dry-run] 将编译: {', '.join(packages)}")
        return False

    cleanup_previous(cfg.project_root, log)

    r = subprocess.run(
        [sys.executable, str(SCRIPT), "build_ext", "--inplace"],
        cwd=str(cfg.project_root),
        capture_output=True,
        text=True,
        env={**_env_with_packages(packages)},
    )
    if r.returncode != 0:
        log("  ❌ Cython 编译失败:")
        log((r.stdout or "")[-3000:])
        log((r.stderr or "")[-3000:])
        return False

    log("  ✓ Cython 编译成功")
    log("  ⚠️  提示：Cython 化后 `get_type_hints()` 行为可能变化，"
        "务必跑一遍 verify_api.py / verify_tool_dto.py")
    return True


def _cython_importable() -> bool:
    try:
        import Cython  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _env_with_packages(packages: List[str]) -> dict:
    import os
    env = dict(os.environ)
    env["CHATBOT_CYTHON_MODULES"] = ",".join(packages)
    return env
