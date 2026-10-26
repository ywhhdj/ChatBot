"""桌面窗口生命周期管理。

约束
────
* 窗口的创建 / 显示 / 关闭**只能在主线程**执行。
  跨线程调用一律经 `MainThreadDispatcher.run_on_main_thread` 转发，
  否则 Qt 会直接崩（QWidget 不是线程安全的）。
* `close()` 必须在 Web 停止**之前**调用：窗口里的页面还在连着
  WebSocket，先停 Web 会让前端抛出断连错误并可能触发重连风暴。
* 管理器持有窗口引用：局部变量会被 GC，窗口会瞬间消失
  （与系统托盘图标同一个坑）。
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from ..logger import logger
from ..manager.base import BaseManager
from .bridge import JsApiBridge, get_bridge
from .views import DesktopBrowserWindow, WebViewBackend


class BrowserViewManager(BaseManager):
    """桌面 WebView 窗口管理器（单例）。"""

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._window: Optional[DesktopBrowserWindow] = None
        self._enabled: bool = True
        self._dispatcher: Optional[Callable[..., Any]] = None
        self._rwlock = threading.RLock()
        self._options: Dict[str, Any] = {}
        self._initialized = True

    # ---------- 配置 ----------

    def configure(self, enabled: bool = True, **options: Any) -> None:
        """配置窗口参数（需在 `open()` 之前调用）。"""
        with self._rwlock:
            self._enabled = bool(enabled)
            self._options.update(options)

    def disable(self) -> None:
        with self._rwlock:
            self._enabled = False

    # ---------- 主线程派发 ----------

    def _dispatcher_fn(self):
        if self._dispatcher is None:
            try:
                from .dispatcher import get_main_thread_dispatcher
                self._dispatcher = get_main_thread_dispatcher().run_on_main_thread
            except Exception:  # noqa: BLE001
                self._dispatcher = None
        return self._dispatcher

    def _on_main_thread(self, func: Callable[[], Any]) -> Any:
        """在主线程执行；调用方已经在主线程时直接执行（零开销）。"""
        dispatch = self._dispatcher_fn()
        if dispatch is None:
            # 派发器不可用时（应用未启动 / 已停止），退化到直接调用
            return func()
        try:
            return dispatch(func)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[BrowserView] 主线程派发失败，退化直接调用: {exc}")
            return func()

    @property
    def is_main_thread(self) -> bool:
        return threading.current_thread() is threading.main_thread()

    # ---------- 打开 / 关闭 ----------

    def open(self, url: Optional[str] = None, **overrides: Any) -> bool:
        """创建并显示窗口。**线程安全**，内部会切到主线程。"""
        with self._rwlock:
            if not self._enabled:
                logger.info("[BrowserView] 已禁用，跳过创建窗口")
                return False
            if self._window is not None:
                logger.debug("[BrowserView] 窗口已存在")
                return True

            options = dict(self._options)
            options.update(overrides)

        if self.is_main_thread:
            return bool(self.__create_and_show(url, options))
        return bool(self._on_main_thread(lambda: self.__create_and_show(url, options)))

    def __create_and_show(self, url: Optional[str], options: Dict[str, Any]) -> bool:
        try:
            window = DesktopBrowserWindow(url=url, **options)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[BrowserView] 创建窗口失败: {exc}")
            return False

        if window.backend_name == WebViewBackend.NONE.value:
            logger.warning("[BrowserView] 无可用后端，不创建窗口")
            window.deleteLater()
            return False

        with self._rwlock:
            self._window = window

        window.show_and_load(url)
        logger.info(f"[BrowserView] 窗口已显示 (backend={window.backend_name}, url={window.url})")
        return True

    def close(self, timeout: float = 3.0) -> bool:
        """关闭并销毁窗口。**线程安全**。"""
        with self._rwlock:
            if self._window is None:
                return True

        if self.is_main_thread:
            return self.__close_impl()

        try:
            return bool(self._on_main_thread(self.__close_impl))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[BrowserView] 关闭窗口失败: {exc}")
            return False

    def __close_impl(self) -> bool:
        with self._rwlock:
            window = self._window
            self._window = None
        if window is None:
            return True
        try:
            # 先推一个事件让前端主动断开 WebSocket，避免断连报错
            window.post_message("shutdown", {})
        except Exception:  # noqa: BLE001
            pass
        try:
            window.close()
            window.deleteLater()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[BrowserView] close window failed: {exc}")
        logger.info("[BrowserView] 窗口已关闭")
        return True

    # ---------- 跨线程推送 ----------

    def post_message(self, event: str, data: Any = None) -> None:
        """向页面推送事件。**任意线程可调用**。"""
        with self._rwlock:
            window = self._window
        if window is None:
            return

        def _send() -> None:
            try:
                window.post_message(event, data)
            except Exception:  # noqa: BLE001
                pass

        if self.is_main_thread:
            _send()
        else:
            self._on_main_thread(_send)

    def evaluate_js(self, script: str) -> None:
        """执行 JS。**任意线程可调用**。"""
        with self._rwlock:
            window = self._window
        if window is None:
            return

        def _run() -> None:
            try:
                window.evaluate_js(script)
            except Exception:  # noqa: BLE001
                pass

        if self.is_main_thread:
            _run()
        else:
            self._on_main_thread(_run)

    def navigate(self, url: str) -> None:
        with self._rwlock:
            window = self._window
        if window is None:
            return

        def _go() -> None:
            try:
                window.load(url)
            except Exception:  # noqa: BLE001
                pass

        if self.is_main_thread:
            _go()
        else:
            self._on_main_thread(_go)

    # ---------- 状态 ----------

    @property
    def window(self) -> Optional[DesktopBrowserWindow]:
        with self._rwlock:
            return self._window

    @property
    def is_open(self) -> bool:
        return self.window is not None

    @property
    def backend(self) -> str:
        w = self.window
        return w.backend_name if w is not None else WebViewBackend.NONE.value

    def bridge(self) -> JsApiBridge:
        return get_bridge()

    def stop(self) -> None:
        """`_BaseManager` 停止钩子。"""
        self.close()
