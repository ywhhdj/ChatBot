"""嵌入 WebView 的桌面窗口。

后端优先级（自动降级，任一不可用都不会让应用起不来）：

    WebViewBackend.WRY      qtwebview2 >= 0.6（wry / Tauri 同款引擎）
    WebViewBackend.CLR      qtwebview2 < 0.6（WinForms + .NET CLR）
    WebViewBackend.WEBENGINE PyQt6-WebEngine（体积大，兜底）
    WebViewBackend.NONE     不可用

Windows 上优先 WRY：不打包 Chromium，共享系统 Edge WebView2 运行时，
体积和内存都比 QWebEngine 小一个数量级。
"""
from __future__ import annotations
import os
from enum import Enum
from typing import Any, Dict, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..logger import logger
from .bridge import JsApiBridge, get_bridge, dumps

DEFAULT_URL = "http://127.0.0.1:8000"


class WebViewBackend(str, Enum):
    WRY = "wry"              # qtwebview2 >= 0.6
    CLR = "clr"              # qtwebview2 < 0.6
    WEBENGINE = "webengine"  # PyQt6-WebEngine
    NONE = "none"


def _detect_backend(prefer: Optional[str] = None) -> tuple:
    """探测可用的 WebView 后端，返回 `(backend, factory, bridge_factory)`。"""
    order = [WebViewBackend.WRY, WebViewBackend.CLR, WebViewBackend.WEBENGINE]
    if prefer:
        want = str(prefer).lower()
        order = [b for b in order if b.value == want] + [b for b in order if b.value != want]

    for backend in order:
        try:
            if backend is WebViewBackend.WRY:
                from qtwebview2 import DictJsBridge, QtWebViewWidget  # type: ignore[union-attr]

                # v0.6 才有 QtWebViewWidget；v0.5 只有 QtWebView2Widget
                return backend, QtWebViewWidget, DictJsBridge
            if backend is WebViewBackend.CLR:
                from qtwebview2 import DictJsBridge, QtWebView2Widget

                return backend, QtWebView2Widget, DictJsBridge
            if backend is WebViewBackend.WEBENGINE:
                from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore[union-attr]

                return backend, QWebEngineView, None
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[BrowserView] backend {backend.value} unavailable: {exc}")
            continue

    return WebViewBackend.NONE, None, None


def available_backends() -> list:
    """返回可用后端列表（不含 NONE），便于诊断。"""
    found = []
    for b in (WebViewBackend.WRY, WebViewBackend.CLR, WebViewBackend.WEBENGINE):
        backend, factory, _ = _detect_backend(b.value)
        if factory is not None and backend is b:
            found.append(b.value)
    return found


class DesktopBrowserWindow(QWidget):
    """承载 WebView 的桌面窗口。

    要点
    ────
    * **惰性加载**（lazyload=True）：窗口立刻可见，网页后台加载，
      避免"白屏等 3 秒才看到窗口"。
    * **页面加载完再推就绪事件**：前端靠 `__onAppReady` 判断可以开始发请求，
      否则会在 Web 服务还没 listen 时打一堆 ConnectionRefused。
    * **evaluate_js 必须在主线程调用**：wry/Qt 都不允许跨线程操作控件。
    """

    # 页面加载完成 / 失败，供外部（manager、托盘）订阅
    pageFinished = pyqtSignal(bool)

    def __init__(
        self,
        url: Optional[str] = None,
        title: str = "ChatBot",
        width: int = 1100,
        height: int = 720,
        frameless: bool = False,
        transparent: bool = False,
        debug: bool = False,
        backend: Optional[str] = None,
        bridge: Optional[JsApiBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._url = url or DEFAULT_URL
        self._debug = debug
        self._bridge = bridge or get_bridge()
        self._backend, factory, bridge_factory = _detect_backend(backend)
        self._webview: Any = None
        self._ready = False

        self.setWindowTitle(title)
        self.resize(width, height)

        if frameless:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        if transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if factory is None:
            logger.warning("[BrowserView] 无可用 WebView 后端，窗口将不显示网页内容")
            self._backend = WebViewBackend.NONE
            return

        try:
            self._webview = self.__create_webview(factory, bridge_factory, transparent)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[BrowserView] 创建 WebView 失败: {exc}")
            self._webview = None
            self._backend = WebViewBackend.NONE
            return

        layout.addWidget(self._webview)
        self.__connect_signals()

    # ---------- 构造 WebView ----------

    def __create_webview(self, factory: Any, bridge_factory: Any, transparent: bool) -> Any:
        if self._backend is WebViewBackend.WEBENGINE:
            view = factory(self)
            return view

        js_apis = None
        if bridge_factory is not None:
            try:
                js_apis = bridge_factory()
                bound = self._bridge.bind_to(js_apis)
                logger.info(f"[BrowserView] js bridge bound {bound} methods")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[BrowserView] 桥接初始化失败: {exc}")
                js_apis = None

        kwargs: Dict[str, Any] = {
            "parent": self,
            "debug": self._debug,
            "js_apis": js_apis,
        }

        # 惰性加载 + 透明背景仅 wry/CLR 后端支持
        try:
            kwargs["lazyload"] = True
            kwargs["transparent"] = transparent
        except Exception:  # noqa: BLE001
            pass

        try:
            return factory(**kwargs)
        except TypeError:
            # 旧版签名不接受 lazyload/transparent
            kwargs.pop("lazyload", None)
            kwargs.pop("transparent", None)
            return factory(**kwargs)

    def __connect_signals(self) -> None:
        """连接页面加载信号（不同后端信号名不同，全部按鸭子类型适配）。"""
        wv = self._webview
        if wv is None:
            return

        if self._backend is WebViewBackend.WEBENGINE:
            try:
                wv.loadFinished.connect(lambda ok: self.__on_finished(ok))
            except Exception:  # noqa: BLE001
                pass
            return

        # qtwebview2：信号载体可能是 widget 本身，也可能是 widget.signals
        holder = wv
        for attr in ("signals", "bridge", "webview_signals"):
            cand = getattr(wv, attr, None)
            if cand is not None and hasattr(cand, "page_loaded"):
                holder = cand
                break

        sig = getattr(holder, "page_loaded", None)
        if sig is None:
            sig = getattr(holder, "domContentLoaded", None)
        if sig is not None:
            try:
                sig.connect(self.__on_qtwebview_loaded)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[BrowserView] connect page_loaded failed: {exc}")

    # ---------- 加载 ----------

    def load(self, url: Optional[str] = None) -> None:
        if url:
            self._url = url
        wv = self._webview
        if wv is None:
            logger.warning("[BrowserView] 无 WebView，跳过加载")
            return

        try:
            if hasattr(wv, "load_url"):
                wv.load_url(self._url)
            elif hasattr(wv, "setUrl"):
                from PyQt6.QtCore import QUrl

                wv.setUrl(QUrl(self._url))
            elif hasattr(wv, "load"):
                from PyQt6.QtCore import QUrl

                wv.load(QUrl(self._url))
            logger.info(f"[BrowserView] loading {self._url}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[BrowserView] 加载失败: {exc}")

    def load_html(self, html: str) -> None:
        wv = self._webview
        if wv is None:
            return
        try:
            if hasattr(wv, "load_html"):
                wv.load_html(html)
            elif hasattr(wv, "setHtml"):
                wv.setHtml(html)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[BrowserView] load_html 失败: {exc}")

    def reload(self) -> None:
        try:
            if self._webview is not None and hasattr(self._webview, "reload"):
                self._webview.reload()
        except Exception:  # noqa: BLE001
            pass

    # ---------- Python → JS ----------

    def evaluate_js(self, script: str) -> None:
        """执行 JS。**必须在主线程调用**。"""
        wv = self._webview
        if wv is None:
            return
        try:
            fn = getattr(wv, "evaluate_js", None) or getattr(wv, "eval_js", None)
            if fn is not None:
                fn(script)
            else:
                wv.page().runJavaScript(script)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[BrowserView] evaluate_js failed: {exc}")

    def post_message(self, event: str, data: Any = None) -> None:
        """向前端推送事件：`window.__onAppEvent(event, data)`。

        用于把后端的流式输出（聊天增量、TTS 音频块、日志）推给页面，
        避免前端轮询。
        """
        payload = dumps({
            "event": event,
            "data": data
        })
        self.evaluate_js(
            f"(function(){{ if (typeof window.__onAppEvent === 'function') "
            f"{{ window.__onAppEvent({payload}); }} }})()"
        )

    # ---------- 信号回调 ----------

    def __on_qtwebview_loaded(self, *args: Any) -> None:
        # qtwebview2 的 page_loaded 带 (PageLoadEvent, url) 参数，
        # 只有 Finished 才算加载完成
        evt = args[0] if args else None
        state = getattr(evt, "name", None) or getattr(evt, "value", None)
        ok = state in (None, "Finished", 2)
        self.__on_finished(bool(ok))

    def __on_finished(self, ok: bool) -> None:
        self._ready = bool(ok)
        logger.info(f"[BrowserView] page {'loaded' if ok else 'failed'}")
        if ok:
            self.post_message("ready", {
                "url": self._url,
                "backend": self.backend_name
            })
        self.pageFinished.emit(bool(ok))

    # ---------- 属性 ----------

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "value", "none")

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def url(self) -> str:
        return self._url

    @property
    def webview(self) -> Any:
        return self._webview

    # ---------- 生命周期 ----------

    def show_and_load(self, url: Optional[str] = None) -> None:
        """先显示窗口（惰性加载下立刻可见），再触发加载。"""
        self.show()
        self.raise_()
        # 下一个事件循环再 load：确保窗口已完成 layout/winId 创建，
        # 原生子窗口（wry）需要宿主窗口先拿到 winId 才能正确嵌入
        QTimer.singleShot(0, lambda: self.load(url))

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        try:
            self._webview = None
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
