import asyncio
import threading
from typing import Any, Dict, Generic, Optional, TypeVar
from ...utils.file import write_yaml
from ...runtime import RuntimePath
from ..base import _BaseManager
from ...services.base import _BaseService,ServiceState
from ...logger import logger
from ...utils import util
from ...events import types, on_event_class
T = TypeVar("T", bound=_BaseService)

@on_event_class([
    (types.AppEventType.ManagerEventType.SERVICE_STOP, "stop")
])
class ServiceManager(Generic[T], _BaseManager):

    def __init__(self) -> None:
        if self._initialized:
            return
        self.services: dict[str, T] = {}
        self.service_threads: dict[str, Dict[str, threading.Thread]] = {}
        self._service_classes: Dict[str, type[T]] = {}  # service_name -> class
        self.config_path=RuntimePath.get_service_config_file_path()
        self._initialized=True
    
    def __shutdown_event_loop(self,service_id:str,loop:asyncio.AbstractEventLoop):
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(self.services[service_id].close_original())
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def __run_loop(self, service_id: str, args, kwargs):
        __loop=None
        try:
            __loop  = asyncio.new_event_loop()
            asyncio.set_event_loop(__loop)
            __loop.run_until_complete(getattr(self.services[service_id], "start_original")(*args, **kwargs))
        finally:
            if __loop is not None:
                try:
                    self.__shutdown_event_loop(service_id,__loop)
                finally:
                    __loop=None
                    asyncio.set_event_loop(None)
    
    def __is_main_thread_service(self, service: T) -> bool:
        return service.main_thread

    def register_service(self, service_id: str, service: T) -> str:
        self.services[service_id] = service
        return service_id
    
    def unregister(self, service_id: str) -> str:
        del self.services[service_id]
        if service_id in self.service_threads:
            del self.service_threads[service_id]
        return service_id

    def is_registered(self, service_id: str) -> bool:
        return str(service_id) in self.services.keys()
    
    def start_service(self, service_id: str = "", *args, **kwargs) -> bool:
        service = self.services.get(service_id)
        if not service:
            return False
        if service.state == ServiceState.RUNNING:
            logger.warning(f"Service {service_id} already running")
            return False
        try:
            if service_id not in self.service_threads:
                self.service_threads[service_id] = {}
            if asyncio.iscoroutinefunction(service.start_original):
                self.service_threads[service_id]["thread"] = util.create_daemon_thread(
                    self.__run_loop, 
                    name=service.name,
                    args=(service_id, args, kwargs)
                )
            else:
                self.service_threads[service_id]["thread"] = util.create_daemon_thread(
                    service.start_original,
                    name=service.name,
                    args=args,
                    kwargs=kwargs
                )
            self.service_threads[service_id]["thread"].start()
            service.state = ServiceState.RUNNING
        except Exception as e:
            service.state = ServiceState.ERROR
            logger.error(f"Error starting service {service_id}: {e}")
            return False
        return True

    def stop_service(self, service_id: str,*args,**kwargs) -> None:
        service = self.services.get(service_id)
        if not service:
            return
        try:
            if asyncio.iscoroutinefunction(service.stop):
                # 异步停止需要通过事件循环
                thread = self.service_threads.get(service_id, {}).get("thread")
                if thread:
                    thread.join()
            else:
                service.stop_original()
            thread = self.service_threads.get(service_id, {}).get("thread")
            if thread:
                thread.join()
            service.state = ServiceState.STOPPED
        except Exception as e:
            service.state = ServiceState.ERROR
            logger.error(f"Error stopping service {service_id}: {e}")
            return
        service.state = ServiceState.STOPPED

    def close_service(self, service_id: str,*args,**kwargs) -> None:
        self.stop_service(service_id, *args, **kwargs)
        self.unregister(service_id)

    def get_service_names(self) -> list[str]:
        names=[]
        for service in self.services.values():
            names.append(service.name)
        return names
    
    def get_service_info(self, service_id: str) -> Optional[dict[str, Any]]:
        if service_id not in self.services:
            return None
        service = self.get_service(service_id)
        return {
            "name": service.name,
            "description": service.description,
            "state": service.state,
            "config": service.config,
            "main_thread": self.__is_main_thread_service(service),
        }
    
    def get_all_service_infos(self) -> list[dict[str, str]]:
        infos=[]
        for service in self.services.values():
            infos.append(self.get_service_info(service.name))
        return infos
    
    def get_service(self, service_id: str) -> T:
        if service_id not in self.services:
            raise ValueError(f"Service {service_id} not registered")
        return self.services[service_id]

    def stop(self) -> None:
        configs={}
        for service_id in self.services.keys():
            configs[service_id]=self.get_service_config(service_id)
        write_yaml(self.config_path,configs)
        for service_id in self.services.keys():
            self.close_service(service_id)
    
    def get_service_tool(self, service_id: str):
        service = self.get_service(service_id)
        return service.get_tools()

    # def initialize_from_config(self, config_file: str):
    #     """从配置文件批量初始化服务"""
    #     self._config_file = Path(config_file)
        
    #     if not self._config_file.exists():
    #         logger.warning(f"Config file {config_file} not found")
    #         return
    #     config=read_yaml(config_file)
    #     if config is None:
    #         logger.error(f"Config file {config_file} is empty")
    #         return
    
    def get_service_config(self, service_id: str) -> Any:
        config=self.services[service_id].config
        if config is None:
            raise ValueError(f"Service {service_id} not found")
        return config
    
    def update_service_config(self, service_id: str, new_config:Optional[Any] = None) -> bool:
        service = self.services.get(service_id)
        if not service:
            logger.error(f"Service {service_id} not found")
            return False
        old_config = service.config
        if new_config is None:
            return False
        service.config = new_config
        return True

    def get_config(self, service_id: str) -> Any:
        config=self.services[service_id].config
        if config is None:
            raise ValueError(f"Service {service_id} not found")
        return config

    def get_service_state(self, service_id: str) -> str:
        service = self.get_service(service_id)
        return service.state
    
    def get_tools(self) -> list[dict[str, Any]]:
        tools=[]
        for service in self.services.values():
            service_tools=service.get_tools()
            if service_tools is None:
                continue
            tools.append({
                "service":service.name,
                "tools":service_tools,
            })
        return tools

    def get_default_services_description(self,service_id:Optional[str] = None):
        from ...services import ServiceId,config
        configs={
            ServiceId.LIVE2D:config.Live2DConfig().get_config_items(),
            ServiceId.OBS:config.ObsConfig().get_config_items(),
            ServiceId.BROWSER:config.BrowserConfig().get_config_items(),
            ServiceId.QQBOT:config.QQBotConfig().get_config_items(),
        }
        if service_id:
            return configs[service_id]
        return configs

service_manager=ServiceManager()
