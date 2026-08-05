from modules.runtime import RuntimePath
from modules.services.config import BrowserConfig, Live2DConfig, ObsConfig, QQBotConfig
from modules.services import ServiceId
from modules.utils.file import write_yaml


def generate_default_config_file():
    service_config={
        ServiceId.LIVE2D:Live2DConfig().to_dict(),
        ServiceId.BROWSER:BrowserConfig().to_dict(),
        ServiceId.OBS:ObsConfig().to_dict(),
        ServiceId.QQBOT:QQBotConfig().to_dict(),
    }
    write_yaml(
        RuntimePath.get_service_config_file_path(),
        service_config
    )