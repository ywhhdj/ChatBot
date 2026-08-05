import argparse
from builder import (
    compile_cython,
    deploy,
    print_final_structure,
    build_with_nuitka
)

DEFAULT_ENTRY = "main.py"
DEFAULT_OUTPUT_DIR = "dist"
DEFAULT_APP_NAME = "ChatBot"

def parse_args():
    parser = argparse.ArgumentParser(description="ChatBot 构建脚本")
    parser.add_argument("--entry", default=DEFAULT_ENTRY)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--cython", action="store_true", help="启用 Cython 预编译")
    return parser.parse_args()

def build():
    args = parse_args()

    # Cython 预编译
    if args.cython:
        compile_cython()

    # Nuitka 编译
    build_with_nuitka(args.entry, args.output_dir, args.app_name)

    # 部署到标准目录
    install_dir = deploy(args)

    # 打印最终结构
    print_final_structure(install_dir)


if __name__ == "__main__":
    build()