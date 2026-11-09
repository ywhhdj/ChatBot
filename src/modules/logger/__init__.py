"""日志包入口"""
from .log import Logger, OptimizedBatchLogHandler
from .models import LogLevel, LogSource, LoggerRecord, redact
from . import audit, trail


def create_logger(app_name: str) -> Logger:
    from ..config import get_config

    config = get_config()
    kwargs = {
        "level": Logger.normalize_level(
            getattr(config.log, "level", LogLevel.INFO) or LogLevel.INFO
        ),
        "enable_file": bool(getattr(config.log, "enable_log_file", False)),
        "log_dir": getattr(config.log, "log_dir", "logs") or "logs",
        "format": getattr(config.log, "format", None) or "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "datefmt": getattr(config.log, "datefmt", None) or "%Y-%m-%d %H:%M:%S",
    }
    log = Logger(name=app_name, **kwargs)
    log.reconfigure(app_name=app_name, **kwargs)
    return log


logger = create_logger("app")


def get_logger() -> Logger:
    return logger


__all__ = [
    "Logger",
    "OptimizedBatchLogHandler",
    "LogLevel",
    "LogSource",
    "LoggerRecord",
    "redact",
    "audit",
    "trail",
    "create_logger",
    "get_logger",
    "logger",
]
