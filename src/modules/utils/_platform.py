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
    py_ext: str
    lib_exts: tuple
    exe_suffix: str


SPECS = {
    "windows": PlatformSpec(
        name="windows",
        py_ext=".pyd",
        lib_exts=(".dll", ".pyd"),
        exe_suffix=".exe",
    ),
    "linux": PlatformSpec(
        name="linux",
        py_ext=".so",
        lib_exts=(".so",),
        exe_suffix="",
    ),
    "macos": PlatformSpec(
        name="macos",
        py_ext=".so",
        lib_exts=(".so", ".dylib"),
        exe_suffix=""
    ),
}


def spec() -> PlatformSpec:
    return SPECS.get(current(), SPECS["linux"])