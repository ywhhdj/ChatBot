import os
import sys
from typing import Callable, Literal, Optional
from ..logger import logger

class UIApp:
    def __init__(
        self,
        app_name: str,
        debug: bool = False,
    ):
        self.app_name = app_name
        self.qt_app = None
        self._exit_code = 0
        self._manager = None
        self._running = False
        self._manager=None
        self._dispatcher=None
        self.debug = debug

        self._qt_timer=None
        self._qt_heartbeat=None
        self._browser_width = 1100
        self._browser_height = 720
        self._browser_frameless = False
        self._browser_transparent = False

        # UI 模式。auto | desktop | web
        #   auto    -> 非 debug 且有 HTML 资源且有 WebView 后端 => desktop，否则 web
        #   desktop -> qtwebview2 桌面端（不启 HTTP，Bridge 进程内调用）
        #   web     -> 启 uvicorn + 挂载静态资源
        self._ui_mode = str(os.environ.get("CHATBOT_UI_MODE", "auto")).lower()
        self._ui_mode_resolved: str = ""   # 实际生效的模式
        self._resource_dir: str = ""       # 前端静态资源目录
    
    def _stop_timers(self) -> None:
        for name in ("_qt_timer", "_qt_heartbeat"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
                setattr(self, name, None)
    
    def _start_web(self):
        # 按模式决定是否启 Web。
        # 桌面端走 JS Bridge 进程内调用，HTTP 服务是纯额外开销
        # （端口、uvicorn 线程、序列化往返），一律不启。
        self._ui_mode_resolved = self._resolve_ui_mode()
        logger.info(f"[App] UI 模式: {self._ui_mode_resolved}")
        if self.web_enabled:
            from ..api.server import run_web
            try:
                run_web(app_name=self.app_name)
            except Exception as e:
                logger.exception(f"[App] start web error: {e}", exc_info=True)

    def show(self):
        self._start_web()
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer

        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False) # type: ignore
        self.qt_app.setApplicationName(self.app_name)
        from .dispatcher import get_main_thread_dispatcher

        # 主线程调度器：同步启动，主线程没有 asyncio loop
        self._dispatcher = get_main_thread_dispatcher()
        self._dispatcher.start_processing()

        # 16ms 派发：消费工作线程投递来的主线程任务
        self._qt_timer = QTimer(self.qt_app)
        self._qt_timer.setInterval(16)
        self._qt_timer.timeout.connect(self._dispatcher.pump)
        self._qt_timer.start()

        # 定期回到 Python 侧，Ctrl+C 才不会「按了没反应」。
        self._qt_heartbeat = QTimer(self.qt_app)
        self._qt_heartbeat.setInterval(200)
        self._qt_heartbeat.timeout.connect(lambda: None)
        self._qt_heartbeat.start()

        self._create_system_tray()

        self._create_browser_view()

        # 主线程唯一的循环。UI 全速响应
        ret = self.qt_app.exec()
        if self._exit_code == 0:
            self._exit_code = int(ret or 0)
    
    def _create_browser_view(self) -> None:
        """创建桌面 WebView 窗口（qtwebview2），在主线程调用"""
        if self.web_enabled:
            return
        try:
            from .manager import BrowserViewManager

            self._manager = BrowserViewManager()
            # 桌面端直接 file:// 加载本地资源，不经过 HTTP
            url = None
            if self._resource_dir:
                from pathlib import Path

                idx = Path(self._resource_dir) / "index.html"
                url = idx.as_uri()

            self._manager.configure(
                enabled=True,
                title="ChatBot",
                width=self._browser_width,
                height=self._browser_height,
                frameless=self._browser_frameless,
                transparent=self._browser_transparent,
                debug=self.debug,
            )
            ok = self._manager.open(url=url)
            if not ok:
                logger.warning("[App] 桌面窗口未创建（无可用 WebView 后端）")
        except Exception as e:
            logger.exception(f"[App] open browser view error: {e}", exc_info=True)
    
    def _create_system_tray(self) -> None:
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QAction

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("[App] system tray is not available")
            return

        from PyQt6.QtGui import QIcon
        from ..runtime import RuntimePath

        icon_path = RuntimePath.get_icon_file_path()
        icon = QIcon(os.fspath(icon_path)) if icon_path and os.path.exists(icon_path) else QIcon()

        # 必须挂在实例上：局部变量会让托盘图标被 GC 掉而立刻消失
        self.system_tray_icon = QSystemTrayIcon(icon, self.qt_app)
        self.system_tray_icon.setToolTip("ChatBotApp")

        menu = QMenu()
        actions = {
            "quit": {
                "compent": QAction("退出"),
                "callback": lambda: self.exit(0),
            }
        }
        for value in actions.values():
            value["compent"].triggered.connect(value["callback"])
            menu.addAction(value["compent"])

        self.system_tray_icon.setContextMenu(menu)
        self.system_tray_icon.show()
    
    def _hide_system_tray(self) -> None:
        if self.system_tray_icon is not None:
            try:
                self.system_tray_icon.hide()
            except Exception:
                pass
            self.system_tray_icon = None
    
    def _close_browser_view(self) -> None:
        try:
            if self._manager is None:
                return
            self._manager.close()
            self._manager = None
        except Exception as e:
            logger.debug(f"[App] close browser view failed: {e}")
    
    def web_stop(self) -> None:
        if self.web_enabled:
            from ..api.server import join_web_thread
            try:
                join_web_thread(timeout=10.0)
            except Exception as e:
                logger.exception(f"[App] shutdown web server error: {e}", exc_info=True)
        else:
            logger.info("[App] desktop 模式，无需停止 Web")

    def stop(self) -> None:
        if not self._running:
            return
        self._close_browser_view()
        if self._dispatcher is not None:
            self._dispatcher.stop()
            self._dispatcher = None
        self._stop_timers()
        self._hide_system_tray()
        self._running = False
    
    def exit(self, exit_code: int = 0) -> None:
        if exit_code:
            self._exit_code = exit_code
        if not self._running:
            return
        if self.qt_app is not None:
            self.qt_app.quit()
            self.qt_app = None

        # ---------- UI 模式决策（K2–K6） ----------
    
    @property
    def exit_code(self) -> int:
        return self._exit_code or 0

    @exit_code.setter
    def exit_code(self, value: int) -> None:
        self._exit_code = value

    def _has_html_resources(self) -> Optional[str]:
        """探测前端静态资源，返回含 index.html 的目录；没有则返回 None。"""
        from ..runtime import RuntimePath, StandardPaths
        candidates = [
            RuntimePath.get_web_resources_dir(),                 # <root>/static
            StandardPaths.get_resources_dir() / "web",           # <root>/resources/web
            StandardPaths.get_app_root() / "web",                # <root>/web
        ]
        for d in candidates:
            try:
                if (d / "index.html").exists():
                    return str(d)
            except Exception:
                continue
        return None
    

    def _has_webview_backend(self) -> bool:
        """后端不可用（如 Linux 无 wry / WebEngine）时必须回退 web。"""
        try:
            from .views import available_backends
            return len(available_backends()) > 0
        except Exception:
            return False

    def _resolve_ui_mode(self) -> Literal["auto", "desktop", "web"]:
        """决定实际启动模式。"""
        mode = (self._ui_mode or "auto").lower()
        if mode not in ("auto", "desktop", "web"):
            mode = "auto"

        # K4：调试模式默认 web，方便用浏览器 DevTools 调试前端
        if mode == "auto" and self.debug:
            return "web"

        if mode == "desktop":
            return "desktop"

        if mode == "web":
            return "web"

        # auto + 非 debug：有资源且有后端才走桌面端
        res = self._has_html_resources()
        if res and self._has_webview_backend():
            self._resource_dir = res
            return "desktop"
        if not res:
            logger.info("[App] 未发现前端 HTML 资源，回退 Web 模式")
        else:
            logger.info("[App] 无可用 WebView 后端，回退 Web 模式")
        return "web"

    @property
    def web_enabled(self) -> bool:
        return self._ui_mode_resolved == "web"