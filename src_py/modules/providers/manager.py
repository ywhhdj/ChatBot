"""供应商管理器：注册能力门面、切换 provider、暴露配置与用量。

并发与可用性约束
────────────────
* 切换按 capability 加锁串行化，避免两个请求同时换模型把实例状态搅乱；
* 新适配器**先构建成功再替换旧的**（entity.initialize_provider 内部实现），
  构建失败时旧 provider 继续可用，不会出现"切换失败 ⇒ 整个能力不可用"；
* ``config`` 覆盖走白名单，前端不能借 switch 接口把 base_url 改成任意地址；
* 停机时统一关闭 HTTP 连接池，不跨事件循环硬关 client。
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from ..manager.base import BaseManager
from ..events import types, on_event_class
from ..logger import logger
from ..keys import ProviderType
from . import factory
from .adapters.registry import CAPABILITIES, SECRET_KEYS

#: switch 允许覆盖的字段：凭据 + 模型 + 有限运行参数 + provider 声明过的参数。
#: 刻意**不含** base_url / chat_path / auth / headers / transport —— 这些是
#: 连接端点，只由 resources/config/providers/*.json（可信配置）决定。放开
#: base_url 等于允许前端把带密钥的请求打到任意地址（SSRF + 凭据外泄）。
#: app.conf 的覆盖走 chat._provider_kwargs，不经过这里。
_OVERRIDE_BASE = frozenset(
    SECRET_KEYS | {
        "model", 
        "model_id",
        "timeout",
        "max_retries",
        "model_dir",
        "device",
    }
)


def _capability(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _run_maybe_async(value: Any) -> Any:
    """把协程结果在同步上下文里跑完"""
    if not inspect.isawaitable(value):
        return value

    async def _await() -> Any:
        return await value

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_await())).result()


@on_event_class([
    (types.AppEventType.ManagerEventType.PIPELINE_START, "start"),
    (types.AppEventType.ManagerEventType.PIPELINE_STOP, "stop"),
])
class ProviderManager(BaseManager):
    def __init__(self):
        if self._initialized:
            return
        self._adapter_classes: Dict[str, Any] = {}
        self._current: Dict[str, Dict[str, Any]] = {}
        self._switch_locks: Dict[str, threading.RLock] = {}
        from modules.providers.adapters.downloads.service import ModelDownload
        self.download_service = ModelDownload()
        self._lock = threading.RLock()
        self._initialized = True

    # ---------- Registry ----------

    def _get_registry(self):
        return factory.get_registry()

    def load_config(self) -> bool:
        """加载/热更新 Registry。保留方法名以兼容 PIPELINE_START 事件。"""
        try:
            reg = factory.reload_registry()
            for warning in reg.warnings:
                logger.warning(f"[Providers] 配置告警: {warning}")
            caps = {c: len(reg.provider_ids(c)) for c in reg.capabilities()}
            logger.info(f"[Providers] 已加载供应商: {caps}")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Providers] 加载配置失败: {exc}")
            return False

    def start(self) -> None:
        ok = self.load_config()
        logger.info(f"[Providers] config loaded: {ok}")

    # ---------- 查询 ----------

    def get_valid_providers(self, adapter_type: Any) -> List[str]:
        return self._get_registry().provider_ids(_capability(adapter_type))

    def get_provider_names(self, adapter_type: Any) -> List[str]:
        return self.get_valid_providers(adapter_type)

    def validate_provider(self, adapter_type: Any, provider_name: str) -> bool:
        return str(provider_name) in self.get_valid_providers(adapter_type)

    def validate_model(self, adapter_type: Any, provider_name: str, model_id: Optional[str]) -> bool:
        if not model_id:
            return True
        spec = self._get_registry().spec(_capability(adapter_type), provider_name, model_id)
        return str(model_id) in spec.model_ids()

    def get_adapter_type_config(self, adapter_type: Any) -> Dict[str, Any]:
        cap = _capability(adapter_type)
        reg = self._get_registry()
        return {
            name: reg.spec(cap, name).describe()
            for name in reg.provider_ids(cap)
        }

    def get_pipeline_all_configs(self) -> Dict[str, Dict[str, Any]]:
        reg = self._get_registry()
        return {
            cap: {name: reg.spec(cap, name).describe() for name in reg.provider_ids(cap)}
            for cap in reg.capabilities()
        }

    def get_provider_config(
        self,
        adapter_type: Any,
        provider_name: str,
        model_id: Optional[str] = None,
        *,
        include_secrets: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """扁平配置。默认不含凭据，可直接返回给 API。"""
        return self._get_registry().flat_config(
            _capability(adapter_type), provider_name, model_id,
            include_secrets=include_secrets,
        )

    def get_provider_meta(
        self, adapter_type: Any, provider_name: str
    ) -> Optional[Dict[str, Any]]:
        cap = _capability(adapter_type)
        reg = self._get_registry()
        if provider_name not in reg.provider_ids(cap):
            return None
        return reg.spec(cap, provider_name).describe()

    def describe(self) -> Dict[str, Any]:
        """前端用的完整清单：可选供应商 + 当前选中 + 用量。"""
        reg = self._get_registry()
        reg.refresh()
        out: Dict[str, Any] = {}
        for cap in CAPABILITIES:
            names = reg.provider_ids(cap)
            current = dict(self._current.get(cap) or {})
            entity = self._get_adapter_manager(cap)
            usage: Dict[str, int] = {}
            if entity is not None:
                if not current.get("name"):
                    current["name"] = getattr(entity, "current_provider", "") or None
                if not current.get("model"):
                    current["model"] = getattr(entity, "current_model", None)
                snapshot = getattr(entity, "get_usage_snapshot", None)
                if callable(snapshot):
                    usage = dict(snapshot()) # type: ignore
                else:
                    provider = getattr(entity, "_provider", None)
                    getter = getattr(provider, "get_usage", None)
                    if callable(getter):
                        usage = dict(getter()) # type: ignore
            out[cap] = {
                "type": cap,
                "providers": names,
                "current": current.get("name"),
                "model": current.get("model"),
                "initialized": bool(entity is not None and entity.is_initialized),
                "usage": usage,
                "available": bool(names),
            }
        return {"adapters": out, "warnings": list(reg.warnings)}

    # ---------- 生命周期 ----------

    def _get_adapter_manager(self, adapter_type: Any) -> Optional[Any]:
        with self._lock:
            return self._adapter_classes.get(_capability(adapter_type))

    def _lock_for(self, cap: str) -> threading.RLock:
        with self._lock:
            lock = self._switch_locks.get(cap)
            if lock is None:
                lock = threading.RLock()
                self._switch_locks[cap] = lock
            return lock

    def _safe_overrides(
        self,
        cap: str,
        provider_name: str,
        config: Optional[Dict[str, Any]],
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """白名单过滤：未知字段一律拒绝，避免注入任意 URL / headers / 参数。"""
        if not config:
            return {}
        # 带上 model_id：模型级 params 只在选中模型的 spec 里，用默认 spec
        # 会把模型专属参数误判成"不允许覆盖"。
        spec = self._get_registry().spec(cap, provider_name, model_id)
        auth_field = (spec.endpoint.get("auth") or {}).get("field")
        allowed = set(_OVERRIDE_BASE) | set(spec.params.keys())
        if auth_field:
            allowed.add(str(auth_field))
        rejected = [k for k in config if k not in allowed]
        if rejected:
            raise ValueError(f"不允许覆盖的配置字段: {', '.join(sorted(rejected))}")
        return {k: v for k, v in config.items() if v is not None}

    def switch_adapter(
        self,
        adapter_type: Any,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cap = _capability(adapter_type)
        if cap not in CAPABILITIES:
            return {"success": False, "errors": [f"未知能力类型: {cap}"]}

        with self._lock_for(cap):
            try:
                entity = self._get_adapter_manager(cap)
                if entity is None:
                    return {"success": False, "errors": [f"{cap} 门面未注册"]}
                if not self.validate_provider(cap, provider_name):
                    return {
                        "success": False,
                        "errors": [
                            f"provider {provider_name} 不适用于 {cap}，可选: "
                            + ", ".join(self.get_valid_providers(cap))
                        ],
                    }
                if not self.validate_model(cap, provider_name, model_id):
                    return {
                        "success": False,
                        "errors": [f"model {model_id} 不在 {provider_name} 的模型清单中"],
                    }

                spec = self._get_registry().spec(cap, provider_name, model_id)
                flat = spec.flat(include_secrets=True)
                flat.update(self._safe_overrides(cap, provider_name, config, model_id))

                # 先构建新适配器，成功后再替换旧的（entity 内部保证）
                entity.initialize_provider(provider_name, model_id=spec.model_id, **flat)
                result = entity.init_provider_client(**flat)
                _run_maybe_async(result)

                self._current[cap] = {
                    "name": provider_name,
                    "model": spec.model_id,
                    "deployment": spec.deployment,
                }
                logger.info(
                    f"[Providers] {cap} 切换到 {provider_name}/{spec.model_id or '-'}"
                )
                return {
                    "success": True,
                    "type": cap,
                    "name": provider_name,
                    "model": spec.model_id,
                    "config": spec.flat(include_secrets=False),
                }
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[Providers] switch {cap}/{provider_name} 失败: {exc}")
                return {"success": False, "errors": [str(exc)]}

    def stop_provider(self, adapter_type: Any) -> bool:
        """停止当前 provider，但保留门面注册，之后仍可 switch 回来。"""
        cap = _capability(adapter_type)
        with self._lock_for(cap):
            entity = self._get_adapter_manager(cap)
            if entity is None:
                return False
            try:
                entity.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[Providers] 停止 {cap} 失败: {exc}")
            self._current.pop(cap, None)
            return True

    def register(self, adapter_type: Any, manager: Any) -> None:
        cap = _capability(adapter_type)
        with self._lock:
            existing = self._adapter_classes.get(cap)
            if existing is not None and existing is not manager:
                raise ValueError(f"AdapterType {cap} already registered")
            self._adapter_classes[cap] = manager

    def unregister(self, adapter_type: Any) -> None:
        cap = _capability(adapter_type)
        with self._lock:
            manager = self._adapter_classes.pop(cap, None)
        if manager is not None:
            try:
                manager.stop()
            except Exception:  # noqa: BLE001
                pass
        self._current.pop(cap, None)
    
    def get_provider_status(
        self,
        adapter_type: str,
        provider_name: str,
        model_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """describe() + 本地模型文件系统状态。前端配置页可直接消费。"""
        from .adapters.status import check_model_status
        cap = _capability(adapter_type)
        reg = self._get_registry()
        if provider_name not in reg.provider_ids(cap):
            return None
        spec = reg.spec(cap, provider_name, model_id)
        payload = spec.describe()
        payload["download_status"] = check_model_status(spec)
        return payload
    
    async def download_model(
        self,
        adapter_type: str,
        provider_name: str,
        model_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """下载本地模型。返回结构与 switch_adapter 一致。"""
        cap = _capability(adapter_type)
        reg = self._get_registry()
        if provider_name not in reg.provider_ids(cap):
            return {
                "success": False,
                "errors": [f"provider {provider_name} 不存在"]
            }

        try:
            spec = reg.spec(cap, provider_name, model_id)
        except KeyError as exc:
            return {
                "success": False,
                "errors": [str(exc)]
            }

        try:
            plan = await self.download_service.plan(spec)
        except ValueError as exc:
            return {
                "success": False,
                "errors": [str(exc)]
            }

        result = await self.download_service.execute(plan, progress_callback)
        result["capability"] = cap
        result["model"] = spec.model_id
        return result

    def stop(self) -> None:
        with self._lock:
            caps = list(self._adapter_classes.keys())
        for cap in caps:
            self.stop_provider(cap)
        try:
            from .adapters.impl.transports.http import shutdown_clients
            _run_maybe_async(shutdown_clients())
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Providers] 连接池关闭跳过: {exc}")


provider_manager = ProviderManager()

T = TypeVar("T", bound=object)


def Provider(obj: Optional[Type[T]] = None, name: str = ""):
    """把 entity 门面注册进 ProviderManager（延迟到实例首次构造时）。"""
    def decorator(cls: Type[T]) -> Type[T]:
        pipeline_name = _capability(name or cls.__name__)
        original_init = cls.__init__

        @wraps(original_init)
        def __init__(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.capability=name
            try:
                provider_manager.register(pipeline_name, self)
            except Exception:  # noqa: BLE001 - 单例已注册是正常情况
                pass

        def unregister_only(self):
            try:
                with provider_manager._lock:
                    if provider_manager._adapter_classes.get(pipeline_name) is self:
                        provider_manager._adapter_classes.pop(pipeline_name, None)
            except Exception:  # noqa: BLE001 - 解释器退出阶段不抛异常
                pass

        cls.__init__ = __init__  # type: ignore[method-assign]
        if hasattr(cls, "__del__"):
            original_del = cls.__del__  # type: ignore[method-assignment]

            @wraps(original_del)
            def __del__(self):  # type: ignore[method-assignment]
                try:
                    original_del(self)
                finally:
                    unregister_only(self)
        else:
            cls.__del__ = unregister_only  # type: ignore[method-assignment]
        return cls

    if obj is None:
        return decorator
    return decorator(obj)


__all__ = ["ProviderManager", "Provider", "provider_manager", "ProviderType"]
