"""平台差异抽象

**唯一**允许出现 `sys.platform` 判断的地方。
其余代码一律从这里取常量，这样新增平台只需改这一个文件。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"


def current() -> str:
    if WINDOWS:
        return "windows"
    if MACOS:
        return "macos"
    if LINUX:
        return "linux"
    return sys.platform


@dataclass(frozen=True)
class PlatformSpec:
    """一个平台的全部差异。"""
    name: str
    #: Python 扩展模块后缀
    py_ext: str
    #: 动态库后缀（资源复制时要**保留**，不能排掉）
    lib_exts: tuple
    #: 可执行文件后缀（Windows 有 .exe）
    exe_suffix: str
    #: Nuitka 在 macOS 上的产物目录结构不同
    macos_bundle: bool
    #: 安装器类型
    installer_kinds: tuple


SPECS = {
    "windows": PlatformSpec(
        name="windows",
        py_ext=".pyd",
        lib_exts=(".dll", ".pyd"),
        exe_suffix=".exe",
        macos_bundle=False,
        installer_kinds=("inno",),
    ),
    "linux": PlatformSpec(
        name="linux",
        py_ext=".so",
        lib_exts=(".so",),
        exe_suffix="",
        macos_bundle=False,
        installer_kinds=("appimage", "deb"),
    ),
    "macos": PlatformSpec(
        name="macos",
        py_ext=".so",
        lib_exts=(".so", ".dylib"),
        exe_suffix="",
        macos_bundle=True,
        installer_kinds=("app", "dmg"),
    ),
}


def spec() -> PlatformSpec:
    return SPECS.get(current(), SPECS["linux"])


# ─────────────────────────────────────────────────────────────
# 便捷访问
# ─────────────────────────────────────────────────────────────

def py_ext() -> str:
    """本平台的 Python 扩展后缀（.pyd / .so）。"""
    return spec().py_ext


def exe_name(app_name: str) -> str:
    """可执行文件名。"""
    return f"{app_name}{spec().exe_suffix}"


def is_lib(path: Path) -> bool:
    """是否是本平台的原生库（复制资源时必须保留）。"""
    return path.suffix.lower() in spec().lib_exts


def native_exts() -> tuple:
    """所有可能的原生产物后缀（用于清理时识别，B15 要用）。"""
    return (".pyd", ".so", ".dylib", ".dll")


# ─────────────────────────────────────────────────────────────
# 工具探测
# ─────────────────────────────────────────────────────────────

def find_tool(*names: str) -> Optional[Path]:
    """在 PATH 里找工具。"""
    for n in names:
        w = shutil.which(n)
        if w:
            return Path(w)
    return None


def find_iscc() -> Optional[Path]:
    """Windows：Inno Setup 编译器。"""
    if not WINDOWS:
        return None
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return Path(c)
    return find_tool("ISCC", "iscc")


def find_appimagetool() -> Optional[Path]:
    """Linux：AppImage 打包工具。"""
    if not LINUX:
        return None
    return find_tool("appimagetool")


def find_dpkg_deb() -> Optional[Path]:
    if not LINUX:
        return None
    return find_tool("dpkg-deb")


def has_hdiutil() -> bool:
    """macOS：DMG 打包（系统自带）。"""
    return MACOS and find_tool("hdiutil") is not None


def has_codesign() -> bool:
    """签名工具，没有就跳过不阻断。"""
    return find_tool("codesign" if MACOS else "signtool") is not None


def available_installers() -> List[str]:
    """本平台**实际可用**的安装器（缺依赖就跳过）。"""
    out: List[str] = []
    for kind in spec().installer_kinds:
        if kind == "inno" and find_iscc():
            out.append(kind)
        elif kind == "appimage" and find_appimagetool():
            out.append(kind)
        elif kind == "deb" and find_dpkg_deb():
            out.append(kind)
        elif kind in ("app", "dmg"):
            # .app 手工组装即可；dmg 需要 hdiutil
            if kind == "app" or has_hdiutil():
                out.append(kind)
    return out


def chmod_executable(path: Path) -> None:
    """非 Windows 加可执行位。"""
    if not WINDOWS and path.exists():
        try:
            path.chmod(0o755)
        except OSError:
            pass


def nuitka_platform_args(app_name: str, version: str, project_root: Path) -> List[str]:
    """Nuitka 的平台相关参数。"""
    args: List[str] = []
    if WINDOWS:
        icon = project_root / "resources" / "app.ico"
        args += [
            f"--windows-company-name={app_name}",
            f"--windows-product-name={app_name}",
            # B3：版本号贯通，不再硬编码 1.0.0
            f"--windows-file-version={version}",
            f"--windows-product-version={version}",
            f"--windows-file-description={app_name}",
        ]
        if icon.exists():
            args.append(f"--windows-icon-from-ico={icon}")
    elif MACOS:
        icon = project_root / "resources" / "app.icns"
        args.append("--macos-create-app-bundle")
        if icon.exists():
            args.append(f"--macos-app-icon={icon}")
    return args
