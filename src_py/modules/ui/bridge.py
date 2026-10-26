"""Python ↔ JavaScript 异步桥（qtwebview2 JS Bridge 封装）。

为什么必须"异步 + 调度器"
────────────────────────
JS 调用 Python 时，回调默认在 **UI 线程** 执行。如果处理函数里有
LLM 推理、记忆检索、文件 IO，整个窗口会冻住——背景 Live2D、托盘菜单、
16ms 派发全部停摆。

所以桥接层只做两件事：

    1. 把处理函数提交到任务调度器（调度器有独立线程 + 独立 loop）
    2. await 调度器返回的 future（不占 UI 线程、不占默认线程池）

主线程只负责"转发"，heavy work 全在调度器上跑。

版本兼容
────────
qtwebview2 v0.6（wry）：`QtWebViewWidget` + `DictJsBridge.bind_js_api_func(async_func=)`
qtwebview2 v0.5（CLR）：`QtWebView2Widget`，桥接 API 略有差异
这里统一用鸭子类型适配，两个版本都能跑。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from typing import Any, Awaitable, Callable, Dict, Optional

from ..logger import logger
from ..core.native import get_scheduler

# 桥接方法在 JS 侧的挂载名：window.qtwebview.api.<name>()
JS_API_NAMESPACE = "qtwebview"


class JsApiBridge:
    """注册 Python 处理函数，供 JS 通过 Promise 调用。

    单一入口 `call(name, payload)` 而非为每个 API 各注册一个函数：
    新增后端能力时只改 Python 侧的 handler 表，前端不用改桥接代码。
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._lock = threading.RLock()

    # ---------- 注册 ----------

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        """注册一个处理函数；可以是同步函数或协程函数。"""
        if not name:
            raise ValueError("handler name is required")
        with self._lock:
            self._handlers[str(name)] = handler
        logger.debug(f"[JsBridge] registered api: {name}")

    def register_many(self, mapping: Dict[str, Callable[..., Any]]) -> None:
        for name, fn in (mapping or {}).items():
            self.register(name, fn)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._handlers.pop(str(name), None)

    def names(self) -> list:
        with self._lock:
            return sorted(self._handlers)

    # ---------- 调度 ----------

    def _schedular(self):
        from ..core.native import get_scheduler
        return get_scheduler()

    async def _run_on_schedular(
        self,
        handler: Callable[..., Any],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Any:
        """把处理函数丢到调度器执行并 await 结果。

        无论 handler 是同步还是异步，都不占用调用方线程：
          * 同步 handler → `schedular.submit()`，走调度器的线程池
          * 异步 handler → `schedular.run_coroutine()`，走调度器 loop
        """
        schedular = self._schedular()

        if not getattr(schedular, "is_runing", False):
            logger.warning("[JsBridge] schedular not running, fallback inline")
            return await self._call_direct(handler, payload)

        if inspect.iscoroutinefunction(handler):
            coro = handler(payload)
            future = schedular.run_coroutine(coro)  # type: ignore[union-attr]
            return await asyncio.wrap_future(future)

        ref = schedular.submit(handler, timeout=timeout, payload=payload)  # type: ignore[union-attr]
        return await _await_reference(ref, timeout)

    @staticmethod
    async def _call_direct(handler: Callable[..., Any], payload: Dict[str, Any]) -> Any:
        """无调度器时直接调用（仅轻量 handler 适用）。"""
        result = handler(payload)
        if inspect.isawaitable(result):
            result = await result
        return result

    # ---------- 暴露给 JS 的方法 ----------

    async def call(
        self,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 600.0,
    ) -> Any:
        """JS 侧统一入口：`window.qtwebview.api.call(name, payload)`。

        K10/K11：**优先查进程内网关**，命中就走 gateway，
        返回与 HTTP 完全一致的信封 —— 桌面端零网络往返。
        网关没有该 op 才退回本地 handler 表。

        出错时返回 `{"ok": false, ...}` 而不是抛异常——
        异常跨 JS 边界传播会变成难懂的序列化错误。
        """
        if not name:
            return {
                "ok": False,
                "error": "missing api name"
            }

        payload = payload if isinstance(payload, dict) else (
            {} if payload is None else {"value": payload}
        )

        try:
            from ..api.gateway import get_gateway

            gw = get_gateway()
            if gw.has(name):
                return await gw.call(name, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[JsBridge] gateway call {name} failed: {exc}")
            return {
                "ok": False,
                "error": str(exc)
            }

        with self._lock:
            handler = self._handlers.get(str(name))

        if handler is None:
            return {
                "ok": False,
                "error": f"unknown api: {name}"
            }

        try:
            result = await self._run_on_schedular(handler, payload=payload, timeout=timeout)
            return {
                "ok": True,
                "data": result
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[JsBridge] api {name} failed: {exc}")
            return {
                "ok": False,
                "error": str(exc)
            }

    def ping(self) -> str:
        return "pong"

    def ready(self) -> bool:
        """前端用它判断 Python 侧是否已就绪。"""
        return True

    def api_names(self) -> list:
        return self.names()

    # ---------- 绑定到 qtwebview2 的桥对象 ----------

    def bind_to(self, js_apis_obj: Any) -> int:
        """把 `call` / `ping` / `ready` / `api_names` 绑到 qtwebview2 桥对象。

        兼容两种注册签名：

            bind_js_api_func(func, async_func=True, name="call")   # v0.6
            bind_js_api_func(func)                                 # v0.5

        返回成功绑定的方法数。
        """
        binder = getattr(js_apis_obj, "bind_js_api_func", None)
        if binder is None:
            # v0.5 也可能只接受 dict 形态
            if hasattr(js_apis_obj, "js_apis") and isinstance(
                getattr(js_apis_obj, "js_apis"), dict
            ):
                js_apis_obj.js_apis.update({
                    "call": self.call,
                    "ping": self.ping,
                    "ready": self.ready,
                    "api_names": self.api_names,
                })
                return 4
            logger.warning("[JsBridge] unsupported js bridge object")
            return 0

        bound = 0
        for name, fn in (
            ("call", self.call),
            ("ping", self.ping),
            ("ready", self.ready),
            ("api_names", self.api_names),
        ):
            if self._bind_one(binder, fn, name):
                bound += 1
        return bound

    @staticmethod
    def _bind_one(binder: Callable[..., Any], fn: Any, name: str) -> bool:
        async_hint = inspect.iscoroutinefunction(fn)
        for kwargs in (
            {"async_func": async_hint, "name": name},
            {"name": name},
            {},
        ):
            try:
                binder(fn, **kwargs)
                return True
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[JsBridge] bind {name} failed: {exc}")
                return False
        return False


async def _await_reference(ref: Any, timeout: float) -> Any:
    """await TaskReference（优先 wait_async，退化到同步等待）。"""
    scheduler = get_scheduler()
    if wait_async is not None:
        try:
            return await scheduler.wait_async(timeout=timeout)
        except TypeError:
            pass
    result = scheduler.result_of(ref)
    return result() if callable(result) else None


# --------------------------------------------------------------------------
# 单例与快捷注册
# --------------------------------------------------------------------------
_bridge: Optional[JsApiBridge] = None
_bridge_lock = threading.Lock()


def get_bridge() -> JsApiBridge:
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = JsApiBridge()
                _register_builtin_apis(_bridge)
    return _bridge


def register_api(name: str, handler: Callable[..., Any]) -> None:
    """注册一个可被前端调用的接口。"""
    get_bridge().register(name, handler)


def _register_builtin_apis(bridge: JsApiBridge) -> None:
    """内置只读接口。

    K14：这些 op 已经在 `api/ops.py` 里注册进网关，
    Bridge 的 `call()` 会优先命中网关，这里的本地实现只是**兜底**
    （网关尚未注册 / 应用未启动时）。

    不再逐条 import 控制器 —— 那会把 Bridge 和控制器硬耦合，
    且要为每个接口写一遍包装。
    """

    def _echo(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"echo": payload}

    def _gateway_ops(_payload: Dict[str, Any]) -> Dict[str, Any]:
        """列出网关全部 op，前端可据此自检可用接口。"""
        try:
            from ..api.gateway import get_gateway

            return get_gateway().describe()
        except Exception as exc:  # noqa: BLE001
            return {"total": 0, "ops": [], "error": str(exc)}

    bridge.register_many({
        "echo": _echo,
        "api.ops": _gateway_ops,
    })


def dumps(value: Any) -> str:
    """JSON 序列化（供 evaluate_js 构造脚本用）。"""
    return json.dumps(value, ensure_ascii=False, default=str)
