"""Live2D 服务入口：控制器（主线程）+ 服务壳（可跨线程调用）"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from PyQt6.QtCore import QObject

from ...events import emit, off, on, on_event_class, types as eventType
from ...events.data import BaseEvent
from ...keys import ServiceKeys
from ...logger import logger
from ...runtime import RuntimePath
from .. import base
from ..manager import Service
from .settings import normalize, parse_canvas_size


class Live2DController(QObject):
    """所有 Qt 操作都只在主线程执行；网络线程只通过服务壳派发。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.dialogue = None
        self.__face_tracker = None
        self._qt_app = None
        self._initialized = False
        self._running = False
        # controller 内部永远是「组件设置 + 对外 5 项」合并后的完整 cfg；
        # 服务壳 Live2DView._settings 只持有 5 个对外字段。
        self._settings: Dict[str, Any] = {}
        self._store = None
        self._panel = None
        self._settings_button = None
        self._last_backlog_request = 0

    @property
    def face_tracker(self):
        """供「创建视图」测试访问动捕组件"""
        return self.__face_tracker

    def initialize(
        self,
        settings: Dict[str, Any],
        canvas_factory=None,
        store=None,
    ) -> None:
        """构建整套 UI。

        ``settings`` 可以只含 5 个对外字段（服务壳），也可以是完整 cfg
        （预览视图）；组件设置一律以 ``ComponentSettingsStore`` 为准，
        对外 5 项覆盖其上，避免 service config 的默认值把组件 UI 里用户
        改过的 107 项冲掉。

        ``canvas_factory`` 供无 GL 环境注入 ``HeadlessCanvas`` 做视图测试。
        """
        if self._initialized:
            return
        from PyQt6.QtWidgets import QApplication, QPushButton
        from .component_settings import ComponentSettingsStore

        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        self._store = store or ComponentSettingsStore()
        cfg = self._store.merge(settings)
        self._settings = cfg

        if canvas_factory is None:
            from .canvas import Live2DCanvas as canvas_factory
        from .components import EnhancedDialogueComponent, FaceTrackerComponent

        w, h = parse_canvas_size(cfg.get("canvas_size"))
        self.canvas = canvas_factory(
            model_path=str(cfg.get("model_path") or ""),
            model_name=str(cfg.get("window_title") or "Live2DModel"),
            canvas_size=(w, h),
            fps=int(cfg.get("fps", 60)),
            enable_audio_sync=bool(cfg.get("enable_audio_sync", False)),
            enable_chunk_playback=bool(cfg.get("enable_chunk_playback", False)),
            audio_sample_rate=int(cfg.get("audio_sample_rate", 44100)),
            audio_channels=int(cfg.get("audio_channels", 1)),
            audio_sample_width=int(cfg.get("audio_sample_width", 2)),
            lipSync=float(cfg.get("lip_sync_gain", 3.0)),
            scale=float(cfg.get("scale", 1.0)),
            settings=cfg,
        )
        self.canvas.init()
        logger.info("[Live2D] Canvas initialized in main thread")

        # 对话框是画布的子控件，天然叠在立绘上方（galgame 布局）
        self.dialogue = EnhancedDialogueComponent(
            parent=self.canvas, cfg=cfg, on_event=self._on_dialogue_event)
        self.dialogue.setVisible(bool(cfg.get("dialogue_enabled", True)))

        self.__face_tracker = FaceTrackerComponent(
            model_path=cfg.get("pipeface_model_path"),
            process_callback=self.canvas.apply_face_data,
            face_source=_coerce_face_source(cfg.get("face_source")),
            face_fps=int(cfg.get("face_fps", 30)),
            mirror=bool(cfg.get("face_mirror", False)),
            enabled=bool(cfg.get("is_face_detected", False)),
            timeout_ms=int(cfg.get("face_timeout_ms", 800)),
            smoothing=float(cfg.get("face_smoothing", 0.45)),
            on_timeout=self.canvas.face_data_lost,
        )
        self.__face_tracker.set_process_callback(self.canvas.apply_face_data)
        self.__face_tracker.init()

        # 组件 UI 设置的唯一入口：画布右下角齿轮。107 项表现开关都在这里改，
        # 不经服务配置 / 存档 / HTTP API。
        try:
            self._settings_button = QPushButton("⚙", self.canvas)
            self._settings_button.setObjectName("live2d_settings_button")
            self._settings_button.setToolTip("Live2D 组件设置（107 项）")
            self._settings_button.setFixedSize(30, 30)
            self._settings_button.clicked.connect(self.open_settings)
            self._place_settings_button()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[Live2D] settings button skipped: {exc}")

        self._initialized = True
        logger.info("[Live2D] Face tracker + dialogue + settings UI initialized")

    def _place_settings_button(self) -> None:
        if self._settings_button is None or self.canvas is None:
            return
        self._settings_button.move(max(0, self.canvas.width() - 38),
                                   max(0, self.canvas.height() - 38))
        self._settings_button.raise_()

    def open_settings(self):
        """打开组件 UI 设置面板；应用后直接热应用，不走三态/API。"""
        from .settings_panel import Live2DSettingsPanel

        store = self._store
        if store is None:
            from .component_settings import ComponentSettingsStore
            store = ComponentSettingsStore()
            self._store = store
        if self._panel is None:
            self._panel = Live2DSettingsPanel(
                store=store, on_apply=self.apply_component_settings,
                public_cfg=store.public_view(self._settings),
                parent=self.canvas)
        self._panel.set_values(store.load())
        self._panel.show()
        self._panel.raise_()
        return self._panel

    def _on_dialogue_event(self, ev) -> None:
        """把对话框事件联动到模型（只提交意图，不碰 GL）。"""
        if self.canvas is None:
            return
        kind = ev.kind
        if kind == "speaking":
            self.canvas.submit("dialogue", state="speaking",
                               on=bool(ev.data.get("on", False)))
        elif kind == "line_started":
            emotion = str(ev.data.get("emotion") or "")
            if emotion:
                self.canvas.submit("dialogue", state="emotion", value=emotion)
            self.canvas.submit("dialogue", state="typing")
        elif kind == "char_typed":
            self.canvas.submit("dialogue", state="typing")
        elif kind == "backlog_requested":
            self._last_backlog_request += 1

    # ── 生命周期 ─────────────────────────────────────────────────

    def start(self):
        if not self._initialized or not self.canvas:
            logger.error("[Live2D] not initialized")
            return
        if self._running:
            return
        self._running = True
        self._do_position()
        self.canvas.start()
        self.canvas.show()
        if self.dialogue and self._settings.get("dialogue_enabled", True):
            self.dialogue.show()
            self.dialogue._reposition()
        if self.__face_tracker:
            try:
                self.__face_tracker.start()
            except Exception as exc:
                logger.error(f"[Live2D] face tracker start error: {exc}")
                self.canvas.face_data_lost()
        logger.info("[Live2D] started")

    def stop(self):
        self._running = False
        if self.__face_tracker:
            self.__face_tracker.stop()      # 内部会通知回落鼠标视线
        if self.dialogue:
            self.dialogue.hide()
        if self.canvas:
            self.canvas.hide()

    def close(self):
        self._running = False
        if self._panel is not None:
            try:
                self._panel.close()
            except Exception:
                pass
            self._panel = None
        if self.__face_tracker:
            self.__face_tracker.close()
            self.__face_tracker = None
        if self.dialogue:
            self.dialogue.close()
            self.dialogue = None
        if self.canvas:
            self.canvas.stop()
            self.canvas.close()
            self.canvas = None
        self._initialized = False

    def show(self):
        if self.canvas:
            self.canvas.show()
        if self.dialogue and self._settings.get("dialogue_enabled", True):
            self.dialogue.show()

    def hide(self):
        if self.dialogue:
            self.dialogue.hide()
        if self.canvas:
            self.canvas.hide()

    def _do_position(self):
        if not self.canvas:
            return
        x, y = int(self._settings.get("window_x", -1)), int(self._settings.get("window_y", -1))
        if x >= 0 and y >= 0:
            self.canvas.move(x, y)
            return
        geometry = self._screen_geometry()
        if geometry is None:
            logger.error("[Live2D] screen geometry unavailable")
            return
        self.canvas.move(max(0, geometry.width() - self.canvas.width() - 50),
                         max(0, geometry.height() - self.canvas.height() - 50))

    @staticmethod
    def _screen_geometry():
        try:
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                return screen.availableGeometry()
        except Exception:
            pass
        return None

    # ── 配置热应用 ───────────────────────────────────────────────

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        """``apply_config`` 触发：只收到 5 个对外字段，组件设置从 store 合并。"""
        cfg = self._store.merge(settings) if self._store else normalize(settings)
        self._apply_full_settings(cfg)

    def apply_component_settings(self, _cfg: Dict[str, Any] | None = None) -> None:
        """组件 UI 面板「应用」：已写进 store，直接热应用，不写服务存档。"""
        if self._store is None:
            return
        public = self._store.public_view(self._settings)
        self._apply_full_settings(self._store.merge(public))

    def _apply_full_settings(self, cfg: Dict[str, Any]) -> None:
        """两层合并后的完整 cfg 增量生效，不重建窗口、不重启服务。"""
        old = dict(self._settings)
        self._settings = cfg
        if self.canvas:
            self.canvas.set_settings(cfg)
        if self.dialogue:
            self.dialogue.set_config(cfg)
            self.dialogue.setVisible(bool(cfg.get("dialogue_enabled", True)))
        if self.__face_tracker:
            self.__face_tracker.set_enabled(bool(cfg.get("is_face_detected", False)))
            self.__face_tracker.set_model_path(cfg.get("pipeface_model_path"))
            self.__face_tracker.set_source(_coerce_face_source(cfg.get("face_source")))
            self.__face_tracker.set_fps(int(cfg.get("face_fps", 30)))
            self.__face_tracker.set_mirror(bool(cfg.get("face_mirror", False)))
            self.__face_tracker.set_timeout(int(cfg.get("face_timeout_ms", 800)))
            self.__face_tracker.set_smoothing(float(cfg.get("face_smoothing", 0.45)))
            self.__face_tracker.set_timeout_callback(self.canvas.face_data_lost)
            if not cfg.get("is_face_detected", False):
                self.canvas.face_data_lost()   # 关键：立刻交还鼠标视线
        if old.get("window_x") != cfg.get("window_x") or old.get("window_y") != cfg.get("window_y"):
            self._do_position()
        self._place_settings_button()

    # ── 对外能力 ─────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        if self.canvas is None:
            return {"model_loaded": False, "running": False,
                    "gaze_source": "center", "note": "canvas 未初始化"}
        return self.canvas.get_status()

    def get_dialogue_status(self) -> Dict[str, Any]:
        if self.dialogue is None:
            return {"state": "idle", "note": "dialogue 未初始化"}
        return self.dialogue._engine.status()

    def get_backlog(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        if self.dialogue is None:
            return []
        return self.dialogue.backlog(limit, offset)

    def set_rotation_angle(self, angle: float):
        if self.canvas:
            self.canvas.set_rotation_angle(angle)

    def set_opacity(self, opacity: float):
        if self.canvas:
            self.canvas.set_opacity(opacity)

    def put_audio(self, audio_path: str):
        if self.canvas:
            self.canvas.pull_audio(audio_path)

    def put_audio_chunk(self, chunk: bytes):
        if self.canvas:
            self.canvas.push_audio_chunk(chunk)

    def set_model_path(self, model_path: str):
        if self.canvas:
            self.canvas.load_model(model_path)

    def set_face_enabled(self, enabled: bool):
        if self.__face_tracker:
            self.__face_tracker.set_enabled(bool(enabled))
        if self.canvas and not enabled:
            self.canvas.face_data_lost()

    def set_face_source(self, source):
        if self.__face_tracker:
            self.__face_tracker.set_source(source)

    def set_face_fps(self, fps: int):
        if self.__face_tracker:
            self.__face_tracker.set_fps(int(fps))

    def set_expression(self, expression: str):
        if self.canvas:
            self.canvas.submit("expression", value=str(expression or ""))

    def reset_expression(self):
        if self.canvas:
            self.canvas.submit("reset_expression")

    def play_motion(self, group: str, index: int = 0, priority: int = 2):
        if self.canvas:
            self.canvas.submit("motion", group=str(group or ""),
                               index=int(index), priority=int(priority))

    def blink(self):
        if self.canvas:
            self.canvas.submit("blink")

    def reset_pose(self):
        if self.canvas:
            self.canvas.submit("reset_pose")

    def set_gaze(self, nx: float, ny: float):
        """手动注入归一化鼠标位置（-1..1），供无窗口环境下测试视线。"""
        if self.canvas:
            self.canvas.submit("mouse", nx=float(nx), ny=float(ny))

    def gaze_home(self):
        if self.canvas:
            self.canvas.submit("mouse_leave")

    def set_speaking(self, on: bool):
        if self.canvas:
            self.canvas.submit("speaking", on=bool(on))

    def set_emotion(self, emotion: str):
        if self.canvas:
            self.canvas.submit("emotion", value=str(emotion or ""))

    def push_dialogue(
        self,
        text: str,
        speaker: str = "",
        emotion: str = "",
        instant: Optional[bool] = None,
        choices: Optional[List[str]] = None,
    ) -> None:
        if self.dialogue:
            self.dialogue.display_text(text, speaker=speaker, emotion=emotion,
                                       instant=instant, choices=choices)

    def skip_dialogue(self):
        if self.dialogue:
            self.dialogue.skip()

    def clear_dialogue(self):
        if self.dialogue:
            self.dialogue.clear()

    def advance_dialogue(self):
        if self.dialogue:
            self.dialogue.advance()

    def choose(self, index: int):
        if self.dialogue:
            self.dialogue.choose(int(index))

    def set_click_through(self, enabled: bool):
        if self.canvas:
            cfg = dict(self._settings)
            cfg["click_through"] = bool(enabled)
            self.apply_settings(cfg)

    def set_always_on_top(self, enabled: bool):
        if self.canvas:
            cfg = dict(self._settings)
            cfg["always_on_top"] = bool(enabled)
            self.apply_settings(cfg)


def _coerce_face_source(value: Any) -> Union[int, str]:
    if isinstance(value, int):
        return value
    text = str(value or "0").strip()
    return int(text) if text.isdigit() else text


@on_event_class([
    (eventType.Live2DEventType.LIVE2D_START, "start"),
    (eventType.Live2DEventType.LIVE2D_AUDIO_PLAY, "put_audio"),
    (eventType.Live2DEventType.LIVE2D_STOP, "stop"),
    (eventType.Live2DEventType.LIVE2D_SET_MODEL, "set_model_path"),
    (eventType.Live2DEventType.LIVE2D_CLOSE, "close"),
])
@Service(id=ServiceKeys.LIVE2D)
class Live2DView(base.BaseService):
    """Live2D / Galgame 服务。

    只对外暴露 ``Live2DConfig.fields`` 的 5 项，走 §3.22 三态链路；``apply_config``
    触发 ``on_config_change`` 做增量热应用。其余 107 项表现设置由窗口内
    ``Live2DSettingsPanel`` 直接编辑（``ComponentSettingsStore``），不进存档、
    不注册 API；两层在 ``ComponentSettingsStore.merge()`` 汇合。
    """

    name = "Live2D"
    description = "Live2D 立绘 + Galgame 对话框（鼠标视线 / 待机演出 / 动捕回落）"
    main_thread = True
    CONTROLLER_BUILD_TIMEOUT = 120.0

    def get_tools(self) -> list:
        from ...core.pipeline.models import ToolFunction, ToolFunctionParameters

        def tool(name: str, desc: str, props: Dict[str, Any], required: List[str]):
            return ToolFunction(
                name=name, description=desc,
                parameters=ToolFunctionParameters(
                    type="object", properties=props, required=required),
            )

        s = {"type": "string"}
        n = {"type": "number"}
        b = {"type": "boolean"}
        return [
            tool("set_model_path", "切换 Live2D 模型（.model3.json 路径）",
                 {"model_path": s}, ["model_path"]),
            tool("set_expression", "切换模型表情（id 需存在于 .model3.json）",
                 {"expression": s}, ["expression"]),
            tool("play_motion", "播放动作组", {"group": s, "index": n, "priority": n},
                 ["group"]),
            tool("blink", "眨一次眼", {}, []),
            tool("reset_pose", "复位姿态", {}, []),
            tool("set_emotion", "按情绪名映射表情",
                 {"emotion": s}, ["emotion"]),
            tool("set_gaze", "手动设置视线目标（归一化 -1..1，测试用）",
                 {"nx": n, "ny": n}, ["nx", "ny"]),
            tool("gaze_home", "视线回中", {}, []),
            tool("set_face_enabled", "开启/关闭人脸动捕；关闭后自动回落到鼠标视线",
                 {"enabled": b}, ["enabled"]),
            tool("set_face_fps", "设置动捕帧率", {"fps": n}, ["fps"]),
            tool("set_rotation_angle", "设置立绘旋转角度", {"angle": n}, ["angle"]),
            tool("set_opacity", "设置窗口不透明度(0~1)", {"opacity": n}, ["opacity"]),
            tool("set_click_through", "开启/关闭点击穿透", {"enabled": b}, ["enabled"]),
            tool("set_always_on_top", "开启/关闭窗口置顶", {"enabled": b}, ["enabled"]),
            tool("push_dialogue", "推送一段 galgame 台词",
                 {"text": s, "speaker": s, "emotion": s, "instant": b},
                 ["text"]),
            tool("skip_dialogue", "跳过当前打字机动画", {}, []),
            tool("clear_dialogue", "清空对话框", {}, []),
            tool("set_speaking", "标记说话开始/结束（联动表情与口型）",
                 {"on": b}, ["on"]),
        ]

    def __init__(
        self,
        model_path: Optional[Path] = None,
        window_size: Union[Optional[tuple[int, int]], Literal["fullscreen"]] = None,
        window_icon_path: str = "",
        window_title: str = "Live2DModel",
        fps: int = 60,
        canvas_size: tuple[int, int] = (1200, 800),
        enable_audio_sync: bool = False,
        enable_chunk_playback: bool = False,
        is_face_detected: bool = False,
        pipeface_model_path: Optional[Path] = None,
        config: Optional[Dict[str, Any]] = None,
        **settings: Any,
    ) -> None:
        super().__init__()
        from ..config import Live2DConfig

        if model_path is None:
            model_path = RuntimePath.get_models_path(
                "live2d/肥牛/hiyori_pro_mic.model3.json")
        if pipeface_model_path is None:
            pipeface_model_path = RuntimePath.get_models_path(
                "mediapipe/face_landmarker.task")

        from .settings import split_public

        raw: Dict[str, Any] = dict(config or {})
        raw.update(settings)
        raw.setdefault("model_path", str(model_path))
        raw.setdefault("pipeface_model_path", str(pipeface_model_path))
        raw.setdefault("fps", int(fps))
        raw.setdefault("enable_audio_sync", bool(enable_audio_sync))
        if isinstance(window_size, (tuple, list)) and len(window_size) == 2:
            raw.setdefault("canvas_size", f"{int(window_size[0])}x{int(window_size[1])}")
        elif isinstance(canvas_size, (tuple, list)) and len(canvas_size) == 2:
            raw.setdefault("canvas_size", f"{int(canvas_size[0])}x{int(canvas_size[1])}")
        self._settings = split_public(raw)
        self.config = Live2DConfig(**self._settings)
        self._component_defaults: Dict[str, Any] = {
            "is_face_detected": bool(is_face_detected),
            "enable_chunk_playback": bool(enable_chunk_playback),
            "window_title": window_title,
            "window_icon_path": window_icon_path,
        }
        self._component_store = None
        self._running = False
        self._view_initialized = False
        self._controller: Optional[Live2DController] = None
        self._audio_chunk_bound = False
        self._closing = False

    # ── 配置三态（只管 5 个对外字段） ─────────────────────────────

    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """apply_config 时由 ServiceManager """
        from .settings import split_public

        self._settings = split_public(new_config)
        if self._controller is None:
            return
        self._dispatch("apply_settings", self._settings)
        logger.info("[Live2D] 对外配置已热应用（%d 项）", len(self._settings))

    def open_settings(self):
        """打开组件 UI 设置面板（派发到 Qt 主线程，不是 HTTP 端点）。"""
        return self._dispatch("open_settings")

    def get_status(self) -> Dict[str, Any]:
        """纯读引擎状态，跨线程安全（不碰 Qt widget 方法）。"""
        if self._controller is None:
            return {
                "model_loaded": False, 
                "running": self._running,
                "gaze_source": "center", 
                "note": "服务未初始化，请 POST /api/service/live2d/start",
            }
        return self._controller.get_status()

    # ── 主线程派发 ───────────────────────────────────────────────

    def _dispatch(self, method_name: str, *args: Any):
        if self._controller is None:
            return None
        method = getattr(self._controller, method_name, None)
        if not callable(method):
            return None
        return emit(BaseEvent(
            type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,
            args=(method, *args),
        ))

    def __ensure_controller(self):
        if self._controller is None:
            self._controller = emit(BaseEvent(
                type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,
                args=(self.__create_controller,),
                kwargs={"timeout": self.CONTROLLER_BUILD_TIMEOUT},
            ))
            if self._controller is None:
                raise RuntimeError(
                    "[Live2D] 主线程调度器未能创建控制器（调度器未就绪或超时）"
                )

    def __create_controller(self):
        from .component_settings import ComponentSettingsStore

        if self._component_store is None:
            store = ComponentSettingsStore()
            self._component_store = store
            if not store.exists and self._component_defaults:
                store.patch(self._component_defaults)
        controller = Live2DController()
        controller.initialize(self._settings, store=self._component_store)
        return controller

    # ── 对外能力（全部派发到主线程） ─────────────────────────────

    def set_rotation_angle(self, angle: float):
        self._dispatch("set_rotation_angle", float(angle))

    def set_opacity(self, opacity: float):
        self._dispatch("set_opacity", float(opacity))

    def put_audio(self, audio_path: str) -> None:
        if not audio_path or not os.path.exists(audio_path):
            logger.error(f"[Live2D] audio file not found: {audio_path}")
            return
        self._dispatch("put_audio", audio_path)

    def put_audio_chunk(self, chunk: bytes) -> None:
        self._dispatch("put_audio_chunk", chunk)

    def set_model_path(self, model_path: str) -> None:
        self._dispatch("set_model_path", str(model_path))

    def set_face_enabled(self, enabled: bool) -> None:
        self._dispatch("set_face_enabled", bool(enabled))

    def set_face_source(self, source: Union[int, str]) -> None:
        self._dispatch("set_face_source", source)

    def set_face_fps(self, fps: int) -> None:
        self._dispatch("set_face_fps", int(fps))

    def set_expression(self, expression: str) -> None:
        self._dispatch("set_expression", str(expression))

    def reset_expression(self) -> None:
        self._dispatch("reset_expression")

    def play_motion(self, group: str, index: int = 0, priority: int = 2) -> None:
        self._dispatch("play_motion", str(group), int(index), int(priority))

    def blink(self) -> None:
        self._dispatch("blink")

    def reset_pose(self) -> None:
        self._dispatch("reset_pose")

    def set_gaze(self, nx: float, ny: float) -> None:
        self._dispatch("set_gaze", float(nx), float(ny))

    def gaze_home(self) -> None:
        self._dispatch("gaze_home")

    def set_speaking(self, on: bool) -> None:
        self._dispatch("set_speaking", bool(on))

    def set_emotion(self, emotion: str) -> None:
        self._dispatch("set_emotion", str(emotion))

    def push_dialogue(self, text: str, speaker: str = "", emotion: str = "",
                      instant: Optional[bool] = None,
                      choices: Optional[List[str]] = None) -> None:
        self._dispatch("push_dialogue", str(text), str(speaker), str(emotion),
                       instant, list(choices or []))

    def skip_dialogue(self) -> None:
        self._dispatch("skip_dialogue")

    def clear_dialogue(self) -> None:
        self._dispatch("clear_dialogue")

    def advance_dialogue(self) -> None:
        self._dispatch("advance_dialogue")

    def choose(self, index: int) -> None:
        self._dispatch("choose", int(index))

    def set_click_through(self, enabled: bool) -> None:
        self._dispatch("set_click_through", bool(enabled))

    def set_always_on_top(self, enabled: bool) -> None:
        self._dispatch("set_always_on_top", bool(enabled))

    def get_dialogue_status(self) -> Dict[str, Any]:
        if self._controller is None:
            return {"state": "idle", "displayed": "", "full_text": ""}
        return self._controller.get_dialogue_status()

    def get_backlog(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        if self._controller is None:
            return []
        return self._controller.get_backlog(int(limit), int(offset))

    # ── 生命周期 ─────────────────────────────────────────────────

    def init(self):
        if self._view_initialized:
            return
        self.__ensure_controller()
        self._view_initialized = True

    def start(self) -> None:
        if not self._view_initialized:
            self.init()
        if self._running:
            return
        self._running = True
        if self._controller is None:
            logger.error("[Live2D] controller not available, start aborted")
            return
        self._dispatch("start")
        if not self._audio_chunk_bound:
            on(eventType.PipelineEventType.TTS_AUDIO_CHUNK, self.put_audio_chunk)
            self._audio_chunk_bound = True
        logger.info("[Live2D] Start signal emitted")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._dispatch("stop")
        if self._audio_chunk_bound:
            off(eventType.PipelineEventType.TTS_AUDIO_CHUNK, self.put_audio_chunk)
            self._audio_chunk_bound = False

    def close(self) -> None:
        self._running = False
        if self._controller:
            self._dispatch("close")
            self._controller = None
            self._view_initialized = False
        if self._audio_chunk_bound:
            off(eventType.PipelineEventType.TTS_AUDIO_CHUNK, self.put_audio_chunk)
            self._audio_chunk_bound = False
        logger.info("[Live2D] Closed")
