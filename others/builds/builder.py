import os
import sys
import shutil

import subprocess
import stat
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent / "src_py"
sys.path.insert(0, str(PROJECT_ROOT))
RESOURCE_DIR = PROJECT_ROOT / "resources"

# ─── 资源目录映射 ─────────────────────────────
# 源路径 → 目标子目录（相对于 share/resources/）
RESOURCE_MAPPING = {
    # 配置类（保持目录结构）
    "defaults":          "defaults",
    "models":           "models",
    "roles":            "roles",

    # 模型文件（保持原始目录结构）
    "live2d":                   "models/live2d",
    "emotion":                   "models/emotion",
    "mediapipe":                 "models/mediapipe",
    "panddleOCR":                "models/panddleOCR",
    "asr":   "models/asr",
    "tts":   "models/tts",
    "ocr":   "models/ocr",

    # Browser 脚本 → 统一转移到 scripts/
    "modules/services/browser/scripts": "scripts",
}

# 需要排除的目录名（不复制）
EXCLUDED_DIR_NAMES = {
    "schema",          # 结构定义文件，不需要分发
    "__pycache__",
    ".git",
    ".pytest_cache",
    "__pyx_cache__",  # Cython 缓存
    "build",
}

# 需要排除的文件扩展名
EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".DS_Store",
    ".gitignore",
    ".pyx",
    ".c"
}

NOFOLLOW_IMPORT_PATTERNS = {
    "*.tests",
    "*.test",
    "tests.*",
    "test_*",
    "pytest",
    "unittest",
}

#忽略的模块
IGNORE_MODULES = {
    "__pycache__",
    "ui"
}

def _resolve_source_path(src_rel: str) -> Path:
    """
    - 以 "modules/" 开头的 → 相对于 PROJECT_ROOT
    - 以 "models/" 开头的 → 相对于 PROJECT_ROOT（因为实际路径是 PROJECT_ROOT/models/）
    - 其他 → 相对于 RESOURCE_DIR
    """
    if src_rel.startswith("modules/") or src_rel.startswith("models/"):
        return PROJECT_ROOT / src_rel
    return RESOURCE_DIR / src_rel

def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
    if path.is_file():
        return path.suffix.lower() in EXCLUDED_EXTENSIONS
    return False


def copy_resource_tree(src: Path, dst: Path):
    """递归复制目录，保持结构，跳过排除项"""
    if not src.exists():
        print(f"  ⚠️  源不存在，跳过: {src}")
        return 0
    count = 0
    for item in src.rglob("*"):
        if should_exclude(item):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    return count


def compile_cython():
    """调用 Cython 编译关键模块"""
    print("\n🔧 [步骤 0] Cython 编译关键模块...")
    cython_script = PROJECT_ROOT / "others/builds/cython.py"
    if not cython_script.exists():
        print(f"  ❌ Cython 脚本不存在: {cython_script}")
        sys.exit(1)

    # 先清理旧的 Cython 产物
    for ext in ["*.c", "*.pyx", "*.pyd", "*.so"]:
        for f in PROJECT_ROOT.rglob(ext):
            if should_exclude(f):
                continue
            # 只删除 build 过程中产生的文件，不动源码
            if "build" in f.parts or "__pyx_cache__" in f.parts:
                try:
                    f.unlink()
                except OSError:
                    pass
    result = subprocess.run(
        [sys.executable, str(cython_script), "build_ext", "--inplace"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("  ❌ Cython 编译失败:")
        print(result.stderr)
        sys.exit(1)
    print("  ✓ Cython 编译成功")


def deploy_resources(install_share_resources: Path):
    """
    按 RESOURCE_MAPPING 复制资源到 share/resources/，
    保持原始目录结构。
    """
    print("\n📦 [步骤 1] 部署资源文件（保持目录结构）...")
    total = 0
    for src_rel, dst_rel in RESOURCE_MAPPING.items():
        src = _resolve_source_path(src_rel)
        dst = install_share_resources / dst_rel
        if not src.exists():
            print(f"  ⚠️  跳过: {src_rel}（不存在）")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        # 计算复制前的文件数
        before = sum(1 for _ in dst.rglob("*") if _.is_file())
        count = copy_resource_tree(src, dst)
        total += count
        print(f"  ✓ {src_rel} → share/resources/{dst_rel}/  ({count} 个文件)")

    print(f"  📊 共复制 {total} 个文件")

# ─── Nuitka 编译 ─────────────────────────────
def _build_nuitka_include_packages() -> list[str]:
    """
    自动发现 modules/ 下的所有一级子包，生成 --include-package 参数。
    这样无论 modules/ 下有哪些包，都能被正确包含。
    """
    modules_dir = PROJECT_ROOT / "modules"
    if not modules_dir.exists():
        print(f"  ❌ modules/ 目录不存在: {modules_dir}")
        sys.exit(1)

    packages = []
    for item in sorted(modules_dir.iterdir()):
        if item.is_dir() and item.name not in IGNORE_MODULES:
            packages.append(f"modules.{item.name}")

    if not packages:
        print("  ❌ modules/ 下没有找到任何 Python 包")
        sys.exit(1)

    print(f"  📋 自动发现 {len(packages)} 个模块包: {', '.join(packages)}")
    return packages


def build_with_nuitka(entry_point: str, output_dir: str, app_name: str):
    """
    调用 Nuitka 编译为 standalone 目录。
    关键修复：
    1. --include-package 使用完整路径 modules.xxx
    2. 添加 --include-dir 确保模块目录被找到
    3. 移除废弃的 numpy 插件
    4. 使用 --follow-imports 的细粒度控制
    """
    print("\n🚀 [步骤 2] Nuitka 编译（standalone 模式）...")

    entry_abs = PROJECT_ROOT / entry_point
    if not entry_abs.exists():
        print(f"  ❌ 入口文件不存在: {entry_abs}")
        sys.exit(1)

    # 自动发现要包含的包
    packages = _build_nuitka_include_packages()

    # 构建 Nuitka 参数
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--follow-imports",
        f"--nofollow-import-to={','.join(NOFOLLOW_IMPORT_PATTERNS)}",
        "--remove-output",
        f"--output-dir={output_dir}",
        f"--output-filename={app_name}",  # Nuitka 4.x 推荐参数名
        "--lto=yes",
        f"--jobs={os.cpu_count() or 4}",
        # 不使用废弃的 --enable-plugin=numpy
        # 显式包含模块目录
    ]

    # 添加所有发现的包
    for pkg in packages:
        cmd.append(f"--include-package={pkg}")

    # 追加入口文件
    cmd.append(str(entry_abs))

    print(f"  执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False)
    if result.returncode != 0:
        print("  ❌ Nuitka 编译失败")
        sys.exit(1)
    print("  ✓ Nuitka 编译成功")


def create_standard_dirs(base_path: str, app_name: str) -> Path:
    root = Path(base_path) / app_name
    structure = {
        "bin": {},
        "lib": {"python": {}, "site-packages": {}},
        "etc": {},
        "var": {"log": {}, "run": {}, "data": {}},
        "share": {"resources": {}, "doc": {}},
        "static": {},
    }
    for parent, children in structure.items():
        parent_path = root / parent
        parent_path.mkdir(parents=True, exist_ok=True)
        for child in children:
            (parent_path / child).mkdir(exist_ok=True)

    # 设置 bin 目录可执行权限（Unix）
    bin_path = root / "bin"
    if bin_path.exists() and os.name != "nt":
        for item in bin_path.iterdir():
            if item.is_file():
                item.chmod(item.stat().st_mode | stat.S_IEXEC)

    print(f"  ✓ 标准目录结构已创建: {root}")
    return root


def move_nuitka_outputs(output_dir: str, install_dir: Path, app_name: str):
    """将 Nuitka 产物移动到标准目录位置"""
    output_path = Path(output_dir)

    # 1. 移动二进制到 bin/
    binary_name = f"{app_name}.exe" if sys.platform == "win32" else app_name
    binary_src = output_path / binary_name
    if binary_src.exists():
        shutil.move(str(binary_src), str(install_dir / "bin" / binary_name))
        if os.name != "nt":
            (install_dir / "bin" / binary_name).chmod(0o755)
        print(f"  ✓ 二进制 → bin/{binary_name}")

    # 2. 移动 .dist 目录到 lib/
    dist_dir = output_path / f"{app_name}.dist"
    if dist_dir.exists():
        target_lib = install_dir / "lib" / app_name
        if target_lib.exists():
            shutil.rmtree(target_lib)
        shutil.move(str(dist_dir), str(target_lib))
        print(f"  ✓ 依赖库 → lib/{app_name}/")

    # 3. 移动 .build 目录到 lib/.build
    build_dir = output_path / f"{app_name}.build"
    if build_dir.exists():
        target_build = install_dir / "lib" / f"{app_name}.build"
        if target_build.exists():
            shutil.rmtree(target_build)
        shutil.move(str(build_dir), str(target_build))
        print(f"  ✓ 构建缓存 → lib/{app_name}.build/")


def deploy(args) -> Path:
    """部署到标准目录"""
    print("\n📂 [步骤 3] 部署到标准目录...")
    install_dir = create_standard_dirs(args.output_dir, args.app_name)

    # 移动 Nuitka 产物
    move_nuitka_outputs(args.output_dir, install_dir, args.app_name)

    # 部署资源（保持目录结构）
    resources_dst = install_dir / "share" / "resources"
    deploy_resources(resources_dst)

    # 复制文档（如果有）
    doc_src = PROJECT_ROOT / "docs"
    if doc_src.exists():
        shutil.copytree(doc_src, install_dir / "share" / "doc", dirs_exist_ok=True)
        print(f"  ✓ 文档 → share/doc/")

    print(f"\n🎉 构建完成！输出目录: {install_dir}")
    return install_dir


def print_final_structure(install_dir: Path):
    """打印最终目录树（前3层）"""
    print(f"\n📁 {install_dir.name}/")
    for root, dirs, files in os.walk(install_dir):
        level = root.replace(str(install_dir), "").count(os.sep)
        if level >= 3:
            continue
        indent = "  " * level
        folder = os.path.basename(root)
        if folder == install_dir.name:
            continue
        print(f"{indent}📂 {folder}/")
        sub_indent = "  " * (level + 1)
        for f in sorted(files)[:5]:
            print(f"{sub_indent}📄 {f}")
        if len(files) > 5:
            print(f"{sub_indent}... ({len(files) - 5} more)")

