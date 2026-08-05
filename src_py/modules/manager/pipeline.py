from functools import wraps
from inspect import iscoroutinefunction
from typing import Dict, Optional, List,Any, Type, TypeVar
import asyncio
from ..runtime import RuntimePath
from ..utils.file import read_json
from .base import _BaseManager
from ..events import types, on_event_class
from ..logger import logger
from ..pipeline.enum import AdapterType

@on_event_class([
    (types.AppEventType.ManagerEventType.PIPELINE_START, "start"),
    (types.AppEventType.ManagerEventType.PIPELINE_STOP, "stop")
])
class PipelineManager(_BaseManager):

    def __init__(self):
        if self._initialized:
            return
        self.__pipeline_config: Dict[str, Any] = {}
        self.__adapter_classes: Dict[AdapterType, Optional[Any]] = {}
        self.__config_path: str = RuntimePath.get_pipeline_config_file_path()
        self._initialized = True
    

    def __get_adapter_manager(self, adapter_type: AdapterType):
        return self.__adapter_classes.get(adapter_type)

    from ..manager.task.decorator import sync_task_scheduler
    @sync_task_scheduler
    def start(self):
        self.load_config(self.__config_path)
        print(self.__pipeline_config)
    
    def get_valid_providers(self, adapter_type: AdapterType) -> List[str]:
        return list(self.__pipeline_config.get(adapter_type.value, {}).keys())
    
    def validate_provider(self, adapter_type: AdapterType, provider_name: str) -> bool:
        valid = self.get_valid_providers(adapter_type)
        return provider_name in valid
    
    def get_provider_names(self, adapter_type: AdapterType) -> List[str]:
        return self.__pipeline_config.get(adapter_type.value, {}).keys()
    
    def get_adapter_type_config(self, adapter_type: AdapterType) -> Dict:
        return self.__pipeline_config.get(adapter_type.value, {})
    
    def get_pipeline_all_configs(self) -> Dict[str, Dict]:
        return self.__pipeline_config

    def get_provider_config(self, adapter_type: AdapterType, provider_name: str) -> Optional[Dict]:
        """
        获取某个 provider 的完整配置
        
        Returns:
        ```json
            {
                "name": "deepseek",
                "description": "...",
                "tags": [...],
                "config": {...}
            }
        ```
        """
        return self.__pipeline_config.get(adapter_type.value, {}).get(provider_name)
    
    def load_config(self, config_path: str) -> bool:
        try:
            self.__pipeline_config = read_json(config_path)
        except Exception:
            return False
        return True

    def stop(self):
        for adapter_type in AdapterType:
            self.unregister(adapter_type.value)

    def switch_adapter(
        self,
        adapter_type: AdapterType,
        provider_name: str,
        config:Optional[Dict[str, Any]] = None
    ):
        try:
            # 2. 关闭旧的适配器
            if adapter_type in self.__adapter_classes:
                adapter_manager=self.__get_adapter_manager(adapter_type)
                if not adapter_manager:
                    raise RuntimeError(f"Adapter {adapter_type.value} already initialized")
                if adapter_manager.is_initialized:
                    if asyncio.iscoroutinefunction(adapter_manager.stop):
                        asyncio.run(adapter_manager.stop())
                    else:
                        adapter_manager.stop()
                #先检查是否支持适配器
                if provider_name not in adapter_manager.get_available_providers():
                    return {
                        "success": False,
                        "errors": [f"Provider {provider_name} not valid for adapter type {adapter_type.value}"]
                    }
                #获取provider的配置，校验配置是否为必填项
                provider_config = self.get_provider_config(adapter_type, provider_name)
                if not provider_config:
                    return {
                        "success": False,
                        "errors": [f"Provider {provider_name} not found for adapter type {adapter_type.value}"]
                    }
                #重新初始化适配器

                adapter_manager.intialize_provider(provider_name, **provider_config)
                #初始化模型,交给任务调度，避免阻塞主线程，如OCR模型
                adapter_manager.init_provider_client(**provider_config)
                return {
                    "success": True,
                    "type": adapter_type.value,
                    "name": provider_name,
                    "config": provider_config
                }
        except Exception as e:
            logger.error(f"[PipelineManager] Failed to create {provider_name}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
        return {
            "success": False,
            "errors": [f"Adapter {adapter_type.value} not found"]
        }

    def register(self, adapter_type:str,manager: Any) -> None:
        if adapter_type not in AdapterType:
            raise ValueError(f"AdapterType {adapter_type} not valid")
        if self.__adapter_classes[AdapterType(adapter_type)] is not None:
            raise ValueError(f"AdapterType {adapter_type} already registered")
        self.__adapter_classes[AdapterType(adapter_type)] = manager

    def unregister(self, adapter_type: str) -> None:
        manager = self.__adapter_classes.get(AdapterType(adapter_type))
        if manager:
            if iscoroutinefunction(manager.stop):
                asyncio.run(manager.stop())
            else:
                manager.stop()
            del self.__adapter_classes[AdapterType(adapter_type)]

pipeline_manager= PipelineManager()


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
            pipeline_manager.register(pipeline_name, self) # type: ignore[assignment]
        
        def new__del__(self):
            if hasattr(self, "stop"):
                self.stop()
            pipeline_manager.unregister(pipeline_name) # type: ignore[assignment]
        
        #如果原类没有__del__方法，则添加一个
        if hasattr(cls, "__del__"):
            original_del = cls.__del__  # type: ignore[method-assignment]
            @wraps(original_del)
            def __del__(self):  # type: ignore[method-assignment]
                original_del(self)
                new__del__(self)
        else:
            def __del__(self):
                new__del__(self)

        cls.__init__ = __init__  # type: ignore[method-assign]
        cls.__del__ = __del__  # type: ignore[method-assign]
        return cls

    if obj is None:
        return decorator
    return decorator(obj)
