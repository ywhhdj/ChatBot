"""Pipeline 管理器：注册/切换各适配器（LLM / TTS / ASR / OCR）"""
from functools import wraps
from inspect import iscoroutinefunction
from typing import Dict, Optional, List, Any, Type, TypeVar
import asyncio
import os
import threading

from ..manager.base import BaseManager
from ..events import types, on_event_class
from ..logger import logger
from ..keys import ProviderType

# endpoint 级字段：不进入请求 payload，只覆盖连接参数
_ENDPOINT_KEYS = {
    "base_url", "chat_path", "auth", "timeout", "max_retries",
    "transport", "runtime", "model_dir", "device", "protocol", "method",
}


@on_event_class([
    (types.AppEventType.ManagerEventType.PIPELINE_START, "start"),
    (types.AppEventType.ManagerEventType.PIPELINE_STOP, "stop")
])
class ProviderManager(BaseManager):

    def __init__(self):
        if self._initialized:
            return
        self._registry = None
        self._adapter_classes: Dict[str, Optional[Any]] = {}
        self._lock = threading.RLock()
        self._initialized = True

    def _get_adapter_manager(self, adapter_type: str) -> Optional[Any]:
        with self._lock:
            return self._adapter_classes.get(adapter_type)

    def _get_registry(self):
        if self._registry is None:
            from ..providers import factory   # 延迟导入，避免循环
            self._registry = factory.get_registry()
        return self._registry

    # ---------- 生命周期 ----------

    def start(self):
        ok = self.load_config()
        logger.info(f"[Pipeline] config loaded: {ok}")

    def load_config(self) -> bool:
        """加载 Registry（schemas + providers）。保留方法名以兼容 start 事件。"""
        try:
            reg = self._get_registry()
            caps = {k: len(v) for k, v in reg.providers.items()}
            logger.info(f"[Pipeline] providers loaded: {caps}")
            return True
        except Exception as exc:
            logger.warning(f"[Pipeline] 加载配置失败: {exc}")
            return False

    # ---------- 查询（全部走 Registry） ----------

    def get_valid_providers(self, adapter_type: str) -> List[str]:
        return list(self._get_registry().providers.get(adapter_type, {}).keys())

    def get_provider_names(self, adapter_type: str) -> List[str]:
        return self.get_valid_providers(adapter_type)

    def validate_provider(self, adapter_type: str, provider_name: str) -> bool:
        return provider_name in self.get_valid_providers(adapter_type)

    def get_adapter_type_config(self, adapter_type: str) -> Dict:
        return dict(self._get_registry().providers.get(adapter_type, {}))

    def get_pipeline_all_configs(self) -> Dict[str, Dict]:
        return {k: dict(v) for k, v in self._get_registry().providers.items()}

    def get_provider_config(
        self,
        adapter_type: str,
        provider_name: str,
        model_id: Optional[str] = None
    ) -> Optional[Dict]:
        """返回**扁平** config，直接可作为 shim 的 kwargs。

        结构：endpoint 关键字段 + auth 字段名（值从 env 取）+ params 的 default + model。
        """
        reg = self._get_registry()
        try:
            merged = reg.merged(adapter_type, provider_name, model_id)
        except KeyError:
            return None

        flat: Dict[str, Any] = {}
        ep = merged.get("endpoint", {})
        for k in _ENDPOINT_KEYS:
            if k in ep and ep[k] is not None:
                flat[k] = ep[k]

        # auth：把字段名展开成 key，值优先从环境变量取，其次留 None 等调用方覆盖
        auth = ep.get("auth") or {}
        field = auth.get("field")
        if field:
            env_key = f"{provider_name.upper()}_{field.upper()}"
            flat[field] = os.environ.get(env_key)

        # params：用 schema 合并后的 default 展开
        for k, spec in merged.get("params", {}).items():
            if isinstance(spec, dict) and "default" in spec:
                v = spec["default"]
                if v is not None:
                    flat[k] = v
            else:
                flat[k] = spec

        # 选中模型
        model = merged.get("selected_model")
        if model:
            flat["model"] = model.get("id")
        elif merged.get("models"):
            flat["model"] = merged["models"][0].get("id")

        return flat

    def get_provider_meta(
        self,
        adapter_type: str,
        provider_name: str
    ) -> Optional[Dict]:
        """给前端用的元数据（label / tags / deployment / region）。"""
        reg = self._get_registry()
        try:
            return reg.merged(adapter_type, provider_name).get("meta")
        except KeyError:
            return None

    # ---------- 适配器停止（保留原跨 loop 修复） ----------

    def _stop_adapter(self, manager: Any) -> None:
        if manager is None:
            return
        stop_fn = getattr(manager, "stop", None)
        if not callable(stop_fn):
            return
        if not iscoroutinefunction(stop_fn):
            try:
                stop_fn()
            except Exception as exc:
                logger.warning(f"[Pipeline] 停止适配器失败: {exc}")
            return

        async def _do_stop():
            try:
                await stop_fn()
            except Exception as exc:
                logger.warning(f"[Pipeline] 停止适配器失败: {exc}")

        try:
            asyncio.get_running_loop()
            has_loop = True
        except RuntimeError:
            has_loop = False

        if has_loop:
            try:
                from .. import runtime
                runtime.manager.task_manager.run_coroutine(_do_stop())
            except Exception as exc:
                logger.warning(f"[Pipeline] 提交停止任务失败: {exc}")
        else:
            try:
                asyncio.run(_do_stop())
            except Exception as exc:
                logger.warning(f"[Pipeline] 停止适配器失败: {exc}")

    # ---------- 切换 / 注册 ----------

    def switch_adapter(
        self,
        adapter_type: str,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None,
        model_id: Optional[str] = None,
    ):
        try:
            adapter_manager = self._get_adapter_manager(adapter_type)
            if adapter_manager is None:
                return {
                    "success": False,
                    "errors": [f"Adapter {adapter_type} not registered"]
                }

            if not self.validate_provider(adapter_type, provider_name):
                return {
                    "success": False,
                    "errors": [f"Provider {provider_name} not valid for {adapter_type}"]
                }

            flat = self.get_provider_config(adapter_type, provider_name, model_id)
            if flat is None:
                return {
                    "success": False,
                    "errors": [f"Provider {provider_name} not found"]
                }
            if config:
                flat.update(config)

            # 释放旧模型由 initialize_provider 负责（见 entity.py）
            adapter_manager.initialize_provider(provider_name, **flat)
            try:
                adapter_manager.init_provider_client(**flat)
            except Exception as e:
                # 初始化失败：清掉半成品，避免下次误判 is_initialized
                try:
                    adapter_manager.stop()
                except Exception:
                    pass
                raise
            return {
                "success": True,
                "type": adapter_type,
                "name": provider_name,
                "config": flat
            }
        except Exception as e:
            logger.error(f"[switch_adapter] {adapter_type}/{provider_name} failed: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }

    def register(self, adapter_type: str, manager: Any) -> None:
        with self._lock:
            existing = self._adapter_classes.get(adapter_type)
            if existing is not None and existing is not manager:
                raise ValueError(f"AdapterType {adapter_type} already registered")
            self._adapter_classes[adapter_type] = manager

    def unregister(self, adapter_type: str) -> None:
        with self._lock:
            manager = self._adapter_classes.pop(adapter_type, None)
        if manager is not None:
            self._stop_adapter(manager)

    def stop(self):
        with self._lock:
            adapter_types = list(self._adapter_classes.keys())
        for adapter_type in adapter_types:
            try:
                self.unregister(adapter_type)
            except Exception as exc:
                logger.warning(f"[Pipeline] 停止 {adapter_type} 失败: {exc}")


provider_manager = ProviderManager()


T = TypeVar("T", bound=object)


def Provider(obj: Optional[Type[T]] = None, name: str = ""):

    def decorator(cls: Type[T]) -> Type[T]:
        if provider_manager is None:
            raise RuntimeError("ProviderManager not initialized")
        pipeline_name = name or cls.__name__
        original_init = cls.__init__

        @wraps(original_init)
        def __init__(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            provider_manager.register(pipeline_name, self)  # type: ignore[assignment]

        def unregister_only(self):
            try:
                provider_manager.unregister(pipeline_name)
            except Exception:
                pass

        if hasattr(cls, "__del__"):
            original_del = cls.__del__  # type: ignore[method-assignment]

            @wraps(original_del)
            def __del__(self):  # type: ignore[method-assignment]
                try:
                    original_del(self)
                finally:
                    unregister_only(self)
        else:
            def __del__(self):
                try:
                    unregister_only(self)
                except Exception:
                    pass

        cls.__init__ = __init__  # type: ignore[method-assign]
        cls.__del__ = __del__  # type: ignore[method-assign]
        return cls

    if obj is None:
        return decorator
    return decorator(obj)
