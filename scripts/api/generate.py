#!/usr/bin/env python3
"""generate.py —— 从 OpenAPI JSON 生成前端 TypeScript 类型 + 服务文件。

用法:
    python scripts/api/generate.py --url http://localhost:8000/openapi.json
    python scripts/api/generate.py --file openapi.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen

# 本文件路径： <project_dir>/scripts/api/generate.py
PROJECT_DIR = Path(__file__).parent.parent.parent


# ============================================================
# 常量 & 默认配置
# ============================================================

TS_KEYWORDS = {
    "string", "number", "boolean", "null", "undefined", "unknown",
    "any", "never", "void", "this",
    "Array", "Record", "Promise", "Date", "Object", "Function",
    "Map", "Set", "Partial", "Required", "Readonly", "Pick", "Omit",
    "Exclude", "Extract", "ReturnType", "Parameters", "NonNullable",
}

# Python 基础类型 -> TS 基础类型
PY_PRIMITIVES: Dict[str, str] = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "Any": "any",
    "None": "null",
    "NoneType": "null",
    "bytes": "string",
    "datetime": "string",
    "date": "string",
    "UUID": "string",
    "Decimal": "number",
}

# FastAPI 自动生成的泛型容器前缀
GENERIC_BASES = ("Dict", "List", "Set", "FrozenSet", "Tuple", "Optional", "Union")

DEFAULT_CONFIG: Dict[str, Any] = {
    "url": None,
    "strip_prefix": "/api",
    "wrapper_name": "ApiResponse",
    "http_import": "../http",
    "rename_map": {},
    "service_map": {
        "session":   ("history.ts",   "historyService"),
        "chat":      ("chat.ts",      "chatService"),
        "character": ("character.ts", "characterService"),
        "memory":    ("memory.ts",    "memoryService"),
        "skill":     ("skill.ts",     "skillService"),
        "service":   ("service.ts",   "serviceService"),
        "system":    ("system.ts",    "systemService"),
        "logger":    ("logger.ts",    "loggerService"),
        "save":      ("save.ts",      "saveService"),
        "pipeline":  ("pipeline.ts",  "pipelineService"),
        "config":    ("config.ts",    "configService"),
        "tts":       ("audio.ts",     "audioService"),
        "asr":       ("audio.ts",     "audioService"),
        "command":   ("command.ts",   "commandService"),
        "task":      ("task.ts",      "taskService"),
        "folder":    ("folder.ts",    "folderService"),
        "status":    ("status.ts",    "statusService"),
    },
}


# ============================================================
# 工具函数
# ============================================================

def to_camel(name: str) -> str:
    if not name:
        return name
    parts = re.split(r"[-_\s]+", name)
    head = parts[0][:1].lower() + parts[0][1:]
    tail = "".join(p[:1].upper() + p[1:] for p in parts[1:])
    result = head + tail
    result = re.sub(r"[^a-zA-Z0-9_$]", "", result)
    if result and result[0].isdigit():
        result = "_" + result
    return result or name


def to_pascal(name: str) -> str:
    if not name:
        return name
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[-_\s]+", name))


def prefix_types(ts: str, ns: str = "API") -> str:
    """给自定义类型名加 `API.` 前缀，跳过 TS 关键字和已带前缀的标识符。"""
    if not ts or ts == "unknown":
        return ts
    out: List[str] = []
    i, n = 0, len(ts)
    while i < n:
        c = ts[i]
        if c.isalpha() and c.isupper():
            j = i
            while j < n and (ts[j].isalnum() or ts[j] in "_$"):
                j += 1
            word = ts[i:j]
            prev = ts[i - 1] if i > 0 else ""
            if prev == ".":
                out.append(word)
            elif word in TS_KEYWORDS:
                out.append(word)
            elif word == ns:
                out.append(word)
            else:
                out.append(f"{ns}.{word}")
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_spec(url: Optional[str], file: Optional[str]) -> dict:
    if file:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    if url:
        with urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    raise SystemExit("必须提供 --url 或 --file")


# ============================================================
# FastAPI 泛型名 -> TS 类型
# ============================================================

def _resolve_py_token(token: str) -> str:
    """解析泛型参数里的单个 token：原始类型 / 嵌套泛型 / 自定义模型。"""
    if token in PY_PRIMITIVES:
        return PY_PRIMITIVES[token]
    # 嵌套泛型的尾部下划线可能在拆分时丢失，两种都试
    for candidate in (token, token + "_"):
        parsed = _try_generic(candidate)
        if parsed is not None:
            return parsed
    return f"API.{token}"


def _try_generic(name: str) -> Optional[str]:
    """解析 FastAPI 泛型名 -> TS 表达式，不是泛型则返回 None。

    Dict_str__Any_        -> Record<string, any>
    Dict_str__str_        -> Record<string, string>
    Dict_str__List_int__  -> Record<string, Array<number>>
    List_str_             -> Array<string>
    List_CharacterInfo_   -> Array<API.CharacterInfo>
    Optional_str_         -> string | null
    Union_str__int_       -> string | number
    Tuple_str__int_       -> [string, number]
    """
    if not name.endswith("_"):
        return None
    for base in GENERIC_BASES:
        prefix = base + "_"
        if not name.startswith(prefix):
            continue
        inner = name[len(prefix):-1]
        if not inner:
            continue

        # 参数之间用 `__` 连接；单参数时没有 `__`
        raw_args = inner.split("__") if "__" in inner else [inner]
        args = [a.strip("_") for a in raw_args if a.strip("_")]
        if not args:
            continue

        resolved = [_resolve_py_token(a) for a in args]

        if base == "Dict":
            if len(resolved) >= 2:
                return f"Record<{resolved[0]}, {resolved[1]}>"
        elif base in ("List", "Set", "FrozenSet"):
            return f"Array<{resolved[0]}>"
        elif base == "Optional":
            return f"{resolved[0]} | null"
        elif base == "Union":
            return " | ".join(resolved)
        elif base == "Tuple":
            return "[" + ", ".join(resolved) + "]"
    return None


# ============================================================
# 类型生成器：JSON Schema -> declare namespace API
# ============================================================

class TypeGenerator:
    def __init__(self, schemas: dict, config: dict):
        self.schemas = schemas
        self.config = config
        self.rename_map = config["rename_map"]
        self.wrapper_name = config["wrapper_name"]

    def resolve(self, name: str) -> str:
        return self.rename_map.get(name, name)

    def generate(self) -> str:
        wrapper_sample = None
        regular: Dict[str, dict] = {}

        for raw, schema in self.schemas.items():
            if re.match(rf"^{re.escape(self.wrapper_name)}_(.+)_$", raw):
                wrapper_sample = schema
            elif _try_generic(raw) is not None:
                # 泛型合成名（Dict_*_ / List_*_ 等）不单独生成，引用处内联
                continue
            else:
                regular[raw] = schema

        blocks: List[str] = []
        if wrapper_sample:
            blocks.append(self._gen_wrapper(wrapper_sample))
        for raw, schema in regular.items():
            blocks.append(self._gen_type(raw, schema))

        header = (
            "/**\n"
            " * 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。\n"
            " * 重新生成: python scripts/api/generate.py\n"
            " */\n\n"
            "declare namespace API {\n"
        )
        return header + "\n\n".join(blocks) + "\n}\n"

    # ---------- wrapper ----------
    def _gen_wrapper(self, sample: dict) -> str:
        props = sample.get("properties", {}) or {}
        required = set(sample.get("required", []) or [])
        lines: List[str] = []
        for key, val in props.items():
            if key == "data":
                lines.append("    data?: T | null;")
            else:
                opt = "" if key in required else "?"
                lines.append(f"    {key}{opt}: {self._schema_to_ts(val, 2)};")
        body = "\n".join(lines) if lines else "    [k: string]: unknown;"
        return f"  interface {self.wrapper_name}<T = unknown> {{\n{body}\n  }}"

    # ---------- 普通 schema ----------
    def _gen_type(self, raw: str, schema: dict) -> str:
        name = self.resolve(raw)
        ts = self._schema_to_ts(schema, 1)
        desc = (schema.get("description") or "").strip()
        doc = ""
        if desc:
            first = desc.split("\n")[0].strip()
            if first:
                doc = f"  /** {first} */\n"
        if ts.startswith("{"):
            return f"{doc}  interface {name} {ts}"
        return f"{doc}  type {name} = {ts};"

    # ---------- JSON Schema -> TS ----------
    def _schema_to_ts(self, schema: dict, indent: int) -> str:
        if not schema:
            return "unknown"

        # $ref
        if "$ref" in schema:
            raw = schema["$ref"].rsplit("/", 1)[-1]

            # 1) 泛型合成名：Dict_str__Any_ 之类，直接内联成 TS 表达式
            parsed = _try_generic(raw)
            if parsed is not None:
                return parsed

            # 2) ApiResponse_Xxx_ 包装
            m = re.match(rf"^{re.escape(self.wrapper_name)}_(.+)_$", raw)
            if m:
                inner_name = m.group(1)
                inner_parsed = _try_generic(inner_name)
                if inner_parsed is not None:
                    return f"{self.wrapper_name}<{inner_parsed}>"
                return f"{self.wrapper_name}<{self.resolve(inner_name)}>"

            # 3) 普通类型
            return self.resolve(raw)

        # enum
        if "enum" in schema and isinstance(schema["enum"], list):
            parts: List[str] = []
            for v in schema["enum"]:
                if v is None:
                    parts.append("null")
                elif isinstance(v, bool):
                    parts.append("true" if v else "false")
                elif isinstance(v, str):
                    parts.append(json.dumps(v))
                else:
                    parts.append(str(v))
            return " | ".join(parts) if parts else "never"

        nullable = bool(schema.get("nullable"))
        t = schema.get("type")

        # OpenAPI 3.1 的 type 数组: ["string", "null"]
        if isinstance(t, list):
            if "null" in t:
                nullable = True
                t = [x for x in t if x != "null"]
            if len(t) == 1:
                t = t[0]
            elif len(t) > 1:
                parts = [self._schema_to_ts({"type": x}, indent) for x in t]
                base = " | ".join(parts)
                return f"({base}) | null" if nullable else base
            else:
                t = None

        # anyOf / oneOf
        for key in ("anyOf", "oneOf"):
            if key in schema and isinstance(schema[key], list):
                parts: List[str] = []
                had_null = nullable
                for s in schema[key]:
                    if s.get("type") == "null":
                        had_null = True
                        continue
                    parts.append(self._schema_to_ts(s, indent))
                if not parts:
                    return "null" if had_null else "unknown"
                seen, uniq = set(), []
                for p in parts:
                    if p not in seen:
                        seen.add(p)
                        uniq.append(p)
                base = " | ".join(uniq)
                if had_null and "null" not in base:
                    base += " | null"
                return base

        # allOf
        if "allOf" in schema and isinstance(schema["allOf"], list):
            base = " & ".join(self._schema_to_ts(s, indent) for s in schema["allOf"])
            return f"({base}) | null" if nullable else base

        # 基础类型
        if t == "string":
            base = "string"
        elif t in ("integer", "number"):
            base = "number"
        elif t == "boolean":
            base = "boolean"
        elif t == "null":
            return "null"
        elif t == "array":
            inner = self._schema_to_ts(schema.get("items", {}), indent)
            base = f"Array<{inner}>" if ("|" in inner or "&" in inner) else f"{inner}[]"
        elif t == "object" or "properties" in schema or "additionalProperties" in schema:
            if "properties" in schema and isinstance(schema["properties"], dict):
                pad = "  " * (indent + 1)
                close = "  " * indent
                required = set(schema.get("required", []) or [])
                lines: List[str] = []
                for k, v in schema["properties"].items():
                    opt = "" if k in required else "?"
                    key = k if re.match(r"^[A-Za-z_$][\w$]*$", k) else json.dumps(k)
                    lines.append(f"{pad}{key}{opt}: {self._schema_to_ts(v, indent + 1)};")
                base = "{\n" + "\n".join(lines) + "\n" + close + "}" if lines else "Record<string, never>"
            elif "additionalProperties" in schema:
                ap = schema["additionalProperties"]
                if ap is True:
                    v = "any"                        # Dict[str, Any] 期望 any
                elif isinstance(ap, dict):
                    v = self._schema_to_ts(ap, indent)
                else:
                    v = "unknown"
                base = f"Record<string, {v}>"
            else:
                base = "Record<string, unknown>"
        else:
            base = "unknown"

        return f"{base} | null" if nullable else base


# ============================================================
# 服务生成器：paths -> xxxService 文件
# ============================================================

class ServiceGenerator:
    HTTP_METHODS = ("get", "post", "put", "delete", "patch")

    def __init__(self, spec: dict, config: dict):
        self.spec = spec
        self.config = config
        self.schemas = spec.get("components", {}).get("schemas", {})
        self.type_gen = TypeGenerator(self.schemas, config)
        self.strip_prefix: str = config["strip_prefix"]
        self.service_map: Dict[str, Tuple[str, str]] = config["service_map"]

    # ---------- 对外 ----------
    def generate(self) -> Dict[str, str]:
        buckets: Dict[str, List[Tuple[str, str, str, dict]]] = {}
        for path, methods in (self.spec.get("paths") or {}).items():
            for method, op in methods.items():
                if method not in self.HTTP_METHODS:
                    continue
                seg = self._segment(path)
                fname, _ = self.service_map.get(seg, (f"{seg}.ts", f"{seg}Service"))
                buckets.setdefault(fname, []).append((path, method, seg, op))
        return {fn: self._render_file(fn, ops) for fn, ops in buckets.items()}

    # ---------- 路径段 ----------
    def _segment(self, path: str) -> str:
        p = path
        if self.strip_prefix and p.startswith(self.strip_prefix):
            p = p[len(self.strip_prefix):]
        parts = [x for x in p.split("/") if x]
        return parts[0] if parts else "root"

    # ---------- 单个文件 ----------
    def _render_file(self, filename: str, ops: List[Tuple[str, str, str, dict]]) -> str:
        service_name = self._pick_service_name(filename, ops)
        methods = sorted(
            (self._process_op(p, m, op) for p, m, _, op in ops),
            key=lambda x: x["name"],
        )

        lines = [
            "// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。",
            f'import {{ request }} from "{self.config["http_import"]}";',
            "",
            f"export const {service_name} = {{",
        ]
        for i, m in enumerate(methods):
            if i > 0:
                lines.append("")
            lines.append(self._render_method(m))
        lines.append("};")
        lines.append("")
        return "\n".join(lines)

    def _pick_service_name(self, filename: str, ops) -> str:
        name: Optional[str] = None
        for _, _, seg, _ in ops:
            info = self.service_map.get(seg)
            if not info:
                continue
            if name is None:
                name = info[1]
            elif name != info[1]:
                name = None
                break
        if not name:
            name = filename.rsplit(".", 1)[0] + "Service"
        return name

    # ---------- 单个 operation ----------
    def _process_op(self, path: str, method: str, op: dict) -> dict:
        # 1) 方法名
        op_id = op.get("operationId") or ""
        name = re.sub(r"_api_.*?_(?:get|post|put|delete|patch)$", "", op_id)
        if not name:
            name = f"{method}_{path}"
        name = to_camel(name)

        # 2) 参数
        path_params: List[dict] = []
        query_params: List[dict] = []
        for p in op.get("parameters", []) or []:
            loc = p.get("in")
            entry = {
                "name": p["name"],
                "schema": p.get("schema") or {},
                "required": bool(p.get("required")),
                "description": (p.get("description") or "").strip(),
            }
            if loc == "path":
                entry["required"] = True
                path_params.append(entry)
            elif loc == "query":
                query_params.append(entry)

        # 3) 路径模板
        stripped = path
        if self.strip_prefix and stripped.startswith(self.strip_prefix):
            stripped = stripped[len(self.strip_prefix):] or "/"
        template = re.sub(r"\{(\w+)\}", r"${\1}", stripped)
        path_expr = f"`{template}`" if path_params else f'"{template}"'

        # 4) requestBody
        body_type: Optional[str] = None
        if "requestBody" in op:
            content = (op["requestBody"].get("content") or {})
            if "application/json" in content:
                bs = content["application/json"].get("schema") or {}
                body_type = prefix_types(self.type_gen._schema_to_ts(bs, 0))

        # 5) 返回类型
        inner, kind = self._extract_return(op)

        return {
            "name": name,
            "http": method,
            "path_expr": path_expr,
            "path_params": path_params,
            "query_params": query_params,
            "body_type": body_type,
            "return_inner": inner,
            "return_kind": kind,
            "summary": (op.get("summary") or "").strip(),
        }

    # ---------- 返回类型解析 ----------
    def _inner_ts(self, name: str) -> str:
        """把内部类型名解析成 TS 字符串（原始类型 / 泛型 / 自定义）。"""
        if name in PY_PRIMITIVES:
            return PY_PRIMITIVES[name]
        parsed = _try_generic(name)
        if parsed is not None:
            return parsed
        return f"API.{self.config['rename_map'].get(name, name)}"

    def _extract_return(self, op: dict) -> Tuple[str, str]:
        responses = op.get("responses") or {}
        ok = responses.get("200") or responses.get("201")
        if not ok:
            return "unknown", "bare"
        content = (ok.get("content") or {})
        if "application/json" not in content:
            return "unknown", "bare"
        schema = content["application/json"].get("schema") or {}

        wrapper = self.config["wrapper_name"]

        if "$ref" in schema:
            raw = schema["$ref"].rsplit("/", 1)[-1]
            m = re.match(rf"^{re.escape(wrapper)}_(.+)_$", raw)
            if m:
                inner_name = m.group(1)
                return self._inner_ts(inner_name), "wrapped"
            # 非包装 $ref
            return self._inner_ts(raw), "bare"

        return self.type_gen._schema_to_ts(schema, 0), "bare"

    # ---------- 渲染单个方法 ----------
    def _render_method(self, m: dict) -> str:
         # 参数列表
        params: List[str] = []
        for p in m["path_params"]:
            params.append(f"{p['name']}: {self.type_gen._schema_to_ts(p['schema'], 0)}")

        if m["query_params"]:
            fields: List[str] = []
            for q in m["query_params"]:
                opt = "" if q["required"] else "?"
                ts = self.type_gen._schema_to_ts(q["schema"], 0)
                if q["description"]:
                    fields.append(f"      /** {q['description']} */")
                fields.append(f"      {q['name']}{opt}: {ts};")
            params.append("query?: {\n" + "\n".join(fields) + "\n    }")

        if m["body_type"]:
            params.append(f"body: {m['body_type']}")

        # 返回 & 泛型
        # http.ts 的响应拦截器已经解包了 ApiResponse，这里直接声明 data 的类型
        inner = m["return_inner"]
        if inner and inner != "unknown":
            promise = f"Promise<{inner}>"
            request_generic = f"<{inner}>"
        else:
            promise = "Promise<unknown>"
            request_generic = ""

        # 调用参数
        call_args = [f'"{m["http"]}"', m["path_expr"]]
        if m["body_type"]:
            call_args.append("body")
        elif m["query_params"]:
            call_args.append("query")

        call = f"request{request_generic}({', '.join(call_args)})"

        doc = f"  /** {m['summary']} */\n" if m["summary"] else ""
        return (
            f"{doc}  async {m['name']}({', '.join(params)}): {promise} {{\n"
            f"    return {call};\n"
            f"  }},"
        )


# ============================================================
# CLI
# ============================================================

def build_config(args) -> dict:
    config = dict(DEFAULT_CONFIG)
    config["service_map"] = dict(DEFAULT_CONFIG["service_map"])
    config["rename_map"] = dict(DEFAULT_CONFIG["rename_map"])

    cfg_path = PROJECT_DIR / "scripts/api" / "config.json"
    if cfg_path.exists():
        user_config = json.loads(cfg_path.read_text(encoding="utf-8"))
        config.update(user_config)

    if args.http_import:
        config["http_import"] = args.http_import
    if args.strip_prefix is not None:
        config["strip_prefix"] = args.strip_prefix
    if args.url:
        config["url"] = args.url
    if args.types_out:
        config["types_out"] = args.types_out
    if args.services_out:
        config["services_out"] = args.services_out
    return config


def main() -> None:
    ap = argparse.ArgumentParser(description="从 OpenAPI 生成 TS 类型 + 服务文件")
    ap.add_argument("--url", help="OpenAPI JSON URL")
    ap.add_argument("--file", help="OpenAPI JSON 文件路径")
    ap.add_argument("--types-out", default="src/types/api.d.ts", help="api.d.ts 输出路径")
    ap.add_argument("--services-out", default="src/api/services", help="服务文件输出目录")
    ap.add_argument("--http-import", default=None, help="服务里 import request 的路径")
    ap.add_argument("--strip-prefix", default=None, help="生成服务文件时去掉的路径前缀")
    ap.add_argument("--index", action="store_true", help="额外生成 index.ts 统一导出")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    config = build_config(args)
    spec = load_spec(config.get("url"), args.file)

    schemas = spec.get("components", {}).get("schemas", {})
    types_content = TypeGenerator(schemas, config).generate()
    services = ServiceGenerator(spec, config).generate()

    if args.dry_run:
        print("=" * 70)
        print(f"// {args.types_out}")
        print("=" * 70)
        print(types_content)
        for fn, content in sorted(services.items()):
            print()
            print("=" * 70)
            print(f"// {args.services_out}/{fn}")
            print("=" * 70)
            print(content)
        return

    # 写类型
    types_path = Path(PROJECT_DIR / config["types_out"])
    types_path.parent.mkdir(parents=True, exist_ok=True)
    types_path.write_text(types_content, encoding="utf-8")
    print(f"✓ {types_path}")

    # 写服务
    services_dir = Path(PROJECT_DIR / config["services_out"])
    services_dir.mkdir(parents=True, exist_ok=True)
    for fn, content in sorted(services.items()):
        p = services_dir / fn
        p.write_text(content, encoding="utf-8")
        print(f"✓ {p}")

    # index.ts
    if args.index:
        lines = [f'export * from "./{fn.rsplit(".", 1)[0]}";' for fn in sorted(services)]
        idx = services_dir / "index.ts"
        idx.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"✓ {idx}")


if __name__ == "__main__":
    main()