"""资源部署与标准目录"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List

from ..config import (
    DOCS_DIR,
    EXCLUDED_DIR_NAMES,
    EXCLUDED_RESOURCE_EXT,
    EXCLUDED_SOURCE_EXT,
    RESOURCE_DIR,
    ResourceSpec,
    BuildConfig,
    get_resource_specs,
)


def _should_skip(rel_parts) -> bool:
    """B30：只对**相对**路径的组件判断。"""
    return any(p in EXCLUDED_DIR_NAMES for p in rel_parts)


def copy_tree(src: Path, dst: Path, *, kind: str = "resource") -> int:
    """递归复制。

    kind=source   → 源码排除规则（排掉 .c/.pyx/.pyi）
    kind=resource → 资源排除规则（**保留** .dll/.so/.dylib/.bin）
    """
    if not src.exists():
        print(f"  ⚠️  源不存在，跳过: {src}")
        return 0

    excluded = (EXCLUDED_SOURCE_EXT if kind == "source"
                else EXCLUDED_RESOURCE_EXT)
    count = 0
    for item in src.rglob("*"):
        try:
            rel = item.relative_to(src)
        except ValueError:
            continue
        if _should_skip(rel.parts):        # B30
            continue
        if item.is_file() and item.suffix.lower() in excluded:
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    return count


def _resolve(spec: ResourceSpec) -> Path:
    """base=project → 项目根；base=resources → resources/；auto → 猜。"""
    if spec.base == "project":
        return Path(__import__("tools.builder.config", fromlist=["PROJECT_ROOT"])
                    .PROJECT_ROOT) / spec.src
    if spec.base == "resources":
        return RESOURCE_DIR / spec.src
    # auto
    if spec.src.startswith(("modules/", "models/")):
        return Path(__import__("tools.builder.config", fromlist=["PROJECT_ROOT"])
                    .PROJECT_ROOT) / spec.src
    return RESOURCE_DIR / spec.src


# ─────────────────────────────────────────────────────────────
# 标准目录
# ─────────────────────────────────────────────────────────────

def _mkdirs(base: Path, structure: Dict) -> None:
    """B5：递归嵌套，支持任意深度。"""
    for name, children in structure.items():
        p = base / name
        p.mkdir(parents=True, exist_ok=True)
        if children:
            _mkdirs(p, children)


STANDARD_STRUCTURE = {
    "bin": {},
    "lib": {"python": {}, "site-packages": {}},
    "etc": {},
    "var": {"log": {}, "run": {}, "data": {}},
    "share": {"resources": {}, "doc": {}},
    "static": {},
}


def create_standard_dirs(cfg: BuildConfig, log=print) -> Path:
    root = cfg.install_dir
    if cfg.dry_run:
        log(f"  [dry-run] 将创建标准目录: {root}")
        return root
    if root.exists():
        if not cfg.force:
            raise RuntimeError(
                f"输出目录已存在: {root}\n"
                "  B6：默认不删除，避免误删数据。确认无误请加 --force。"
            )
        log(f"  🗑  --force：删除已有 {root}")
        shutil.rmtree(root)
    _mkdirs(root, STANDARD_STRUCTURE)
    log(f"  ✓ 标准目录结构: {root}")
    return root


def deploy_resources(cfg: BuildConfig, log=print) -> int:
    """B31：映射来自 resources.yaml 或内置默认。"""
    log("📦 部署资源文件...")
    specs = get_resource_specs()
    total = 0
    for spec in specs:
        src = _resolve(spec)
        if not src.exists():
            log(f"  ⚠️  跳过: {spec.src}（不存在）")
            continue
        if cfg.dry_run:
            n = sum(1 for f in src.rglob("*") if f.is_file())
            log(f"  [dry-run] {spec.src} → share/resources/{spec.dst}/  (约 {n} 个文件)")
            total += n
            continue
        dst = cfg.share_resources / spec.dst
        dst.mkdir(parents=True, exist_ok=True)
        n = copy_tree(src, dst, kind=spec.kind)
        total += n
        log(f"  ✓ {spec.src} → share/resources/{spec.dst}/  ({n} 个文件)")
    log(f"  📊 共复制 {total} 个文件")
    return total


def deploy_docs(cfg: BuildConfig, log=print) -> None:
    if DOCS_DIR.exists():
        dst = cfg.install_dir / "share" / "doc"
        shutil.copytree(DOCS_DIR, dst, dirs_exist_ok=True)
        log("  ✓ 文档 → share/doc/")


def move_outputs(cfg: BuildConfig, install_dir: Path, log=print) -> None:
    """按入口 stem + app_name 两种可能找二进制和 .dist。"""
    from .nuitka import locate_binary
    from .. import _platform as PF

    if cfg.dry_run:
        log(f"  [dry-run] 二进制 → bin/{PF.exe_name(cfg.app_name)}")
        log(f"  [dry-run] 依赖库 → lib/{cfg.app_name}/")
        return

    bins = locate_binary(cfg)
    if bins:
        target = install_dir / "bin" / PF.exe_name(cfg.app_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(bins[0]), str(target))
        PF.chmod_executable(target)
        log(f"  ✓ 二进制 → bin/{target.name}")
    else:
        log(f"  ⚠️  未找到二进制（找过 {cfg.app_name} / {cfg.entry_stem}）")

    if cfg.dist_dir.exists():
        target_lib = install_dir / "lib" / cfg.app_name
        if target_lib.exists():
            shutil.rmtree(target_lib)
        shutil.move(str(cfg.dist_dir), str(target_lib))
        log(f"  ✓ 依赖库 → lib/{cfg.app_name}/")
    else:
        log(f"  ⚠️  未找到 .dist 目录: {cfg.dist_dir}")
