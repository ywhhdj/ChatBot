from modules.runtime import RuntimePath
from modules.services.config import get_service_classes
from src_py.modules.services.keys import ServiceId
from modules.utils.file import yaml


def generate_ui_config_file():
    service_config={}
    for service_id in [
        ServiceId.LIVE2D,
        ServiceId.BROWSER,
        ServiceId.OBS,
        ServiceId.QQBOT
    ]:
        service_config[service_id] = get_service_classes(service_id)().to_dict()
    yaml.write_yaml(
        RuntimePath.get_service_config_file_path(),
        service_config
    )