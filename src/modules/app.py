"""应用主控（主线程 = 纯 Qt；Web/服务/音频各自独立线程）。

线程模型
────────
    主线程（纯 Qt，不跑 asyncio）
    └── QApplication.exec()
        ├── QTimer(16ms)   -> MainThreadDispatcher.pump()   工作线程投递来的 Qt 任务
        ├── QTimer(200ms)  -> 心跳，让 CPython 有机会处理 Ctrl+C
        └── 托盘 / Live2D 窗口

    Web 线程(daemon)   -> 独立 asyncio loop 跑 uvicorn（永不阻塞 UI）
    Live2D 服务        -> main_thread=True，全部在主线程直接执行
    渲染线程(QThread)  -> OpenGL 绘制
    音频线程(daemon)   -> 各自独立 loop

三条铁律：
  1. 主线程不跑 asyncio loop；asyncio.run() 只在 Qt 退出后的清理阶段一次性使用。
  2. 主线程等待任何线程时，必须用 join_with_pump()，否则死锁。
  3. emit() 在有运行中 loop 的线程里不得调用 asyncio.run()
"""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Optional

from .logger import logger
from .config import load_config, get_config
from . import runtime


class Application:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        app_name: str = "ChatBot",
        debug: bool = False,
        debug_modules: str = "",
    ):
        if getattr(self, "_app_initialized", False):
            return
        self._app_initialized = True

        self.app_name = app_name
        self.debug = debug
        self.debug_modules = debug_modules

        self._running = False
        self._closing = False
        self._config_loaded = False
        self._exit_code: int = 0
        self.ui = None  # type: ignore[assignment]  # UIApp，可能为 None
        self._old_signal_handlers: dict = {}

    # ---------- 配置 ----------

    def init(self) -> None:
        """加载 app.conf，并把日志配置同步到已构造的日志单例（幂等）。"""
        if self._config_loaded:
            return
        try:
            candidate = Path(runtime.StandardPaths.get_resources_dir()) / "configs" / "app.conf"
        except Exception:  # noqa: BLE001
            candidate = Path(".env")

        config_path: Optional[str] = str(candidate) if candidate.exists() else None
        try:
            load_config(config_path, self.debug)
        except Exception as exc:  # noqa: BLE001 - 配置失败也要能启动
            logger.warning(f"[App] 配置加载失败，使用默认配置: {exc}")
        self._config_loaded = True
        try:
            cfg = get_config().log
            logger.reconfigure(
                app_name=self.app_name,
                log_level=str(getattr(cfg, "level", "info") or "info"),
                enable_file=bool(getattr(cfg, "enable_log_file", False)),
                log_dir=str(getattr(cfg, "log_dir", "") or ""),
                format=str(getattr(cfg, "format", "") or ""),
                datefmt=str(getattr(cfg, "datefmt", "") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[App] 日志配置同步失败: {exc}")

        logger.info(f"[App] 配置已加载: {config_path or '内置默认值'}")

    # ---------- 启动 ----------

    def run(self) -> int:
        with self._lock:
            if self._running:
                logger.warning("[App] already running, ignore duplicate run()")
                return self._exit_code
            self._running = True
        self._exit_code = 0

        try:
            # 1) 配置（幂等，调用方忘调 init() 也不会跑在默认值上）
            self.init()

            # 2) 运行时先起来：事件总线 / 调度器 / 网关 op 必须在任何日志与
            #    API 请求之前就绪（否则 events.emit 拿到 runtime.manager=None）。
            runtime.instance().init()

            # 3) 日志消费者启动（此时事件总线已可用）
            logger.start()
            self._install_signal_handlers()

            # 4) UI（Qt 主循环在这里阻塞）
            from .ui.setup import UIApp

            self.ui = UIApp(self.app_name, self.debug)
            logger.info("[App] entering Qt main event loop")
            self.ui.show()
            ui_code = int(getattr(self.ui, "exit_code", 0) or 0)
            if ui_code:
                self._exit_code = ui_code
        except KeyboardInterrupt:
            logger.info("[App] interrupted by user")
            self._exit_code = 130
        except Exception as e:
            logger.exception(f"ChatBotApp run error: {e}", exc_info=True)
            self._exit_code = self._exit_code or 1
            raise
        finally:
            self._shutdown()
        return self._exit_code

    def _install_signal_handlers(self) -> None:
        """把 SIGINT/SIGTERM 转成优雅退出。

        signal handler 只在主线程执行；配合 200ms 心跳，Qt 阻塞期间也能被触发。
        UI 尚未创建时只记退出码，不碰任何 Qt 对象。
        """

        def _handler(signum, frame):  # noqa: ARG001
            self._exit_code = 130
            ui = self.ui
            if ui is None:
                return
            try:
                ui.exit(130)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[App] signal handler exit failed: {exc}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._old_signal_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, _handler)
            except (ValueError, OSError) as exc:
                logger.debug(f"[App] cannot install handler for signal {sig}: {exc}")

    def _restore_signal_handlers(self) -> None:
        for sig, old in self._old_signal_handlers.items():
            try:
                if old is not None:
                    signal.signal(sig, old)
            except (ValueError, OSError, TypeError):
                pass
        self._old_signal_handlers.clear()

    # ---------- 关闭 ----------

    def _step(self, label: str, fn) -> None:
        """清理步骤隔离：任何一步失败都不能中断后续清理。"""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[App] shutdown step '{label}' failed: {exc}")

    def _shutdown(self) -> None:
        """唯一清理路径，带幂等守卫。"""
        if self._closing:
            return
        self._closing = True
        try:
            ui = self.ui

            # 0) 退出前保存存档，避免用户数据丢失（原来在 try 外面，一抛异常
            #    后面所有清理都不会执行）。
            self._step("save_saves", lambda: runtime.instance()._save_saves())

            # 1) 先关桌面窗口：页面还连着 WebSocket，先停 Web 会让前端抛断连
            #    错误甚至触发重连风暴。关窗前由 manager 推一次 shutdown 事件。
            if ui is not None:
                self._step("close_browser_view", ui._close_browser_view)
                self._step("web_stop", ui.web_stop)

            # 2) 再停各管理器
            self._step("runtime_stop", runtime.instance().stop)

            # 3) UI 收尾（dispatcher 最后，前面的清理还要往主线程投递）
            if ui is not None:
                self._step("ui_stop", ui.stop)

            self._restore_signal_handlers()
            logger.info("[App] stopped")
        finally:
            self._running = False
            logger.info("[App] closed")
            self._step("logger_stop", logger.stop)
            # 注意：_closing 保持 True，重复调用 _shutdown 不会二次清理。
