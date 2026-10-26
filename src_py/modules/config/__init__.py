from typing import Optional

from .manager import ConfigManager as _ConfigManager

CONFIG_PATH = "config.json"

_config_manager = _ConfigManager()


def get_config():
    return _config_manager.get_config()

def get_default_config():
    return _config_manager.get_default_config()


def load_config(
    config_file_path: Optional[str] = None,
    debug: bool = False
):
    _config_manager.initialize(config_file_path, debug)
    return get_config()


def reload_config():
    return _config_manager.reload()


def save_config(file_path: str):
    _config_manager.save_config(file_path)
