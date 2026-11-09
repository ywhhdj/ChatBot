"""UI 装配：QApplication / 主线程派发器 / 托盘 / 桌面窗口 / Web 服务器"""

from __future__ import annotations

import os
import sys
from typing import Callable, Literal, Optional

from ..logger import logger


class UIApp:
    def __init__(self, app_name: str, debug: bool = False):
        self.app_name = app_name
        self.debug = debug

        self.qt_app = None
        self._exit_code = 0
        self._manager = None
        self._dispatcher = None
        self._running = False
        self._stopped = False
        self._exit_requested = False
        self._web_started = False

        self.system_tray_icon = None
        self._tray_menu = None
        self._tray_actions: dict = {}

        self._qt_timer = None
        self._qt_heartbeat = None
        self._browser_width = 1100
        self._browser_height = 720
        self._browser_frameless = False
        self._browser_transparent = False

        # UI 模式：auto | desktop | web
        #   auto    -> 非 debug 且有 HTML 资源且有 WebView 后端 => desktop，否则 web
        #   desktop -> qtwebview2 桌面端（不启 HTTP，Bridge 进程内调用）
        #   web     -> 启 uvicorn + 挂载静态资源
        self._ui_mode = str(os.environ.get("CHATBOT_UI_MODE", "auto")).lower()
        self._ui_mode_resolved: str = ""
        self._resource_dir: str = ""

    # ---------- 定时器 ----------

    def _stop_timers(self) -> None:
        for name in ("_qt_timer", "_qt_heartbeat"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
                setattr(self, name, None)

    # ---------- Web ----------

    def _start_web(self) -> bool:
        """按模式决定是否启 Web，返回是否真的启动成功。"""
        self._ui_mode_resolved = self._resolve_ui_mode()
        logger.info(f"[App] UI 模式: {self._ui_mode_resolved}")
        self._web_started = False
        if not self.web_enabled:
            return True  # desktop 模式不需要 Web

        from ..api.server import run_web

        try:
            self._web_started = bool(run_web(app_name=self.app_name))
        except Exception as e:
            logger.exception(f"[App] start web error: {e}", exc_info=True)
            self._web_started = False
        return self._web_started

    def _fallback_to_desktop(self) -> None:
        """Web 启动失败时尽量降级到桌面窗口，而不是留一个连不上的页面。"""
        res = self._resource_dir or self._has_html_resources()
        if res and self._has_webview_backend():
            self._resource_dir = res
            self._ui_mode_resolved = "desktop"
            logger.warning("[App] Web 服务未启动，已降级到桌面窗口模式")
        else:
            logger.error(
                "[App] Web 服务未启动且无可用桌面 WebView 后端；"
                "应用仅在系统托盘运行"
            )

    # ---------- Qt 主循环 ----------

    def show(self):
        web_ok = self._start_web()
        if self.web_enabled and not web_ok:
            self._fallback_to_desktop()

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

        # 定期回到 Python 侧，Ctrl+C 才不会「按了没反应」
        self._qt_heartbeat = QTimer(self.qt_app)
        self._qt_heartbeat.setInterval(200)
        self._qt_heartbeat.timeout.connect(lambda: None)
        self._qt_heartbeat.start()

        self._running = True
        self._create_system_tray()
        self._create_browser_view()

        # 信号在 UI 建好之前就到了：不要进 Qt 循环，直接交给退出流程
        if self._exit_requested:
            logger.info("[App] 退出请求早于 Qt 主循环，跳过 exec()")
            return

        # 主线程唯一的循环
        ret = self.qt_app.exec()
        if self._exit_code == 0:
            self._exit_code = int(ret or 0)

    # ---------- 桌面窗口 ----------

    def _create_browser_view(self) -> None:
        """创建桌面 WebView 窗口（qtwebview2），在主线程调用。"""
        if self.web_enabled:
            return
        try:
            from .manager import BrowserViewManager

            self._manager = BrowserViewManager()
            url = None
            if self._resource_dir:
                from pathlib import Path

                idx = Path(self._resource_dir) / "index.html"
                if idx.exists():
                    url = idx.as_uri()

            self._manager.configure(
                enabled=True,
                title=self.app_name,
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

    def _show_window(self) -> None:
        """托盘「显示窗口」：web 模式下重新打开页面，desktop 模式下唤起窗口。"""
        try:
            if self._manager is not None and self._manager.is_open:
                window = self._manager.window
                if window is not None:
                    window.show()
                    window.raise_()
                return
            if self.web_enabled:
                # web 模式：交给浏览器（这里只做一次明确提示，不擅自起进程）
                logger.info("[App] Web 模式请在浏览器访问后端监听地址")
                return
            self._manager = None
            self._create_browser_view()
        except Exception as e:
            logger.debug(f"[App] show window failed: {e}")

    # ---------- 系统托盘 ----------

    def _create_system_tray(self) -> None:
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QAction, QIcon
        from ..runtime import RuntimePath

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("[App] system tray is not available")
            return

        icon_path = RuntimePath.get_icon_file_path()
        icon = QIcon(os.fspath(icon_path)) if icon_path and os.path.exists(icon_path) else QIcon()

        # 必须挂在实例上：局部变量会让托盘图标被 GC 掉而立刻消失
        self.system_tray_icon = QSystemTrayIcon(icon, self.qt_app)
        self.system_tray_icon.setToolTip(self.app_name)

        # QMenu / QAction 同样必须持有引用，否则右键菜单与退出项会随函数返回消失
        menu = QMenu()
        show_action = QAction("显示窗口", self.system_tray_icon)
        quit_action = QAction("退出", self.system_tray_icon)
        show_action.triggered.connect(self._show_window)
        quit_action.triggered.connect(lambda: self.exit(0))
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray_actions = {"show": show_action, "quit": quit_action}
        self._tray_menu = menu
        self.system_tray_icon.setContextMenu(menu)
        self.system_tray_icon.show()

    def _hide_system_tray(self) -> None:
        icon = getattr(self, "system_tray_icon", None)
        if icon is not None:
            try:
                icon.hide()
            except Exception:
                pass
        self.system_tray_icon = None
        self._tray_menu = None
        self._tray_actions = {}

    def _close_browser_view(self) -> None:
        try:
            if self._manager is None:
                return
            self._manager.close()
            self._manager = None
        except Exception as e:
            logger.debug(f"[App] close browser view failed: {e}")

    # ---------- 停止 ----------

    def web_stop(self) -> None:
        if not self._web_started:
            logger.info("[App] Web 未启动，无需停止")
            return
        from ..api.server import join_web_thread

        try:
            join_web_thread(timeout=10.0)
        except Exception as e:
            logger.exception(f"[App] shutdown web server error: {e}", exc_info=True)
        finally:
            self._web_started = False

    def _step(self, label: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as e:
            logger.debug(f"[App] UI stop step '{label}' failed: {e}")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        # 不依赖 _running：show() 抛异常时 _running 可能仍是 False，
        # 但定时器 / dispatcher / 托盘已经创建，必须清理。
        self._step("close_browser_view", self._close_browser_view)

        dispatcher = self._dispatcher
        if dispatcher is not None:
            self._step("dispatcher_stop", dispatcher.stop)
            self._dispatcher = None

        self._step("stop_timers", self._stop_timers)
        self._step("hide_system_tray", self._hide_system_tray)
        self._running = False

    def exit(self, exit_code: int = 0) -> None:
        """退出 Qt 主循环。托盘菜单与信号处理器都会走这里。"""
        if exit_code:
            self._exit_code = exit_code
        self._exit_requested = True
        app = self.qt_app
        if app is None:
            return
        try:
            app.quit()
        except Exception as e:
            logger.debug(f"[App] qt_app.quit failed: {e}")
        # 不清空 self.qt_app：关机阶段的定时器与托盘仍属于这个 QApplication

    # ---------- UI 模式决策 ----------

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
            RuntimePath.get_web_resources_dir(),       # <root>/static
            StandardPaths.get_resources_dir() / "web", # <root>/resources/web
            StandardPaths.get_app_root() / "web",      # <root>/web
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

    def _resolve_ui_mode(self) -> Literal["desktop", "web"]:
        """决定实际启动模式，并保证 ``_resource_dir`` 始终被设置。"""
        mode = (self._ui_mode or "auto").lower()
        if mode not in ("auto", "desktop", "web"):
            mode = "auto"

        self._resource_dir = self._has_html_resources() or ""

        # 调试模式默认 web，方便用浏览器 DevTools 调试前端
        if mode == "auto" and self.debug:
            return "web"

        if mode == "web":
            return "web"

        if mode == "desktop" or mode == "auto":
            if not self._resource_dir:
                logger.info("[App] 未发现前端 HTML 资源，回退 Web 模式")
                return "web"
            if not self._has_webview_backend():
                logger.info("[App] 无可用 WebView 后端，回退 Web 模式")
                return "web"
            return "desktop"

        return "web"

    @property
    def web_enabled(self) -> bool:
        return self._ui_mode_resolved == "web"
