"""Live2D 的两个 UI 组件"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ...utils.util import create_daemon_thread
from .dialogue_core import (
    DialogueEngine, DialogueEvent, build_stylesheet, to_rich_text,
)
from .settings import normalize


class EnhancedDialogueComponent(QWidget):
    """Galgame 风格对话框（打字机 / 说话人 / 选项 / 回看 / 自动模式）。

    对外信号
    ────────
    ``eventFired(object)`` 转发所有 ``DialogueEvent``，controller 用它把
    「说话开始/结束」「情绪」「逐字」等联动到 Live2D 模型与 TTS；
    另提供常用信号的具名版本，方便只连其中一两个。
    """

    eventFired = pyqtSignal(object)
    lineStarted = pyqtSignal(object)
    textChanged = pyqtSignal(str, float)
    typingFinished = pyqtSignal(str)
    choiceSelected = pyqtSignal(int, str)
    speakingChanged = pyqtSignal(bool)
    charTyped = pyqtSignal(str)
    backlogRequested = pyqtSignal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        cfg: Optional[Dict[str, Any]] = None,
        on_event: Optional[Callable[[DialogueEvent], None]] = None,
        instant: bool = False,
        text_speed: int = 30,
        max_width: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dialogue_component")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.cfg = normalize(cfg)
        if cfg is None:
            self.cfg["dialogue_typing_cps"] = int(text_speed)
            self.cfg["dialogue_max_width"] = int(max_width)
            self.cfg["dialogue_instant"] = bool(instant)
        self._on_event = on_event
        self._engine = DialogueEngine(self.cfg)
        self._dragging = False
        self._drag_global = QPoint()
        self._drag_widget = QPoint()
        self._choice_buttons: List[QPushButton] = []
        self._blink_visible = True
        self._blink_phase = 0.0
        self._last_tick = time.monotonic()

        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(16)     # ~60Hz 足够，别用 1ms 空转
        self._typing_timer.timeout.connect(self._tick)

        self._create_ui()
        self.set_config(self.cfg)
        self._typing_timer.start()

    # ── UI ────────────────────────────────────────────────────────

    def _create_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QWidget(self)
        self.header.setObjectName("dialogue_header")
        self.header.setFixedHeight(30)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(6, 0, 6, 0)
        hl.setSpacing(4)

        self.title_label = QLabel("", self.header)
        self.title_label.setObjectName("dialogue_title")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)
        hl.addWidget(self.title_label)

        self._make_button("回看", self._request_backlog, "backlog_button")
        self._make_button("跳过", self.skip, "skip_button")
        self._make_button("清空", self.clear, "clear_button")
        self._make_button("×", self.hide, "close_button")
        self.close_button.setFixedSize(22, 22)   # type: ignore[assignment]
        root.addWidget(self.header)

        self.text_label = QLabel("", self)
        self.text_label.setObjectName("text_label")
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.RichText)
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Expanding)
        root.addWidget(self.text_label, 1)

        self.choice_container = QWidget(self)
        self.choice_layout = QVBoxLayout(self.choice_container)
        self.choice_layout.setContentsMargins(18, 0, 18, 8)
        self.choice_layout.setSpacing(4)
        self.choice_container.setVisible(False)
        root.addWidget(self.choice_container)

        self.indicator = QLabel("▼", self)
        self.indicator.setObjectName("dialogue_indicator")
        self.indicator.setAlignment(Qt.AlignmentFlag.AlignRight |
                                    Qt.AlignmentFlag.AlignBottom)
        root.addWidget(self.indicator)

    def _make_button(self, text: str, callback: Callable, name: str) -> None:
        btn = QPushButton(text, self.header)
        btn.setObjectName("dialogue_button")
        btn.clicked.connect(callback)
        setattr(self, name, btn)
        self.header.layout().addWidget(btn)  # type: ignore[union-attr]

    def _apply_layout(self) -> None:
        c = self.cfg
        w = max(320, int(c.get("dialogue_max_width", 1000)))
        h = max(100, int(c.get("dialogue_height", 200)))
        self.setMinimumWidth(320)
        self.setMaximumWidth(w)
        self.resize(w, h)
        self.setFixedHeight(h)
        self.title_label.setVisible(bool(c.get("dialogue_name_visible", True)))
        self.indicator.setVisible(bool(c.get("dialogue_indicator_visible", True)))
        self.text_label.setWordWrap(bool(c.get("dialogue_word_wrap", True)))
        align = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(str(c.get("dialogue_text_align") or "left"),
              Qt.AlignmentFlag.AlignLeft)
        self.text_label.setAlignment(align | Qt.AlignmentFlag.AlignTop)

        flags = Qt.WindowType.Widget
        if c.get("dialogue_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        try:
            self.setWindowFlags(flags)
            if was_visible:
                self.show()
        except Exception:
            pass
        self._reposition()

    def _reposition(self) -> None:
        pos = str(self.cfg.get("dialogue_position") or "bottom")
        p = self.parentWidget()
        if pos == "custom":
            self.move(int(self.cfg.get("dialogue_anchor_x", 0)),
                      int(self.cfg.get("dialogue_anchor_y", 0)))
            return
        if p is None:
            return
        pg = p.geometry()
        x = max(0, (pg.width() - self.width()) // 2)
        if pos == "bottom":
            y = max(0, pg.height() - self.height() - 24)
        else:
            y = 24
        self.move(x, y)

    # ── 配置 ──────────────────────────────────────────────────────

    def set_config(self, cfg: Dict[str, Any]) -> None:
        """热应用配置，不重启、不丢当前台词。"""
        self.cfg = normalize(cfg)
        self._engine.update_config(self.cfg)
        self.setStyleSheet(build_stylesheet(self.cfg))
        self._apply_layout()
        self._render_text()

    def set_text_color(self, color: str) -> None:
        self.set_config({
            **self.cfg,
            "dialogue_text_color": str(color)
        })

    def set_background_color(self, color: str, opacity: float = 0.8) -> None:
        self.set_config({
            **self.cfg,
            "dialogue_bg_color": str(color),
            "dialogue_bg_opacity": float(opacity)
        })

    def set_typing_speed(self, cps: int) -> None:
        self.set_config({**self.cfg, "dialogue_typing_cps": int(cps)})

    # ── 台词 ──────────────────────────────────────────────────────

    def display_text(
        self,
        text: str,
        speaker: str = "",
        emotion: str = "",
        instant: Optional[bool] = None,
        choices: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        events = self._engine.show(
            text,
            speaker=speaker,
            emotion=emotion,
            instant=instant,
            choices=choices,
            meta=meta
        )
        self._dispatch(events)
        if not self.isVisible() and self.cfg.get("dialogue_enabled", True):
            self.show()

    def skip(self) -> None:
        self._dispatch(self._engine.skip())

    def clear(self) -> None:
        self._dispatch(self._engine.clear())
        self._render_text()

    def advance(self) -> None:
        self._dispatch(self._engine.advance())

    def choose(self, index: int) -> None:
        self._dispatch(self._engine.choose(index))

    def status(self) -> Dict[str, Any]:
        return {
            **self._engine.status(),
            "visible": self.isVisible(),
            "enabled": bool(self.cfg.get("dialogue_enabled", True))
        }

    def backlog(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        return self._engine.backlog_page(limit, offset)

    def _request_backlog(self) -> None:
        self.backlogRequested.emit()
        self._on_event and self._on_event(DialogueEvent("backlog_requested", {}))

    # ── 帧驱动 ────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = time.monotonic()
        dt = max(0.0, min(250.0, (now - self._last_tick) * 1000.0))
        self._last_tick = now
        if self._engine.state != "idle":
            self._dispatch(self._engine.tick(dt))
        # 等待指示器闪烁
        if self.indicator.isVisible() and self._engine.state == "waiting":
            self._blink_phase += dt
            if self._blink_phase >= 420:
                self._blink_phase = 0.0
                self._blink_visible = not self._blink_visible
                self.indicator.setVisible(self._blink_visible)
        elif not self._blink_visible:
            self._blink_visible = True
            self.indicator.setVisible(True)

    def _dispatch(self, events: List[DialogueEvent]) -> None:
        for ev in events:
            self.eventFired.emit(ev)
            if self._on_event:
                try:
                    self._on_event(ev)
                except Exception:
                    pass
            kind = ev.kind
            if kind == "line_started":
                self.lineStarted.emit(ev.data)
                self.title_label.setText(str(ev.data.get("speaker") or ""))
                self.indicator.setVisible(False)
                self._render_choices([])
            elif kind in ("text_changed", "char_typed"):
                if kind == "char_typed":
                    self.charTyped.emit(str(ev.data.get("chunk") or ""))
                self._render_text()
            elif kind == "typing_finished":
                self.typingFinished.emit(str(ev.data.get("text") or ""))
                self.indicator.setVisible(
                    bool(self.cfg.get("dialogue_indicator_visible", True)))
                self._render_choices(list(ev.data.get("choices") or []))
            elif kind == "choices_shown":
                self._render_choices(list(ev.data.get("choices") or []))
            elif kind == "choice_selected":
                self.choiceSelected.emit(int(ev.data.get("index", -1)),
                                         str(ev.data.get("value") or ""))
            elif kind == "speaking":
                self.speakingChanged.emit(bool(ev.data.get("on", False)))
            elif kind == "cleared":
                self.title_label.setText("")
                self._render_choices([])
                self._render_text()
            elif kind == "queued":
                pass
            if kind == "text_changed":
                self.textChanged.emit(str(ev.data.get("text") or ""),
                                      float(ev.data.get("progress", 0.0)))

    def _render_text(self) -> None:
        cfg = self.cfg
        self.text_label.setText(to_rich_text(
            cfg,
            self._engine.displayed,
            name=self._engine.status().get("speaker", "")
        ))

    def _render_choices(self, choices: List[str]) -> None:
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            w = item.widget() # type: ignore
            if w is not None:
                w.deleteLater()
        self._choice_buttons.clear()
        self.choice_container.setVisible(bool(choices))
        for i, label in enumerate(choices):
            btn = QPushButton(f"{i + 1}.  {label}", self.choice_container)
            btn.setObjectName("choice_button")
            btn.clicked.connect(lambda _=False, idx=i: self.choose(idx))
            self.choice_layout.addWidget(btn)
            self._choice_buttons.append(btn)

    # ── 交互 ──────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self._dispatch(self._engine.click(ctrl=ctrl))
            if self.cfg.get("dialogue_draggable", True):
                self._dragging = True
                self._drag_global = event.globalPosition().toPoint()
                self._drag_widget = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(self._drag_widget +
                      event.globalPosition().toPoint() - self._drag_global)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        k = event.key()
        if k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._dispatch(self._engine.click(
                ctrl=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)))
        elif k == Qt.Key.Key_Escape:
            self.hide()
        elif self._choice_buttons and Qt.Key.Key_1 <= k <= Qt.Key.Key_9:
            idx = int(k) - int(Qt.Key.Key_1)
            if 0 <= idx < len(self._choice_buttons):
                self.choose(idx)
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._typing_timer.stop()
        self._dispatch(self._engine.clear())
        super().closeEvent(event)


class FaceTrackerComponent:
    """人脸追踪组件 + 新鲜度看门狗"""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        process_callback: Optional[Callable[[Any], None]] = None,
        mirror: bool = False,
        face_source: Union[int, str] = 0,
        face_fps: int = 30,
        enabled: bool = False,
        timeout_ms: int = 800,
        smoothing: float = 0.45,
        on_timeout: Optional[Callable[[], None]] = None,
    ):
        self.model_path = model_path
        self.__source: Union[int, str] = face_source
        self.__fps = max(1, int(face_fps))
        self.__enabled = bool(enabled)
        self.__process_callback = process_callback
        self.__mirror = bool(mirror)
        self.__timeout_ms = int(timeout_ms)
        self.__smoothing = float(smoothing)
        self.__on_timeout = on_timeout
        self.__thread = None
        self.__timer: Optional[QTimer] = None
        self.__watchdog: Optional[QTimer] = None
        self.__face_tracker = None
        self.__running = False
        self.__last_data_at = 0.0
        self._notified_lost = False
        self._available = False
        self._last_error = ""

    def init(self):
        if not self.__enabled:
            self._notify_lost()
            return
        if not self.model_path or not self.__process_callback:
            raise ValueError("FaceTrackerTask is not initialized")
        if self.__face_tracker:
            return
        # 后端模块此前缺失，一启用动捕就 ImportError；现在已补全
        # （core/pipeline/adapters/landmarker/face.py）。仍保留兜底，
        # 缺依赖时只回落到鼠标视线，不让服务起不来。
        try:
            from .face import FaceTracker
        except Exception as exc:  # noqa: BLE001
            self._available = False
            self._last_error = f"FaceTracker 模块不可用: {type(exc).__name__}: {exc}"
            self._notify_lost()
            return

        self.__face_tracker = FaceTracker(
            str(self.model_path),
            source=self.__source,
            mirror=self.__mirror,
            fps=self.__fps,
            smoothing=self.__smoothing,
        )
        self.__face_tracker.init()
        self._available = bool(getattr(self.__face_tracker, "available", True))
        self._last_error = str(getattr(self.__face_tracker, "last_error", "") or "")
        if not self._available:
            self._notify_lost()
        if self.__timer is None:
            self.__timer = QTimer()
            self.__timer.timeout.connect(self.__poll_face_data)
        if self.__watchdog is None:
            self.__watchdog = QTimer()
            self.__watchdog.setInterval(max(100, self.__timeout_ms // 2))
            self.__watchdog.timeout.connect(self.__check_freshness)

    def __poll_face_data(self):
        if not self.__face_tracker:
            return None
        try:
            data = self.__face_tracker.poll_result()
        except Exception:
            return None
        if data and self.__process_callback:
            self.__last_data_at = time.monotonic()
            self._notified_lost = False
            self.__process_callback(data)
        return data

    def poll_once(self):
        """显式驱动一次轮询（供「创建视图」测试，不依赖 QTimer 事件循环）。

        返回本帧 ``ResultFaceData`` 或 ``None``；同时完成时间戳 / 回落状态
        的更新，与定时器路径完全同一套逻辑。
        """
        return self.__poll_face_data()

    @property
    def available(self) -> bool:
        return bool(getattr(self, "_available", False))

    @property
    def backend(self) -> str:
        tracker = self.__face_tracker
        return str(getattr(tracker, "backend", "none")) if tracker else "none"

    @property
    def last_error(self) -> str:
        return str(getattr(self, "_last_error", "") or "")

    @property
    def tracker(self):
        """暴露后端实例，便于视图测试直接断言帧数据。"""
        return self.__face_tracker

    def __check_freshness(self) -> None:
        if not self.__enabled or not self.__running:
            return
        elapsed = (time.monotonic() - self.__last_data_at) * 1000.0
        if elapsed > self.__timeout_ms:
            self._notify_lost()

    def _notify_lost(self) -> None:
        if self._notified_lost:
            return
        self._notified_lost = True
        if self.__on_timeout:
            try:
                self.__on_timeout()
            except Exception:
                pass

    def set_fps(self, fps: int) -> None:
        self.__fps = max(1, int(fps))
        if self.__face_tracker is not None:
            self.__face_tracker.set_fps(self.__fps)
        if self.__timer is not None:
            self.__timer.setInterval(int(1000 / self.__fps))

    def set_smoothing(self, smoothing: float) -> None:
        """组件 UI 里的「动捕平滑」热应用；同步到后端 EMA 系数。"""
        self.__smoothing = max(0.0, min(1.0, float(smoothing)))
        if self.__face_tracker is not None:
            self.__face_tracker.set_smoothing(self.__smoothing)

    def set_timeout(self, timeout_ms: int) -> None:
        self.__timeout_ms = max(100, int(timeout_ms))
        if self.__watchdog is not None:
            self.__watchdog.setInterval(max(100, self.__timeout_ms // 2))

    @property
    def is_running(self) -> bool:
        return bool(self.__thread and self.__thread.is_alive())

    @property
    def has_fresh_data(self) -> bool:
        if not self.__enabled or not self.__running or self.__last_data_at <= 0:
            return False
        return (time.monotonic() - self.__last_data_at) * 1000.0 <= self.__timeout_ms

    def start(self) -> None:
        if not self.__enabled:
            self._notify_lost()
            return
        if self.__face_tracker is None:
            self.init()
        if self.__face_tracker is None or not self._available:
            # 依赖缺失 / 模型缺失 / 摄像头打不开：不抛错、不开空线程，
            # 直接保持「无动捕 → 眼睛随鼠标移动」。
            self._notify_lost()
            return
        if self.is_running:
            if self.__timer is not None and not self.__timer.isActive():
                self.__timer.start(int(1000 / self.__fps))
            if self.__watchdog is not None and not self.__watchdog.isActive():
                self.__watchdog.start()
            return
        self.__running = True
        self.__last_data_at = 0.0
        self.__thread = create_daemon_thread(
            self.__face_tracker.start,
            name="faceTracker"
        )
        self.__thread.start()
        if self.__timer is not None:
            self.__timer.start(int(1000 / self.__fps))
        if self.__watchdog is not None:
            self.__watchdog.start()
        # 刚启动还没数据，先让画布用鼠标视线
        self._notify_lost()

    def set_model_path(self, model_path: Union[str, Path]) -> None:
        self.model_path = model_path

    def set_source(self, source: Union[int, str]) -> None:
        self.__source = source
        if self.__face_tracker:
            self.__face_tracker.set_source(source)
            self._available = bool(getattr(self.__face_tracker, "available", True))
            self._last_error = str(getattr(self.__face_tracker, "last_error", "") or "")
            if not self._available:
                self._notify_lost()

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.__enabled and self.__face_tracker is not None:
            return
        self.__enabled = enabled
        if enabled:
            self.init()
            self.start()
        else:
            self.stop()          # stop() 里会立刻 _notify_lost()

    def set_mirror(self, mirror: bool) -> None:
        self.__mirror = bool(mirror)
        if self.__face_tracker:
            self.__face_tracker.set_mirror(mirror)

    def set_process_callback(self, process_callback: Callable[[Any], None]) -> None:
        self.__process_callback = process_callback

    def set_timeout_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self.__on_timeout = callback

    def stop(self) -> None:
        self.__running = False
        if self.__face_tracker:
            try:
                self.__face_tracker.stop()
            except Exception:
                pass
        if self.__thread is not None:
            self.__thread.join(timeout=1)
            self.__thread = None
        if self.__timer is not None:
            self.__timer.stop()
        if self.__watchdog is not None:
            self.__watchdog.stop()
        # 关键：动捕一停就交还视线控制权
        self._notify_lost()

    def close(self) -> None:
        self.stop()
        if self.__face_tracker:
            try:
                self.__face_tracker.close()
            except Exception:
                pass
        self.__face_tracker = None
        for attr in ("__timer", "__watchdog"):
            timer = getattr(self, attr, None)
            if timer is not None:
                timer.stop()
                try:
                    timer.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.__process_callback = None
        self.__on_timeout = None
