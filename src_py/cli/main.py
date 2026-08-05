# def main():
import argparse


def build_pipline_json_args(parser: argparse.ArgumentParser):
    INPUT_MODULES_PATH="src_py/modules"
    OUTPUT_PATH="resources/defaults/pipeline.json"
    #归属子命令generate:pipepline
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")
    parser = subparsers.add_parser("generate:pipeline", 
        help="生成 modules/config/pipeline.json 配置模板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--modules", "-m",
        default=INPUT_MODULES_PATH,
        help="modules 目录路径（默认: modules）"
    )
    parser.add_argument(
        "--output", "-o",
        default=OUTPUT_PATH,
        help=f"输出 pipeline.json 路径（默认: {OUTPUT_PATH}）"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="生成后交互式填写 description"
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="额外输出前端用的精简 manifest.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印结果，不写文件"
    )
    return parser

def build_service_config_args(parser: argparse.ArgumentParser):
    #归属子命令generate:service
    output_path="modules/defaults/services.yaml"
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")
    parser = subparsers.add_parser("generate:service", 
        help="生成 modules/config/service.yaml 配置模板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--output", "-o",
        default=output_path,
        help=f"输出 service.yaml 配置文件路径（默认: {output_path}）"
    )
    return parser

def main():
    parser = argparse.ArgumentParser(
        description="生成 各种配置模板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser = build_pipline_json_args(parser)
    parser = build_service_config_args(parser)
    args = parser.parse_args()
    print(args)
if __name__ == "__main__":
    main()
