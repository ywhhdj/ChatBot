"""配置加载与保存"""

from typing import Any, Dict, List, Optional, Tuple

from . import models
from ..utils.file import env

CONFIG_BINDINGS: List[Tuple[str, List[str]]] = [
    ("SYSTEM", ["log", "network"]),
    ("DATABASE", ["sqlite"]),
    ("MODEL", ["llm", "tts"]),
    ("WEB", ["web"]),
    ("SKILLS", ["skills"]),
    ("ASR", ["asr"]),
]


def _normalize_section(section: str) -> str:
    return str(section or "").strip().upper()


class ConfigLoader:
    """配置加载器 —— 负责从文件加载配置。"""

    def __init__(self, config_file_path: Optional[str] = None):
        self.config_file_path = config_file_path

    def load(self, config_file_path: Optional[str] = None) -> models.AppConfig:
        file_path = config_file_path or self.config_file_path
        config = models.AppConfig()
        if not file_path:
            return config
        try:
            config_dict = env.read_env(file_path)
        except Exception as exc:
            from ..logger import logger

            logger.warning(f"[Config] 读取配置失败，使用默认值: {exc}")
            return config

        if not config_dict:
            return config
        self.__apply_config(config, config_dict)
        return config

    def __apply_config(self, config: models.AppConfig, config_dict: Dict[str, Any]) -> None:
        for section, section_data in config_dict.items():
            if not isinstance(section_data, dict):
                continue
            attr_names = self._get_binding_attrs(section)
            if not attr_names:
                continue
            for attr_name in attr_names:
                config_obj = getattr(config, attr_name, None)
                if config_obj is None:
                    continue
                if isinstance(config_obj, models._BaseConfig):
                    config_obj.update_from_dict(section_data)

    @staticmethod
    def _get_binding_attrs(section: str) -> List[str]:
        """C10：比较前把**两侧**都规范化成大写。

        原实现只把配置文件的 section 转大写，绑定表却是小写的 ->
        除了恰好叫 "MCP" 的那一项，其余全部匹配失败。
        """
        wanted = _normalize_section(section)
        for bind_section, attrs in CONFIG_BINDINGS:
            if _normalize_section(bind_section) == wanted:
                return attrs
        return []


class ConfigManager:
    __instance = None
    __config: Optional[models.AppConfig] = None
    __loader: Optional[ConfigLoader] = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def initialize(self, config_file_path: Optional[str] = None, debug: bool = False) -> models.AppConfig:
        """C12：debug 不再决定是否读文件。

        原实现 `if config_file_path is None or debug: self.__config = AppConfig()`，
        导致以 debug 启动时全部配置回落默认值（空 api_key），LLM 无法工作。
        debug 现在只影响默认日志级别。
        """
        self.__loader = ConfigLoader(config_file_path)
        if config_file_path is None:
            self.__config = models.AppConfig()
        else:
            self.__config = self.__loader.load(config_file_path)

        if debug:
            log_cfg = getattr(self.__config, "log", None)
            if log_cfg is not None and not log_cfg.level:
                log_cfg.level = "DEBUG"
        return self.__config

    def get_config(self) -> models.AppConfig:
        if self.__config is None:
            self.__config = models.AppConfig()
        return self.__config

    def reload(self) -> models.AppConfig:
        if self.__loader is None:
            raise RuntimeError("Config loader not initialized.")
        self.__config = self.__loader.load()
        return self.__config
    
    def get_default_config(self) -> models.AppConfig:
        return models.AppConfig()

    def save_config(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("Config file path is required")
        serialized = self.__serialize_config(self.get_config())
        env.write_env(file_path, serialized)

    def __serialize_config(self, config: models.AppConfig) -> Dict[str, Dict[str, Any]]:
        """把 attr 的字段**平铺**进 section。"""
        result: Dict[str, Dict[str, Any]] = {}
        for section, attrs in CONFIG_BINDINGS:
            section_data: Dict[str, Any] = {}
            for attr_name in attrs:
                config_obj = getattr(config, attr_name, None)
                if isinstance(config_obj, models._BaseConfig):
                    section_data.update(config_obj.to_dict())
            if section_data:
                result[section] = section_data
        return result
