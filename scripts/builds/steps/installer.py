"""安装器（B9–B13）。

| 平台 | 产物 | 依赖 |
|---|---|---|
| Windows | `setup.exe` | Inno Setup 6（ISCC.exe） |
| Linux   | `*.AppImage` / `*.deb` | appimagetool / dpkg-deb |
| macOS   | `*.app` / `*.dmg` | hdiutil（系统自带） |

B9：缺依赖时**跳过并提示**，绝不 `sys.exit(1)` —— 安装器不是主产物。
B4：输出统一放在 `output_dir/installer/`，不再猜 `tools/dist/installer`。
B13：签名可选，没证书就跳过。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .. import _platform as PF
from ..config import BuildConfig


def installer_dir(cfg: BuildConfig) -> Path:
    """B4：统一输出位置。"""
    return cfg.output_path / "installer"


# ─────────────────────────────────────────────────────────────
# Windows: Inno Setup
# ─────────────────────────────────────────────────────────────

def _iss_template(cfg: BuildConfig) -> str:
    path = Path(__file__).resolve().parent / f"windows.iss"
    iss=path.read_text(encoding="utf-8").strip()
    rep={
        "app_name": cfg.app_name,
        "app_version": cfg.version,
        "exe_name": PF.exe_name(cfg.app_name),
        "installer_dir": installer_dir(cfg),
    }
    return iss.format(**rep)


def build_inno(cfg: BuildConfig, log=print) -> Optional[Path]:
    iscc = PF.find_iscc()
    if iscc is None:
        log("  ⚠️  未找到 ISCC.exe，跳过（安装 https://jrsoftware.org/isdl.php）")
        return None

    out = installer_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    iss = _iss_template(cfg)

    if cfg.dry_run:
        log(f"  [dry-run] 将执行: {iscc} {iss} /DAppVersion={cfg.version}")
        return None

    r = subprocess.run(
        [
            str(iscc), 
            str(iss), 
            f"/DAppVersion={cfg.version}"
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log("  ❌ Inno Setup 编译失败:")
        log((r.stdout or "")[-1500:])
        return None

    setups = sorted(
        out.glob("*-setup.exe"),
        key=lambda p: p.stat().st_mtime, 
        reverse=True
    )
    if setups:
        mb = setups[0].stat().st_size / 1024 / 1024
        log(f"  ✓ 安装器: {setups[0]}  ({mb:.1f} MB)")
        return setups[0]
    log("  ⚠️未找到生成的 setup.exe")
    return None


# ─────────────────────────────────────────────────────────────
# Linux: AppImage + deb
# ─────────────────────────────────────────────────────────────

def build_appimage(cfg: BuildConfig, log=print) -> Optional[Path]:
    tool = PF.find_appimagetool()
    if tool is None:
        log("  ⚠️  未找到 appimagetool，跳过")
        return None

    appdir = installer_dir(cfg) / f"{cfg.app_name}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "share").mkdir(parents=True, exist_ok=True)

    exe = cfg.install_dir / "bin" / PF.exe_name(cfg.app_name)
    if not exe.exists():
        log(f"  ⚠️  二进制不存在: {exe}")
        return None
    shutil.copy2(exe, appdir / "usr" / "bin" / cfg.app_name)

    # B11：AppImage 三件套
    (appdir / f"{cfg.app_name}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName={cfg.app_name}\n"
        f"Exec={cfg.app_name}\nTerminal=false\nCategories=Utility;\n",
        encoding="utf-8"
    )
    (appdir / "AppRun").write_text(
        "#!/bin/sh\nSELF=$(readlink -f \"$0\")\n"
        "exec \"$SELF/usr/bin/%s\" \"$@\"\n" % cfg.app_name,
        encoding="utf-8"
    )
    PF.chmod_executable(appdir / "AppRun")

    icon = cfg.project_root / "resources" / "app.png"
    if icon.exists():
        shutil.copy2(icon, appdir / f"{cfg.app_name}.png")

    if cfg.dry_run:
        log(f"  [dry-run] 将执行: {tool} {appdir}")
        return None

    r = subprocess.run(
        [str(tool), str(appdir)],
        cwd=str(installer_dir(cfg)),
        capture_output=True, 
        text=True
    )
    if r.returncode != 0:
        log("  ❌ AppImage 打包失败:")
        log((r.stderr or "")[-1500:])
        return None

    found = sorted(installer_dir(cfg).glob("*.AppImage"))
    if found:
        log(f"  ✓ AppImage: {found[-1]}")
        return found[-1]
    return None


def build_deb(cfg: BuildConfig, log=print) -> Optional[Path]:
    if PF.find_dpkg_deb() is None:
        log("  ⚠️  未找到 dpkg-deb，跳过")
        return None

    root = installer_dir(cfg) / f"{cfg.app_name}_deb"
    if root.exists():
        shutil.rmtree(root)
    debian = root / "DEBIAN"
    debian.mkdir(parents=True, exist_ok=True)
    (root / "opt").mkdir(parents=True, exist_ok=True)

    # B-A：umask 宽松的环境（umask 000 / 容器默认）会让目录落成 0777，
    # dpkg-deb 要求 control 目录必须在 0755~0775 之间，否则直接失败。
    # 构建脚本不能依赖运行环境的 umask，这里显式收紧。
    for d in (root, debian):
        try:
            d.chmod(0o755)
        except OSError:
            pass

    (root / "DEBIAN" / "control").write_text(
        f"Package: {cfg.app_name.lower()}\n"
        f"Version: {cfg.version}\n"
        f"Section: utils\nPriority: optional\n"
        f"Architecture: amd64\nMaintainer: ChatBot\n"
        f"Description: {cfg.app_name} desktop application\n",
        encoding="utf-8"
    )

    target = root / "opt" / cfg.app_name
    shutil.copytree(cfg.install_dir, target)

    out = installer_dir(cfg) / f"{cfg.app_name}_{cfg.version}_amd64.deb"
    if cfg.dry_run:
        log(f"  [dry-run] 将执行: dpkg-deb --build {root} {out}")
        return None

    r = subprocess.run(
        ["dpkg-deb", "--build", str(root), str(out)],
        capture_output=True,
        text=True
    )
    if r.returncode != 0:
        log("  ❌ deb 打包失败:")
        log((r.stderr or "")[-1500:])
        return None
    log(f"  ✓ deb: {out}")
    return out


# ─────────────────────────────────────────────────────────────
# macOS: .app + DMG
# ─────────────────────────────────────────────────────────────

def build_app_bundle(cfg: BuildConfig, log=print) -> Optional[Path]:
    """B10：手工组装 .app（Nuitka 在 macOS 上直接出可执行）。"""
    if not PF.MACOS:
        return None
    app = installer_dir(cfg) / f"{cfg.app_name}.app"
    contents = app / "Contents"
    for sub in ("MacOS", "Resources", "Frameworks"):
        (contents / sub).mkdir(parents=True, exist_ok=True)

    exe = cfg.install_dir / "bin" / PF.exe_name(cfg.app_name)
    if not exe.exists():
        log(f"  ⚠️  二进制不存在: {exe}")
        return None
    shutil.copy2(exe, contents / "MacOS" / cfg.app_name)
    PF.chmod_executable(contents / "MacOS" / cfg.app_name)

    (contents / "Info.plist").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleName</key><string>{cfg.app_name}</string>
<key>CFBundleExecutable</key><string>{cfg.app_name}</string>
<key>CFBundleVersion</key><string>{cfg.version}</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>""",
    encoding="utf-8"
)

    if cfg.dry_run:
        log(f"  [dry-run] .app → {app}")
        return app

    log(f"  ✓ .app: {app}")
    return app


def build_dmg(cfg: BuildConfig, log=print) -> Optional[Path]:
    if not PF.has_hdiutil():
        log("  ⚠️  未找到 hdiutil（仅 macOS），跳过")
        return None
    app = build_app_bundle(cfg, log)
    if app is None:
        return None
    dmg = installer_dir(cfg) / f"{cfg.app_name}-{cfg.version}.dmg"
    if cfg.dry_run:
        log(f"  [dry-run] 将执行: hdiutil create {dmg}")
        return None
    r = subprocess.run(
        ["hdiutil", "create", "-volname", cfg.app_name,
         "-srcfolder", str(app), "-ov", "-format", "UDZO", str(dmg)],
        capture_output=True, text=True)
    if r.returncode != 0:
        log("  ❌ DMG 打包失败:")
        log((r.stderr or "")[-1200:])
        return None
    log(f"  ✓ DMG: {dmg}")
    return dmg


# ─────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────

def build(cfg: BuildConfig, log=print) -> List[Path]:
    log(f"📦 安装器（{PF.current()}）...")
    installer_dir(cfg).mkdir(parents=True, exist_ok=True)

    # B-C：安装器依赖已部署的 install_dir。
    # 原来直接 copytree 会抛 FileNotFoundError —— 单独跑 `--only installer`
    # 时必然崩。改为明确提示并跳过：安装器不是主产物。
    if not cfg.install_dir.exists():
        log(f"  ⚠️  尚未部署（{cfg.install_dir} 不存在），跳过安装器")
        log("     先跑完整构建，或 --only deploy 后再做安装器")
        return []

    out: List[Path] = []

    for kind in PF.available_installers():
        p = None
        if kind == "inno":
            p = build_inno(cfg, log)
        elif kind == "appimage":
            p = build_appimage(cfg, log)
        elif kind == "deb":
            p = build_deb(cfg, log)
        elif kind == "app":
            p = build_app_bundle(cfg, log)
        elif kind == "dmg":
            p = build_dmg(cfg, log)
        if p:
            out.append(p)

    if not out:
        avail = PF.available_installers()
        if not avail:
            log("  ⚠️  本平台没有可用的安装器依赖，已跳过")
        log("     （安装器不是主产物，standalone 目录仍可直接运行）")
    return out


__all__ = ["build", "installer_dir", "build_inno", "build_appimage",
           "build_deb", "build_app_bundle", "build_dmg"]
