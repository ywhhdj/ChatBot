"""加载 endpoints.json → 注册 gateway op + 生成 FastAPI router。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter

from ..logger import logger
from .registry import EndpointSpec, resolve_handler


class EndpointLoader:
    def __init__(self, config_dir: str = "config/api"):
        self.config_dir = Path(config_dir)
        self.specs: List[EndpointSpec] = []
        self.groups: Dict[str, Any] = {}
        self._loaded = False

    # ---------- 加载 ----------

    def load(self) -> None:
        if self._loaded:
            return
        self._load_groups()
        self._load_endpoints()
        self._validate()
        self._loaded = True
        logger.info(f"[API] 已加载 {len(self.specs)} 个端点配置")

    def _load_groups(self) -> None:
        path = self.config_dir / "groups.json"
        if path.exists():
            try:
                self.groups = json.loads(path.read_text("utf-8"))
            except Exception as e:
                logger.warning(f"[API] groups.json 解析失败: {e}")

    def _load_endpoints(self) -> None:
        path = self.config_dir / "endpoints.json"
        if not path.exists():
            logger.warning(f"[API] endpoints.json 不存在: {path}，使用空清单")
            return
        raw = json.loads(path.read_text("utf-8"))
        items = raw.get("endpoints", []) if isinstance(raw, dict) else raw
        self.specs = [EndpointSpec(**e) for e in items if e.get("enabled", True)]

    def _validate(self) -> None:
        """启动即校验：handler 必须能 import，path 不能重复。"""
        seen: Dict[str, str] = {}
        for spec in self.specs:
            try:
                resolve_handler(spec.handler)
            except Exception as e:
                raise RuntimeError(f"[API] 端点 {spec.op} 的 handler 解析失败: {e}") from e
            if spec.http is not None:
                key = f"{spec.http.method.upper()} {spec.http.path}"
                if key in seen:
                    raise RuntimeError(f"[API] 路由冲突: {key}（{seen[key]} vs {spec.op}）")
                seen[key] = spec.op

    # ---------- 网关注册 ----------

    def register_gateway(self) -> int:
        self.load()
        from .gateway import register_op

        count = 0
        for spec in self.specs:
            if not spec.desktop:
                continue
            fn = resolve_handler(spec.handler)
            wrapped = self._wrap(fn, spec)
            register_op(spec.op, wrapped, overwrite=True)
            count += 1
        return count

    def _wrap(self, fn: Callable, spec: EndpointSpec) -> Callable:
        """按 dispatch 包装 handler，让调度器/线程池/主线程派发对业务透明。"""
        if spec.dispatch == "thread":
            async def _thread(payload=None):
                import asyncio
                return await asyncio.to_thread(_call_handler_sync, fn, payload)
            return _thread

        if spec.dispatch == "main":
            async def _main(payload=None):
                from ..ui.dispatcher import run_in_main_thread  # 你自己的派发器
                return await run_in_main_thread(lambda: _call_handler_sync(fn, payload))
            return _main

        return fn  # loop：网关本身已在调度器 loop 里跑

    # ---------- HTTP 路由 ----------

    def build_router(self) -> APIRouter:
        self.load()
        router = APIRouter()
        for spec in self.specs:
            if spec.http is None:
                continue
            fn = resolve_handler(spec.handler)
            router.add_api_route(
                spec.http.path,
                fn,
                methods=[spec.http.method.upper()],
                status_code=spec.http.status_code,
                tags=spec.tags or ["default"],
                summary=spec.http.summary or spec.meta.get("label", ""),
                deprecated=spec.http.deprecated,
                name=spec.op,
            )
        return router

    # ---------- 查询（给 catalog 用） ----------

    def by_tag(self) -> Dict[str, List[EndpointSpec]]:
        out: Dict[str, List[EndpointSpec]] = {}
        for spec in self.specs:
            for t in (spec.tags or ["default"]):
                out.setdefault(t, []).append(spec)
        return out


def _call_handler_sync(fn: Callable, payload: Any) -> Any:
    """thread/main 分支：把 handler 当同步函数调，兼容 dict / pydantic。"""
    import inspect
    if inspect.iscoroutinefunction(fn):
        import asyncio
        return asyncio.run(fn() if payload is None else fn(payload))
    try:
        return fn() if payload is None else fn(payload)
    except TypeError:
        return fn(**payload) if isinstance(payload, dict) else fn()


_loader: Optional[EndpointLoader] = None


def get_loader() -> EndpointLoader:
    global _loader
    if _loader is None:
        _loader = EndpointLoader(os.getenv("API_CONFIG_DIR", "config/api"))
    return _loader