from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Literal, TypeVar

from .manager.base import BaseManager

Mode: Literal["dev", "prod"] = "dev"

APP_ROOT_ENV = "APP_ROOT"

# 本文件位于 <app_root>/src_py/modules/runtime.py
_PACKAGE_PARENT = Path(__file__).resolve().parent.parent.parent


def is_dev_mode() -> bool:
    return Mode == "dev"


def set_mode(mode: Literal["dev", "prod"]) -> None:
    global Mode
    Mode = mode


def ensure_dir(path: Path) -> Path:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path


def _default_root() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller: <root>/bin/<exe> → 上两级
        return Path(sys.executable).resolve().parent.parent
    return _PACKAGE_PARENT


class StandardPaths:
    APP_ROOT_ENV = APP_ROOT_ENV

    @classmethod
    def get_app_root(cls) -> Path:
        """应用根目录。优先级：环境变量 > frozen 推导 > 包位置推导。"""
        env_root = os.environ.get(cls.APP_ROOT_ENV)
        if env_root:
            return Path(env_root).resolve()

        root = _default_root()
        try:
            os.environ.setdefault(cls.APP_ROOT_ENV, str(root))
        except Exception:
            pass
        return root

    # ---------- 资源目录 ----------

    @classmethod
    def get_resources_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            return cls.get_app_root() / "share" / "resources"
        return cls.get_app_root() / "resources"

    @classmethod
    def get_models_dir(cls) -> Path:
        return cls.get_resources_dir() / "models"

    @classmethod
    def get_scripts_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            return cls.get_resources_dir() / "scripts"
        return cls.get_app_root() / "scripts"

    @classmethod
    def get_configs_dir(cls) -> Path:
        return cls.get_resources_dir() / "configs"
    
    @classmethod
    def get_template_dir(cls) -> Path:
        return cls.get_template_dir()

    @classmethod
    def get_user_data_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            return cls.get_app_root() / "var" / "data"
        return cls.get_app_root() / "data"


class RuntimePath:
    model_dir = StandardPaths.get_models_dir()
    # roles_dir = StandardPaths.get_roles_dir()
    memory_dir = StandardPaths.get_user_data_dir() / "memory"

    @staticmethod
    def update_model_dir(new_dir: Path):
        RuntimePath.model_dir = new_dir

    # @staticmethod
    # def update_roles_dir(new_dir: Path):
    #     RuntimePath.roles_dir = new_dir

    @staticmethod
    def update_memory_dir(new_dir: Path):
        RuntimePath.memory_dir = new_dir

    @staticmethod
    def get_models_path(subpath: str = "") -> Path:
        return RuntimePath.model_dir / subpath

    @staticmethod
    def get_service_config_file_path():
        return StandardPaths.get_configs_dir() / "services.yaml"

    @staticmethod
    def get_provider_path(relative_path: str = ""):
        return StandardPaths.get_configs_dir() / "providers"/ relative_path

    @staticmethod
    def get_icon_file_path(icon_name: str = "chatbot.ico"):
        return RuntimePath.get_web_resources_dir(f"icons/{icon_name}")

    @staticmethod
    def get_user_data_path(relative_path: str = "") -> Path:
        return ensure_dir(StandardPaths.get_user_data_dir() / relative_path)

    @staticmethod
    def get_web_resources_dir(relative_path: str = "") -> Path:
        return StandardPaths.get_app_root() / "static" / relative_path

    @staticmethod
    def get_prompts_file_path() -> Path:
        return StandardPaths.get_configs_dir() / "prompts.toml"

    @staticmethod
    def get_template_path(relative_path: str = "") -> Path:
        return StandardPaths.get_template_dir() / relative_path

    @staticmethod
    def get_scripts_path(subpath: str = "") -> Path:
        return StandardPaths.get_scripts_dir() / subpath

    @staticmethod
    def get_memory_db_path() -> Path:
        return RuntimePath.get_user_data_path("memories") / "memories.db"

    @staticmethod
    def get_memories_path(relative_path:str) -> Path:
        return StandardPaths.get_configs_dir()/ "memories"/ relative_path

    @staticmethod
    def get_sql_file_path():
        return RuntimePath.get_memories_path("schema.sql")

    @staticmethod
    def get_log_dir() -> Path:
        if getattr(sys, "frozen", False):
            path = StandardPaths.get_app_root() / "var" / "log"
        else:
            path = StandardPaths.get_app_root() / "log"
        return ensure_dir(path)

    @staticmethod
    def get_save_dir() -> Path:
        return ensure_dir(RuntimePath.get_user_data_path("saves"))

    @staticmethod
    def get_skill_dir():
        return StandardPaths.get_app_root() / "skills"

    # ---------- 工作区（权威判定在 security/workspace） ----------

    @staticmethod
    def get_workspace_dir() -> Path:
        from .security.workspace import default_workspace_root

        return Path(default_workspace_root())


T = TypeVar("T", bound=BaseManager)


def get_logging():
    from .logger import logger
    return logger


class _NoopScheduler:
    """调度器不可用时的最小兜底：submit 直接在调用方执行。"""

    def __init__(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return False

    def start(self) -> None:
        self._running = True

    def stop(self, *args, **kwargs) -> None:
        self._running = False

    def submit(self, func, *args, **kwargs):
        class _Ref:
            def __init__(self, value):
                self.value = value

            def result(self, timeout=None):
                return self.value

            def wait_async(self, timeout=None):
                async def _done():
                    return self.value
                return _done()

        return _Ref(func(*args, **kwargs))


class RuntimeManager:
    """运行时管理器：事件总线 / 调度器 / 网关 / 存档门面的唯一持有者"""
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        if getattr(self, "_rt_initialized", False):
            return
        self._rt_initialized = True
        self._running = False

        self.scheduler = None
        self.task_manager = None       # 与 scheduler 同一个对象，供 API 层读取
        self.event_bus = None
        self.save_manager = None

        from .characters.manager import CharacterManager
        from .manager.session.manager import SessionManager

        self.character_manager = CharacterManager()
        self.session_manager = SessionManager()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        if self._running:
            return
        self._start_schedular_task()
        self._register_all_ops()
        try:
            from .manager.saves.manager import SaveSlotManager

            self.save_manager = SaveSlotManager()
        except Exception as e:  # noqa: BLE001
            get_logging().warning(f"[App] save manager init failed: {e}")
            self.save_manager = None
        self._running = True

    def _register_all_ops(self):
        # 把所有 API 端点注册进进程内网关。
        # 桌面端 Bridge 与 Web 控制器共用同一张 op 表、同一套信封。
        try:
            from .api.ops import register_all

            register_all()
        except Exception as e:
            get_logging().exception(f"[App] register api ops error: {e}", exc_info=True)

    def _start_schedular_task(self):
        try:
            from .events.bus import LeakProofEventBus
            from .core.native import get_scheduler

            self.scheduler = get_scheduler()
            self.event_bus = LeakProofEventBus()
        except Exception as e:
            get_logging().error(f"[App] inject async fallback failed: {e}")
            try:
                from .events.bus import LeakProofEventBus

                self.event_bus = LeakProofEventBus()
            except Exception:
                self.event_bus = None
            if self.scheduler is None:
                self.scheduler = _NoopScheduler()
        self.task_manager = self.scheduler

    def _save_saves(self):
        """退出前保存存档。失败只记录，绝不阻塞关机。"""
        log = get_logging()
        mgr = getattr(self, "save_manager", None)
        if mgr is None:
            log.debug("[App] 存档管理器未就绪，跳过退出保存")
            return
        try:
            mgr.save_slot()
            log.info("[App] 存档已保存")
        except Exception as e:  # noqa: BLE001
            log.warning(f"[App] save slot error: {e}")

    def stop(self):
        if not self._running:
            return
        self._running = False
        scheduler = getattr(self, "scheduler", None)
        if scheduler is not None:
            try:
                scheduler.stop()
            except Exception as e:  # noqa: BLE001
                get_logging().debug(f"[App] scheduler stop failed: {e}")
        bus = getattr(self, "event_bus", None)
        if bus is not None:
            try:
                bus.clear()
            except Exception:
                pass


manager = None
# 延迟初始化
def instance() -> RuntimeManager:
    global manager
    obj = RuntimeManager._instance
    if obj is None:
        obj = RuntimeManager()
    manager = obj
    return obj
