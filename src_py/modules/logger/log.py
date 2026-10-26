"""批量日志处理器 + Logger 门面。

修复对应清单：L1 L8 L9 L10 L15–L22

关键设计
────────
1. **日志只在 LoggerThread 里做重活**（格式化、打印、落盘、emit 事件）。
   业务线程调用 `logger.info()` 时，Handler.emit() 只做「必要字段提取 + 入队」。
2. **写文件不依赖 TaskSchedular**（L8）。
   原实现用 `@sync_task_scheduler` 装饰写文件方法，而 app 关闭时调度器
   先于 logger 停止 —— 导致退出时的最后一批日志（往往包含退出原因）全部丢失。
   现在改用 logger 自有的单线程 IO 池。
3. **队列用阻塞 get，零忙轮询**（L15）。
4. **退出前排空队列**（L9）。
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import models
from ..models import TermColors

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 队列与批次的合理下界（L22）
_MIN_QUEUE_LENGTH = 100
_MIN_BATCH_SIZE = 10


def _consume_future_exception(fut: Future) -> None:
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        print(f"Log writer error: {exc}", file=sys.stderr)


class OptimizedBatchLogHandler(logging.Handler):
    """批量日志处理器。

    线程模型：
        业务线程 ──emit()──> queue ──> LoggerThread（唯一消费者）
                                          ├─ 控制台着色打印
                                          ├─ emit(GET_LOG) 事件（供前端）
                                          └─ IO 池落盘（不依赖 TaskSchedular）
    """

    def __init__(
        self,
        app_name: str,
        log_level: str = models.LogLevel.INFO,
        enable_log_file: bool = False,
        log_dir: str = "logs",
        max_length: int = 2000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ):
        super().__init__()
        self.app_name = app_name
        self.log_level = log_level
        self.enable_log_file = enable_log_file
        self.log_dir = Path(log_dir)

        # L22：下界保护，避免 batch_size 被算成 0 后退化
        self.max_length = max(_MIN_QUEUE_LENGTH, int(max_length))
        self.batch_size = max(_MIN_BATCH_SIZE, min(int(batch_size), self.max_length // 2))
        self.flush_interval = max(0.05, float(flush_interval))

        self.__log_queue: "queue.Queue[Optional[models.LoggerRecord]]" = queue.Queue()
        self.__current_batch: List[models.LoggerRecord] = []
        self.__batch_lock = threading.RLock()

        # L16：统计值从多线程更新，必须加锁
        self.__stats_lock = threading.Lock()
        self.stats: Dict[str, int] = {
            "logs_processed": 0,
            "batches_written": 0,
            "queue_size": 0,
            "dropped_logs": 0,
        }

        # L10：文件句柄在 __init__ 初始化，避免 hasattr 竞态与删除后重建
        self.__file_handles: Dict[Path, Any] = {}
        self.__file_locks: Dict[Path, threading.Lock] = {}
        self.__file_lock = threading.RLock()
        self.__io_pool: Optional[ThreadPoolExecutor] = None

        self.__running = False
        self.__processor_thread: Optional[threading.Thread] = None

        self.color_map = {
            models.LogLevel.INFO: TermColors.GREEN,
            models.LogLevel.WARNING: TermColors.YELLOW,
            models.LogLevel.ERROR: TermColors.RED,
            models.LogLevel.CRITICAL: TermColors.RED,
        }

    # ---------- 采集（业务线程） ----------

    def emit(self, record: logging.LogRecord) -> None:
        """在**调用方线程**执行，必须极轻量。"""
        try:
            log_entry = models.LoggerRecord.from_logging_record(record)
            # 队列满时丢弃最旧的一条，保证调用方永不阻塞（LD4）
            if self.__log_queue.qsize() >= self.max_length:
                with suppress(queue.Empty):
                    self.__log_queue.get_nowait()
                    with self.__stats_lock:
                        self.stats["dropped_logs"] += 1
            self.__log_queue.put_nowait(log_entry)
        except Exception:
            self.handleError(record)

    def bump_stat(self, key: str, delta: int = 1) -> None:
        with self.__stats_lock:
            self.stats[key] = self.stats.get(key, 0) + delta

    def get_stats(self) -> Dict[str, int]:
        with self.__stats_lock:
            stats = self.stats.copy()
        stats["queue_size"] = self.__log_queue.qsize()
        return stats

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self.__running:
            return
        self.__running = True

        if self.enable_log_file:
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception as e:
                print(f"Log dir create error: {e}", file=sys.stderr)
            # L8：自有 IO 池，与 TaskSchedular 解耦
            self.__io_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="LogWriter"
            )

        self.__processor_thread = threading.Thread(
            target=self.__process_logs, name="LoggerThread", daemon=True
        )
        self.__processor_thread.start()

    def __process_logs(self) -> None:
        """LoggerThread 主循环（L15：阻塞等待，零忙轮询）。"""
        try:
            while self.__running:
                try:
                    record = self.__log_queue.get(timeout=self.flush_interval)
                except queue.Empty:
                    continue

                if record is None:
                    # 收到停止信号：先排空残留（L9），再退出
                    self.__drain_remaining()
                    break

                logs = [record]
                # 顺手把队列里已有的日志一起取走，减少循环开销
                while len(logs) < self.batch_size:
                    try:
                        nxt = self.__log_queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is None:
                        break
                    logs.append(nxt)

                self.__handle_batch(logs)
        except Exception as e:
            print(f"Log processor error: {e}", file=sys.stderr)
        finally:
            with self.__batch_lock:
                self.__flush_current_batch()

    def __drain_remaining(self) -> None:
        """退出前把队列里剩余的日志处理完（L9）。"""
        pending: List[models.LoggerRecord] = []
        while True:
            try:
                record = self.__log_queue.get_nowait()
            except queue.Empty:
                break
            if record is None:
                continue
            pending.append(record)
        if pending:
            self.__handle_batch(pending)

    def __handle_batch(self, logs: List[models.LoggerRecord]) -> None:
        if not logs:
            return
        for record in logs:
            try:
                self.__print_log_color(record)
            except Exception as e:
                print(f"Log print error: {e}", file=sys.stderr)

        with self.__batch_lock:
            self.__current_batch.extend(logs)
            if len(self.__current_batch) >= self.batch_size:
                self.__flush_current_batch()

        self.bump_stat("logs_processed", len(logs))

    # ---------- 输出 ----------

    def __print_log_color(self, log: models.LoggerRecord) -> None:
        # 推给前端。监听器必须是**同步**的（见 websocket 控制器），
        # 否则事件总线会在无 loop 的线程里 asyncio.run()，阻塞日志线程并跨 loop 操作 WebSocket。
        from ..events import emit
        from ..events.data import BaseEvent
        from ..events.types import WebSocketEventType

        emit(BaseEvent(type=WebSocketEventType.GET_LOG, args=(log.to_dict(),)))

        if log.level == models.LogLevel.DEBUG:
            print(
                f"{TermColors.GREY}[{log.timestamp}] "
                f"[{log.level.upper()}] {log.message}{TermColors.RESET}"
            )
            return
        color = self.color_map.get(log.level, TermColors.WHITE)
        print(
            f"[{log.log_name}] [{log.timestamp}] "
            f"{color}[{log.level.upper()}]{TermColors.RESET} {log.message}"
        )

    def __flush_current_batch(self) -> None:
        """调用方需持有 __batch_lock。"""
        if not self.__current_batch:
            return
        batch = self.__current_batch.copy()
        self.__current_batch.clear()
        if self.enable_log_file and self.__io_pool is not None:
            try:
                fut = self.__io_pool.submit(self.__write_batch_to_file, batch)
                fut.add_done_callback(_consume_future_exception)
            except Exception as e:
                print(f"Batch write submit error: {e}", file=sys.stderr)

    def flush(self) -> None:
        with self.__batch_lock:
            self.__flush_current_batch()
        if self.__io_pool is not None:
            # 等待已提交的写任务完成，保证 stop 时数据落盘
            with suppress(Exception):
                self.__io_pool.submit(lambda: None).result(timeout=5.0)

    # ---------- 落盘（IO 线程） ----------

    def __get_file_handle(self, filepath: Path):
        """L10：句柄表 + 锁，避免跨线程重建导致句柄泄漏。"""
        with self.__file_lock:
            fh = self.__file_handles.get(filepath)
            if fh is None:
                fh = open(filepath, "a", encoding="utf-8", buffering=8192)
                self.__file_handles[filepath] = fh
                self.__file_locks[filepath] = threading.Lock()
            return fh, self.__file_locks[filepath]

    def __write_batch_to_file(self, batch: List[models.LoggerRecord]) -> None:
        """L8：在 IO 线程同步写，不再经过 TaskSchedular。"""
        if not self.enable_log_file or not batch:
            return
        try:
            date_groups: Dict[str, List[models.LoggerRecord]] = {}
            for log in batch:
                date_str = log.timestamp[:10]
                date_groups.setdefault(date_str, []).append(log)

            for date_str, logs in date_groups.items():
                filepath = self.log_dir / f"{date_str}.log"
                fh, lock = self.__get_file_handle(filepath)
                content = "".join(
                    f"[{log.log_name}] {log.timestamp} [{log.level}] {log.message}\n"
                    for log in logs
                )
                with lock:
                    fh.write(content)
                self.bump_stat("batches_written")
        except Exception as e:
            print(f"Batch write error: {e}", file=sys.stderr)

    # ---------- 停止 ----------

    def stop(self) -> None:
        self.__running = False
        # 哨兵唤醒阻塞在 get() 上的线程
        with suppress(Exception):
            self.__log_queue.put_nowait(None)

        thread = self.__processor_thread
        if thread is None:
            self.__close_files()
            return
        if not thread.is_alive():
            self.__processor_thread = None
            self.__close_files()
            return
        if threading.current_thread() is thread:
            print("[Logger] refuse to join processor thread from itself")
            return

        try:
            from ..ui.dispatcher import join_with_pump

            ok = join_with_pump(thread, timeout=5.0)
        except Exception:
            thread.join(5.0)
            ok = not thread.is_alive()
        if not ok:
            print("[Logger] processor thread did not stop within 5s", file=sys.stderr)
        self.__processor_thread = None

        # L9：线程退出后仍可能有残留，再排一次
        self.__drain_remaining()
        self.flush()
        self.__close_files()

    def __close_files(self) -> None:
        if self.__io_pool is not None:
            with suppress(Exception):
                self.__io_pool.shutdown(wait=True)
            self.__io_pool = None

        with self.__file_lock:
            handles = list(self.__file_handles.values())
            self.__file_handles.clear()
            self.__file_locks.clear()
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
    ):
        # L19：统一用 _initialized（原 _intialized 拼写错误）
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.app_name = name
        self.log_level = level
        self.enable_file = enable_file
        self.enable_console = enable_console
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_dir = log_dir
        self.datefmt = datefmt
        self.format = format

        self.__logger: Optional[logging.Logger] = None
        self.__init_lock = threading.Lock()

    # ---------- 初始化 ----------

    def init(self) -> None:
        with self.__init_lock:
            logger = logging.getLogger(self.app_name)
            logger.propagate = False
            logger.setLevel(self.get_logging_level(self.log_level))

            for handler in logger.handlers[:]:
                with suppress(Exception):
                    handler.close()
                logger.removeHandler(handler)

            handler = self.__create_handler()
            if handler is not None:
                logger.addHandler(handler)
            self.__logger = logger

    def __create_handler(self) -> Optional[logging.Handler]:
        try:
            if self.enable_file:
                os.makedirs(self.log_dir, exist_ok=True)
            handler = OptimizedBatchLogHandler(
                self.app_name,
                log_level=self.log_level,
                enable_log_file=self.enable_file,
                log_dir=self.log_dir,
                # 队列默认容量要给足：启动期/异常期日志会瞬间爆发，
                # 容量太小会直接丢弃最旧的日志（恰恰可能是故障原因）。
                max_length=max(self.batch_size * 50, _MIN_QUEUE_LENGTH * 50),
                batch_size=self.batch_size,
                flush_interval=self.flush_interval,
            )
            # L17：原来挂了 ColorFormatter，但 handler.emit() 从不用 formatter，
            # 颜色是 __print_log_color 自己拼的 —— 这个 formatter 是死代码。
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
        lg = self.__get_logger()
        return list(lg.handlers) if lg is not None else []

    def __get_logger(self) -> logging.Logger:
        """L20：未 init 时惰性初始化，避免 AttributeError。

        最坏情况下退化为 root logger，保证日志不会整个崩掉。
        """
        if self.__logger is None:
            with self.__init_lock:
                if self.__logger is None:
                    with suppress(Exception):
                        self.init()
                    if self.__logger is None:
                        self.__logger = logging.getLogger(self.app_name)
        return self.__logger

    def get_logging_levels(self) -> List[str]:
        return [
            models.LogLevel.DEBUG,
            models.LogLevel.INFO,
            models.LogLevel.WARNING,
            models.LogLevel.ERROR,
        ]

    def get_logging_level(self, level: str) -> int:
        level_map = {
            models.LogLevel.DEBUG: logging.DEBUG,
            models.LogLevel.INFO: logging.INFO,
            models.LogLevel.WARNING: logging.WARNING,
            models.LogLevel.ERROR: logging.ERROR,
            models.LogLevel.CRITICAL: logging.CRITICAL,
        }
        return level_map.get(level, logging.INFO)

    # ---------- 记录 ----------

    def info(self, msg: str) -> None:
        self.__get_logger().info(msg)

    def error(self, msg: str) -> None:
        self.__get_logger().error(msg)

    def warning(self, msg: str) -> None:
        self.__get_logger().warning(msg)

    def debug(self, msg: str) -> None:
        self.__get_logger().debug(msg)

    def critical(self, msg: str, exc_info: bool = True) -> None:
        self.__get_logger().critical(msg, exc_info=exc_info)

    def exception(self, msg: str, exc_info: bool = True) -> None:
        self.__get_logger().error(msg, exc_info=exc_info)

    def log(self, level: int, record: str) -> None:
        if level == logging.DEBUG:
            self.__get_logger().debug(record)
        elif level == logging.INFO:
            self.__get_logger().info(record)
        elif level == logging.WARNING:
            self.__get_logger().warning(record)
        elif level == logging.ERROR:
            self.__get_logger().error(record)
        elif level == logging.CRITICAL:
            self.__get_logger().critical(record)
        else:
            self.__get_logger().info(record)

    # ---------- 启停 ----------

    def start(self) -> None:
        for handler in self.__get_logger().handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.start()

    def stop(self) -> None:
        for handler in self.__get_logger().handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.stop()

    def get_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        for handler in self.__get_logger().handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                stats = handler.get_stats()
        return stats

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
