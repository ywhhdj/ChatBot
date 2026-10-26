import asyncio
import inspect
import threading
from typing import Any, Dict, Generic, Optional, TypeVar

from ...utils.file import yaml
from ...runtime import RuntimePath
from ..base import BaseManager
from ...services.base import BaseService,ServiceState
from ...logger import logger
from ...utils import util
from ...events import types, on_event_class
from src_py.modules import runtime

T = TypeVar("T", bound=BaseService)
SERVICE_JOIN_TIMEOUT = 5.0

@on_event_class([(types.AppEventType.ManagerEventType.SERVICE_STOP, "stop")])
class ServiceManager(Generic[T], BaseManager):
    def __init__(self) -> None:
        if self._initialized:
            return
        self.services: dict[str, T] = {}
        self.service_threads: dict[str, Dict[str, threading.Thread]] = {}
        self.services_config: dict[str, Dict[str, Any]] = {}
        self._initialized = True

    def __shutdown_event_loop(self, service_id: str, loop: asyncio.AbstractEventLoop):
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            service = self.services.get(service_id)
            if service is None:
                return
            close_fn = getattr(service, "close_original", None)
            if close_fn is None:
                return
            # A6：close_original 可能是同步方法，也可能是协程函数
            result = close_fn()
            if inspect.isawaitable(result):
                loop.run_until_complete(result)
        except Exception as e:
            logger.error(f"[Service] shutdown event loop error for {service_id}: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def __run_loop(self, service_id: str, args, kwargs):
        __loop = None
        try:
            __loop = asyncio.new_event_loop()
            asyncio.set_event_loop(__loop)
            start_fn = getattr(self.services[service_id], "start_original")
            result = start_fn(*args, **kwargs)
            if inspect.isawaitable(result):
                __loop.run_until_complete(result)
        except Exception as e:
            logger.error(f"[Service] run loop error for {service_id}: {e}")
        finally:
            if __loop is not None:
                try:
                    self.__shutdown_event_loop(service_id, __loop)
                finally:
                    __loop = None
                    asyncio.set_event_loop(None)

    # ---------- 主线程服务判定（A7） ----------

    @staticmethod
    def _is_main_thread_service(service: T) -> bool:
        return bool(getattr(service, "main_thread", False))

    def _run_on_main_thread(self, service: T, method_name: str, args, kwargs) -> bool:
        fn = getattr(service, method_name, None)
        if fn is None:
            return False

        if threading.current_thread() is threading.main_thread():
            fn(*args, **kwargs)
            return True

        try:
            from ...ui.dispatcher import get_main_thread_dispatcher

            dispatcher = get_main_thread_dispatcher()
            dispatcher.run_on_main_thread(fn, *args, **kwargs)
            return True
        except Exception as e:
            logger.error(f"[Service] dispatch {method_name} to main thread failed: {e}")
            return False

    # ---------- 注册 ----------

    def register_service(self, service_id: str, service: T) -> str:
        if service_id in self.services and self.services[service_id] is not service:
            logger.warning(f"[Service] service id {service_id} registered again, overwritten")
        self.services[service_id] = service
        config = self.get_service_config(service_id)
        if config is not None:
            service.config = config
        return service_id

    def unregister(self, service_id: str) -> str:
        self.services.pop(service_id, None)
        self.service_threads.pop(service_id, None)
        return service_id

    def is_registered(self, service_id: str) -> bool:
        return str(service_id) in self.services.keys()
    
    def set_service_config(self, service_id: str, config: Dict[str, Any]) -> None:
        self.services_config[service_id] = config

    # ---------- 启停 ----------

    def start_service(self, service_id: str = "", *args, **kwargs) -> bool:
        service = self.services.get(service_id)
        if not service:
            return False
        if service.state == ServiceState.RUNNING:
            logger.warning(f"Service {service_id} already running")
            return False

        try:
            if self._is_main_thread_service(service):
                ok = self._run_on_main_thread(service, "start_original", args, kwargs)
                service.state = ServiceState.RUNNING if ok else ServiceState.ERROR
                return ok

            if service_id not in self.service_threads:
                self.service_threads[service_id] = {}

            start_fn = getattr(service, "start_original", None)
            if start_fn is None:
                service.state = ServiceState.ERROR
                return False

            if asyncio.iscoroutinefunction(start_fn):
                self.service_threads[service_id]["thread"] = util.create_daemon_thread(
                    self.__run_loop,
                    name=service.name,
                    args=(service_id, args, kwargs),
                )
            else:
                self.service_threads[service_id]["thread"] = util.create_daemon_thread(
                    start_fn,
                    name=service.name,
                    args=args,
                    kwargs=kwargs,
                )
            self.service_threads[service_id]["thread"].start()
            service.state = ServiceState.RUNNING
        except Exception as e:
            service.state = ServiceState.ERROR
            logger.error(f"Error starting service {service_id}: {e}")
            return False
        return True

    def stop_service(self, service_id: str, *args, **kwargs) -> None:
        service = self.services.get(service_id)
        if not service:
            return
        try:
            # A7：主线程服务直接（或投递到）主线程执行
            if self._is_main_thread_service(service):
                self._run_on_main_thread(service, "stop_original", args, kwargs)
            else:
                stop_fn = getattr(service, "stop_original", None)
                if stop_fn is not None and not asyncio.iscoroutinefunction(stop_fn):
                    stop_fn(*args, **kwargs)
                # A5/D5：带超时 + Qt 事件泵地回收线程
                thread = self.service_threads.get(service_id, {}).get("thread")
                if thread is not None:
                    if threading.current_thread() is thread:
                        logger.warning(f"[Service] skip joining self for {service_id}")
                    else:
                        try:
                            from ...ui.dispatcher import join_with_pump

                            if not join_with_pump(thread, SERVICE_JOIN_TIMEOUT):
                                logger.warning(
                                    f"[Service] thread of {service_id} did not stop "
                                    f"within {SERVICE_JOIN_TIMEOUT}s"
                                )
                        except Exception:
                            thread.join(SERVICE_JOIN_TIMEOUT)
        except Exception as e:
            service.state = ServiceState.ERROR
            logger.error(f"Error stopping service {service_id}: {e}")
            return
        finally:
            # B20：统一在这里落状态
            service.state = ServiceState.STOPPED
            self.service_threads.pop(service_id, None)

    def close_service(self, service_id: str, *args, **kwargs) -> None:
        self.stop_service(service_id, *args, **kwargs)
        self.unregister(service_id)

    # ---------- 查询 ----------

    def get_service_names(self) -> list[str]:
        return [service.name for service in self.services.values()]

    def get_service_info(self, service_id: str) -> Optional[dict[str, Any]]:
        if service_id not in self.services:
            return None
        service = self.get_service(service_id)
        return {
            "name": service.name,
            "description": service.description,
            "state": service.state,
            "config": service.config,
            "main_thread": self._is_main_thread_service(service),
        }

    def get_all_service_infos(self) -> list[dict[str, Any]]:
        infos = []
        for service_id in self.services.keys():
            info = self.get_service_info(service_id)
            if info is not None:
                infos.append(info)
        return infos

    def get_service(self, service_id: str) -> T:
        if service_id not in self.services:
            raise ValueError(f"Service {service_id} not registered")
        return self.services[service_id]

    def get_service_state(self, service_id: str) -> str:
        service = self.get_service(service_id)
        return service.state

    def stop(self) -> None:
        # A4：list() 快照，close_service 内部会 unregister 删除元素
        service_ids = list(self.services.keys())

        configs = {}
        for service_id in service_ids:
            try:
                configs[service_id] = self.get_service_config(service_id)
            except Exception as e:
                logger.error(f"[Service] read config of {service_id} failed: {e}")

        # B19：落盘失败不能影响后续清理
        try:
            if configs:
                runtime.manager.save_manager.server[service_id] = configs
        except Exception as e:
            logger.error(f"[Service] write service config failed: {e}")

        for service_id in service_ids:
            try:
                self.close_service(service_id)
            except Exception as e:
                logger.error(f"[Service] close {service_id} failed: {e}")

    # ---------- 工具 ----------

    def get_service_tool(self, service_id: str):
        service = self.get_service(service_id)
        return service.get_tools()

    def get_service_config(self, service_id: str) -> Any:
        service = self.services.get(service_id)
        if service is None:
            raise ValueError(f"Service {service_id} not found")
        config = service.config
        if config is None:
            raise ValueError(f"Service {service_id} config is None")
        return config

    def update_service_config(self, service_id: str, new_config: Optional[Any] = None) -> bool:
        #先存储服务配置，在服务注册时注入配置
        if new_config is None:
            return False
        self.set_service_config(service_id, new_config)
        return True

    def get_config(self, service_id: str) -> Any:
        return self.get_service_config(service_id)

    def get_tools(self) -> list[dict[str, Any]]:
        tools = []
        for service in self.services.values():
            service_tools = service.get_tools()
            if service_tools is None:
                continue
            tools.append(
                {
                    "service": service.name,
                    "tools": service_tools,
                }
            )
        return tools

    def get_ui_service_description(self, service_id: str):
        from ...services import config
        config_class = config.get_service_classes(service_id)
        return config_class().get_ui_config_items()


service_manager = ServiceManager()
