"""日志记录的数据模型。"""

from dataclasses import dataclass
from enum import Enum
import logging
import re
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

#: 单条日志正文上限。超长通常是把整个 prompt / 响应 / 二进制转储打进来了。
MAX_MESSAGE_CHARS = 8000
#: 单条堆栈上限。
MAX_STACK_CHARS = 12000
REDACTED = "[REDACTED]"

_SECRET_ASSIGN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|"
    r"password|passwd|authorization|credential)\b(\s*[=:]\s*)"
    r"(?!bearer\b)([^\s,;\"'}\]]{4,})"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}")
_SK_LIKE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")


def _scrub(text: str) -> str:
    """顺序敏感：Bearer 整段 → 键=值 → sk- 形态。"""
    raw = _BEARER.sub(f"Bearer {REDACTED}", str(text or ""))
    raw = _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", raw)
    return _SK_LIKE.sub(REDACTED, raw)


def redact(text: Any) -> str:
    raw = _scrub(str(text or ""))
    if len(raw) > MAX_MESSAGE_CHARS:
        raw = raw[:MAX_MESSAGE_CHARS] + "…[truncated]"
    return raw


def _short_stack(text: Optional[str]) -> str:
    if not text:
        return ""
    value = _scrub(str(text))
    if len(value) > MAX_STACK_CHARS:
        value = value[:MAX_STACK_CHARS] + "…[truncated]"
    return value


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
  timestamp: str
  level: str
  log_name: str
  message: str
  source: Optional[LogSource] = None
  stack_trace: Optional[str] = None
  metadata: Optional[Dict[str, Any]] = None

  def to_dict(self) -> Dict[str, Any]:
    """给 WebSocket / REST 的前端结构。新增 ``stack_trace`` 是增量字段，
    旧前端忽略即可，不影响既有 6 个字段。
    """
    out = {
        "log_name": self.log_name,
        "timestamp": self.timestamp,
        "level": self.level,
        "message": self.message,
        "source": (
            self.source.value if isinstance(self.source, LogSource)
            else str(self.source or LogSource.BACKEND.value)
        ),
        "metadata": self.metadata or {},
    }
    if self.stack_trace:
        out["stack_trace"] = self.stack_trace
    return out

  def file_line(self) -> str:
    """落盘的一行（含堆栈），统一由本方法生成，避免三路格式各自漂移。"""
    head = f"[{self.log_name}] {self.timestamp} [{self.level}] {self.message}\n"
    if self.stack_trace:
        # 堆栈每行加前缀，方便 grep 时与普通日志区分
        tail = "".join(
            f"    | {line}\n" for line in self.stack_trace.splitlines()
        )
        return head + tail + "    | --- end traceback ---\n"
    return head

  @classmethod
  def from_logging_record(cls, record: Any) -> "LoggerRecord":
    from datetime import datetime
    import traceback

    metadata: Dict[str, Any] = {}
    if hasattr(record, "pathname"):
        metadata.update({
            "pathname": record.pathname,
            "lineno": record.lineno,
            "funcName": record.funcName,
            "module": record.module,
        })

    exc_text: Optional[str] = None
    if record.exc_info and record.exc_info != (None, None, None):
        try:
            exc_text = _short_stack(
                "".join(traceback.format_exception(*record.exc_info))
            )
        except Exception:  # noqa: BLE001 - 格式化失败不该丢掉整条日志
            exc_text = None

    try:
        message = redact(record.getMessage())
    except Exception:  # noqa: BLE001 - args 格式化失败时退回原始 msg
        message = redact(getattr(record, "msg", ""))

    return cls(
        timestamp=datetime.fromtimestamp(record.created).isoformat(),
        level=LogLevel.from_logging_level(record.levelno),
        message=message,
        log_name=record.name,
        source=LogSource.BACKEND,
        stack_trace=exc_text,
        metadata=metadata,
    )
