"""Nuitka standalone 编译（B24–B29）。

产物名来自**入口文件名**，不是 `--app-name`。
     `--app-name=ChatBot` 而入口是 `main.py` 时，产物叫 `main.exe`；
     按 `ChatBot.exe` 找必然找不到 → 二进制静默不进 `bin/`。
`.dist` 目录同理是 `<entry_stem>.dist`。

静态资源（Live2D 模型 / skills / static）必须显式带。
失败时保留现场，便于排查。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .. import _platform as PF
from ..config import (
    EXCLUDED_DIR_NAMES,
    NOFOLLOW_IMPORT_PATTERNS,
    PROJECT_ROOT,
    STATIC_DIR,
    SKILLS_DIR,
    RUST_DIR,
    BuildConfig,
)


def discover_packages(root=None) -> List[str]:
    mods = (root or PROJECT_ROOT) / "modules"
    if not mods.exists():
        return []
    return [
        f"modules.{d.name}"
        for d in sorted(mods.iterdir())
        if d.is_dir()
        and (d / "__init__.py").exists()
        and d.name not in EXCLUDED_DIR_NAMES
    ]


def _data_dirs(cfg: BuildConfig) -> List[str]:
    """非 py 资源必须显式声明。"""
    out: List[str] = []
    for src, dst in ((SKILLS_DIR, "skills"), (STATIC_DIR, "static")):
        if src.exists() and any(src.iterdir()):
            out.append(f"--include-data-dir={src}={dst}")
    res = PROJECT_ROOT / "resources"
    if res.exists():
        out.append(f"--include-data-dir={res}=resources")
    return out


def _rust_artifact_args(cfg: BuildConfig) -> List[str]:
    """Rust 扩展不是 py 源码，`--follow-imports` 带不上。"""
    from . import rust as rust_step

    art = rust_step.already_built(cfg.project_root)
    if art is None:
        return []
    rel = art.relative_to(cfg.project_root).as_posix()
    return [f"--include-data-file={art}={rel}"]


def build_cmd(cfg: BuildConfig) -> List[str]:
    packages = discover_packages()
    if not packages:
        raise RuntimeError("modules/ 下没有找到任何 Python 包")

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--follow-imports",
        f"--output-dir={cfg.output_path}",
        f"--jobs={cfg.jobs}",
        # 失败时保留中间产物
        *([] if cfg.debug else ["--remove-output"]),
    ]

    # B26：新版语法 <package>=<pattern>，按包逐个指定
    for pkg in packages:
        cmd.append(f"--include-package-data={pkg}=*")
        cmd.append(f"--include-package={pkg}")

    if not cfg.debug:
        cmd.append("--lto=yes")
    else:
        cmd += ["--debug", "--nooptimization"]

    # 每个 pattern 单独一个参数，不能逗号拼接
    for pattern in NOFOLLOW_IMPORT_PATTERNS:
        cmd.append(f"--nofollow-import-to={pattern}")

    cmd += _data_dirs(cfg)
    cmd += _rust_artifact_args(cfg)

    # 版本号贯通
    cmd += PF.nuitka_platform_args(cfg.app_name, cfg.version, cfg.project_root)

    # 显式指定输出名，让产物可预测（B24 的兜底）
    cmd.append(f"--output-filename={cfg.app_name}")

    cmd.append(str(cfg.entry_abs))
    return cmd


def build(cfg: BuildConfig, log=print) -> bool:
    log(f"Nuitka 编译（{PF.current()} / standalone）...")

    if not cfg.entry_abs.exists():
        log(f"  ❌ 入口不存在: {cfg.entry_abs}")
        return False

    cmd = build_cmd(cfg)
    log(f"  执行: {' '.join(str(c) for c in cmd[:6])} ... "
        f"（共 {len(cmd)} 个参数）")

    if cfg.dry_run:
        for c in cmd:
            log(f"      {c}")
        return True

    r = subprocess.run(cmd, cwd=str(cfg.project_root))
    if r.returncode != 0:
        log("  ❌ Nuitka 编译失败")
        if not cfg.debug:
            log("     提示：加 --debug 可保留中间产物便于排查（B28）")
        return False

    log("  ✓ Nuitka 编译成功")
    return True


def locate_binary(cfg: BuildConfig) -> List[Path]:
    """B24：按入口 stem + app_name 两种可能找，避免静默丢失。"""
    cands = []
    for stem in (cfg.app_name, cfg.entry_stem):
        for suf in (PF.spec().exe_suffix, ".bin", ""):
            p = cfg.output_path / f"{stem}{suf}"
            if p.is_file() and p not in cands:
                cands.append(p)
    # Nuitka 也常把二进制放进 .dist 里
    if cfg.dist_dir.exists():
        for stem in (cfg.app_name, cfg.entry_stem):
            p = cfg.dist_dir / f"{stem}{PF.spec().exe_suffix}"
            if p.is_file() and p not in cands:
                cands.append(p)
    return cands
