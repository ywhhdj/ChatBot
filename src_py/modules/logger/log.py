from contextlib import suppress
import os
from pathlib import Path
import logging
import sys
import threading
import time
from typing import Dict, List, Optional
import queue

from ..manager.task.decorator import sync_task_scheduler
from ..events.types import WebSocketEventType
from . import types
from ..types.common import TermColors

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str = DEFAULT_FORMAT, datefmt: str = DEFAULT_DATE_FORMAT):
        super().__init__(fmt, datefmt)
        self.color_map = {
            types.LogLevel.INFO: TermColors.GREEN,
            types.LogLevel.WARNING: TermColors.YELLOW,
            types.LogLevel.ERROR: TermColors.RED
        }
    
    def format(self, record:logging.LogRecord):
        message = record.getMessage()
        color = self.color_map.get(types.LogLevel.from_logging_level(record.levelno), TermColors.WHITE)
        return f"{color}[{record.levelname}]{TermColors.RESET}{message}"


class OptimizedBatchLogHandler(logging.Handler):
    def __init__(
        self,
        app_name: str,
        log_level: str = types.LogLevel.INFO,
        enable_log_file: bool = False,
        log_dir: str = "logs",
        max_length: int = 1000,
        batch_size: int = 50,
        flush_interval: float = 1.0,  # 自动刷新间隔
    ):
        super().__init__()
        self.app_name = app_name
        self.log_level = log_level
        self.enable_log_file = enable_log_file
        self.log_dir = Path(log_dir)
        self.max_length = max_length
        self.batch_size = min(batch_size, max_length // 2)
        self.flush_interval = flush_interval
        # self.__handle_write_result = handle_write_result
        
        self.__log_queue: queue.Queue[Optional[types.LoggerRecord]] = queue.Queue()
        self.__current_batch: List[types.LoggerRecord] = []
        self.__batch_lock = threading.RLock()
        
        # 线程控制
        self.__running = False
        
        # 性能监控
        self.stats = {
            'logs_processed': 0,
            'batches_written': 0,
            'queue_size': 0,
            'dropped_logs':0
        }
        self.color_map = {
            types.LogLevel.INFO: TermColors.GREEN,
            types.LogLevel.WARNING: TermColors.YELLOW,
            types.LogLevel.ERROR: TermColors.RED
        }
        self.__has_logs = threading.Event()
    
    def emit(self, record) -> None:
        try:
            log_entry = types.LoggerRecord.from_logging_record(record)
            if self.__log_queue.qsize() >= self.max_length:
                with suppress(queue.Empty):
                    self.__log_queue.get_nowait()
                    self.stats['dropped_logs'] += 1
            self.__log_queue.put_nowait(log_entry)
            self.__has_logs.set()
        except Exception:
            self.handleError(record)
        
    def start(self):
        if  self.__running:
            return
        self.__running = True
        self.__has_logs.clear()
        # 启动处理线程
        self._processor_thread = threading.Thread(
            target=self.__process_logs,
            name=f"Logger-{self.app_name}",
            daemon=True
        )
        self._processor_thread.start()
    
    def __wait_for_logs(self) -> bool:
        waited = 0
        while self.__log_queue.empty() and self.__running:
            if waited >= self.flush_interval:
                return False
            time.sleep(0.05)
            waited += 0.05
        return not self.__log_queue.empty()
    
    def __process_logs(self):
        while self.__running:
            try:
                if not self.__wait_for_logs():  # 避免空转
                    continue
                logs = []
                # 尽可能多地获取更多日志
                while not self.__log_queue.empty() and len(logs) < self.batch_size:
                    try:
                        record = self.__log_queue.get_nowait()
                        if record:
                            self.__print_log_color(record)
                            logs.append(record)
                    except queue.Empty:
                        break
                if logs:
                    with self.__batch_lock:
                        self.__current_batch.extend(logs)
                        # self.__frontend_logs.extend(logs)
                        # while len(self.__frontend_logs) > self.__frontend_logs_max_length:
                        #     self.__frontend_logs.pop(0)

                        if len(self.__current_batch) >= self.batch_size:
                            self.__flush_current_batch()
                    self.stats['logs_processed'] += len(logs)
                    self.stats['queue_size'] = self.__log_queue.qsize()
            except Exception as e:
                print(f"Log processor error: {e}", file=sys.stderr)
                time.sleep(0.1)
        with self.__batch_lock:
            self.__flush_current_batch()

    def __print_log_color(self, log: types.LoggerRecord):
        from ..events import emit
        from ..events.data import BaseEvent
        # 将 LoggerRecord 转为字典
        log_dict = {
            "log_name": log.log_name,
            "timestamp": log.timestamp,
            "level": log.level,
            "message": log.message,
            "source": log.source if hasattr(log, 'source') else "backend",
            "metadata": log.metadata if hasattr(log, 'metadata') else None,
        }
        emit(BaseEvent(
            type=WebSocketEventType.GET_LOG,
            args=(log_dict,)
        ))

        #如果前端日志里有则遍历发送
        # if self.__frontend_logs:
        #     for log in self.__frontend_logs:
        #         log_dict = {
        #             "log_name": log.log_name,
        #             "timestamp": log.timestamp,
        #             "level": log.level,
        #             "message": log.message,
        #             "source": log.source if hasattr(log, 'source') else "backend",
        #             "metadata": log.metadata if hasattr(log, 'metadata') else None,
        #         }
        #         emit(BaseEvent(
        #             type=WebSocketEventType.GET_LOG,
        #             data=log_dict
        #         ))
        #     self.__frontend_logs.clear()
            
        if log.level == types.LogLevel.DEBUG:
            print(f"{TermColors.GREY}[{log.timestamp}] [{log.level.upper()}] {log.message}{TermColors.RESET}")
            return
        color = self.color_map.get(log.level, TermColors.WHITE)
        print(f"[{log.log_name}] [{log.timestamp}] {color}[{log.level.upper()}]{TermColors.RESET} {log.message}")

    def __flush_current_batch(self):
        if not self.__current_batch:
            return
        batch = self.__current_batch.copy()
        self.__current_batch.clear()
        if batch and self.enable_log_file:
            self.__write_batch_to_file(batch)

    def flush(self):
        """刷新当前批次到文件"""
        with self.__batch_lock:
            self.__flush_current_batch()

    @sync_task_scheduler
    def __write_batch_to_file(self, batch: list[types.LoggerRecord]):
        """优化的文件写入"""
        if not self.enable_log_file or not batch:
            return
        if not hasattr(self, '_file_handles'):
            self._file_handles = {}
            self._file_locks = {}
        try:
            # 按日期分组 (从 timestamp 中提取日期部分)
            date_groups: Dict[str, List[types.LoggerRecord]] = {}
            for log in batch:
                # 假设 timestamp 格式为 "YYYY-MM-DD HH:MM:SS"
                date_str = log.timestamp[:10]  # 取前10个字符 "YYYY-MM-DD"
                if date_str not in date_groups:
                    date_groups[date_str] = []
                date_groups[date_str].append(log)
            # 写入每个日期的文件
            for date_str, logs in date_groups.items():
                filepath = self.log_dir / f"{date_str}.log"
                # 获取或创建文件句柄和锁
                if filepath not in self._file_handles:
                    self._file_handles[filepath] = open(filepath, 'a', encoding='utf-8', buffering=8192)
                    self._file_locks[filepath] = threading.Lock()
                # 构建要写入的内容
                lines = []
                for log in logs:
                    line = f"[{log.log_name}] {log.timestamp} [{log.level}] {log.message}\n"
                    lines.append(line)
                content = ''.join(lines)
                # 加锁写入，确保线程安全
                with self._file_locks[filepath]:
                    self._file_handles[filepath].write(content)
                    # 不立即 flush，依赖操作系统和 Python 的缓冲机制
                self.stats['batches_written'] += 1
        except Exception as e:
            print(f"Batch write error: {e}", file=sys.stderr)
    
    def stop(self):
        self.__running = False
        self.__has_logs.set()
        # 放入哨兵值确保线程退出
        try:
            self.__log_queue.put_nowait(None)
        except queue.Full:
            pass
        with suppress(Exception):
            if hasattr(self, '_processor_thread')  and self._processor_thread.is_alive():
                self._processor_thread.join(timeout=5.0)
        self.flush()
        if hasattr(self, '_file_handles'):
            for fh in self._file_handles.values():
                with suppress(Exception):
                    fh.close()
            del self._file_handles
            del self._file_locks

class Logger:
    DEFAULT_ANIMATION_STYLE = 'braille'
    _instance = None
    _intialized = False
    __instance = None
    __lock = threading.Lock()

    ANIMATION_STYLES=types.AnimationStyle(
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
        heartbeat=["♡", "♥"]
    )
    
    def __new__(cls, *args, **kwargs):
        with cls.__lock:
            if cls.__instance is None:
                cls.__instance = super().__new__(cls)
        return cls.__instance
    
    def __init__(
            self,
            name: str = "app",
            level: str = types.LogLevel.INFO,
            log_dir: str = "./logs",
            enable_file: bool = True,
            enable_console: bool = True,
            batch_size: int = 100,
            flush_interval: float = 2.0,
            format: str = DEFAULT_FORMAT,
            datefmt: str = DEFAULT_DATE_FORMAT
        ):
            if self._intialized:
                return
            Logger._instance = self
            self.app_name = name
            self.log_level = level
            self.enable_file = enable_file
            self.enable_console = enable_console
            self.batch_size = batch_size
            self.flush_interval = flush_interval
            self.log_dir = log_dir
            self.datefmt = datefmt
            self.format = format
            # self.debug = debug
            self._intialized = True

    def get_logging_levels(self) -> list[str]:
        return [types.LogLevel.DEBUG,types.LogLevel.INFO,types.LogLevel.WARNING,types.LogLevel.ERROR]

    def get_logging_level(self, level: str) -> int:
        """转换日志级别字符串为logging级别"""
        level_map = {
            types.LogLevel.DEBUG: logging.DEBUG,
            types.LogLevel.INFO: logging.INFO,
            types.LogLevel.WARNING: logging.WARNING,
            types.LogLevel.ERROR: logging.ERROR
        }
        return level_map.get(level, logging.INFO)

    def init(self):
        self.__logger = logging.getLogger(self.app_name)
        self.__logger.propagate = False
        self.__logger.setLevel(self.get_logging_level(self.log_level))

        for handler in self.__logger.handlers[:]:
            handler.close()
            self.__logger.removeHandler(handler)

        # 添加处理器
        file_handler = self.__create_handler()
        if file_handler:
            self.__logger.addHandler(file_handler)

    def __create_handler(self) -> Optional[logging.Handler]:
        try:
            if self.enable_file:
                os.makedirs(self.log_dir, exist_ok=True)
            file_handler = OptimizedBatchLogHandler(
                self.app_name,
                log_level=self.log_level,
                enable_log_file=self.enable_file,
                log_dir=self.log_dir,
                max_length=self.batch_size,
                flush_interval=self.flush_interval
            )
            file_handler.setFormatter(ColorFormatter(
                self.format,
                datefmt=self.datefmt
            ))
            return file_handler
        except Exception:
            sys.stderr.write(f"{TermColors.RED}Error: Failed to create file handler for {self.app_name}{TermColors.RESET}\n")
            return None
    
    def info(self, msg: str) -> None:
        self.__logger.info(msg)
    
    def exception(self,msg:str,exc_info:bool=True):
        self.__logger.error(msg,exc_info=exc_info)
    
    def critical(self, msg: str,exc_info:bool=True) -> None:
        self.__logger.critical(msg,exc_info=exc_info)
        
    def error(self, msg: str) -> None:
        self.__logger.error(msg)

    def warning(self, msg: str) -> None:
        self.__logger.warning(msg)

    def debug(self, msg: str) -> None:
        self.__logger.debug(msg)
    
    def log(self, level: int,  record: str) -> None:
        if level == logging.DEBUG:
            self.__logger.debug(record)
        elif level == logging.INFO:
            self.__logger.info(record)
        elif level == logging.WARNING:
            self.__logger.warning(record)
        elif level == logging.ERROR:
            self.__logger.error(record)
        elif level == logging.CRITICAL:
            self.__logger.critical(record)
        
    def start(self) -> None:
        for handler in self.__logger.handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.start()
                self.__logger.info(f"Batch handler started")
    
    def stop(self) -> None:
        for handler in self.__logger.handlers:
            if isinstance(handler, OptimizedBatchLogHandler):
                handler.stop()
                self.__logger.info(f"Batch handler stopped")

    def __enter__(self):
        """上下文管理器支持"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.stop()