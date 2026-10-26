from enum import Enum
import logging

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