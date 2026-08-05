from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, Dict, Optional, TypedDict

class LogSource(str,Enum):
  FRONTEND = 'frontend'
  BACKEND = 'backend'
  SYSTEM = 'system'
  NETWORK = 'network'
  AI_SERVICE = 'ai_service'
  UNKNOWN = 'unknown'

class LogLevel:
  DEBUG = "debug"
  INFO = "info"
  WARNING = "warning"
  ERROR = "error"
  CRITICAL = "critical"

  @staticmethod
  def from_logging_level(level: int) -> str:
    if level >= logging.CRITICAL:
        return LogLevel.CRITICAL
    elif level >= logging.ERROR:
        return LogLevel.ERROR
    elif level >= logging.WARNING:
        return LogLevel.WARNING
    elif level >= logging.INFO:
        return LogLevel.INFO
    else:
        return LogLevel.DEBUG

class AnimationStyle(TypedDict):
  braille: list[str]
  spinner: list[str]
  dots: list[str]
  arrows: list[str]
  moon: list[str]
  clock: list[str]
  directional_arrows_unicode: list[str]
  traffic_lights: list[str]
  growth_emoji: list[str]
  weather_icons: list[str]
  heartbeat: list[str]

@dataclass
class LoggerRecord:
  timestamp:str
  level:str
  log_name:str
  message:str
  source: Optional[LogSource] = None
  stack_trace: Optional[str] = None
  metadata: Optional[Dict[str, Any]] = None

  @classmethod
  def from_logging_record(cls, record):
    from datetime import datetime
    # 提取额外信息
    metadata = {}
    if hasattr(record, 'pathname'):
        metadata.update({
            'pathname': record.pathname,
            'lineno': record.lineno,
            'funcName': record.funcName,
            'module': record.module
        })
    # 如果有异常信息
    exc_text = None
    if record.exc_info and record.exc_info != (None, None, None):
        import traceback
        exc_text = ''.join(traceback.format_exception(*record.exc_info))
    return cls(
        timestamp=datetime.fromtimestamp(record.created).isoformat(),
        level=LogLevel.from_logging_level(record.levelno),
        message=record.getMessage(),
        log_name=record.name,
        source=LogSource.BACKEND,
        stack_trace=exc_text,
        metadata=metadata
    )