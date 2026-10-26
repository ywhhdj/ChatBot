from __future__ import annotations

import os
import sys
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
        # S9/S14：仅当 env 未设置时写入默认值，且不再依赖 CWD。
        # 之后 set_mode("prod") 改的是 Mode，不会把已经固化的路径改回去，
        # 但也不会因为 dev 模式而在每次调用时覆盖用户显式设置的值。
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
    def get_defaults_dir(cls) -> Path:
        return cls.get_resources_dir() / "defaults"

    @classmethod
    def get_roles_dir(cls) -> Path:
        return cls.get_resources_dir() / "roles"

    @classmethod
    def get_user_data_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            return cls.get_app_root() / "var" / "data"
        return cls.get_app_root() / "data"

class RuntimePath:
    model_dir=StandardPaths.get_models_dir()
    roles_dir=StandardPaths.get_roles_dir()
    memory_dir=StandardPaths.get_user_data_dir()/"memory"

    #更新路径，给用户实时更新
    @staticmethod
    def update_model_dir(new_dir: Path):
        RuntimePath.model_dir=new_dir

    @staticmethod
    def update_roles_dir(new_dir: Path):
        RuntimePath.roles_dir=new_dir

    @staticmethod
    def update_memory_dir(new_dir: Path):
        RuntimePath.memory_dir=new_dir

    @staticmethod
    def get_models_path(subpath: str = "") -> Path:
        return RuntimePath.model_dir / subpath

    @staticmethod
    def get_service_config_file_path():
        return StandardPaths.get_defaults_dir() / "services.yaml"

    @staticmethod
    def get_pipeline_config_file_path():
        return StandardPaths.get_defaults_dir() / "pipeline.json"

    @staticmethod
    def get_icon_file_path(icon_name: str="chatbot.ico"):
        return RuntimePath.get_web_resources_dir(f"icons/{icon_name}")

    @staticmethod
    def get_user_data_path(relative_path: str = "") -> Path:
        return ensure_dir(StandardPaths.get_user_data_dir() / relative_path)

    @staticmethod
    def get_web_resources_dir(relative_path: str="") -> Path:
        return StandardPaths.get_app_root()/"static" / relative_path

    @staticmethod
    def get_prompts_file_path() -> Path:
        return StandardPaths.get_defaults_dir() / "prompts.toml"
    
    @staticmethod
    def get_ppt_template_file_path(relative_path: str="",is_defaults: bool=False) -> Path:
        if is_defaults:
            return StandardPaths.get_defaults_dir() / "ppt_templates.yaml"
        return ensure_dir(RuntimePath.model_dir / relative_path)
    
    @staticmethod
    def get_roles_file_path(relative_path: str="",is_defaults: bool=False) -> Path:
        if is_defaults:
            return StandardPaths.get_defaults_dir() / "roles.yaml"
        return ensure_dir(RuntimePath.roles_dir / relative_path)

    @staticmethod
    def get_scripts_path(subpath: str = "") -> Path:
        return StandardPaths.get_scripts_dir() / subpath
    
    @staticmethod
    def get_memory_db_path() -> Path:
        return ensure_dir(
            RuntimePath.get_user_data_path("memory").parent
        ) / "memory" / "memory.db"
    
    @staticmethod
    def get_sql_file_path():
        return StandardPaths.get_defaults_dir() / "memory.sql"
    
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

T = TypeVar("T", bound=BaseManager)


def  get_logging():
    from .logger import logger
    return logger

#运行时管理器
class RuntimeManager:
    """运行时管理器和管理器的生命周期管理"""
    _instance= None

    def __init__(self):
        self._running = False
        from .manager.character import CharacterManager
        from .manager.session.manager import SessionManager
        self.character_manager = CharacterManager()
        self.session_manager = SessionManager()
        self._instance = self
    
    def __new__(cls,*args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def init(self):
        if self._running:
            return
        self._start_schedular_task()
        self._register_all_ops()
        from .manager.saves.manager import SaveSlotManager
        self.save_manager = SaveSlotManager()
        self._running = True
    
    def _register_all_ops(self):
        # 把所有 API 端点注册进进程内网关。
        # 桌面端 Bridge 与 Web 控制器共用同一张 op 表、同一套信封。
        try:
            from .api.ops import register_all
            register_all()
        except Exception as e:
            logger = get_logging()
            logger.exception(f"[App] register api ops error: {e}", exc_info=True)
    
    def _start_schedular_task(self):
        try:
            from .events.bus import LeakProofEventBus
            from .core.native import get_scheduler
            self.scheduler = get_scheduler()
            self.event_bus = LeakProofEventBus()
        except Exception as e:
            get_logging().error(f"[App] inject async fallback failed: {e}")

    def _save_saves(self):
        logger = get_logging()
        try:
            try:
                self.save_manager.save_slot()
            except Exception as e:
                logger.debug(f"[App] import saves error: {e}")
                self.save_manager.save_slot()
                logger.info("[App] 存档已保存")
        except Exception as e:
            logger.exception(f"[App] save slot error: {e}", exc_info=True)

    def stop(self):
        if not self._running:
            return
        self._running = False
        self.scheduler.stop()
        if self.event_bus:
            self.event_bus.clear()
            self.event_bus = None
    

manager=None
#延迟初始化
def instance() -> "RuntimeManager":
    global manager
    if manager is None:
        manager=RuntimeManager()
    return manager