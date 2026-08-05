from .log import Logger
from .types import LogLevel,LogSource,LoggerRecord

def create_logger(app_name: str) -> Logger:
    from ..config import get_config
    config = get_config()
    return Logger(
        app_name, 
        enable_file=config.log.enable_log_file,
        log_dir=config.log.log_dir,
        format=config.log.format,
        datefmt=config.log.datefmt
    )

logger = create_logger("app")
logger.init()

