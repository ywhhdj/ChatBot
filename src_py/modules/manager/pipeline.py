"""Pipeline 管理器：注册/切换各适配器（LLM / TTS / ASR / OCR）。

修复对应清单：C49 C50 C51 C52 / CD5

C49 `register()` 里 `if self.__adapter_classes[AdapterType(...)] is not None`
    键不存在时直接 KeyError —— 与"判断未注册"的意图正好相反。
C50 `switch_adapter` / `unregister` 里 `asyncio.run(adapter.stop())`：
    调用方若在有运行中 loop 的线程（Web loop / 调度器 loop）必然抛
    `RuntimeError: asyncio.run() cannot be called from a running event loop`。
C51 `Pipeline` 装饰器覆写 `__del__` 并在其中调用 unregister，
    而 unregister 会 asyncio.run —— GC 时机不确定，可能在解释器清理阶段、
    没有任何 loop 的时候触发，抛出的异常无法被捕获。
C52 `start()` 被 `@sync_task_scheduler` 装饰 -> 返回 TaskReference，
    load_config 是否完成没有保证。
"""

from functools import wraps
from inspect import iscoroutinefunction
from typing import Dict, Optional, List, Any, Type, TypeVar
import asyncio
import threading

from ..runtime import RuntimePath
from ..utils.file import json
from .base import BaseManager
from ..events import types, on_event_class
from ..logger import logger
from ..pipeline.enum import AdapterType


@on_event_class([
    (types.AppEventType.ManagerEventType.PIPELINE_START, "start"),
    (types.AppEventType.ManagerEventType.PIPELINE_STOP, "stop")
])
class PipelineManager(BaseManager):

    def __init__(self):
        if self._initialized:
            return
        self.__pipeline_config: Dict[str, Any] = {}
        self.__adapter_classes: Dict[AdapterType, Optional[Any]] = {}
        self.__lock = threading.RLock()
        self._initialized = True

    def __get_adapter_manager(self, adapter_type: AdapterType):
        with self.__lock:
            return self.__adapter_classes.get(adapter_type)

    # ---------- 生命周期 ----------

    def start(self):
        with self.__lock:
            ok = self.load_config()
        logger.info(f"[Pipeline] config loaded: {ok}")

    def load_config(self) -> bool:
        config_path = RuntimePath.get_pipeline_config_file_path()
        try:
            config = json.read_json(config_path)
        except Exception as exc:
            logger.warning(f"[Pipeline] 读取配置失败 {config_path}: {exc}")
            return False
        if not isinstance(config, dict):
            logger.warning(f"[Pipeline] 配置格式不是对象: {config_path}")
            return False
        with self.__lock:
            self.__pipeline_config = config
        return True

    # ---------- 查询 ----------

    def get_valid_providers(self, adapter_type: AdapterType) -> List[str]:
        with self.__lock:
            return list(self.__pipeline_config.get(adapter_type.value, {}).keys())

    def validate_provider(self, adapter_type: AdapterType, provider_name: str) -> bool:
        return provider_name in self.get_valid_providers(adapter_type)

    def get_provider_names(self, adapter_type: AdapterType) -> List[str]:
        with self.__lock:
            return list(self.__pipeline_config.get(adapter_type.value, {}).keys())

    def get_adapter_type_config(self, adapter_type: AdapterType) -> Dict:
        with self.__lock:
            return self.__pipeline_config.get(adapter_type.value, {})

    def get_pipeline_all_configs(self) -> Dict[str, Dict]:
        with self.__lock:
            return dict(self.__pipeline_config)

    def get_provider_config(self, adapter_type: AdapterType, provider_name: str) -> Optional[Dict]:
        with self.__lock:
            return self.__pipeline_config.get(adapter_type.value, {}).get(provider_name)

    # ---------- 适配器停止（核心） ----------

    def __stop_adapter(self, manager: Any) -> None:
        """停止适配器，兼容同步/异步两种 stop，且**不使用 asyncio.run**。

        C50：`asyncio.run()` 在有运行中 loop 的线程必然抛 RuntimeError。
        这里分三种情况：
          - 有运行中 loop  -> 交给调度器 loop 执行（跨 loop 安全）
          - 无 loop        -> 一次性 asyncio.run
          - 同步 stop      -> 直接调用
        """
        if manager is None:
            return
        stop_fn = getattr(manager, "stop", None)
        if stop_fn is None:
            return

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
            # 当前线程有 loop，交给调度器自有 loop，避免跨 loop 操作
            try:
                from .. import runtime
                runtime.manager.task_manager.run_coroutine(_do_stop())  # type: ignore[union-attr]
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
        adapter_type: AdapterType,
        provider_name: str,
        config: Optional[Dict[str, Any]] = None
    ):
        try:
            adapter_manager = self.__get_adapter_manager(adapter_type)
            if not adapter_manager:
                raise RuntimeError(f"Adapter {adapter_type.value} already initialized")

            if getattr(adapter_manager, "is_initialized", False):
                # 先检查 provider 是否支持，再关旧的（避免关了才发现切不了）
                if provider_name not in adapter_manager.get_available_providers():
                    return {
                        "success": False,
                        "errors": [f"Provider {provider_name} not valid for adapter type {adapter_type.value}"]
                    }
                provider_config = self.get_provider_config(adapter_type, provider_name)
                if not provider_config:
                    return {
                        "success": False,
                        "errors": [f"Provider {provider_name} not found for adapter type {adapter_type.value}"]
                    }
                self.__stop_adapter(adapter_manager)
                adapter_manager.intialize_provider(provider_name, **(config or provider_config))
                adapter_manager.init_provider_client(**(config or provider_config))
                return {
                    "success": True,
                    "type": adapter_type.value,
                    "name": provider_name,
                    "config": config or provider_config
                }

            # 尚未初始化：直接初始化
            provider_config = config or self.get_provider_config(adapter_type, provider_name)
            if not provider_config:
                return {
                    "success": False,
                    "errors": [f"Provider {provider_name} not found for adapter type {adapter_type.value}"]
                }
            adapter_manager.intialize_provider(provider_name, **provider_config)
            adapter_manager.init_provider_client(**provider_config)
            return {
                "success": True,
                "type": adapter_type.value,
                "name": provider_name,
                "config": provider_config
            }
        except Exception as e:
            logger.error(f"[PipelineManager] Failed to create {provider_name}: {e}")
            return {"success": False, "errors": [str(e)]}

    def register(self, adapter_type: str, manager: Any) -> None:
        try:
            key = AdapterType(adapter_type)
        except ValueError:
            raise ValueError(f"AdapterType {adapter_type} not valid")

        with self.__lock:
            existing = self.__adapter_classes.get(key)
            if existing is not None and existing is not manager:
                raise ValueError(f"AdapterType {adapter_type} already registered")
            self.__adapter_classes[key] = manager

    def unregister(self, adapter_type: str) -> None:
        try:
            key = AdapterType(adapter_type)
        except ValueError:
            logger.warning(f"[Pipeline] 未知的 AdapterType: {adapter_type}")
            return

        with self.__lock:
            manager = self.__adapter_classes.pop(key, None)
        if manager is not None:
            self.__stop_adapter(manager)

    def stop(self):
        with self.__lock:
            adapter_types = list(self.__adapter_classes.keys())
        for adapter_type in adapter_types:
            try:
                self.unregister(adapter_type.value)
            except Exception as exc:
                logger.warning(f"[Pipeline] 停止 {adapter_type.value} 失败: {exc}")


pipeline_manager = PipelineManager()


T = TypeVar("T", bound=object)


def Pipeline(obj: Optional[Type[T]] = None, name: str = ""):

    def decorator(cls: Type[T]) -> Type[T]:
        if pipeline_manager is None:
            raise RuntimeError("PipelineManager not initialized")
        pipeline_name = name or cls.__name__
        original_init = cls.__init__

        @wraps(original_init)
        def __init__(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            pipeline_manager.register(pipeline_name, self)  # type: ignore[assignment]

        def unregister_only(self):
            try:
                with pipeline_manager._PipelineManager__lock:  # type: ignore[attr-defined]
                    pipeline_manager._PipelineManager__adapter_classes.pop(  # type: ignore[attr-defined]
                        AdapterType(pipeline_name), None
                    )
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
