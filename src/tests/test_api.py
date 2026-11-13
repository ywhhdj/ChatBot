#!/usr/bin/env python3
"""
API 冒烟测试脚本
================
从 resources/configs/api/endpoints.json 读取所有端点，构造最小合法请求，
对运行中的 Web 服务做冒烟测试，输出 PASS / FAIL / WARN 统计。

用法示例
--------
    # 1) 只测只读端点（默认，安全）
    python scripts/test_api.py

    # 2) 只测某个分组
    python scripts/test_api.py --group system --group logger

    # 3) 只测某个 op
    python scripts/test_api.py --op system.health

    # 4) 测全部端点（含写操作，会修改数据，仅本地开发用）
    python scripts/test_api.py --all

    # 5) 输出 JSON 报告（供 CI 消费）
    python scripts/test_api.py --json > report.json

设计原则
--------
* 安全优先：默认跳过所有 PUT/PATCH/POST/DELETE。
* 参数模板：按 op 提供路径参数 / query / body 的默认值，保证请求能被路由。
* 状态分级：
    PASS  → 2xx 且 ok=true
    WARN  → 2xx 但 ok=false（业务拒绝，路由本身是通的，如未初始化）
    FAIL  → 4xx/5xx 或连接错误
* 不使用 pytest：这是运维侧的"服务健康快照"，不是单测。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("[FATAL] 需要 requests：pip install requests", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINTS = ROOT / "resources" / "configs" / "api" / "endpoints.json"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# 名字上是 GET 但会打开系统窗口 / 触发副作用，safe 模式下跳过
ALWAYS_UNSAFE_OPS = {
    "generate.open_folder",
    "system.gc",
    "memory.decay", "memory.flush",
    "logger.flush", "logger.append", "logger.set_level",
    "config.reload", "config.save", "config.patch_section",
    "workspace.select", "workspace.confirm", "workspace.clear",
    "session.create", "session.delete", "session.switch",
    "session.append", "session.flush",
    "character.create", "character.update", "character.delete",
    "character.switch", "character.update_state",
    "provider.switch", "provider.stop", "provider.download",
    "service.register", "service.start", "service.stop",
    "service.update_config", "service.apply_config",
    "skill.reload", "skill.activate", "skill.deactivate", "skill.execute",
    "save.create", "save.delete", "save.toggle", "save.save", "save.load",
    "save.sync", "save.restore", "save.update_section",
    "save.snapshot", "save.snapshot_restore", "save.snapshot_preview",
    "memory.retention", "memory.pin", "memory.revive", "memory.delete",
    "generate.chat", "generate.chat_stream", "generate.tts", "generate.asr",
    "generate.image", "generate.ocr", "generate.embedding", "generate.command",
    "ppt.outline", "ppt.render", "ppt.render_async",
    "hotkeys.validate", "hotkeys.reset", "hotkeys.batch_update", "hotkeys.update",
    "task.cancel",
}

# 路径参数默认值（按 {name} 匹配）
DEFAULT_PATH_PARAMS: Dict[str, str] = {
    "type": "images",
    "section": "llm",
    "task_id": "0000000000000000",
    "slot_id": "slot_000",
    "session_id": "default",
    "character_id": "default",
    "skill_id": "echo",
    "service_id": "ppt",
    "adapter": "llm",
    "provider": "openai",
    "action": "toggle_voice",
    "file_name": "demo.pptx",
    "memory_id": "mem_000",
}

# query 默认值（按 op 精确匹配）
OP_QUERIES: Dict[str, Dict[str, Any]] = {
    "memory.layers":       {"session_id": "default", "detail_top_k": 4, "summary_limit": 4},
    "memory.short_term":   {"session_id": "default", "limit": 5},
    "memory.long_term":    {"session_id": "default", "limit": 5},
    "memory.compressed":   {"session_id": "default", "limit": 5},
    "memory.stats":        {"session_id": "default"},
    "session.messages":    {"limit": 5},
    "service.list":        {"running_only": False},
    "skill.list":          {"active_only": False},
    "logger.records":      {"limit": 5, "level": "INFO"},
    "task.get":            {"wait": False, "timeout": 1.0},
    "save.snapshot_graph": {"slot_id": ""},
    "save.snapshot_preview": {"slot_id": "", "revision": ""},
}

# body 默认值（按 op 精确匹配）
OP_BODIES: Dict[str, Dict[str, Any]] = {
    "generate.chat":        {"text": "你好", "session_id": "default"},
    "generate.chat_stream": {"text": "你好", "session_id": "default"},
    "generate.tts":         {"text": "你好"},
    "generate.asr":         {"audio": "UklGRg=="},
    "generate.image":       {"prompt": "a cat", "n": 1},
    "generate.ocr":         {"image": "iVBORw0KGgo="},
    "generate.embedding":   {"texts": ["hello"]},
    "generate.command":     {"text": "skill --id weather"},
    "session.create":       {"name": "test-session"},
    "session.append":       {"role": "user", "content": "hi"},
    "character.create":     {"id": "test-char", "name": "Test"},
    "character.update":     {"name": "Test2"},
    "character.update_state": {"mood": 4, "affection": 60},
    "skill.execute":        {"params": {}},
    "config.patch_section": {"values": {"model": "test"}},
    "provider.switch":      {"provider": "openai"},
    "service.start":        {"kwargs": {}},
    "service.update_config": {"config": {}},
    "memory.search":        {"query": "test", "top_k": 4, "session_id": "default"},
    "memory.retention":     {"memory_id": "mem_000", "session_id": "default", "dry_run": True},
    "memory.pin":           {"memory_id": "mem_000", "session_id": "default", "pinned": True},
    "memory.revive":        {"memory_id": "mem_000", "session_id": "default", "dry_run": True},
    "hotkeys.validate":     {"combo": "Ctrl+Shift+A", "action": "toggle_voice"},
    "hotkeys.update":       {"combo": "Ctrl+Shift+A"},
    "hotkeys.batch_update": {"bindings": {}},
    "logger.set_level":     {"level": "INFO"},
    "logger.append":        {"records": []},
    "ppt.outline":          {"topic": "Demo", "pages": 3},
    "ppt.render":           {"topic": "Demo", "pages": 3},
    "ppt.render_async":     {"topic": "Demo", "pages": 3},
    "task.cancel":          {"reason": "test"},
    "workspace.select":     {"root": "C:\\temp", "mode": "writable"},
    "workspace.confirm":    {"confirmation_id": "test"},
    "save.create":          {"name": "test-slot"},
    "save.update_section":  {"data": {}},
    "save.sync":            {"session_id": "default"},
    "save.snapshot_preview": {"slot_id": "", "revision": ""},
    "save.snapshot":        {"slot_id": "", "trigger": "test", "label": "test"},
    "save.snapshot_restore": {"slot_id": "", "revision": ""},
}


def load_endpoints(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text("utf-8"))
    items = raw.get("endpoints", []) if isinstance(raw, dict) else raw
    return [s for s in items if s.get("enabled", True)]


def fill_path(path: str) -> str:
    for name, value in DEFAULT_PATH_PARAMS.items():
        path = path.replace("{" + name + "}", value)
    return path


def is_unsafe(spec: Dict[str, Any]) -> bool:
    if spec["op"] in ALWAYS_UNSAFE_OPS:
        return True
    method = ((spec.get("http") or {}).get("method") or "GET").upper()
    return method not in SAFE_METHODS


def run_one(session: requests.Session, base: str, spec: Dict[str, Any],
            timeout: float, verbose: bool) -> Dict[str, Any]:
    op = spec["op"]
    http = spec.get("http")
    if not http:
        return {"op": op, "status": "SKIP", "reason": "no http"}

    method = http["method"].upper()
    path = fill_path(http["path"])
    url = base.rstrip("/") + "/api" + path
    query = OP_QUERIES.get(op, {})
    body = OP_BODIES.get(op)

    started = time.time()
    try:
        resp = session.request(method, url, params=query, json=body, timeout=timeout)
        elapsed = (time.time() - started) * 1000.0
    except Exception as exc:
        return {"op": op, "method": method, "path": path, "status": "FAIL",
                "error": f"{type(exc).__name__}: {exc}"}

    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text[:200]}

    ok = isinstance(payload, dict) and bool(payload.get("ok"))
    code = payload.get("code") if isinstance(payload, dict) else None

    if resp.status_code >= 400:
        status = "FAIL"
    elif ok:
        status = "PASS"
    else:
        # 2xx 但 ok=false：业务拒绝（未初始化 / 缺参数等），路由本身是通的
        status = "WARN"

    result = {
        "op": op, "method": method, "path": path,
        "http": resp.status_code, "code": code, "ok": ok,
        "status": status, "elapsed_ms": round(elapsed, 1),
    }
    if verbose:
        result["query"] = query
        result["body"] = body
        result["response"] = payload
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="服务地址")
    ap.add_argument("--endpoints", default=str(DEFAULT_ENDPOINTS))
    ap.add_argument("--group", action="append", help="只测指定分组（可多次）")
    ap.add_argument("--op", action="append", help="只测指定 op（可多次）")
    ap.add_argument("--all", action="store_true", help="包含写操作（会改数据）")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = ap.parse_args()

    path = Path(args.endpoints)
    if not path.exists():
        print(f"[FATAL] endpoints.json 不存在: {path}", file=sys.stderr)
        return 2

    specs = load_endpoints(path)
    selected: List[Dict[str, Any]] = []
    for spec in specs:
        tags = spec.get("tags") or []
        if args.group and not any(g in args.group for g in tags):
            continue
        if args.op and spec["op"] not in args.op:
            continue
        if not args.all and is_unsafe(spec):
            continue
        selected.append(spec)

    if not selected:
        print("[WARN] 没有匹配的端点", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    # 探活
    try:
        r = session.get(args.base.rstrip("/") + "/api/system/ping", timeout=5)
        if r.status_code >= 400:
            print(f"[WARN] ping 返回 {r.status_code}，继续尝试", file=sys.stderr)
    except Exception as exc:
        print(f"[FATAL] 无法连接 {args.base}: {exc}", file=sys.stderr)
        return 2

    results: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for spec in selected:
        res = run_one(session, args.base, spec, args.timeout, args.verbose)
        results.append(res)
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if args.verbose and not args.json:
            print(f"{res['status']:4} {res.get('method',''):6} "
                  f"{res.get('path',''):40} http={res.get('http','')} "
                  f"code={res.get('code','')}")

    if args.json:
        print(json.dumps({"base": args.base, "counts": counts, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print()
        print(f"共 {len(results)} 个端点："
              f"PASS={counts.get('PASS',0)} "
              f"FAIL={counts.get('FAIL',0)} "
              f"WARN={counts.get('WARN',0)} "
              f"SKIP={counts.get('SKIP',0)}")
        fails = [r for r in results if r["status"] == "FAIL"]
        if fails:
            print("\n失败列表：")
            for r in fails:
                reason = r.get("error") or f"http={r.get('http')} code={r.get('code')}"
                print(f"  - {r['op']}: {reason}")

    return 0 if counts.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())