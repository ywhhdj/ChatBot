from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field
from typing import List, Tuple

from . import models
from ..services import config

class AppConfig(BaseModel):
    web: models.WebConfig = Field(default_factory=models.WebConfig)
    log: models.LogConfig = Field(default_factory=models.LogConfig)
    network: models.NetworkConfig = Field(default_factory=models.NetworkConfig)
    sqlite: models.SqliteConfig = Field(default_factory=models.SqliteConfig)
    llm: models.LLMConfig = Field(default_factory=models.LLMConfig)
    tts: models.TTSConfig = Field(default_factory=models.TTSConfig)
    asr: models.ASRConfig = Field(default_factory=models.ASRConfig)
    skills: models.SkillsConfig = Field(default_factory=models.SkillsConfig)
    debug:bool=True

    
# 配置绑定映射: (section_name, [attr_names])
CONFIG_BINDINGS: List[Tuple[str, List[str]]] = [
    ("system", ["log", "network"]),
    ("database", ["sqlite"]),
    ("model", ["llm", "tts"]),
    ("services", ["obs", "live2d", "browser", "livestream"]),
    ("web", ["web"]),
    ("skills", ["skills"]),
    ("MCP", ["mcp"]),
]

class ConfigLoader:
    """配置加载器 - 负责从文件加载配置"""
    def __init__(self, config_file_path: Optional[str] = None):
        self.config_file_path = config_file_path
        
    def load(self, config_file_path: Optional[str] = None):
        """
        加载配置
        
        Args:
            config_file_path: 配置文件路径，如果不传则使用初始化时的路径
            
        Returns:
            AppConfig实例
        """
        file_path = config_file_path or self.config_file_path
        if not file_path:
            raise ValueError("Config file path is required")
        config = AppConfig()
        # 尝试从文件加载
        from ..utils.file import read_env
        config_dict = read_env(file_path)
        if config_dict is None:
            return config
        # 应用配置
        self.__apply_config(config, config_dict)
        return config
    
    def __apply_config(self, config: AppConfig, config_dict: Dict[str, Dict[str, Any]]) -> None:
        """将字典配置应用到AppConfig对象"""
        for section, section_data in config_dict.items():
            if not isinstance(section_data, dict):
                continue
            # 查找对应的属性
            attrs = self.__get_binding_attrs(section)
            if not attrs:
                continue
            for attr_name in attrs:
                if not hasattr(config, attr_name):
                    continue
                config_obj = getattr(config, attr_name)
                if isinstance(config_obj, models._BaseConfig):
                    config_obj.update_from_dict(section_data)
    
    def __get_binding_attrs(self, section: str) -> List[str]:
        """获取section绑定的属性列表"""
        section_upper = section.upper()
        for bind_section, attrs in CONFIG_BINDINGS:
            if bind_section == section_upper:
                return attrs
        return []

class ConfigManager:
    __instance = None
    __config: Optional[AppConfig] = None
    __loader: Optional[ConfigLoader] = None
    
    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance
    
    def initialize(self, config_file_path: Optional[str] = None, debug: bool = False) :
        self.__loader = ConfigLoader(config_file_path)
        if config_file_path is None or debug:
            self.__config = AppConfig()
        else:
            self.__config = self.__loader.load(config_file_path)
        return self.__config
    
    def get_config(self):
        if self.__config is None:
            self.__config = AppConfig()
        return self.__config
    
    def reload(self):
        if self.__loader is None:
            raise RuntimeError("Config loader not initialized.")
        self.__config = self.__loader.load()
        return self.__config
    
    def save_config(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("Config file path is required")
        target_config= self.get_config()
        serialized = self.__serialize_config(target_config)
        from ..utils.file import write_env
        write_env(file_path, serialized)
    
    def __serialize_config(self, config: AppConfig) -> Dict[str, Dict[str, Any]]:
        """序列化配置为字典"""
        result: Dict[str, Dict[str, Any]] = {}
        for section, attrs in CONFIG_BINDINGS:
            section_data = {}
            for attr_name in attrs:
                config_obj = getattr(config, attr_name, None)
                if config_obj is not None and isinstance(config_obj, models._BaseConfig):
                    section_data[attr_name] = config_obj.to_dict()
            if section_data:
                result[section] = section_data
                
        return result
