#!/usr/bin/env python3
"""generate_frontend_services.py —— 由 API 契约生成前端 service 与类型补充。

用法（仓库根目录，先跑契约生成器再跑本脚本）：

    python scripts/api/generate_api_contract.py
    python scripts/api/generate_frontend_services.py

输入
────
* `resources/configs/api/endpoints.json`（唯一契约源，决定端点顺序与 op 集合）
* `scripts/api/generate_api_contract.py::ENDPOINTS`（同一契约的 Python 表，提供
  body / data / sse / summary 等字段；本脚本以 JSON 的 op 集合做一致性校验）
* `src/modules/api/requests.py` / `dto.py`（经契约脚本的 AST 解析得到模型字段）

产出
────
* `web/api/services/*.ts`：每个请求显式携带 `opName`，带路径参数的端点
  额外携带 `pathParams`，桌面 bridge 不再依赖 `getOpName(path)` 推导。
* `web/types/api.d.ts`：幂等追加契约引用但旧 api.d.ts 缺失的模型声明。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
EPS_JSON = ROOT / "resources" / "configs" / "api" / "endpoints.json"
CONTRACT_PY = ROOT / "scripts" / "api" / "generate_api_contract.py"
SERVICES_DIR = ROOT / "ui" / "api" / "services"
TYPES_FILE = ROOT / "ui" / "types" / "api.d.ts"

MARK_BEGIN = "  // ── 契约模型补充（generate_frontend_services.py 生成，请勿手工编辑） ──"
MARK_END = "  // ── 契约模型补充结束 ──"


# ── 载入契约脚本（只执行顶层 AST 解析，不调用 main，不写文件） ──────────
_spec = importlib.util.spec_from_file_location("api_contract", CONTRACT_PY)
contract = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(contract)
ALL_MODELS: Dict[str, List[Dict[str, Any]]] = contract.ALL_MODELS


def camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def file_of(e: Dict[str, Any]) -> str:
    """契约分组 → 前端文件名（保留历史文件名，组件 import 不改动）。"""
    p, grp = e["path"], e["group"]
    if grp == "generate":
        if p.startswith("/chat"):
            return "chat.ts"
        if p.startswith(("/tts", "/asr")):
            return "audio.ts"
        if p.startswith("/command"):
            return "command.ts"
        if p.startswith("/folder"):
            return "folder.ts"
        if p == "/status":
            return "status.ts"
        return "greater.ts"          # image / ocr / embedding / progress-stream
    if grp == "provider":
        return "pipeline.ts"
    if grp == "session":
        return "history.ts"
    if grp in ("ppt", "audit"):
        return "api.ts"
    if grp == "catalog":
        return "root.ts"
    return grp + ".ts"


def export_of(filename: str) -> str:
    return camel(filename[:-3]) + "Service"


def ts_type(ann: str) -> str:
    a = (ann or "").strip()
    if a.startswith("Optional[") and a.endswith("]"):
        a = a[len("Optional["):-1].strip()
    if a.endswith("| None"):
        a = a[:-len("| None")].strip()
    if a.startswith(("List[", "list[")):
        return ts_type(a[a.find("[") + 1:-1]) + "[]"
    if a.startswith(("Dict[", "dict[")) or a in ("Any", "object", "Dict[str, Any]"):
        return "Record<string, any>"
    if a == "str":
        return "string"
    if a in ("int", "float"):
        return "number"
    if a == "bool":
        return "boolean"
    return "any"


# ── 少数端点需要兼容旧组件调用形态，单独给出方法文本 ────────────────────
COMPAT_METHODS: Dict[str, str] = {
    "logger.append": """  /** 接收前端 LogForwarder 批量日志（兼容直接传数组） */
  async appendLog(body: API.LogAppendRequest | API.LogRecord[]): Promise<API.LogAppendData> {
    const payload: API.LogAppendRequest = Array.isArray(body)
      ? { records: body, no_frontend_push: true }
      : body;
    return request<API.LogAppendData>("post", "/logger/append", payload, { opName: "logger.append" });
  },""",
    "service.update_config": """  /** 更新服务配置（兼容直接传裸配置对象） */
  async updateConfig(service_id: string, body: API.ServiceConfigUpdateRequest | Record<string, any>): Promise<Record<string, any>> {
    const payload: API.ServiceConfigUpdateRequest =
      Object.prototype.hasOwnProperty.call(body, "config")
        ? (body as API.ServiceConfigUpdateRequest)
        : { config: body as Record<string, any> };
    return request<Record<string, any>>("put", `/service/${service_id}/config`, payload, { opName: "service.update_config", pathParams: { service_id } });
  },""",
}


def render_method(e: Dict[str, Any]) -> str:
    if e["op"] in COMPAT_METHODS:
        return COMPAT_METHODS[e["op"]]

    path_names = re.findall(r"\{(\w+)\}", e["path"])
    params: List[str] = [n + ": string" for n in path_names]
    method = e["method"].lower()

    if method == "get":
        if e.get("body"):
            params.append("body: API." + e["body"])
            payload_expr = "body"
        else:
            params.append("query?: Record<string, any>")
            payload_expr = "query"
    else:
        if e.get("body"):
            params.append("body: API." + e["body"])
            payload_expr = "body"
        else:
            params.append("body?: Record<string, any> | null")
            payload_expr = "body"

    data = e.get("data")
    if e.get("sse"):
        ret = "unknown"
    elif data == "str":
        ret = "string"
    elif data:
        ret = "API." + data
    else:
        ret = "Record<string, any>"

    url = e["path"]
    for n in path_names:
        url = url.replace("{" + n + "}", "${" + n + "}")

    opts = 'opName: "' + e["op"] + '"'
    if path_names:
        opts += ", pathParams: { " + ", ".join(path_names) + " }"

    summary = (e.get("summary") or e["op"]).replace("*/", "* /")
    lines = ["  /** " + summary + " */"]
    if e.get("sse"):
        lines.append("  // SSE 端点：此处仅给出签名，实际流式消费请用 fetch + ReadableStream")
    lines.append("  async " + camel(e["fn"]) + "(" + ", ".join(params) + "): Promise<" + ret + "> {")
    lines.append(
        "    return request<" + ret + '>("' + method + '", `' + url + "`, "
        + payload_expr + ", { " + opts + " });"
    )
    lines.append("  },")
    return "\n".join(lines)


# ── config.ts 页面级前端本地配置（不对应任何后端端点） ───────────────────
CONFIG_COMPAT = """
// ── 页面级前端本地配置：AdvancedConfig / SystemConfig 仅存在于浏览器，
// ── 不对应后端端点（后端 /config 的 section 白名单见 docs/api.md §3.3）。
export interface AdvancedConfig {
  install_components?: string[];
  code_highlight?: { enabled?: boolean; theme?: string };
  extra?: Record<string, any>;
}

export interface SystemConfig {
  log_config?: { level?: string; dir?: string };
  network_config?: { port?: number; timeout?: number };
}

const LOCAL_CONFIG_KEY = "chatbot.page_config";
const DEFAULT_PAGE_CONFIG = { advanced: {}, system: {} } as {
  advanced: AdvancedConfig;
  system: SystemConfig;
};

function readPageConfig(): typeof DEFAULT_PAGE_CONFIG {
  try {
    const raw = localStorage.getItem(LOCAL_CONFIG_KEY);
    return raw ? { ...DEFAULT_PAGE_CONFIG, ...JSON.parse(raw) } : DEFAULT_PAGE_CONFIG;
  } catch {
    return DEFAULT_PAGE_CONFIG;
  }
}

function writePageConfig(next: typeof DEFAULT_PAGE_CONFIG): void {
  localStorage.setItem(LOCAL_CONFIG_KEY, JSON.stringify(next));
}

export async function getAdvancedConfig(): Promise<AdvancedConfig> {
  return readPageConfig().advanced;
}

export async function saveAdvancedConfig(config: AdvancedConfig): Promise<void> {
  writePageConfig({ ...readPageConfig(), advanced: config });
}

export async function getSystemConfig(): Promise<SystemConfig> {
  return readPageConfig().system;
}

export async function saveSystemConfig(config: SystemConfig): Promise<void> {
  writePageConfig({ ...readPageConfig(), system: config });
}
"""


def render_service(filename: str, endpoints: List[Dict[str, Any]]) -> str:
    header = (
        "// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。\n"
        "// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）\n"
        "// 重新生成：python scripts/api/generate_frontend_services.py\n"
        'import { request } from "../http";\n\n'
    )
    body = "\n\n".join(render_method(e) for e in endpoints)
    out = header + "export const " + export_of(filename) + " = {\n" + body + "\n};\n"
    if filename == "config.ts":
        out += CONFIG_COMPAT
    if filename == "greater.ts":
        out += "\n/** 兼容别名：生成组亦可按 greaterService 导入 */\nexport const generateService = greaterService;\n"
    return out


def sync_types(used_models: set) -> int:
    text = TYPES_FILE.read_text("utf-8")
    existing = set(re.findall(r"^\s*interface\s+(\w+)", text, re.M))
    missing = sorted(used_models - existing - {"str"})

    block_lines = [MARK_BEGIN]
    for name in missing:
        fields = ALL_MODELS.get(name)
        if not fields:
            continue
        block_lines.append("  interface " + name + " {")
        for f in fields:
            opt = "" if f["required"] else "?"
            block_lines.append("    " + f["name"] + opt + ": " + ts_type(f["ann"]) + ";")
        block_lines.append("  }")
        block_lines.append("")
    block_lines.append(MARK_END)
    block = "\n".join(block_lines)

    if MARK_BEGIN in text and MARK_END in text:
        text = re.sub(
            re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END),
            lambda _: block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        idx = text.rfind("\n}")
        if idx < 0:
            raise SystemExit("api.d.ts 结构异常：找不到 namespace 结束括号")
        text = text[:idx] + "\n" + block + "\n" + text[idx:]
    TYPES_FILE.write_text(text, "utf-8")
    return len(missing)


def main() -> None:
    raw = json.loads(EPS_JSON.read_text("utf-8"))["endpoints"]
    json_ops = [e["op"] for e in raw]
    by_op = {e["op"]: e for e in contract.ENDPOINTS}
    missing = [op for op in json_ops if op not in by_op]
    stale = [op for op in by_op if op not in set(json_ops)]
    if missing or stale:
        raise SystemExit(
            "契约与 endpoints.json 不一致，请先重跑 generate_api_contract.py\n"
            "  JSON 多出: " + str(missing) + "\n  契约多出: " + str(stale)
        )
    endpoints = [by_op[op] for op in json_ops]

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for e in endpoints:
        groups.setdefault(file_of(e), []).append(e)

    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    for filename, eps in sorted(groups.items()):
        (SERVICES_DIR / filename).write_text(render_service(filename, eps), "utf-8")

    used: set = set()
    for e in endpoints:
        if e.get("body"):
            used.add(e["body"])
        if e.get("data") and e["data"] != "str":
            used.add(e["data"])
    added = sync_types(used)

    print("[OK] endpoints.json 与契约一致：" + str(len(endpoints)) + " 端点")
    print("[OK] 生成 " + str(len(groups)) + " 个前端 service：" + ", ".join(sorted(groups)))
    print("[OK] web/types/api.d.ts 补充 " + str(added) + " 个模型声明")


if __name__ == "__main__":
    main()
