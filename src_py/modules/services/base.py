from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Literal, Optional

from ..pipeline.models import ServiceTool
from .config import BaseServiceConfig


class ServiceState:
    """服务状态（字符串常量，JSON 直接可序列化）。"""

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    NOT_ENABLED = "not_enabled"
    ERROR = "error"

    @classmethod
    def values(cls) -> List[str]:
        return [
            cls.CREATED,
            cls.RUNNING,
            cls.STOPPED,
            cls.NOT_ENABLED,
            cls.ERROR,
        ]

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in (cls.STOPPED, cls.ERROR)


class ServiceLifecycleHook:
    """生命周期钩子，子类按需覆盖。"""

    def on_config_change(self, old_config: Dict, new_config: Dict) -> None:
        """配置被更新时回调（ServiceManager.update_config 触发）。"""

    def on_health_check_failed(self) -> None:
        """健康检查失败时回调。默认什么都不做，由 ServiceManager 记录状态。"""


class BaseService(ABC, ServiceLifecycleHook):
    name: str = ""
    description: str = ""
    main_thread: bool = False

    # 装饰器会保留原方法为 *_original
    start_original: Callable
    stop_original: Callable
    close_original: Callable

    state: Literal["created", "running", "stopped", "error"] = "stopped"

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any):
        with cls._lock:
            if getattr(cls, "_instance", None) is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # S3：重复构造不能把已启动的驱动清掉
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.config: Optional["BaseServiceConfig"] = None
        # S4：总是创建；是否起线程由 ServiceManager 决定
        self.stop_event = threading.Event()
        self.state = "created"

    # ---------- 状态 ----------

    def set_status(self, state: Optional[Literal["created", "running", "stopped", "error"]] = None) -> None:
        """设置状态；不传参时按 `running` 属性推断（兼容既有子类）。"""
        if state is not None:
            self.state = state
            return
        running = getattr(self, "running", None)
        if running is None:
            return
        self.state = "running" if running else "stopped"

    def get_status(self):
        return self.state

    # 便于 ServiceManager / API 统一取值
    status = property(get_status)

    # ---------- 生命周期 ----------

    @abstractmethod
    def start(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def stop(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def close(self, *args: Any, **kwargs: Any) -> Any:
        """S5：释放资源。默认转调 stop，子类可覆盖。"""
        try:
            return self.stop(*args, **kwargs)
        finally:
            self.state = ServiceState.STOPPED

    @abstractmethod
    def get_tools(self) -> ServiceTool:
        raise NotImplementedError

    # ---------- 单例控制 ----------

    @classmethod
    def reset_instance(cls) -> None:
        """S3：清空单例，允许重建（测试 / 配置热重载用）。"""
        with cls._lock:
            cls._instance = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "state": self.state,
            "main_thread": bool(self.main_thread),
        }
