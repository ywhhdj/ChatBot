"""Live2D + 对话框 + 组件设置 + 动捕 的综合测试 Demo。

用法:
    python -m pkg.core.live2d.demo /path/to/xxx.model3.json [音频.wav] [脸部模型目录]

不带音频/动捕也能跑：音频用合成正弦喂 RMS，动捕模块缺失时自动跳过。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .canvas import Live2DCanvas
from .components import EnhancedDialogueComponent
from .dialogue_core import DialogueEvent


# ─────────────────────────────────────────────────────────────────────────────
# 口型演示：50ms 喂一块正弦 PCM
# ─────────────────────────────────────────────────────────────────────────────
class LipSyncDemo:
    def __init__(self, canvas: Live2DCanvas, parent: QWidget):
        self.canvas = canvas
        self.sr = 44100
        self.chunk_frames = int(self.sr * 0.05)
        self._t = 0.0
        self._left = 0
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._tick)

    def start(self, seconds: float = 2.0) -> None:
        self._left = int(seconds / 0.05)
        self._t = 0.0
        self._timer.start(50)

    def _tick(self) -> None:
        if self._left <= 0:
            self._timer.stop()
            return
        self._left -= 1
        t = np.arange(self.chunk_frames, dtype=np.float64) / self.sr + self._t
        wave = (0.28 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        pcm = (wave * 32767).astype(np.int16).tobytes()
        self._t += self.chunk_frames / self.sr
        self.canvas.push_audio_chunk(pcm)


# ─────────────────────────────────────────────────────────────────────────────
# 控制面板
# ─────────────────────────────────────────────────────────────────────────────
class ControlPanel(QWidget):
    def __init__(self, canvas: Live2DCanvas, dialogue: EnhancedDialogueComponent):
        super().__init__()
        self.setWindowTitle("Live2D 测试面板")
        self.canvas = canvas
        self.dialogue = dialogue
        self._line_idx = 0
        self._expr_idx = 0
        self._motion_idx = 0
        self._speaking = False
        self._fps_flip = False
        self._scale_idx = 0
        self.lipsync = LipSyncDemo(canvas, self)
        self.face = None
        self.store = None

        root = QVBoxLayout(self)
        self.status = QLabel("状态加载中…", self)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status)

        for title, buttons in [
            ("对话", [
                ("下一句", self._next_line),
                ("跳过", lambda: dialogue.skip()),
                ("清空", lambda: dialogue.clear()),
                ("回看", self._backlog),
                ("选 1", lambda: dialogue.choose(0)),
                ("选 2", lambda: dialogue.choose(1)),
            ]),
            ("表情/动作", [
                ("表情+", self._next_expression),
                ("动作+", self._next_motion),
                ("眨眼", lambda: canvas.submit("blink")),
                ("重置表情", lambda: canvas.submit("reset_expression")),
                ("重置姿态", lambda: canvas.submit("reset_pose")),
            ]),
            ("音频/口型", [
                ("口型脉冲", lambda: self.lipsync.start(2.0)),
                ("说话开/关", self._toggle_speaking),
                ("播放 WAV", self._play_wav),
            ]),
            ("设置热更新", [
                ("fps 30/60", self._toggle_fps),
                ("scale 0.6/0.8/1.0", self._cycle_scale),
                ("idle 开/关", self._toggle_idle),
                ("保存 UI 设置", self._save_settings),
                ("重置 UI 设置", self._reset_settings),
            ]),
            ("动捕", [
                ("初始化/开/关", self._toggle_face),
                ("单次轮询", self._poll_face),
            ]),
            ("调试", [
                ("打印状态", self._print_status),
            ]),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{title}:"))
            for text, cb in buttons:
                b = QPushButton(text)
                b.clicked.connect(cb)
                row.addWidget(b)
            row.addStretch(1)
            root.addLayout(row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(1000)

    # ── 状态 ──
    def _refresh_status(self) -> None:
        st = self.canvas.get_status()
        keys = ["running", "model_loaded", "fps", "frames", "render_scale",
                "gaze_source", "idle", "speaking", "render_width", "render_height"]
        text = "  ".join(f"{k}={st.get(k)}" for k in keys)
        text += f"\n表情={len(st.get('expressions') or [])}  动作组={list((st.get('motion_groups') or {}).keys())}"
        if self.face is not None:
            text += f"\n动捕: available={self.face.available} backend={self.face.backend} err={self.face.last_error or '-'}"
        self.status.setText(text)

    def _print_status(self) -> None:
        print("[status]", json.dumps(self.canvas.get_status(), ensure_ascii=False, default=str))

    # ── 对话 ──
    _LINES = [
        ("欢迎使用 Live2D 测试 Demo。", "旁白", ""),
        ("鼠标在窗口里移动，眼睛和头会跟着你。", "助手", "happy"),
        ("把鼠标移出窗口，视线会回中；静止一会儿会开始待机漂移。", "助手", ""),
        ("要听一段合成音吗？点「口型脉冲」看看嘴会不会动。", "助手", "happy"),
        ("最后来一个选项，试试选择按钮。", "助手", "sad"),
    ]

    def _next_line(self) -> None:
        text, speaker, emotion = self._LINES[self._line_idx % len(self._LINES)]
        self._line_idx += 1
        choices = ["好的，继续", "算了，停一下"] if self._line_idx >= len(self._LINES) else None
        self.dialogue.display_text(text, speaker=speaker, emotion=emotion, choices=choices)

    def _backlog(self) -> None:
        rows = self.dialogue.backlog(limit=10)
        print("[backlog]", json.dumps(rows, ensure_ascii=False))

    # ── 表情/动作 ──
    def _next_expression(self) -> None:
        exprs = self.canvas.get_status().get("expressions") or []
        if not exprs:
            print("[expr] 模型没有表情，跳过")
            return
        name = exprs[self._expr_idx % len(exprs)]
        self._expr_idx += 1
        print("[expr] 触发 ->", name)
        
        # 完全无需硬编码，直接走统一入口
        self.canvas.submit("expression", value=name)

    def _next_motion(self) -> None:
        groups = self.canvas.get_status().get("motion_groups") or {}
        if not groups:
            print("[motion] 模型没有动作组，跳过")
            return
        names = list(groups.keys())
        name = names[self._motion_idx % len(names)]
        self._motion_idx += 1
        print("[motion] ->", name)
        self.canvas.submit("motion", group=name, priority=2)

    # ── 音频/说话 ──
    def _toggle_speaking(self) -> None:
        self._speaking = not self._speaking
        self.canvas.submit("dialogue", state="speaking", on=self._speaking)
        print("[speaking]", self._speaking)

    def _play_wav(self) -> None:
        path, _ = (None, None)
        # 简单起见，用环境变量给 WAV 路径
        path = os.environ.get("DEMO_WAV", "")
        if not path or not os.path.isfile(path):
            print("[wav] 未设置 DEMO_WAV 或文件不存在")
            return
        print("[wav] play", path)
        self.canvas.sync_play(path)

    # ── 设置热更新 ──
    def _toggle_fps(self) -> None:
        self._fps_flip = not self._fps_flip
        fps = 30 if self._fps_flip else 60
        self.canvas.set_settings({**self.canvas.settings, "fps": fps, "idle_fps": fps // 2})
        print("[settings] fps ->", fps)

    def _cycle_scale(self) -> None:
        scales = [0.6, 0.8, 1.0]
        self._scale_idx = (self._scale_idx + 1) % len(scales)
        s = scales[self._scale_idx]
        self.canvas.set_settings({**self.canvas.settings, "render_scale": s, "adaptive_fps": False})
        print("[settings] render_scale ->", s)

    def _toggle_idle(self) -> None:
        cur = bool(self.canvas.settings.get("idle_enabled", True))
        self.canvas.set_settings({**self.canvas.settings, "idle_enabled": not cur})
        print("[settings] idle_enabled ->", not cur)

    # ── 组件设置存储 ──
    def _save_settings(self) -> None:
        try:
            from .component_settings import ComponentSettingsStore
            if self.store is None:
                self.store = ComponentSettingsStore(Path("./_demo_ui_settings.json"))
            saved = self.store.save(self.canvas.settings)
            print("[store] saved", len(saved), "keys ->", self.store.path)
        except Exception as exc:
            print("[store] 不可用:", type(exc).__name__, exc)

    def _reset_settings(self) -> None:
        if self.store is None:
            return
        try:
            self.store.reset()
            print("[store] reset ->", self.store.path)
            self.canvas.set_settings(self.store.merge({"model_path": self.canvas.model_path}))
            print("[store] applied to canvas")
        except Exception as exc:
            print("[store] reset 失败:", exc)

    # ── 动捕 ──
    def _toggle_face(self) -> None:
        try:
            from .components import FaceTrackerComponent
        except Exception as exc:
            print("[face] 组件不可用:", exc)
            return
        if self.face is None:
            self.face = FaceTrackerComponent(
                model_path=os.environ.get("FACE_MODEL", ""),
                process_callback=lambda d: self.canvas.apply_face_data(d),
                mirror=True, face_source=int(os.environ.get("CAM_INDEX", "0")),
                face_fps=30, enabled=True, timeout_ms=800, smoothing=0.45,
                on_timeout=lambda: self.canvas.face_data_lost(),
            )
            self.face.set_timeout_callback(lambda: self.canvas.face_data_lost())
            self.face.init()
            print("[face] available=", self.face.available,
                  "backend=", self.face.backend,
                  "err=", self.face.last_error)
            if self.face.available:
                self.face.start()
                print("[face] started")
        else:
            enabled = not self.face.is_running
            self.face.set_enabled(enabled)
            print("[face] enabled ->", enabled)

    def _poll_face(self) -> None:
        if self.face is None:
            print("[face] 未初始化")
            return
        data = self.face.poll_once()
        print("[face] poll ->", "None" if data is None else type(data).__name__)

    # ── 生命周期 ──
    def closeEvent(self, event) -> None:
        if self.face is not None:
            try:
                self.face.close()
            except Exception:
                pass
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    model = sys.argv[1]
    if not os.path.isfile(model):
        print(f"[demo] 模型不存在: {model}")
        return 2
    audio_wav = sys.argv[2] if len(sys.argv) > 2 else ""
    if audio_wav:
        os.environ["DEMO_WAV"] = audio_wav

    app = QApplication(sys.argv[:1])

    W, H = 900, 700
    canvas = Live2DCanvas(
        model_path=model,
        model_name="Live2D Demo",
        canvas_size=(W, H),
        fps=60,
        enable_audio_sync=True,        # 走 RMS meter，口型脉冲不依赖声卡
        enable_chunk_playback=False,   # demo 不出声，只驱动口型
        audio_sample_rate=44100,
        audio_channels=1,
        audio_sample_width=2,
        lipSync=3.0,
        scale=1.0,
        settings={
            "canvas_size": [W, H],
            "frameless": False,        # 有标题栏，方便关闭/移动
            "always_on_top": False,
            "click_through": False,
            "opacity": 1.0,
            "render_scale": 1.0,
            "auto_blink": True,
            "auto_breath": True,
            "gaze_enabled": True,
            "gaze_when_no_face": True,
            "gaze_idle_drift": True,
            "idle_enabled": True,
            "idle_after_seconds": 3.0,
            "idle_min_interval": 4.0,
            "idle_max_interval": 8.0,
            "adaptive_fps": True,
            "frame_skip_on_hidden": True,
            "hit_test_enabled": True,
            "drag_enabled": True,
            "dialogue_position": "custom",
            "dialogue_anchor_x": 100,
            "dialogue_anchor_y": 720,
            "dialogue_max_width": 900,
            "dialogue_height": 180,
            "dialogue_typing_cps": 35,
            "dialogue_auto_seconds": 0.0,
            "dialogue_bg_opacity": 0.86,
            "emotion_map": {"happy": "happy", "sad": "sad",
                            "angry": "angry", "neutral": ""},
        },
    )
    try:
        canvas.init()
    except Exception as exc:
        print(f"[demo] canvas.init 失败: {exc}")
        return 3
    canvas.move(100, 50)
    canvas.show()
    canvas.start()

    # 对话框：custom 位置 + 事件桥接
    dialogue = EnhancedDialogueComponent(
        cfg={**canvas.settings},
        instant=False, text_speed=35, max_width=900,
    )

    def bridge(ev: DialogueEvent) -> None:
        if ev.kind == "speaking":
            on = bool(ev.data.get("on"))
            canvas.submit("dialogue", state="speaking", on=on)
            emo = str(ev.data.get("emotion") or "")
            if on and emo:
                canvas.submit("dialogue", state="emotion", value=emo)
        elif ev.kind == "line_started":
            emo = str(ev.data.get("emotion") or "")
            if emo:
                canvas.submit("dialogue", state="emotion", value=emo)
        elif ev.kind == "char_typed":
            canvas.submit("dialogue", state="typing")

    dialogue.eventFired.connect(bridge)
    dialogue.move(100, 720)
    dialogue.show()

    panel = ControlPanel(canvas, dialogue)
    panel.move(1020, 60)
    panel.show()

    # 自动演示：启动 1.5s 后开始第一句
    QTimer.singleShot(1500, lambda: dialogue.display_text(
        "Demo 已启动。用「下一句」推进台词，用控制面板测各种功能。",
        speaker="系统", emotion="happy"))

    def _report() -> None:
        st = canvas.get_status()
        keys = ("model_loaded", "fps", "frames", "gaze_source", "idle", "speaking")
        print("[demo]", json.dumps({k: st.get(k) for k in keys}, ensure_ascii=False))
    t = QTimer()
    t.timeout.connect(_report)
    t.start(3000)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())