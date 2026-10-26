from dataclasses import dataclass
from typing import Any, Dict
from ..config.models import AppConfig
from ..services.config import ServiceConfig

@dataclass
class UserConfig:
    app: AppConfig = AppConfig()
    service: ServiceConfig = ServiceConfig()
    ui:Dict[str, Any] = {}

@dataclass
class User:
    save_path: str = ""
    session_path: str = ""
    tmp_session_path: str = ""
    config_path: UserConfig = UserConfig()
