"""ChatBot 统一构建入口（跨平台）。

用法
────
```bash
py build.py --dry-run            # 只看计划
py build.py                      # 完整构建
py build.py --only rust          # 只构建 Rust 内核
py build.py --only nuitka
py build.py --cython --installer # 开 Cython + 安装器
py build.py --clean              # 清理产物
```

设计
────
* 平台差异只在 `platform_.py`，这里不出现 `sys.platform` 判断
* 项目根自动探测（B1），不硬编码目录名
* 每步可单独跑（B33），失败不用重跑全流程
* 缺依赖（Rust 工具链 / Inno Setup / appimagetool）**跳过并提示**，
  不阻断 —— 安装器和 Rust 内核都有降级路径
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

BUILDER_DIR = Path(__file__).resolve().parent

# 任意 cwd 都能跑 —— 项目根必须在 sys.path 里，
# 否则 `tools.builder.*` 的绝对导入会失败。
sys.path.insert(0, str(BUILDER_DIR.parent.parent))
sys.path.insert(0, str(BUILDER_DIR))

from scripts.builds.config import PROJECT_ROOT, BuildConfig, parse_args  # noqa: E402
from scripts.builds.steps import cython as cython_step, rust, nuitka as nuitka_step  # noqa: E402
from scripts.builds.steps import resources as resources_step, installer as installer_step  # noqa: E402
from scripts.builds._platform import current as platform_name  # noqa: E402

LOG = print


def clean(cfg: BuildConfig) -> None:
    """清理时**必须**排除 Rust 产物。"""
    LOG("\n🧹 清理构建产物...")
    targets = [
        cfg.install_dir,
        cfg.output_path / f"{cfg.app_name}.dist",
        cfg.output_path / f"{cfg.entry_stem}.dist",
        cfg.output_path / f"{cfg.app_name}.build",
        cfg.output_path / f"{cfg.entry_stem}.build",
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "__pyx_cache__",
    ]
    for t in targets:
        if t.exists():
            shutil.rmtree(t, ignore_errors=True)
            LOG(f"  🗑  已删除 {t}")

    # 只扫 modules/ 下的包，避免误删 rust 产物
    from scripts.builds.config import EXCLUDED_DIR_NAMES
    mods = PROJECT_ROOT / "modules"
    if mods.exists():
        for pkg_dir in mods.iterdir():
            if not pkg_dir.is_dir() or pkg_dir.name in EXCLUDED_DIR_NAMES:
                continue
            for ext in (".pyd", ".so", ".dylib", ".c"):
                for f in pkg_dir.rglob(f"*{ext}"):
                    if "chatbot_core" in f.name:   # B15
                        continue
                    try:
                        f.unlink()
                    except OSError:
                        pass
    LOG("  ✓ 清理完成（Rust 内核产物已保留）")


def run(cfg: BuildConfig) -> int:
    only = cfg.only

    LOG(f"═══ ChatBot 构建 ═══")
    LOG(f"  项目根    : {PROJECT_ROOT}")
    LOG(f"  平台      : {platform_name()}")
    LOG(f"  应用名    : {cfg.app_name}  版本: {cfg.version}")
    LOG(f"  入口      : {cfg.entry}  (产物名按 '{cfg.entry_stem}' 推导)")
    LOG(f"  输出      : {cfg.output_path}")
    if cfg.dry_run:
        LOG("  模式      : dry-run（只打印计划）")

    # ── Rust 内核 ──
    if only in (None, "rust") and cfg.rust:
        LOG("\n[1/6] Rust 并发内核")
        rust.build(cfg, LOG)
        if rust.verify():
            LOG("  ✓ 内核可被 Python 加载")
        else:
            LOG("  x  内核不可用")

    if only == "rust":
        return 0

    # ── Cython ──
    if only in (None, "cython"):
        LOG("\n[2/6] Cython 预编译")
        cython_step.build(cfg, LOG)

    if only == "cython":
        return 0

    # ── Nuitka ──
    if only in (None, "nuitka"):
        LOG("\n[3/6] Nuitka 编译")
        if not nuitka_step.build(cfg, LOG):
            return 1

    if only == "nuitka":
        return 0

    if not cfg.deploy:
        LOG(f"\n✅ 编译完成，产物在 {cfg.output_path}/")
        return 0

    if only == "resources":
        LOG("\n[4/6] 资源部署")
        try:
            resources_step.create_standard_dirs(cfg, LOG)
        except RuntimeError as e:
            LOG(f"  ❌ {e}")
            return 1
        resources_step.deploy_resources(cfg, LOG)
        return 0

    # ── 部署 ──
    LOG("\n[4/6] 部署到标准目录")
    try:
        install_dir = resources_step.create_standard_dirs(cfg, LOG)
    except RuntimeError as e:
        LOG(f"  ❌ {e}")
        return 1
    resources_step.move_outputs(cfg, install_dir, LOG)
    resources_step.deploy_resources(cfg, LOG)
    resources_step.deploy_docs(cfg, LOG)

    if only == "deploy":
        return 0

    # ── 安装器 ──
    if cfg.installer or only == "installer":
        LOG("\n[5/6] 安装器")
        installer_step.build(cfg, LOG)

    # ── 结构 ──
    LOG("\n[6/6] 输出结构")
    print_final_structure(install_dir)

    LOG(f"\n 构建完成：{install_dir}")
    return 0


def print_final_structure(install_dir: Path, max_depth: int = 3) -> None:
    if not install_dir.exists():
        print(f"  （{install_dir} 不存在）")
        return
    print(f"📁 {install_dir.name}/")
    for root, dirs, files in os.walk(install_dir):
        level = str(root).replace(str(install_dir), "").count(os.sep)
        if level >= max_depth:
            continue
        indent = "  " * level
        folder = os.path.basename(root)
        if folder == install_dir.name:
            continue
        print(f"{indent}📂 {folder}/")
        sub = "  " * (level + 1)
        for f in sorted(files)[:5]:
            print(f"{sub}📄 {f}")
        if len(files) > 5:
            print(f"{sub}... ({len(files) - 5} more)")


def main(argv=None) -> int:
    cfg = parse_args(argv)
    if cfg.clean:
        clean(cfg)
        return 0
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
