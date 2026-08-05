from __future__ import annotations
import os
from pathlib import Path
import sys

class StandardPaths:
    APP_ROOT_ENV = "APP_ROOT"

    @classmethod
    def get_app_root(cls) -> Path:
        env_root = os.environ.get(cls.APP_ROOT_ENV)
        if env_root:
            return Path(env_root).resolve()
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent.parent  # bin/ 上一级
        return Path(__file__).parent.parent.resolve()

    @classmethod
    def get_resources_dir(cls) -> Path:
        if getattr(sys, 'frozen', False):
            return cls.get_app_root() / "share" / "resources"
        return cls.get_app_root() / "resources"

    @classmethod
    def get_models_dir(cls) -> Path:
        return cls.get_resources_dir() / "models"

    @classmethod
    def get_scripts_dir(cls) -> Path:
        if getattr(sys, 'frozen', False):
            return cls.get_resources_dir() / "scripts"
        return Path(os.path.abspath("."))

    @classmethod
    def get_defaults_dir(cls) -> Path:
        return cls.get_resources_dir() / "defaults"

    @classmethod
    def get_roles_dir(cls) -> Path:
        return cls.get_resources_dir() / "roles"
    
    @classmethod
    def get_user_data_dir(cls) -> Path:
        if getattr(sys, 'frozen', False):
            return cls.get_app_root() / "var" / "data"
        return cls.get_app_root() / "data"

class RuntimePath:

    STATIC_PATH = StandardPaths.get_app_root()/"static"

    @staticmethod
    def get_models_path(subpath: str = "") -> str:
        return str(StandardPaths.get_models_dir() / subpath)

    @staticmethod
    def get_service_config_file_path():
        return str(StandardPaths.get_defaults_dir() / "services.yaml")

    @staticmethod
    def get_pipeline_config_file_path():
        return str(StandardPaths.get_defaults_dir() / "pipeline.json")

    @staticmethod
    def get_icon_file_path():
        return str(RuntimePath.STATIC_PATH / "icons/chatbot.ico")

    @staticmethod
    def get_user_data_path(relative_path: str=""):
        return str(StandardPaths.get_resources_dir() / relative_path)

    @staticmethod
    def get_static_path(relative_path: str=""):
        return str(RuntimePath.STATIC_PATH / relative_path)

    @staticmethod
    def get_prompts_file_path():
        return str(StandardPaths.get_defaults_dir() / "prompts.toml")
    
    @staticmethod
    def get_roles_file_path(relative_path: str=""):
        return str(StandardPaths.get_roles_dir() / relative_path)
    
    @staticmethod
    def get_scripts_path(subpath: str = "") -> str:
        return str(StandardPaths.get_scripts_dir() / subpath)
    
    @staticmethod
    def get_memory_db_path() -> str:
        return str(StandardPaths.get_user_data_dir() /"memory" / "memory.db")
    
    @staticmethod
    def get_sql_file_path():
        return str(StandardPaths.get_defaults_dir() / "memory.sql.sql")
    
    @staticmethod
    def get_log_dir():
        if getattr(sys, 'frozen', False):
            path= StandardPaths.get_app_root()/"var" / "log"
        else:
            path= StandardPaths.get_app_root() / "log"
        return str(path)

if __name__ == "__main__":
    print(StandardPaths.get_scripts_dir())