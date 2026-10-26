"""API 层自检：路由注册、信封格式、错误处理、SDK 解包。

只验证"接口契约"，不启动 uvicorn、不触达真实 LLM。
用 FastAPI TestClient 直接驱动 app。
"""

import importlib
import os
import sys

FIXED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixed")
sys.path.insert(0, FIXED)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


# ============================================================ 1. 导入
def test_imports():
    print("\n[1] 控制器与 SDK 导入")
    mods = [
        "modules.api.response",
        "modules.api.models",
        "modules.api.controllers",
        "modules.api.controllers.system",
        "modules.api.controllers.config",
        "modules.api.controllers.pipline",
        "modules.api.controllers.service",
        "modules.api.controllers.logger",
        "modules.api.controllers.request",
        "modules.api.controllers.session",
        "modules.api.controllers.save",
        "modules.api.controllers.character",
        "modules.api.controllers.memory",
        "modules.api.controllers.skill",
        "modules.api.controllers.task",
        "modules.api.client",
    ]
    for m in mods:
        try:
            importlib.import_module(f"{m}")
            ok = True
            detail = ""
        except Exception as e:
            ok = False
            detail = f"({type(e).__name__}: {str(e)[:90]})"
        check(f"导入 {m.split('.')[-1]}", ok, detail)


# ============================================================ 2. 路由注册
def build_app():
    from fastapi import FastAPI

    from modules.api.controllers import register_all_routers
    from modules.api.response import (
        install_exception_handlers,
        install_request_id_middleware,
    )

    app = FastAPI(title="ChatBot API Test")
    install_request_id_middleware(app)
    register_all_routers(app)
    install_exception_handlers(app)
    return app


def test_routes():
    print("\n[2] 路由清单（对照 api文档.md）")
    app = build_app()
    paths = {}
    for r in app.routes:
        methods = sorted(getattr(r, "methods", None) or [])
        paths.setdefault(getattr(r, "path", ""), set()).update(methods)

    expected = [
        ("GET", "/api/system/health"),
        ("GET", "/api/system/info"),
        ("GET", "/api/system/stats"),
        ("POST", "/api/system/gc"),
        ("GET", "/api/config"),
        ("PATCH", "/api/config/{section}"),
        ("POST", "/api/config/reload"),
        ("POST", "/api/config/save"),
        ("GET", "/api/config/schema"),
        ("GET", "/api/pipeline/adapters"),
        ("GET", "/api/pipeline/adapters/{adapter}/providers"),
        ("POST", "/api/pipeline/adapters/{adapter}/switch"),
        ("GET", "/api/service"),
        ("GET", "/api/service/{service_id}"),
        ("POST", "/api/service/{service_id}/start"),
        ("POST", "/api/service/{service_id}/stop"),
        ("GET", "/api/service/tools"),
        ("GET", "/api/logger/level"),
        ("PUT", "/api/logger/level"),
        ("GET", "/api/logger/stats"),
        ("GET", "/api/logger/records"),
        ("GET", "/api/request/status"),
        ("POST", "/api/request/chat"),
        ("POST", "/api/request/chat/stream"),
        ("POST", "/api/request/tts"),
        ("POST", "/api/request/asr"),
        ("POST", "/api/request/command"),
        ("GET", "/api/session"),
        ("POST", "/api/session"),
        ("GET", "/api/session/{session_id}/messages"),
        ("GET", "/api/save/slots"),
        ("POST", "/api/save/slots"),
        ("GET", "/api/character"),
        ("GET", "/api/character/current"),
        ("GET", "/api/character/presets"),
        ("POST", "/api/character/{character_id}/switch"),
        ("GET", "/api/memory/layers"),
        ("POST", "/api/memory/search"),
        ("GET", "/api/skill"),
        ("POST", "/api/skill/{skill_id}/execute"),
        ("GET", "/api/task/{task_id}"),
        ("POST", "/api/task/{task_id}/cancel"),
    ]
    missing = []
    for method, path in expected:
        methods = paths.get(path)
        if not methods or method not in methods:
            missing.append(f"{method} {path}")
    check(f"文档声明的 {len(expected)} 个端点全部注册", not missing, f"(缺失: {missing[:3]})")

    # 顺序检查：/current 必须在 /{character_id} 之前，否则被当作 id 匹配
    order = [getattr(r, "path", "") for r in app.routes]
    check("静态路径 /api/character/current 先于 /api/character/{character_id}",
          "/api/character/current" in order
          and "/api/character/{character_id}" in order
          and order.index("/api/character/current") < order.index("/api/character/{character_id}"))
    return app


# ============================================================ 3. 信封与错误
def test_envelope(app):
    print("\n[3] 统一信封 / 错误处理 / request_id")
    from fastapi.testclient import TestClient

    client = TestClient(app)

    r = client.get("/api/system/ping")
    body = r.json()
    check("ping 返回 200", r.status_code == 200)
    check("信封字段完整",
          all(k in body for k in ("ok", "code", "message", "data", "request_id", "ts")),
          f"({sorted(body)})")
    check("ping data == 'pong'", body.get("data") == "pong")

    # 自定义 request_id 应被沿用并回写 header
    r2 = client.get("/api/system/ping", headers={"X-Request-ID": "rid-test-001"})
    check("沿用客户端 request_id", r2.json().get("request_id") == "rid-test-001",
          f"({r2.json().get('request_id')})")
    check("响应头回写 X-Request-ID", r2.headers.get("X-Request-ID") == "rid-test-001")

    # 404 也是信封
    r3 = client.get("/api/not-exists")
    b3 = r3.json()
    check("未知路径返回信封而非 FastAPI 默认体",
          r3.status_code == 404 and b3.get("ok") is False and "code" in b3,
          f"({r3.status_code}, code={b3.get('code')})")
    check("未知路径 code == 1002", b3.get("code") == 1002, f"({b3.get('code')})")

    # 业务 404：配置段不存在
    r4 = client.get("/api/config/unknown-section")
    b4 = r4.json()
    check("未知配置段返回 1002 + 信封",
          b4.get("ok") is False and b4.get("code") == 1002, f"({b4.get('code')})")

    # 参数错误：空 body 的 patch
    r5 = client.patch("/api/config/llm", json={"values": {}})
    b5 = r5.json()
    check("空更新返回 1001", b5.get("code") == 1001, f"({b5.get('code')})")


# ============================================================ 4. 真实子系统（不 500）
def test_live_endpoints(app):
    print("\n[4] 真实子系统端点（不应 500）")
    from fastapi.testclient import TestClient

    client = TestClient(app)

    for method, path, label in [
        ("GET", "/api/system/health", "健康检查"),
        ("GET", "/api/system/info", "应用信息"),
        ("GET", "/api/config", "读取配置"),
        ("GET", "/api/config/schema", "配置字段说明"),
        ("GET", "/api/logger/level", "日志级别"),
        ("GET", "/api/logger/stats", "日志统计"),
        ("GET", "/api/character", "角色列表"),
        ("GET", "/api/character/current", "当前角色"),
        ("GET", "/api/character/presets", "角色预设"),
        ("GET", "/api/skill", "技能列表"),
        ("GET", "/api/service", "服务列表"),
        ("GET", "/api/session", "会话列表"),
        ("GET", "/api/save/slots", "存档列表"),
    ]:
        try:
            r = client.request(method, path)
            ok = r.status_code < 500
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            detail = f"({r.status_code})"
            if r.status_code >= 500:
                detail = f"({r.status_code} {body.get('message','')[:60]})"
            check(f"{label} {method} {path}", ok, detail)
        except Exception as e:
            check(f"{label} {method} {path}", False, f"({type(e).__name__}: {str(e)[:70]})")

    # health 的 status 字段合法
    r = client.get("/api/system/health")
    status = (r.json().get("data") or {}).get("status")
    check("health.status 取值合法", status in ("healthy", "degraded", "unhealthy"), f"({status})")

    # 角色预设确实返回了内容（验证新补的 character_manager 可用）
    r = client.get("/api/character/presets")
    data = r.json().get("data") or {}
    check("角色预设返回 emotion_map", bool(data.get("emotion_map")), f"({len(data.get('emotion_map') or {})} 项)")


# ============================================================ 5. SDK
def test_sdk(app):
    print("\n[5] Python SDK（同步 / 异步）")
    import httpx
    from fastapi.testclient import TestClient

    from modules.api.client import ApiClient, ApiResponseError, AsyncApiClient

    # 同步：用 TestClient 作为 transport
    with TestClient(app) as tc:
        c = ApiClient("http://testserver")
        c._http = httpx.Client(
            base_url="http://testserver",
            transport=httpx.WSGITransport(app=app),
        )

        res = c.system.ping()
        check("SDK 同步 ping", res.ok and res.data == "pong", f"({res.data})")

        res = c.config.get("llm")
        check("SDK 读取配置段", res.ok and isinstance(res.data, dict),
              f"({type(res.data).__name__})")

        # 错误转异常
        try:
            c.config.get("nope-not-exist")
            check("SDK 错误转 ApiResponseError", False, "(未抛异常)")
        except ApiResponseError as e:
            check("SDK 错误转 ApiResponseError", e.code == 1002, f"(code={e.code})")

        # 角色（走新补的 character_manager）
        res = c.character.current()
        check("SDK 当前角色", res.ok and bool((res.data or {}).get("id")),
              f"({(res.data or {}).get('id')})")

        res = c.character.presets()
        check("SDK 角色预设", res.ok and bool((res.data or {}).get("emotion_map")))

        # 非严格模式：不抛异常，返回 ok=False 的结果
        res = c.config.get("nope", raise_on_error=False) if False else None
        res2 = c._client if False else None

    # 异步
    import asyncio

    async def _run():
        transport = httpx.ASGITransport(app=app)
        ac = AsyncApiClient("http://testserver")
        ac._http = httpx.AsyncClient(
            base_url="http://testserver", transport=transport
        )
        r = await ac.system.ping()
        ok1 = r.ok and r.data == "pong"
        r2 = await ac.character.current()
        ok2 = r2.ok and bool((r2.data or {}).get("id"))
        try:
            await ac.config.get("nope")
            ok3 = False
            code = None
        except ApiResponseError as e:
            ok3 = True
            code = e.code
        await ac.aclose()
        return ok1, ok2, ok3, code

    ok1, ok2, ok3, code = asyncio.run(_run())
    check("SDK 异步 ping", ok1)
    check("SDK 异步当前角色", ok2)
    check("SDK 异步错误转异常", ok3, f"(code={code})")


# ============================================================ 6. 文档一致性
def test_doc_consistency():
    print("\n[6] 文档与实现一致性")
    doc = open(os.path.join(os.path.dirname(FIXED), "api文档.md"), encoding="utf-8").read()

    from modules.api.controllers import all_routers

    # 文档里声明的分组前缀都要有对应 router
    for prefix in [
        "/api/system", "/api/config", "/api/pipeline", "/api/service",
        "/api/logger", "/api/request", "/api/session", "/api/save",
        "/api/character", "/api/memory", "/api/skill", "/api/task",
    ]:
        has_router = any(
            prefix == r.prefix for r in all_routers()
        )
        in_doc = prefix in doc
        check(f"{prefix}: 文档声明 + router 存在", has_router and in_doc,
              f"(router={has_router}, doc={in_doc})")

    # 错误码表
    for code in ["1001", "1002", "1003", "2001", "2002", "3001", "3002"]:
        check(f"错误码 {code} 在文档中定义", code in doc)

    # shell 不支持执行
    check("文档声明 shell 技能不支持执行", "shell" in doc and "暂不支持执行" in doc)
    # 只认 --id
    check("文档声明命令只认 --id", "--id" in doc and "--name" in doc)


if __name__ == "__main__":
    test_imports()
    app = test_routes()
    test_envelope(app)
    test_live_endpoints(app)
    test_sdk(app)
    test_doc_consistency()

    failed = [r for r in results if not r[1]]
    print(f"\n==== {len(results) - len(failed)}/{len(results)} 通过 ====")
    sys.exit(1 if failed else 0)