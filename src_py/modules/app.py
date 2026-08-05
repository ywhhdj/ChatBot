import asyncio
from re import S
import sys
import threading

from .events import emit,types,BaseEvent
from typing import Literal
from .logger import logger
from .manager import pipeline
from .manager.task import schedular
from .manager.service import manager
from .manager.dispatcher import get_main_thread_dispatcher


class Application:
    _instance = None
    _initialized = False
    _running = False
    _lock = threading.Lock()
    
    def __init__(self, debug: bool = False, debug_modules: str = ""):
        if self._initialized:
            return
        self._instance = self
        self.debug = debug
        self.debug_modules = debug_modules
        self._asyncio_thread = None
        self._initialized = True
        self.main_thread_dispatcher = None

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        from .config import load_config
        load_config(".env", self.debug)

    async def close(self) -> None:
        if not self._initialized:
            return
        logger.stop()
        from .api.server import stop_web_server
        # 或者直接用 call_soon_threadsafe
        stop_web_server()
        try:
            events=[
                types.AppEventType.ManagerEventType.SERVICE_STOP,
                types.AppEventType.ManagerEventType.PIPELINE_STOP,
                types.AppEventType.ManagerEventType.SERVICE_STOP,
                types.AppEventType.TaskSchedularEventType.STOP,
                types.AppEventType.ManagerEventType.MEMORY_STOP,
                types.AppEventType.MainThreadDispatcherEventType.STOP,
                types.AppEventType.ManagerEventType.CHARACTER_STOP,
            ]
            for event in events:
                emit(BaseEvent(type=event))
            self.runtime=None
        except Exception as e:
            logger.exception(f"ChatBotApp close error: {e}", exc_info=True)
        finally:
            from .events.bus import event_bus
            event_bus.clear()
            self._running = False

    # async def __run_asyncio_loop(self):
    #     try:
    #         loop = asyncio.new_event_loop()
    #         asyncio.set_event_loop(loop)
    #         logger.info("Asyncio event loop started in background thread")
    #         self.run_web()
    #     except Exception as e:
    #         logger.error(f"Asyncio loop error: {e}")
    #     finally:
    #         loop.close()
    #         logger.info("Asyncio event loop stopped")

    def run_web(self) -> None:
        from .api.server import start_web_server
        start_web_server()

    async def run(self) -> None:
        """主入口 - 主线程运行 Qt，后台线程运行 asyncio"""
        try:
            self._running = True
            logger.start()
            emit(BaseEvent(type=types.AppEventType.TaskSchedularEventType.START))    
            self._asyncio_thread = threading.Thread(
                target=self.run_web,
                daemon=True,
                name="AsyncioThread"
            )
            self._asyncio_thread.start()
            from .pipeline import chat
            import time
            time.sleep(3)
            await self.ui()
        except KeyboardInterrupt:
            logger.info("ChatBotApp interrupted by user")
        except Exception as e:
            logger.exception(f"ChatBotApp run error: {e}", exc_info=True)
        finally:
            await self.close()
    
    def close_app(self,qt_app):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.close())
            else:
                loop.run_until_complete(self.close())
        except RuntimeError:
            asyncio.run(self.close())
        qt_app.quit()
        
    async def ui(self):
        from PyQt5.QtWidgets import QApplication
        qt_app = QApplication.instance() or QApplication(sys.argv)
        from PyQt5.QtCore import QTimer 
        timer = QTimer()
        # 初始化主线程调度器
        self.main_thread_dispatcher = get_main_thread_dispatcher()
        await self.main_thread_dispatcher.start_processing()
        timer.timeout.connect(self.main_thread_dispatcher._process_pending_qt_tasks)
        timer.start(16)  # ~60fps
        qt_app.setQuitOnLastWindowClosed(False) # type: ignore
        self.__create_system_tray(qt_app)
        logger.info("Entering Qt main event loop")
        ret = qt_app.exec_()
        if self._running:
            await self.close()
        sys.exit(ret)
    
    def __create_system_tray(self,qt_app):
        from PyQt5.QtWidgets import  QSystemTrayIcon, QMenu, QAction
        if QSystemTrayIcon.isSystemTrayAvailable():
            from PyQt5.QtGui import QIcon
            from .runtime import RuntimePath
            self.system_tray_icon = QSystemTrayIcon()# 避免被gc回收
            self.system_tray_icon.setToolTip("ChatBotApp")
            self.system_tray_icon.setIcon(QIcon(RuntimePath.get_icon_file_path()))
            # 创建右键菜单
            menu = QMenu()
            from PyQt5.QtWidgets import QAction

            actions={
                "quit":{
                    "compent":QAction("退出"),
                    "callback":lambda: self.close_app(qt_app)
                }
            }
            for key,value in actions.items():
                value["compent"].triggered.connect(value["callback"])
                menu.addAction(value["compent"])
            self.system_tray_icon.setContextMenu(menu)
            self.system_tray_icon.show()

_app=None

def create_app(
        debug:bool=False,
        debug_modules:Literal["service","pipeline","web","all"]= "all"
    ):
    global _app
    if _app is None:
        _app = Application(debug,debug_modules)
    return _app

def get_app():
    global _app
    if _app is None:
        raise Exception("App not initialized")
    return _app

