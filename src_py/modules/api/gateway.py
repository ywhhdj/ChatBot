"""进程内 API 网关。

修复对应清单：K9–K16

为什么需要它
────────────
桌面端（qtwebview2）与 Web 端（uvicorn）**必须调用同一批处理函数**，
否则会出现两份实现、两套返回格式，前端要写两套解析。

更关键的是桌面端：它走 JS Bridge 进程内调用，**不需要经过 HTTP**。
原来 `run()` 无条件 `run_web()`，桌面端每次操作都要
"JS → 本地回环 → uvicorn → 控制器 → 回来"，白白多一次序列化与线程切换。

网关把处理函数抽成一张 op 表：

    desktop: JS → Bridge → gateway.call(op)              ← 进程内，零网络
    web:     HTTP → controller → gateway.call(op)        ← 同一 op、同一返回

两端拿到的信封完全一致：
`{"ok","code","message","data","request_id","ts"}`。

协程怎么跑
──────────
* **有运行中 loop**（HTTP 控制器）：直接 `await handler`
* **没有 loop**（Bridge 在调度器线程）：投递到调度器自有 loop，
  `wrap_future` 等待 —— 复用已有 loop，**不新建销毁**
  （原实现每次调用 `new_event_loop()` + `run_until_complete`，开销大且不安全）
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..logger import logger
from .response import (
    CODE_INTERNAL,
    ApiError,
    error_body,
    get_request_id,
    new_request_id,
    set_request_id,
    success,
)

from .. import runtime

Handler = Callable[..., Any]


class ApiGateway:
    """op → handler 注册表，统一信封输出。"""

    def __init__(self) -> None:
        self._ops: Dict[str, Handler] = {}
        self._lock = threading.RLock()

    # ---------- 注册 ----------

    def register(self, op: str, handler: Handler, *, overwrite: bool = False) -> None:
        if not op:
            raise ValueError("op is required")
        with self._lock:
            if op in self._ops and not overwrite:
                logger.warning(f"[Gateway] op 重复注册，已忽略: {op}")
                return
            self._ops[str(op)] = handler
        logger.debug(f"[Gateway] registered: {op}")

    def register_many(self, mapping: Dict[str, Handler]) -> None:
        for op, fn in (mapping or {}).items():
            self.register(op, fn)

    def unregister(self, op: str) -> None:
        with self._lock:
            self._ops.pop(str(op), None)

    def has(self, op: str) -> bool:
        with self._lock:
            return str(op) in self._ops

    def ops(self) -> list:
        with self._lock:
            return sorted(self._ops)

    def _handler(self, op: str) -> Optional[Handler]:
        with self._lock:
            return self._ops.get(str(op))

    # ---------- 调用 ----------

    async def call(
        self,
        op: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """统一入口。**恒返回 dict 信封**，绝不为 None。"""
        rid = request_id or new_request_id()
        token = set_request_id(rid)
        try:
            return await self._invoke(op, payload or {}, rid)
        finally:
            # 复位 contextvar，避免污染同一线程上的后续调用
            try:
                set_request_id(token)  # type: ignore[arg-type]
            except Exception:
                pass

    async def _invoke(self, op: str, payload: Dict[str, Any], rid: str) -> Dict[str, Any]:
        handler = self._handler(op)
        if handler is None:
            return error_body(ApiError(f"未知接口: {op}", code=1002), rid)

        try:
            result = await _call_handler(handler, payload)
        except ApiError as exc:
            return error_body(exc, rid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Gateway] op {op} 失败: {exc}")
            return error_body(ApiError(str(exc), code=CODE_INTERNAL), rid)

        return _ok(result, rid)

    # ---------- 同步入口（无 loop 的线程用） ----------

    def call_sync(
        self,
        op: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
        *,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在**没有运行中 loop 的线程**里调用（如调度器线程）。

        优先投递到任务调度器自有 loop；调度器不可用时才退化到临时 loop。
        """
        rid = request_id or new_request_id()
        schedular = _try_get_schedular()
        if schedular is not None:
            try:
                fut = schedular.run_coroutine(self.call(op, payload, request_id=rid))
                return asyncio.wrap_future(fut).result() if False else fut.result(timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[Gateway] 调度器执行 {op} 失败，退化临时 loop: {exc}")

        # 退化：临时 loop（仅用于轻量 op）
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.call(op, payload, request_id=rid))
        finally:
            try:
                loop.close()
            except Exception:
                pass

    # ---------- 元数据 ----------

    def describe(self) -> Dict[str, Any]:
        ops = []
        for op in self.ops():
            h = self._handler(op)
            ops.append({
                "op": op,
                "async": inspect.iscoroutinefunction(h),
                "doc": (inspect.getdoc(h) or "").split("\n")[0],
            })
        return {
            "total": len(ops),
            "ops": ops
        }


# --------------------------------------------------------------------------
# 内部辅助
# --------------------------------------------------------------------------

async def _call_handler(handler: Handler, payload: Dict[str, Any]) -> Any:
    """按 handler 签名调用：支持 (payload) / (**payload) / ()。"""
    if not inspect.iscoroutinefunction(handler):
        result = _call_plain(handler, payload)
        if inspect.isawaitable(result):
            result = await result
        return result

    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        sig = None

    if sig is not None and _accepts_payload(sig):
        result = handler(_coerce(handler, sig, payload))
    elif sig is not None and _accepts_kwargs(sig):
        result = handler(**payload)
    else:
        result = handler()

    if inspect.isawaitable(result):
        result = await result
    return result


def _call_plain(handler: Handler, payload: Dict[str, Any]) -> Any:
    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler()
    if _accepts_payload(sig):
        return handler(_coerce(handler, sig, payload))
    if _accepts_kwargs(sig):
        return handler(**payload)
    return handler()


# 这些名字表示"整个请求体"，应该按位置传，不能拆成关键字
_PAYLOAD_NAMES = {
    "payload",
    "body",
    "data",
    "req",
    "request",
    "params",
    "payload_dict"
}


def _coerce(handler: Handler, sig: inspect.Signature, payload: Any) -> Any:
    """把 dict 转成 handler 注解要求的 pydantic 模型。

    HTTP 层由 FastAPI 做这件事；网关直连时没人做 ——
    直接把 dict 传给 `async def outline(payload: PptOutlineRequest)`，
    控制器里 `payload.topic` 立刻 AttributeError，
    被兜底成 500（3001），真正的校验错误码 1001 反而丢了。

    注意：控制器普遍开了 `from __future__ import annotations`，
    `inspect.signature` 拿到的是**字符串** `'Optional[PptOutlineRequest]'`，
    必须用 `typing.get_type_hints()` 解析才能拿到真实类型。
    """
    if not isinstance(payload, dict):
        return payload

    hints = _type_hints(handler)
    for p in sig.parameters.values():
        if p.name.lower() not in _PAYLOAD_NAMES:
            continue
        annotation = hints.get(p.name, p.annotation)
        model = _unwrap_optional(annotation)
        if model is None:
            return payload
        try:
            from pydantic import BaseModel

            if isinstance(model, type) and issubclass(model, BaseModel):
                return model.model_validate(payload)
        except Exception:  # noqa: BLE001
            return payload
        return payload
    return payload


_HINTS_CACHE: Dict[int, Dict[str, Any]] = {}


def _type_hints(handler: Handler) -> Dict[str, Any]:
    """带缓存的 get_type_hints（解析失败时返回空 dict，不影响主流程）。"""
    key = id(handler)
    if key in _HINTS_CACHE:
        return _HINTS_CACHE[key]
    hints: Dict[str, Any] = {}
    try:
        import typing

        hints = typing.get_type_hints(handler)
    except Exception:  # noqa: BLE001
        hints = {}
    _HINTS_CACHE[key] = hints
    return hints


def _unwrap_optional(annotation: Any) -> Any:
    """Optional[X] / X | None → X。"""
    if annotation is inspect.Parameter.empty or annotation is None:
        return None
    args = getattr(annotation, "__args__", None)
    if args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _accepts_payload(sig: inspect.Signature) -> bool:
    """存在名为 payload/body/... 的位置参数 → 整体传入。

    不能只看"有默认值就拆关键字"：`async def outline(payload=None)`
    有默认值，但语义是"接整个请求体"。按 `**payload` 拆开会
    TypeError（unexpected keyword argument），被兜底成 500。
    """
    return any(
        p.name.lower() in _PAYLOAD_NAMES
        and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        for p in sig.parameters.values()
    )


def _accepts_kwargs(sig: inspect.Signature) -> bool:
    """参数可直接用 payload 的字段填充（如 `character_id: str`）。"""
    has_payload = _accepts_payload(sig)
    for p in sig.parameters.values():
        if p.name.lower() in _PAYLOAD_NAMES and has_payload:
            continue
        if p.kind in (p.VAR_KEYWORD, p.KEYWORD_ONLY):
            return True
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY) \
                and p.default is not p.empty:
            return True
    return False


def _ok(rid: str, data: Any) -> Dict[str, Any]:
    """把 handler 返回值统一成信封。

    handler 可能返回：
      * `ApiResponse`（pydantic）→ 直接 model_dump，保留其 request_id
      * 裸数据 → 包一层
    """
    if isinstance(data, dict) and {"ok", "code", "message"} <= set(data):
        data.setdefault("request_id", rid)
        data.setdefault("ts", time.time())
        return data
    return success(
        data,
        request_id=rid,
        ts=time.time(),
    ).model_dump()


def _try_get_schedular():
    try:
        from .. import runtime

        if getattr(runtime.manager.task_manager, "is_runing", False):
            return runtime.manager.task_manager  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------
# 单例
# --------------------------------------------------------------------------
_gateway: Optional[ApiGateway] = None
_gw_lock = threading.Lock()


def get_gateway() -> ApiGateway:
    global _gateway
    if _gateway is None:
        with _gw_lock:
            if _gateway is None:
                _gateway = ApiGateway()
    return _gateway


def register_op(op: str, handler: Handler, *, overwrite: bool = False) -> None:
    get_gateway().register(op, handler, overwrite=overwrite)


def register_ops(mapping: Dict[str, Handler]) -> None:
    get_gateway().register_many(mapping)


async def call(
    op: str,
    payload: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await get_gateway().call(op, payload, request_id=request_id)


def call_sync(
    op: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 60.0
) -> Dict[str, Any]:
    return get_gateway().call_sync(op, payload, timeout=timeout)


__all__ = [
    "ApiGateway",
    "get_gateway",
    "register_op",
    "register_ops",
    "call",
    "call_sync",
]
