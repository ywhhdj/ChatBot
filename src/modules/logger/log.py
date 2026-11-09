"""批量日志处理器 + Logger 门面。

线程模型
────────
业务线程 ──emit()──▶ 有界队列 ──▶ LoggerThread（唯一消费者）
                                    ├─ 控制台批量着色打印
                                    ├─ emit(GET_LOG) 事件（隔离 + 冷却）
                                    └─ IO 池按日批量落盘（每批 flush）

性能
* 控制台由「每条一次 print」改为「每批一次 write + 一次 flush」；
* 事件总线的 import 与符号查找缓存，失败后 5s 冷却，不再每条重试；
* 统计、句柄、队列操作都收敛到各自的锁，减少跨线程争用。
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import models
from ..models import TermColors

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

_MIN_QUEUE_LENGTH = 100
_MIN_BATCH_SIZE = 10
#: 同时打开的日志文件句柄上限（按天分文件，长跑不能无限累积）
_DEFAULT_MAX_OPEN_FILES = 8
#: 事件总线连续失败后的冷却，避免每条日志都做一次注定失败的调用
_EVENT_COOLDOWN_SECONDS = 5.0
#: 每多少次 emit 检查一次消费者线程是否还活着
_WATCHDOG_EVERY = 256


def _consume_future_exception(fut: Future) -> None:
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        print(f"Log writer error: {exc}", file=sys.stderr)


class _FlushBarrier:
    """放进日志队列的同步屏障"""

    def __init__(self) -> None:
        self.event = threading.Event()


class OptimizedBatchLogHandler(logging.Handler):
    """批量日志处理器。所有慢活都在消费者线程 / IO 池里做。"""

    def __init__(
        self,
        app_name: str,
        log_level: str = models.LogLevel.INFO,
        enable_log_file: bool = False,
        enable_console: bool = True,
        log_dir: str = "logs",
        max_length: int = 2000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        retention_days: int = 0,
        max_open_files: int = _DEFAULT_MAX_OPEN_FILES,
    ):
        super().__init__()
        self.app_name = app_name
        self.log_level = log_level
        self.enable_log_file = enable_log_file
        self.enable_console = enable_console
        self.log_dir = Path(log_dir)
        self.max_length = max(_MIN_QUEUE_LENGTH, int(max_length))
        self.batch_size = max(_MIN_BATCH_SIZE, min(int(batch_size), self.max_length // 2))
        self.flush_interval = max(0.05, float(flush_interval))
        self.retention_days = max(0, int(retention_days))
        self.max_open_files = max(1, int(max_open_files))
        self._log_queue: "queue.Queue[Any]" = queue.Queue(maxsize=self.max_length)
        self._current_batch: List[models.LoggerRecord] = []
        self._batch_lock = threading.RLock()

        self._stats_lock = threading.Lock()
        self.stats: Dict[str, Any] = {
            "logs_processed": 0,
            "batches_written": 0,
            "dropped_logs": 0,
            "handler_errors": 0,
            "event_push_failures": 0,
            "by_level": {},
        }

        self._file_handles: "OrderedDict[Path, Any]" = OrderedDict()
        self._file_locks: Dict[Path, threading.Lock] = {}
        self._file_lock = threading.RLock()
        self._io_pool: Optional[ThreadPoolExecutor] = None
        self._last_cleanup_date = ""

        self._running = False
        self._processor_thread: Optional[threading.Thread] = None
        self._emit_counter = 0
        self._event_api: Optional[Any] = None
        self._event_cooldown_until = 0.0
        self._event_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

        self.color_map = {
            models.LogLevel.DEBUG: TermColors.GREY,
            models.LogLevel.INFO: TermColors.GREEN,
            models.LogLevel.WARNING: TermColors.YELLOW,
            models.LogLevel.ERROR: TermColors.RED,
            models.LogLevel.CRITICAL: TermColors.RED,
        }

    # ---------- 采集（业务线程，必须极轻量） ----------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = models.LoggerRecord.from_logging_record(record)
        except Exception:
            self.bump_stat("handler_errors")
            return

        try:
            self._log_queue.put_nowait(entry)
        except queue.Full:
            with suppress(queue.Empty):
                self._log_queue.get_nowait()
                self.bump_stat("dropped_logs")
            try:
                self._log_queue.put_nowait(entry)
            except queue.Full:
                self.bump_stat("dropped_logs")
                return

        self._emit_counter += 1
        if self._emit_counter % _WATCHDOG_EVERY == 0:
            self._ensure_worker()

    def _put_control(self, item: Any) -> None:
        """放哨兵 / flush 屏障。队列满时丢最旧腾位，控制项绝不能被吞掉。"""
        try:
            self._log_queue.put_nowait(item)
            return
        except queue.Full:
            pass
        with suppress(queue.Empty):
            self._log_queue.get_nowait()
            self.bump_stat("dropped_logs")
        with suppress(Exception):
            self._log_queue.put_nowait(item)

    def _ensure_worker(self) -> None:
        """消费者意外退出后自动拉起，避免系统静默失明。"""
        if not self._running:
            return
        thread = self._processor_thread
        if thread is not None and thread.is_alive():
            return
        with self._lifecycle_lock:
            if not self._running:
                return
            thread = self._processor_thread
            if thread is not None and thread.is_alive():
                return
            self.bump_stat("handler_errors")
            self._processor_thread = threading.Thread(
                target=self._process_logs, name="LoggerThread", daemon=True
            )
            self._processor_thread.start()

    def bump_stat(self, key: str, delta: int = 1) -> None:
        with self._stats_lock:
            self.stats[key] = self.stats.get(key, 0) + delta

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = dict(self.stats)
            stats["by_level"] = dict(self.stats.get("by_level") or {})
        qsize = self._log_queue.qsize()
        processed = int(stats.get("logs_processed", 0))
        dropped = int(stats.get("dropped_logs", 0))
        stats.update({
            "queue_size": qsize,
            "total": processed,
            "dropped": dropped,
            "queue": qsize,
            "file_enabled": bool(self.enable_log_file),
            "console_enabled": bool(self.enable_console),
            "running": bool(self._running),
            "open_files": len(self._file_handles),
            "retention_days": self.retention_days,
        })
        return stats

    @property
    def is_running(self) -> bool:
        return bool(self._running)

    # ---------- 生命周期 ----------

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._running and self._processor_thread is not None \
                    and self._processor_thread.is_alive():
                return
            self._running = True
            if self.enable_log_file:
                try:
                    os.makedirs(self.log_dir, exist_ok=True)
                except Exception as exc:
                    print(f"Log dir create error: {exc}", file=sys.stderr)
                if self._io_pool is None:
                    self._io_pool = ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="LogWriter"
                    )
            self._processor_thread = threading.Thread(
                target=self._process_logs, name="LoggerThread", daemon=True
            )
            self._processor_thread.start()

    def _process_logs(self) -> None:
        """LoggerThread 主循环：逐批隔离异常，任何单批失败都不许杀死消费者。"""
        try:
            while True:
                try:
                    record = self._log_queue.get(timeout=self.flush_interval)
                except queue.Empty:
                    continue
                except Exception as exc:
                    self.bump_stat("handler_errors")
                    print(f"Log queue error: {exc}", file=sys.stderr)
                    continue

                if record is None:
                    # 停止哨兵：先排空残留再退出
                    with suppress(Exception):
                        self._drain_remaining()
                    break

                if isinstance(record, _FlushBarrier):
                    # 队列里排在屏障之前的记录都已被取走并处理完
                    with suppress(Exception):
                        with self._batch_lock:
                            self._flush_current_batch()
                    record.event.set()
                    continue

                logs = [record]
                barrier: Optional[_FlushBarrier] = None
                while len(logs) < self.batch_size:
                    try:
                        nxt = self._log_queue.get_nowait()
                    except queue.Empty:
                        break
                    except Exception:
                        break
                    if isinstance(nxt, _FlushBarrier):
                        barrier = nxt
                        break
                    if nxt is None:
                        # 哨兵不能被吞掉：放回队列，主循环下一轮会收到并 drain。
                        self._put_control(None)
                        break
                    logs.append(nxt)

                try:
                    self._handle_batch(logs)
                except Exception as exc:
                    self.bump_stat("handler_errors")
                    print(f"Log batch error: {exc}", file=sys.stderr)

                if barrier is not None:
                    with suppress(Exception):
                        with self._batch_lock:
                            self._flush_current_batch()
                    barrier.event.set()
        finally:
            with suppress(Exception):
                with self._batch_lock:
                    self._flush_current_batch()

    def _drain_remaining(self) -> None:
        """退出前把队列里剩余的日志处理完。"""
        pending: List[models.LoggerRecord] = []
        while True:
            try:
                record = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if record is None:
                continue
            if isinstance(record, _FlushBarrier):
                record.event.set()
                continue
            pending.append(record)
        if pending:
            self._handle_batch(pending)

    def _handle_batch(self, logs: List[models.LoggerRecord]) -> None:
        if not logs:
            return
        # 顺序很关键：先保证本地可见，再尝试推前端；事件总线失败不能吞掉日志。
        self._print_batch(logs)
        self._push_to_frontend(logs)

        with self._batch_lock:
            self._current_batch.extend(logs)
            if len(self._current_batch) >= self.batch_size:
                self._flush_current_batch()

        with self._stats_lock:
            self.stats["logs_processed"] = self.stats.get("logs_processed", 0) + len(logs)
            by_level = self.stats.setdefault("by_level", {})
            for log in logs:
                key = str(log.level or "unknown").lower()
                by_level[key] = by_level.get(key, 0) + 1

    # ---------- 输出 ----------

    def _print_batch(self, logs: List[models.LoggerRecord]) -> None:
        """每批一次 write + 一次 flush，而不是每条一次 print。"""
        if not self.enable_console:
            return
        lines: List[str] = []
        for log in logs:
            color = self.color_map.get(log.level, TermColors.WHITE)
            lines.append(
                f"[{log.log_name}] [{log.timestamp}] "
                f"{color}[{log.level.upper()}]{TermColors.RESET} {log.message}"
            )
            if log.stack_trace:
                lines.append(
                    "".join(f"    | {line}\n" for line in log.stack_trace.splitlines())
                    + "    | --- end traceback ---"
                )
        try:
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            # 无控制台（pythonw / 打包 GUI）时不再反复尝试
            self.enable_console = False
            print(f"Log print error (console disabled): {exc}", file=sys.stderr)

    def _push_to_frontend(self, logs: List[models.LoggerRecord]) -> None:
        """GET_LOG 事件推送：缓存导入、异常隔离、失败冷却。"""
        now = time.monotonic()
        if now < self._event_cooldown_until:
            return
        api = self._event_api
        if api is None:
            try:
                from ..events import emit as _emit
                from ..events.data import BaseEvent
                from ..events.types import WebSocketEventType

                api = (_emit, BaseEvent, WebSocketEventType.GET_LOG)
            except Exception:
                self.bump_stat("event_push_failures")
                self._event_cooldown_until = now + _EVENT_COOLDOWN_SECONDS
                return
            with self._event_lock:
                self._event_api = api
        try:
            _emit, BaseEvent, event_type = api
            for log in logs:
                _emit(BaseEvent(type=event_type, args=(log.to_dict(),)))
        except Exception:
            # 事件总线未就绪 / 监听器异常：只计数并冷却，绝不影响控制台与落盘
            self.bump_stat("event_push_failures")
            self._event_cooldown_until = now + _EVENT_COOLDOWN_SECONDS

    def _flush_current_batch(self) -> None:
        """调用方需持有 _batch_lock。"""
        if not self._current_batch:
            return
        batch = self._current_batch.copy()
        self._current_batch.clear()
        if self.enable_log_file and self._io_pool is not None:
            try:
                fut = self._io_pool.submit(self._write_batch_to_file, batch)
                fut.add_done_callback(_consume_future_exception)
            except Exception as exc:
                print(f"Batch write submit error: {exc}", file=sys.stderr)
                self.bump_stat("handler_errors")

    def flush(self) -> None:
        """强制落盘：先等消费者把队列里已有的日志全部处理完，再提交批次，
        最后等 IO 池把已提交任务全部做完。
        """
        thread = self._processor_thread
        worker_alive = (
            thread is not None
            and thread.is_alive()
            and threading.current_thread() is not thread
        )
        if worker_alive:
            barrier = _FlushBarrier()
            self._put_control(barrier)
            with suppress(Exception):
                barrier.event.wait(timeout=5.0)
        else:
            # 消费者未运行（未 start / 已退出 / 从消费者线程自身调用）
            with suppress(Exception):
                self._drain_remaining()

        with self._batch_lock:
            self._flush_current_batch()
        pool = self._io_pool
        if pool is None:
            return
        try:
            # 单线程池 FIFO：barrier 完成 == 之前所有写任务完成
            pool.submit(lambda: None).result(timeout=5.0)
        except Exception:
            pass

    # ---------- 落盘（IO 线程） ----------

    def _get_file_handle(self, filepath: Path):
        """按天分文件 + LRU 句柄上限，避免长跑累积文件描述符。"""
        with self._file_lock:
            fh = self._file_handles.get(filepath)
            if fh is None:
                os.makedirs(self.log_dir, exist_ok=True)
                fh = open(filepath, "a", encoding="utf-8", buffering=8192)
                self._file_handles[filepath] = fh
                self._file_locks[filepath] = threading.Lock()
                while len(self._file_handles) > self.max_open_files:
                    old_path, old_fh = self._file_handles.popitem(last=False)
                    with suppress(Exception):
                        old_fh.flush()
                        old_fh.close()
                    self._file_locks.pop(old_path, None)
            else:
                self._file_handles.move_to_end(filepath)
            return fh, self._file_locks[filepath]

    def _cleanup_expired_files(self, today: str) -> None:
        """按天清理过期日志。retention_days=0 时完全不动用户文件。"""
        if self.retention_days <= 0 or self._last_cleanup_date == today:
            return
        self._last_cleanup_date = today
        cutoff = time.time() - self.retention_days * 86400
        try:
            for path in self.log_dir.glob("????-??-??.log"):
                try:
                    if path.stat().st_mtime >= cutoff:
                        continue
                    with self._file_lock:
                        fh = self._file_handles.pop(path, None)
                        self._file_locks.pop(path, None)
                    if fh is not None:
                        with suppress(Exception):
                            fh.flush()
                            fh.close()
                    path.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def _write_batch_to_file(self, batch: List[models.LoggerRecord]) -> None:
        if not self.enable_log_file or not batch:
            return
        try:
            date_groups: Dict[str, List[models.LoggerRecord]] = {}
            for log in batch:
                date_str = log.timestamp[:10]
                date_groups.setdefault(date_str, []).append(log)

            for date_str, logs in date_groups.items():
                self._cleanup_expired_files(date_str)
                filepath = self.log_dir / f"{date_str}.log"
                fh, lock = self._get_file_handle(filepath)
                content = "".join(log.file_line() for log in logs)
                with lock:
                    fh.write(content)
                    # 每批 flush：运行期日志文件即时可读，崩溃不丢整批
                    fh.flush()
                self.bump_stat("batches_written")
        except Exception as exc:
            self.bump_stat("handler_errors")
            print(f"Batch write error: {exc}", file=sys.stderr)

    # ---------- 停止 ----------

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._running = False
            self._put_control(None)

            thread = self._processor_thread
            can_join = (
                thread is not None
                and thread.is_alive()
                and threading.current_thread() is not thread
            )
            if can_join:
                try:
                    from ..ui.dispatcher import join_with_pump

                    joined = join_with_pump(thread, timeout=5.0)
                except Exception:
                    thread.join(5.0) # type: ignore
                    joined = not thread.is_alive() #type: ignore
                if not joined:
                    print("[Logger] processor thread did not stop within 5s",
                          file=sys.stderr)
            self._processor_thread = None

            # 无论是外部 stop 还是从日志线程自身调用，都必须排空 + 落盘 + 关文件
            with suppress(Exception):
                self._drain_remaining()
            self.flush()
            self._close_files()

    def _close_files(self) -> None:
        pool = self._io_pool
        self._io_pool = None
        if pool is not None:
            with suppress(Exception):
                pool.shutdown(wait=True)

        with self._file_lock:
            handles = list(self._file_handles.values())
            self._file_handles.clear()
            self._file_locks.clear()
        for fh in handles:
            with suppress(Exception):
                fh.flush()
            with suppress(Exception):
                fh.close()


class Logger:

    DEFAULT_ANIMATION_STYLE = "braille"
    __instance = None
    __lock = threading.Lock()

    ANIMATION_STYLES = models.AnimationStyle(
        braille=["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"],
        spinner=["-", "\\", "|", "/"],
        dots=[".  ", ".. ", "...", " ..", "  .", "   "],
        arrows=["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        moon=["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"],
        clock=["🕛", "🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚"],
        directional_arrows_unicode=["⬆️", "↗️", "➡️", "↘️", "⬇️", "↙️", "⬅️", "↖️"],
        traffic_lights=["🔴", "🟡", "🟢"],
        growth_emoji=["🌱", "🌿", "🌳"],
        weather_icons=["☀️", "☁️", "🌧️", "⚡️"],
        heartbeat=["♡", "♥"],
    )

    _LEVEL_MAP = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
        "fatal": logging.CRITICAL,
    }

    def __new__(cls, *args, **kwargs):
        with cls.__lock:
            if cls.__instance is None:
                cls.__instance = super().__new__(cls)
        return cls.__instance

    def __init__(
        self,
        name: str = "app",
        level: str = models.LogLevel.INFO,
        log_dir: str = "./logs",
        enable_file: bool = True,
        enable_console: bool = True,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        format: str = DEFAULT_FORMAT,
        datefmt: str = DEFAULT_DATE_FORMAT,
        retention_days: int = 0,
    ):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.app_name = name
        self.log_level = self.normalize_level(level)
        self.enable_file = enable_file
        self.enable_console = enable_console
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_dir = log_dir
        self.datefmt = datefmt
        self.format = format
        self.retention_days = retention_days

        self._logger: Optional[logging.Logger] = None
        self._init_lock = threading.RLock()

    # ---------- 级别 ----------

    @classmethod
    def normalize_level(cls, level: Any) -> str:
        """统一成小写规范值（``LogLevel`` 常量），并接受整数级别。"""
        if isinstance(level, int):
            return models.LogLevel.from_logging_level(level)
        value = str(level or "").strip().lower()
        if value in cls._LEVEL_MAP:
            return value
        if value in ("critical", "fatal"):
            return models.LogLevel.CRITICAL
        return models.LogLevel.INFO

    @classmethod
    def get_logging_level(cls, level: Any) -> int:
        if isinstance(level, int):
            return level
        return cls._LEVEL_MAP.get(
            str(level or "").strip().lower(), logging.INFO
        )

    def get_logging_levels(self) -> List[str]:
        return [
            models.LogLevel.DEBUG,
            models.LogLevel.INFO,
            models.LogLevel.WARNING,
            models.LogLevel.ERROR,
        ]

    # ---------- 初始化 ----------

    def init(self) -> None:
        """创建/替换批量 handler"""
        with self._init_lock:
            lg = logging.getLogger(self.app_name)
            lg.propagate = False
            numeric = self.get_logging_level(self.log_level)
            lg.setLevel(numeric)

            old: Optional[OptimizedBatchLogHandler] = None
            for handler in lg.handlers[:]:
                if isinstance(handler, OptimizedBatchLogHandler):
                    old = handler
                    lg.removeHandler(handler)

            was_running = bool(old is not None and old.is_running)
            if old is not None:
                # 先停旧消费者，避免两个线程抢同一个队列
                with suppress(Exception):
                    old.stop()

            handler = self._create_handler()
            if handler is not None:
                handler.setLevel(numeric)
                lg.addHandler(handler)
                if was_running:
                    handler.start() # type: ignore
            self._logger = lg

    def reconfigure(self, **kwargs: Any) -> "Logger":
        """让 `create_logger()` 的配置在进程单例上真正生效。"""
        allowed = {
            "app_name", "log_level", "enable_file", "enable_console",
            "batch_size", "flush_interval", "log_dir", "format", "datefmt",
            "retention_days", "level", "name",
        }
        with self._init_lock:
            for key, value in kwargs.items():
                if key not in allowed:
                    continue
                if key == "name":
                    key = "app_name"
                if key == "level":
                    key, value = "log_level", self.normalize_level(value)
                if key == "log_level":
                    value = self.normalize_level(value)
                setattr(self, key, value)
            self.init()
        return self

    def _create_handler(self) -> Optional[logging.Handler]:
        try:
            if self.enable_file:
                os.makedirs(self.log_dir, exist_ok=True)
            handler = OptimizedBatchLogHandler(
                self.app_name,
                log_level=self.log_level,
                enable_log_file=self.enable_file,
                enable_console=self.enable_console,
                log_dir=self.log_dir,
                max_length=max(self.batch_size * 50, _MIN_QUEUE_LENGTH * 50),
                batch_size=self.batch_size,
                flush_interval=self.flush_interval,
                retention_days=self.retention_days,
            )
            # formatter 供外部挂在同一个 logger 上的 handler 使用；
            # 批量 handler 自己拼格式（见 __print_batch / file_line）。
            handler.setFormatter(logging.Formatter(self.format, datefmt=self.datefmt))
            return handler
        except Exception:
            sys.stderr.write(
                f"{TermColors.RED}Error: Failed to create log handler "
                f"for {self.app_name}{TermColors.RESET}\n"
            )
            return None

    @property
    def handlers(self) -> List[logging.Handler]:
        return list(self._get_logger().handlers)

    def _get_logger(self) -> logging.Logger:
        lg = self._logger
        if lg is None:
            with self._init_lock:
                if self._logger is None:
                    self.init()
                lg = self._logger
        return lg or logging.getLogger(self.app_name)

    # ---------- 记录 ----------

    def info(self, msg: str) -> None:
        self._get_logger().info(msg)

    def error(self, msg: str) -> None:
        self._get_logger().error(msg)

    def warning(self, msg: str) -> None:
        self._get_logger().warning(msg)

    def debug(self, msg: str) -> None:
        self._get_logger().debug(msg)

    def critical(self, msg: str, exc_info: bool = True) -> None:
        self._get_logger().critical(msg, exc_info=exc_info)

    def exception(self, msg: str, exc_info: bool = True) -> None:
        self._get_logger().error(msg, exc_info=exc_info)

    def log(self, level: int, record: str) -> None:
        # uvicorn 桥接传的是 levelno(int)；其它调用方可能传字符串级别
        if not isinstance(level, int):
            level = self.get_logging_level(level)
        self._get_logger().log(level, record)

    # ---------- 运行时控制 ----------

    def set_level(self, level: Any) -> str:
        """同时更新门面、底层 logger 与所有 handler 的级别。"""
        value = self.normalize_level(level)
        numeric = self.get_logging_level(value)
        with self._init_lock:
            self.log_level = value
            lg = self._get_logger()
            lg.setLevel(numeric)
            for handler in lg.handlers:
                with suppress(Exception):
                    handler.setLevel(numeric)
        return value

    def current_level(self) -> str:
        return str(self.log_level or models.LogLevel.INFO).upper()

    # ---------- 启停 / 统计 ----------

    def start(self) -> None:
        for handler in self.handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.start()

    def stop(self) -> None:
        for handler in self.handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.stop()

    def flush(self) -> int:
        count = 0
        for handler in self.handlers:
            fn = getattr(handler, "flush", None)
            if callable(fn):
                with suppress(Exception):
                    fn()
                    count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """合并所有批量 handler 的统计，并保证字段齐全（API 层直接可读）。"""
        out: Dict[str, Any] = {
            "total": 0,
            "dropped": 0,
            "queue": 0,
            "file_enabled": bool(self.enable_file),
            "console_enabled": bool(self.enable_console),
            "by_level": {},
            "logs_processed": 0,
            "batches_written": 0,
            "queue_size": 0,
            "dropped_logs": 0,
            "event_push_failures": 0,
            "handler_errors": 0,
            "running": False,
            "open_files": 0,
        }
        for handler in self.handlers:
            if not isinstance(handler, OptimizedBatchLogHandler):
                continue
            data = handler.get_stats()
            for key in ("total", "dropped", "queue", "logs_processed",
                        "batches_written", "queue_size", "dropped_logs",
                        "event_push_failures", "handler_errors", "open_files"):
                out[key] = out.get(key, 0) + int(data.get(key, 0) or 0)
            for key, value in dict(data.get("by_level") or {}).items():
                out["by_level"][key] = out["by_level"].get(key, 0) + int(value)
            out["running"] = out["running"] or bool(data.get("running"))
            out["file_enabled"] = bool(data.get("file_enabled"))
            out["console_enabled"] = bool(data.get("console_enabled"))
        return out

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
