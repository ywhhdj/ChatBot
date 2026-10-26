"""Rust 内核构建"""

from __future__ import annotations
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

from .. import _platform as PF
from ..config import BuildConfig, RUST_DIR

#: 扩展模块名（与 Cargo.toml 的 [lib] name 一致）
MODULE_NAME = "core"


def toolchain_available() -> bool:
    # 检查 cargo 是否可用
    return shutil.which("cargo") is not None


def maturin_available() -> bool:
    try:
        import maturin  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return shutil.which("maturin") is not None


def already_built(project_root: Path) -> Optional[Path]:
    """项目根下已存在的扩展模块。"""
    for p in project_root.glob(f"{MODULE_NAME}.*"):
        if p.is_file() and p.suffix.lower() in PF.native_exts():
            return p
    return None

verified = False

def build(cfg: BuildConfig, log=print) -> Optional[Path]:
    global verified
    """构建 Rust 内核，返回扩展模块路径；跳过或失败返回 None。"""
    if not RUST_DIR.exists():
        log("  ⚠️  无 rust/ 目录，跳过 Rust 内核（Python 后端兜底）")
        return None

    if not toolchain_available():
        log("  ⚠️  未找到 cargo，跳过 Rust 内核（Python 后端兜底）")
        log("     需要时安装：https://rustup.rs  然后 pip install maturin")
        return None

    if not maturin_available():
        log("  ⚠️  未找到 maturin，跳过 Rust 内核")
        log("     安装：pip install maturin")
        return None

    if cfg.dry_run:
        log("  [dry-run] 将执行: maturin build --release")
        return None

    log(f"🔧 Rust 内核构建（{PF.current()} / {PF.py_ext()}）...")

    wheel_dir = RUST_DIR / "target" / "wheels"
    if wheel_dir.exists():
        shutil.rmtree(wheel_dir, ignore_errors=True)

    cmd = ["maturin", "build", "--release", "--out", str(wheel_dir), "-i", cfg.python_path]
    r = subprocess.run(
        cmd,
        cwd=str(RUST_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",     # 关键：强制用 UTF-8 解码
        errors="replace",     # 遇到非法字节也不抛异常，替换成 �
    )
    if r.returncode != 0:
        log("  ❌ maturin build 失败:")
        log((r.stdout or "")[-2000:])
        log((r.stderr or "")[-2000:])
        return None

    wheels = sorted(wheel_dir.glob("*.whl"))
    if not wheels:
        log("  ❌ 未找到 wheel 产物")
        return None

    ext = _extract_extension(wheels[-1], cfg.project_root)
    if ext is None:
        log("  ❌ wheel 中未找到扩展模块")
        return None

    log(f"  ✓ {ext.name} → {ext.relative_to(cfg.project_root)}")
    verified = True
    return ext


def _extract_extension(wheel: Path, project_root: Path) -> Optional[Path]:
    """从 wheel 里解出扩展模块，放到项目根（Nuitka/PyInstaller 能找到）。"""
    target = project_root / f"{MODULE_NAME}{PF.py_ext()}"
    with zipfile.ZipFile(wheel) as z:
        for name in z.namelist():
            if not name.endswith(PF.native_exts()):
                continue
            # 只取顶层扩展模块，跳过嵌套的 .libs/ 依赖
            if "/" in name.rsplit("/", 1)[0] and not name.startswith(MODULE_NAME):
                continue
            data = z.read(name)
            target.write_bytes(data)
            return target
    return None


def verify() -> bool:
    global verified
    return verified
