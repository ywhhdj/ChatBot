from abc import ABC, abstractmethod
from threading import Lock
import threading
from typing import Callable, Optional, Dict
from ..tools.models import ServiceTool

class ServiceState:
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    NOT_ENABLED = "not_enabled"
    ERROR = "error"

class ServiceLifecycleHook:
    def on_config_change(self, old_config: Dict, new_config: Dict) -> None:
        pass
    
    def on_health_check_failed(self) -> None:
        pass

class _BaseService(ABC, ServiceLifecycleHook):
    name: str
    description: str
    main_thread: bool = False
    start_original:Callable
    stop_original:Callable
    close_original:Callable
    state= ServiceState.NOT_ENABLED
    # status: str = ServiceState.NOT_ENABLED
    def __init__(self):
        _BaseService.state = ServiceState.CREATED
        self.config=None
        self.stop_event = threading.Event() if not self.main_thread else None

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    # @abstractmethod
    # def close(self) -> None:
    #     raise NotImplementedError
    
    @staticmethod
    def get_status() -> str:
        return _BaseService.state
    
    #允许的工具命令
    @abstractmethod
    def get_tools(self) -> Optional[ServiceTool]:
        raise NotImplementedError