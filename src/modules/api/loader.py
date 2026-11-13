"""加载 endpoints.json → 注册 gateway op + 生成 FastAPI router。"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import typing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from fastapi import APIRouter

from ..runtime import StandardPaths
from ..logger import logger
from .exceptions import ApiError
from .registry import EndpointSpec, resolve_handler


def _default_api_config_dir() -> str:
    env = os.environ.get("API_CONFIG_DIR")
    if env:
        return env
    try:
        from ..runtime import StandardPaths

        candidate = StandardPaths.get_resources_dir() / "config" / "api"
        if (candidate / "endpoints.json").exists():
            return str(candidate)
    except Exception:  # noqa: BLE001
        pass
    return "config/api"  # 兼容打包后的相对布局


class EndpointLoader:
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir or _default_api_config_dir())
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
        path= StandardPaths.get_configs_dir() / "api" / "groups.json"
        if path.exists():
            try:
                self.groups = json.loads(path.read_text("utf-8"))
            except Exception as e:
                logger.warning(f"[API] groups.json 解析失败: {e}")

    def _load_endpoints(self) -> None:
        path= StandardPaths.get_configs_dir() / "api" / "endpoints.json"
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
        """生成 desktop bridge 的契约适配入口（api.md §2.1 / §4.3 P1）。

        HTTP 由 FastAPI 负责「path/query/body → handler 参数」的绑定；
        bridge 只拿到一个平铺 dict（pathParams + query + body），过去直接
        塞给期望 Pydantic DTO 的 handler，必然 AttributeError → 3001。
        这里按 `EndpointSpec` + handler 注解做同一套绑定，两端语义一致。
        """

        async def entry(payload: Optional[Dict[str, Any]] = None):
            kwargs = _build_handler_kwargs(fn, spec, payload or {})
            return await _dispatch_handler(fn, kwargs, spec.dispatch)

        entry.__name__ = "op_" + re.sub(r"\W", "_", spec.op)
        entry.__doc__ = f"bridge op {spec.op}"
        return entry

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
                tags=spec.tags or ["default"], # type:ignore
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


_PAYLOAD_PARAM_NAMES = frozenset({
    "payload", "body", "data", "req", "request", "params", "payload_dict",
})


def _unwrap_model(annotation: Any) -> Any:
    """Optional[X] / X | None → X。"""
    args = getattr(annotation, "__args__", None)
    if args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _build_handler_kwargs(
    fn: Callable, spec: EndpointSpec, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """把平铺 payload 绑定成 handler 的具名参数（含 Pydantic DTO 构造）。"""
    from pydantic import BaseModel

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {}
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001
        hints = {}

    http_path = spec.http.path if spec.http is not None else ""
    path_names = set(re.findall(r"\{(\w+)\}", http_path))
    kwargs: Dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = hints.get(name, param.annotation)
        model = _unwrap_model(annotation)

        if isinstance(model, type) and issubclass(model, BaseModel):
            raw = payload.get(name)
            if isinstance(raw, model):
                kwargs[name] = raw
                continue
            if isinstance(raw, dict):
                data = raw
            else:
                # body 字段被前端平铺进 payload：只取模型声明过的字段
                fields = getattr(model, "model_fields", {}) or {}
                data = {k: v for k, v in payload.items() if k in fields}
            try:
                kwargs[name] = model.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                raise ApiError.bad_request(f"请求体校验失败: {exc}")
            continue

        if name in payload:
            kwargs[name] = payload[name]
        elif name in path_names:
            raise ApiError.bad_request(f"缺少路径参数 {name}")
        elif param.default is inspect.Parameter.empty:
            raise ApiError.bad_request(f"缺少参数 {name}")
        # 其余可选参数用 handler 自身默认值，不显式传
    return kwargs


async def _dispatch_handler(
    fn: Callable, kwargs: Dict[str, Any], dispatch: str
) -> Any:
    """按 dispatch 执行；异步 handler 内部已用 to_thread/调度器卸载重活。"""
    if dispatch == "main":
        from ..ui.dispatcher import get_main_thread_dispatcher

        dispatcher = get_main_thread_dispatcher()
        return await dispatcher.run_async_on_main_thread(lambda: fn(**kwargs))

    if dispatch == "thread" and not inspect.iscoroutinefunction(fn):
        return await asyncio.to_thread(fn, **kwargs)

    result = fn(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


_loader: Optional[EndpointLoader] = None


def get_loader() -> EndpointLoader:
    global _loader
    if _loader is None:
        _loader = EndpointLoader()
    return _loader