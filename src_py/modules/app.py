"""应用主控（主线程 = 纯 Qt；Web/服务/音频各自独立线程）。

修复对应清单：A1 A2 B1–B7 / D1 D3

线程模型（详见《调用链修复清单》第 0 节）::

    主线程（纯 Qt，不跑 asyncio）
    └── QApplication.exec_()
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
  3. emit() 在有运行中 loop 的线程里不得调用 asyncio.run()（已由 bus 修复）。
"""
import signal
import threading

from .logger import logger
from .config import load_config
from . import runtime


class Application:
    _instance = None
    _initialized = False
    _running = False
    _closing = False
    _lock = threading.Lock()

    def __init__(
        self,
        app_name: str = "ChatBot",
        debug: bool = False,
        debug_modules: str = ""
    ):
        if getattr(self, "_initialized", False):
            return
        type(self)._instance = self
        self.app_name = app_name
        self.debug = debug
        self.debug_modules = debug_modules
        self._initialized = True

        self._running = False
        self._closing = False
        self._exit_code: int = 0

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        load_config(".env", self.debug)

    def run(self) -> int:
        if self._running:
            logger.warning("[App] already running, ignore duplicate run()")
            return self._exit_code

        self._running = True
        self._exit_code = 0

        logger.start()        
        self._install_signal_handlers()
        runtime.instance().init()
        try:
            from .ui.setup import UIApp
            self.ui=UIApp(self.app_name,self.debug)
            self.ui.show()
            logger.info("[App] entering Qt main event loop")
        except KeyboardInterrupt:
            logger.info("[App] interrupted by user")
            self.ui.exit_code=130
            raise KeyboardInterrupt
        except Exception as e:
            logger.exception(f"ChatBotApp run error: {e}", exc_info=True)
            self.ui.exit_code=1
            raise e
        finally:
            self._shutdown()
        return self.ui.exit_code

    def _install_signal_handlers(self) -> None:
        """把 SIGINT/SIGTERM 转成优雅退出。

        signal handler 只在主线程执行；配合 200ms 心跳，Qt 阻塞期间也能被触发。
        """

        def _handler(signum, frame):  # noqa: ARG001
            logger.info(f"[App] received signal {signum}, shutting down gracefully")
            if hasattr(self, "ui"):
                self.ui.exit(130)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except ValueError:
                logger.debug(f"[App] cannot install handler for signal {sig}")


    def _shutdown(self) -> None:
        """A2 / B4：唯一清理路径，带幂等守卫。"""
        if not self._initialized or self._closing:
            return
        self._closing = True
        # 退出前保存存档，避免用户数据丢失。
        runtime.manager._save_saves()
        try:
            # 0) 先关桌面窗口：页面还连着 WebSocket，
            #    先停 Web 会让前端抛断连错误甚至触发重连风暴。
            #    关窗前推一次 shutdown 事件，让前端主动断开。
            self.ui._close_browser_view()

            # 1) 再停 Web：等它优雅跑完 shutdown 释放端口，避免它继续处理请求并 emit 事件
            self.ui.web_stop()

            # 2) 再停各管理器
            runtime.instance().stop()

            # 3) 收尾 按依赖顺序；dispatcher 最后，前面的清理还要往主线程投递
            self.ui.stop()

            self._running = False
            logger.info("[App] stopped")
        except Exception as e:
            logger.exception(f"ChatBotApp close error: {e}", exc_info=True)
        finally:
            self._closing = False
            logger.info("[App] closed")
            logger.stop()
    

