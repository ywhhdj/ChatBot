"""
pipeline.json 配置自动生成器
=================================
功能：
    扫描 modules/pipeline/adapters/ 下所有 adapter 类，
    通过 inspect 反射提取 __init__ 参数签名，
    自动生成符合 PipelineManager 加载格式的 pipeline.json。

输出结构（与 pipeline.py 对齐）：
```json
    {
        "asr": {
            "whisper": {
                "name": "whisper",
                "description": "",          ← 留空，手动填写
                "tags": [],
                "config": {
                    "model_size": {
                        "default": "base",
                        "required": false,
                        "description": ""
                    }
                }
            }
        },
        "tts": { ... },
        "llm": { ... },
        "ocr": { ... }
    }
Example
    ```bash
        # 在项目根目录执行
        cd D:\\Project\\ChatBot
        python cli/generates/config.py

        # 指定输出路径
        python cli/generates/config.py --output ./modules/config/pipeline.json

        # 指定 modules 目录路径
        python cli/generates/config.py --modules ./modules

        # 生成后交互式填写 description
        python cli/generates/config.py --interactive
    ```
"""
import argparse
import inspect
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Type

import yaml

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def camel_to_snake(name: str) -> str:
    """CamelCase → snake_case"""
    s = re.sub(r"(?<=.)([A-Z])", r"_\1", name)
    return s.lower()


def strip_adapter_suffix(name: str) -> str:
    """WhisperASRAdapter → whisper_asr / ASRAdapter → asr"""
    name = re.sub(r"Adapter$", "", name)
    return name


def get_provider_name(class_name: str) -> str:
    """WhisperASRAdapter → whisper"""
    name = strip_adapter_suffix(class_name)
    name = re.sub(r"_(asr|tts|llm|ocr)$", "", name, flags=re.IGNORECASE)
    return camel_to_snake(name)


def python_type_to_json_type(t) -> str:
    """把 Python 类型注解转为 JSON Schema 风格的字符串"""
    if t is None:
        return "null"
    # 处理 typing 模块的类型
    origin = getattr(t, "__origin__", None)
    if origin is not None:
        # Optional[str] → Optional / Union
        args = getattr(t, "__args__", ())
        if origin is Optional or (origin is getattr(__import__("typing"), "Union", None)):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return python_type_to_json_type(non_none[0])
            return " | ".join(python_type_to_json_type(a) for a in non_none)
        if origin in (list, List):
            return "list"
        if origin in (dict, Dict):
            return "object"
        return str(origin).replace("typing.", "")
    # 基础类型
    if t is str:
        return "str"
    if t is int:
        return "integer"
    if t is float:
        return "number"
    if t is bool:
        return "boolean"
    if t is bytes:
        return "string"
    if t is type(None):
        return "null"
    # 兜底
    return getattr(t, "__name__", str(t))


def default_to_jsonable(val: Any) -> Any:
    if val is inspect.Parameter.empty or val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, dict):
        return dict(val)
    # 不可序列化 → 用 repr
    return repr(val)


# ──────────────────────────────────────────────
# 核心：从 adapter 类提取参数信息
# ──────────────────────────────────────────────

def extract_adapter_info(cls: Type, adapter_type: str) -> Optional[Dict[str, Any]]:
    """
    从 adapter 类提取信息，返回 provider 条目。
    如果类不是 _BaseAdapter 子类或没有 __init__，返回 None。
    """
    # 获取 __init__ 签名
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return None

    # 读取类文档字符串
    doc = inspect.getdoc(cls) or ""
    # 取第一行作为简短描述
    short_doc = doc.strip().split("\n")[0] if doc else ""

    init_params: Dict[str, dict] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        # 跳过 *args, **kwargs
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        has_default = param.default is not inspect.Parameter.empty
        default_val = param.default if has_default else None

        # 类型注解
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            annotation = None

        # type_str = python_type_to_json_type(annotation)

        init_params[param_name] = {
            # "type": type_str,
            "default": default_to_jsonable(default_val),
            "required": not has_default,
            "description": ""  # ← 留空，给前端/人工填写
        }

    # 特殊处理：如果参数里有 config 或 params 这种 dict 大对象，展开提示
    # （可选增强，当前保持简单）

    provider_name = get_provider_name(cls.__name__)

    return {
        "name": provider_name,
        "class": f"{cls.__module__}.{cls.__name__}",
        "description": short_doc,   # 从 docstring 自动提取，可后续覆盖
        "tags": [],
        "adapter_type": adapter_type,
        "config": init_params
    }


# ──────────────────────────────────────────────
# 自动发现 adapter 类
# ──────────────────────────────────────────────

# adapter_type → (目录名, 基类提示)
# 用于在没有真实模块时可回退的手动注册表
ADAPTER_TYPE_MAP = {
    "asr": "asr",
    "tts": "tts",
    "llm": "llm",
    "ocr": "ocr",
}


def discover_adapters(modules_root: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    自动发现并提取所有 adapter。

    策略：
    1. 尝试把 modules_root 加入 sys.path，动态 import 各 adapter 模块
    2. 在模块中查找继承自 _BaseAdapter (或 _ASRBaseAdapter 等) 的子类
    3. 提取参数信息

    如果 import 失败（运行环境不全），则回退到内置的静态注册表。
    """
    results: Dict[str, List[Dict[str, Any]]] = {}

    adapters_root = os.path.join(modules_root, "pipeline", "adapters")
    if not os.path.isdir(adapters_root):
        print(f"⚠️  未找到 adapters 目录: {adapters_root}")
        return {}

    # 把项目根（modules 的父目录）加入 path
    project_root = os.path.dirname(modules_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    for adapter_type_dir in os.listdir(adapters_root):
        type_path = os.path.join(adapters_root, adapter_type_dir)
        if not os.path.isdir(type_path):
            continue

        adapter_type = adapter_type_dir  # asr / tts / llm / ocr / landmarker
        results[adapter_type] = []

        # 遍历目录下的 .py 文件
        for fname in sorted(os.listdir(type_path)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            module_name = fname[:-3]

            # 构造 import 路径: modules.pipeline.adapters.tts.adapter
            rel_path = os.path.relpath(type_path, project_root).replace(os.sep, ".")
            import_path = f"{rel_path}.{module_name}"

            try:
                mod = __import__(import_path, fromlist=["*"])
            except Exception as e:
                print(f"  ⚠️  无法导入 {import_path}: {e}")
                continue

            # 在模块中找 adapter 类
            for attr_name in dir(mod):
                if attr_name.startswith("_"):
                    continue
                obj = getattr(mod, attr_name)
                if not inspect.isclass(obj):
                    continue
                if obj.__module__ != mod.__name__:
                    continue  # 跳过导入的类
                # 判断是否是 adapter（类名含 Adapter 或以 _Base 开头）
                if "Adapter" not in attr_name and "_Base" not in attr_name:
                    continue
                if attr_name.startswith("_"):
                    continue

                info = extract_adapter_info(obj, adapter_type)
                if info is not None:
                    results[adapter_type].append(info)
                    print(f"  ✅ 发现 {adapter_type}/{info['name']} ({obj.__name__})")

    # 过滤空类别
    results = {k: v for k, v in results.items() if v}
    return results


def build_final_config(discovered: Dict[str, List[Dict[str, Any]]]) -> dict:
    """
    将发现结果转为 pipeline.json 最终格式。

    注意：pipeline.py 中 load_config 读到的结构是：
        { adapter_type: { provider_name: { name, description, tags, config } } }
    其中 config 下的每个 key 就是 provider 的 init 参数名。
    PipelineManager.switch_adapter 会把这个 config dict 解包传给
    adapter_manager.intialize_provider(**provider_config)
    """
    output:dict[str,Any] = {}
    for adapter_type, providers in discovered.items():
        output[adapter_type] = {}
        for prov in providers:
            name:str = prov["name"]
            name = name.replace("_", "").replace(adapter_type, "")
            # 去掉内部字段
            clean = {
                "name": name,
                "description": prov.get("description", ""),
                "tags": prov.get("tags", []),
                "config": prov.get("config", {})
            }
            output[adapter_type][name] = clean
    return output


def merge_with_existing(new_config: dict, existing_path: str) -> dict:
    """
    如果已有 pipeline.json，合并保留手动填写的 description / tags。
    新参数追加，已删除的参数移除。
    """
    if not os.path.isfile(existing_path):
        return new_config

    try:
        with open(existing_path, "r", encoding="utf-8") as f:
            old = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠️  已有文件解析失败，将覆盖: {e}")
        return new_config

    for adapter_type, providers in new_config.items():
        old_type = old.get(adapter_type, {})
        if not isinstance(old_type, dict):
            continue
        for prov_name, prov_cfg in providers.items():
            if prov_name in old_type:
                old_prov = old_type[prov_name]
                # 保留旧 description（如果非空）
                if old_prov.get("description"):
                    prov_cfg["description"] = old_prov["description"]
                # 保留旧 tags
                if old_prov.get("tags"):
                    prov_cfg["tags"] = old_prov["tags"]
                # 合并 config：保留旧 description
                old_config = old_prov.get("config", {})
                for param_name, param_cfg in prov_cfg["config"].items():
                    if param_name in old_config:
                        old_param = old_config[param_name]
                        if old_param.get("description"):
                            param_cfg["description"] = old_param["description"]
    return new_config


# ──────────────────────────────────────────────
# 交互式填写
# ──────────────────────────────────────────────

def interactive_fill(config: dict) -> dict:
    """交互式让用户输入每个 provider 的 description"""
    print("\n" + "=" * 60)
    print("📝 交互式填写 description")
    print("   直接回车 = 保留现有值，输入 '.' = 清空")
    print("=" * 60 + "\n")

    for adapter_type, providers in config.items():
        print(f"\n── {adapter_type.upper()} ──")
        for prov_name, prov_cfg in providers.items():
            current = prov_cfg.get("description", "")
            prompt = f"  [{prov_name}] 描述"
            if current:
                prompt += f" (当前: {current})"
            prompt += ": "
            try:
                user_input = input(prompt).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n⏭️  跳过剩余")
                break
            if user_input == ".":
                prov_cfg["description"] = ""
            elif user_input:
                prov_cfg["description"] = user_input

    return config

def build_frontend_manifest(config: dict) -> dict:
    """
    生成给前端用的精简清单（不含敏感默认值以外的冗余信息）。
    前端用它来渲染「可切换的 provider 列表 + 参数表单」。
    """
    manifest = {}
    for adapter_type, providers in config.items():
        manifest[adapter_type] = []
        for prov_name, prov_cfg in providers.items():
            params = []
            for pname, pcfg in prov_cfg.get("config", {}).items():
                params.append({
                    "key": pname,
                    "type": pcfg.get("type", "str"),
                    "required": pcfg.get("required", False),
                    "default": pcfg.get("default"),
                    "description": pcfg.get("description", "")
                })
            manifest[adapter_type].append({
                "name": prov_name,
                "description": prov_cfg.get("description", ""),
                "tags": prov_cfg.get("tags", []),
                "params": params
            })
    return manifest

INPUT_MODULES_PATH="src_py/modules"
OUTPUT_PATH="resources/defaults/pipeline.yaml"

def main():
    parser = argparse.ArgumentParser(
        description="生成 modules/config/pipeline.json 配置模板",
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
    args = parser.parse_args()

    modules_root = os.path.abspath(args.modules)
    if not os.path.isdir(modules_root):
        print(f"❌ modules 目录不存在: {modules_root}")
        print("   请用 --modules 指定正确路径")
        sys.exit(1)

    # 默认输出路径
    if args.output is None:
        args.output = os.path.join(os.path.abspath("."), "resources","defaults", "pipeline.json")
    output_path = os.path.abspath(args.output)

    print(f"🔍 扫描 adapters: {modules_root}/pipeline/adapters/\n")
    discovered = discover_adapters(modules_root)

    if not discovered:
        print("❌ 未发现任何 adapter")
        sys.exit(1)

    # 构建最终配置
    new_config = build_final_config(discovered)

    # 合并已有文件（保留手填的 description）
    new_config = merge_with_existing(new_config, output_path)

    # 交互式填写
    if args.interactive:
        new_config = interactive_fill(new_config)

    # 统计
    total_providers = sum(len(v) for v in new_config.values())
    print(f"\n{'=' * 60}")
    print(f"📊 汇总: {len(new_config)} 个 adapter 类型, {total_providers} 个 provider")
    for at, ps in new_config.items():
        if isinstance(ps, str):
            continue
        print(f"   {at:12s} → {len(ps)} 个: {', '.join(ps.keys())}")
    print(f"{'=' * 60}")

    # 写文件 or dry-run
    if args.dry_run:
        print("\n📄 [DRY RUN] 以下内容将被写入:\n")
        print(json.dumps(new_config, ensure_ascii=False, indent=2))
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(new_config, f, allow_unicode=True)
        print(f"\n✅ 已写入: {output_path}")

    # 前端 manifest
    if args.manifest:
        manifest = build_frontend_manifest(new_config)
        manifest_path = os.path.join(os.path.dirname(output_path), "pipeline_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"✅ 前端 manifest 已写入: {manifest_path}")

    print("\n💡 提示: description 字段为空的需要你手动填写（或加 -i 交互填写）")


if __name__ == "__main__":
    main()