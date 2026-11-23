"""Live2D 行为与性能内核
```
主线程 / 网络线程           渲染线程（唯一能碰 model 的地方）
  submit_intent(...)  ────►  BehaviorEngine.step(dt)
  （只写线程安全状态）          │
                                └─► FrameCommand(params, actions, stats)
                                      canvas 逐条应用到 model
```
"""
from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# 用字符串常量而不是 live2d.StandardParams，保证本模块可离线导入
P_ANGLE_X = "ParamAngleX"
P_ANGLE_Y = "ParamAngleY"
P_ANGLE_Z = "ParamAngleZ"
P_EYE_BALL_X = "ParamEyeBallX"
P_EYE_BALL_Y = "ParamEyeBallY"
P_EYE_L_OPEN = "ParamEyeLOpen"
P_EYE_R_OPEN = "ParamEyeROpen"
P_MOUTH_OPEN_Y = "ParamMouthOpenY"
P_BODY_ANGLE_X = "ParamBodyAngleX"
P_BREATH = "ParamBreath"

# 会让打字机额外停顿的标点
PAUSE_PUNCTUATION = set("，。！？…、；：,.!?;:")


def clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def smooth_to(current: float, target: float, alpha: float, dt: float = 1 / 60) -> float:
    """帧率无关的指数插值：alpha 是「60fps 下一帧追上的比例」。"""
    if alpha <= 0:
        return current
    a = 1.0 - math.pow(max(1e-6, 1.0 - min(1.0, alpha)), dt * 60.0)
    return current + (target - current) * a


def weighted_pick(weights: Dict[str, float], rng: random.Random,
                  exclude: str = "") -> str:
    """按权重挑一个 key；全为 0 / 空表时返回空串。"""
    items = [(k, float(v)) for k, v in (weights or {}).items()
             if k and k != exclude and float(v) > 0]
    if not items:
        # exclude 把唯一项排除了 → 允许回退到它，避免演出卡死
        items = [(k, float(v)) for k, v in (weights or {}).items()
                 if k and float(v) > 0]
    if not items:
        return ""
    total = sum(w for _, w in items)
    if total <= 0:
        return ""
    r = rng.random() * total
    acc = 0.0
    for key, w in items:
        acc += w
        if r <= acc:
            return key
    return items[-1][0]


# ─────────────────────────────────────────────────────────────────────────────
# 帧指令
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParamWrite:
    name: str
    value: float
    mode: str = "set"          # set | add


@dataclass
class ModelAction:
    kind: str                  # expression | motion | blink | reset_expression | reset_pose
    value: str = ""
    priority: int = 1
    index: int = 0


@dataclass
class FrameCommand:
    params: List[ParamWrite] = field(default_factory=list)
    actions: List[ModelAction] = field(default_factory=list)
    gaze_source: str = "center"
    idle: bool = False
    lip_rms: float = 0.0
    should_render: bool = True
    render_scale: float = 1.0
    target_fps: float = 60.0


@dataclass
class FrameStats:
    """滑动窗口统计，给 /api/live2d/status 与 devtools 面板用。"""

    fps: float = 0.0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    frames: int = 0
    render_width: int = 0
    render_height: int = 0
    render_scale: float = 1.0
    gaze_source: str = "center"
    idle: bool = False
    dropped_frames: int = 0
    model_loaded: bool = False
    face_active: bool = False
    speaking: bool = False
    process_rss_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fps": round(self.fps, 2), "avg_ms": round(self.avg_ms, 3),
            "p50_ms": round(self.p50_ms, 3), "p95_ms": round(self.p95_ms, 3),
            "frames": self.frames,
            "render_width": self.render_width, "render_height": self.render_height,
            "render_scale": round(self.render_scale, 3),
            "gaze_source": self.gaze_source, "idle": self.idle,
            "dropped_frames": self.dropped_frames,
            "model_loaded": self.model_loaded, "face_active": self.face_active,
            "speaking": self.speaking,
            "process_rss_mb": round(self.process_rss_mb, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 视线驱动
# ─────────────────────────────────────────────────────────────────────────────

class GazeDriver:
    """把鼠标 / 动捕 / 空闲漂移解析成头部与眼球参数。

    ``gaze_when_no_face=True`` 时：动捕未启用、无数据或超时，一律用鼠标位置。
    这是「没使用动捕时眼睛随鼠标移动」的实现点。
    """

    def __init__(self, cfg: Dict[str, Any], rng: Optional[random.Random] = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self._mouse: Optional[Tuple[float, float]] = None   # 归一化 -1..1
        self._mouse_left_at: float = 0.0
        self._last_mouse_activity: float = 0.0
        self._drift_target = (0.0, 0.0)
        self._next_drift: float = 0.0
        self._cur = (0.0, 0.0)      # 平滑后的 (x, y)
        self._z = 0.0
        self._face: Optional[Dict[str, float]] = None
        self._face_at: float = -1e9
        self._face_smoothed: Dict[str, float] = {}

    # ── 主线程入口 ────────────────────────────────────────────────

    def set_mouse(self, nx: float, ny: float, now: float) -> None:
        self._mouse = (clamp(nx), clamp(ny))
        self._last_mouse_activity = now
        self._mouse_left_at = 0.0

    def mouse_leave(self, now: float) -> None:
        self._mouse_left_at = now

    def set_face(self, data: Dict[str, float], now: float) -> None:
        self._face = dict(data)
        self._face_at = now

    def clear_face(self) -> None:
        self._face = None
        self._face_at = -1e9

    # ── 渲染线程 ──────────────────────────────────────────────────

    def face_is_fresh(self, now: float) -> bool:
        if not self.cfg.get("is_face_detected") or self._face is None:
            return False
        return (now - self._face_at) * 1000.0 <= float(self.cfg.get("face_timeout_ms", 800))

    def step(self, now: float, dt: float) -> Tuple[List[ParamWrite], str]:
        cfg = self.cfg
        if not cfg.get("gaze_enabled", True):
            return [], "off"

        # 1) 动捕优先
        if self.face_is_fresh(now) and cfg.get("face_priority", True):
            return self._step_face(dt), "face"

        # 2) 无动捕 / 动捕超时 → 鼠标
        if not cfg.get("gaze_when_no_face", True):
            target = (0.0, 0.0)
            source = "center"
        else:
            target, source = self._mouse_target(now)

        alpha = float(cfg.get("gaze_smoothing", 0.18))
        self._cur = (
            smooth_to(self._cur[0], target[0], alpha, dt),
            smooth_to(self._cur[1], target[1], alpha, dt),
        )
        x, y = self._cur

        dead = float(cfg.get("gaze_dead_zone", 0.03))
        if abs(x) < dead:
            x = 0.0
        if abs(y) < dead:
            y = 0.0

        sens = float(cfg.get("gaze_sensitivity", 1.0))
        max_x = float(cfg.get("gaze_max_x", 1.0))
        max_y = float(cfg.get("gaze_max_y", 0.7))
        eye = float(cfg.get("gaze_eyeball", 0.65))

        # 待机歪头：与头部角度叠加一个缓慢正弦，幅度很小
        z_target = 0.0
        if cfg.get("idle_head_sway", True) and source == "idle":
            z_target = math.sin(now * 0.7) * 0.12
        self._z = smooth_to(self._z, z_target, 0.05, dt)

        writes = [
            ParamWrite(P_ANGLE_X, clamp(x * sens * max_x)),
            ParamWrite(P_ANGLE_Y, clamp(-y * sens * max_y)),
            ParamWrite(P_ANGLE_Z, clamp(self._z)),
            ParamWrite(P_EYE_BALL_X, clamp(x * sens * eye)),
            ParamWrite(P_EYE_BALL_Y, clamp(-y * sens * eye)),
        ]
        return writes, source

    def _mouse_target(self, now: float) -> Tuple[Tuple[float, float], str]:
        # 鼠标已离开 → 在 return_seconds 内回中
        if self._mouse_left_at:
            span = max(1e-3, float(self.cfg.get("gaze_return_seconds", 1.2)))
            k = clamp((now - self._mouse_left_at) / span, 0.0, 1.0)
            if k >= 1.0:
                self._mouse = None
                self._mouse_left_at = 0.0
                return (0.0, 0.0), "center"
            base = self._mouse or (0.0, 0.0)
            return (base[0] * (1 - k), base[1] * (1 - k)), "returning"

        if self._mouse is None:
            return (0.0, 0.0), "center"

        # 长时间不动 → 轻微随机游离（galgame 的「活人感」）
        idle_for = now - self._last_mouse_activity
        if self.cfg.get("gaze_idle_drift", True) and idle_for >= 1.0:
            if now >= self._next_drift:
                amp = float(self.cfg.get("gaze_drift_amount", 0.22))
                interval = float(self.cfg.get("gaze_drift_interval", 3.2))
                self._drift_target = (
                    self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp))
                self._next_drift = now + max(0.5, interval)
            mx, my = self._mouse
            dx, dy = self._drift_target
            return (clamp(mx + dx), clamp(my + dy)), "idle"
        return self._mouse, "mouse"

    def _step_face(self, dt: float) -> List[ParamWrite]:
        alpha = float(self.cfg.get("face_smoothing", 0.45))
        out: List[ParamWrite] = []
        mapping = {
            "yaw": P_ANGLE_X, "pitch": P_ANGLE_Y, "roll": P_ANGLE_Z,
            "eye_left": P_EYE_L_OPEN, "eye_right": P_EYE_R_OPEN,
            "mouth_y": P_MOUTH_OPEN_Y,
        }
        for key, param in mapping.items():
            raw = float((self._face or {}).get(key, 0.0))
            prev = self._face_smoothed.get(key, raw)
            val = smooth_to(prev, raw, alpha, dt)
            self._face_smoothed[key] = val
            out.append(ParamWrite(param, clamp(val, -2.0, 2.0)))
        return out


# ─────────────────────────────────────────────────────────────────────────────
# 待机演出
# ─────────────────────────────────────────────────────────────────────────────

class IdleDirector:
    """空闲计时 + 随机表情 / 动作 / 眨眼，带冷却与暂停条件。"""

    def __init__(self, cfg: Dict[str, Any], rng: Optional[random.Random] = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self._last_activity = 0.0
        self._next_event = 0.0
        self._next_blink = 0.0
        self._last_expression = ""
        self._speaking = False
        self._face_active = False
        self._idle = False

    def note_activity(self, now: float) -> None:
        self._last_activity = now
        self._idle = False
        # 重新进入待机后，重新排一次事件时间
        self._next_event = 0.0

    def set_speaking(self, value: bool, now: float) -> None:
        if value != self._speaking:
            self._speaking = value
            self.note_activity(now)

    def set_face_active(self, value: bool) -> None:
        self._face_active = value

    @property
    def is_idle(self) -> bool:
        return self._idle

    def step(self, now: float) -> Tuple[bool, List[ModelAction]]:
        cfg = self.cfg
        if not cfg.get("idle_enabled", True):
            return False, []
        paused = (
            (self._speaking and cfg.get("idle_pause_on_speaking", True))
            or (self._face_active and cfg.get("idle_pause_on_face", True))
        )
        after = float(cfg.get("idle_after_seconds", 5.0))
        if paused or (now - self._last_activity) < after:
            self._idle = False
            return False, []
        was_idle = self._idle
        self._idle = True

        actions: List[ModelAction] = []
        lo = float(cfg.get("idle_min_interval", 4.0))
        hi = max(lo, float(cfg.get("idle_max_interval", 12.0)))
        if not was_idle:
            # 刚进入待机立刻给一次演出，别让用户再等一个 4~12 秒的完整间隔
            self._next_event = now
            self._next_blink = now
        elif self._next_event <= 0.0:
            self._next_event = now + self.rng.uniform(lo, hi)
        if now >= self._next_event:
            weights = cfg.get("idle_expression_weights") or {}
            expr = weighted_pick(weights, self.rng, exclude=self._last_expression)
            if expr:
                actions.append(ModelAction("expression", expr))
                self._last_expression = expr
            group = str(cfg.get("idle_motion_group") or "")
            if group:
                actions.append(ModelAction(
                    "motion", group,
                    priority=int(cfg.get("idle_motion_priority", 1))))
            self._next_event = now + self.rng.uniform(lo, hi)

        if cfg.get("idle_blink", True):
            interval = float(cfg.get("idle_blink_interval", 4.5))
            if self._next_blink <= 0.0:
                self._next_blink = now + interval
            if now >= self._next_blink:
                actions.append(ModelAction("blink"))
                self._next_blink = now + interval * self.rng.uniform(0.7, 1.4)
        return True, actions


# ─────────────────────────────────────────────────────────────────────────────
# 口型 / 情绪 / 性能
# ─────────────────────────────────────────────────────────────────────────────

class LipSyncSmoother:
    """RMS → 平滑的嘴巴开合；静音时按 decay 回 0，避免张嘴不闭。"""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.value = 0.0
        self.rms = 0.0

    def set_rms(self, rms: float) -> None:
        self.rms = max(0.0, float(rms))

    def step(self, dt: float) -> float:
        gain = float(self.cfg.get("lip_sync_gain", 3.0))
        target = clamp(self.rms * gain, 0.0, 1.0)
        if target > self.value:
            alpha = float(self.cfg.get("lip_sync_smoothing", 0.35))
            self.value = smooth_to(self.value, target, alpha, dt)
        else:
            decay = float(self.cfg.get("lip_sync_decay", 0.25))
            self.value = smooth_to(self.value, 0.0, decay, dt)
        # RMS 是一次性脉冲，取用后归零，下一帧没新数据就自然闭合
        self.rms = 0.0
        return self.value


class EmotionMapper:
    @staticmethod
    def resolve(cfg: Dict[str, Any], emotion: str) -> str:
        table = cfg.get("emotion_map") or {}
        if not isinstance(table, dict):
            return ""
        key = str(emotion or "").strip().lower()
        return str(table.get(key) or table.get("neutral") or "")


class PerformanceGovernor:
    """帧耗时统计 + 自适应降分辨率 + 空闲降帧 + 隐藏停帧。"""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.samples: List[float] = []
        self.window = max(10, int(cfg.get("stats_window_size", 120)))
        self.frames = 0
        self.dropped = 0
        self.render_scale = float(cfg.get("render_scale", 1.0))
        self._target_scale = self.render_scale
        self._slow_streak = 0
        self._fast_streak = 0
        self._last_frame_at = 0.0
        self._rss_mb = 0.0

    def note_frame(self, frame_ms: float, now: float) -> None:
        self.samples.append(float(frame_ms))
        if len(self.samples) > self.window:
            self.samples.pop(0)
        self.frames += 1
        self._last_frame_at = now
        self._auto_scale(frame_ms)

    def note_drop(self) -> None:
        self.dropped += 1

    def _auto_scale(self, frame_ms: float) -> None:
        if not self.cfg.get("adaptive_fps", True) or len(self.samples) < 30:
            return
        avg = sum(self.samples) / len(self.samples)
        budget = 1000.0 / max(1.0, float(self.cfg.get("fps", 60)))
        floor = float(self.cfg.get("min_render_scale", 0.6))
        base = float(self.cfg.get("render_scale", 1.0))
        if avg > budget * 1.35:
            self._slow_streak += 1
            self._fast_streak = 0
        elif avg < budget * 0.8:
            self._fast_streak += 1
            self._slow_streak = 0
        else:
            self._slow_streak = self._fast_streak = 0
        if self._slow_streak >= 30:
            self._target_scale = max(floor, self._target_scale - 0.1)
            self._slow_streak = 0
        elif self._fast_streak >= 90:
            self._target_scale = min(base, self._target_scale + 0.05)
            self._fast_streak = 0
        self.render_scale = self._target_scale

    def should_render(self, dt: float, *, visible: bool, idle: bool,
                      target_fps: float) -> bool:
        if not visible and self.cfg.get("frame_skip_on_hidden", True):
            return False
        fps = float(self.cfg.get("idle_fps", 30)) if idle else float(target_fps)
        # 让 request_render 的定时器负责节流，这里只做隐藏态硬开关
        return fps > 0

    def stats(self) -> FrameStats:
        s = sorted(self.samples)
        out = FrameStats()
        out.frames = self.frames
        out.dropped_frames = self.dropped
        out.render_scale = self.render_scale
        if s:
            out.avg_ms = sum(s) / len(s)
            out.p50_ms = s[len(s) // 2]
            out.p95_ms = s[min(len(s) - 1, int(len(s) * 0.95))]
            out.fps = 1000.0 / max(1e-3, out.avg_ms)
        out.process_rss_mb = self._rss_mb
        return out

    def set_rss(self, mb: float) -> None:
        self._rss_mb = max(0.0, float(mb))


# ─────────────────────────────────────────────────────────────────────────────
# 聚合引擎（线程边界）
# ─────────────────────────────────────────────────────────────────────────────

class BehaviorEngine:
    """主线程写意图、渲染线程取帧指令的唯一入口"""

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        rng: Optional[random.Random] = None,
    ):
        from .settings import normalize

        self._clock = clock
        self._lock = threading.RLock()
        self.cfg: Dict[str, Any] = normalize(cfg)
        seed = rng or random.Random()
        self.gaze = GazeDriver(self.cfg, seed)
        self.idle = IdleDirector(self.cfg, seed)
        self.lipsync = LipSyncSmoother(self.cfg)
        self.perf = PerformanceGovernor(self.cfg)
        self._pending: List[ModelAction] = []
        self._speaking = False
        self._visible = True
        self._model_loaded = False
        self._last_step = 0.0
        self._expressions: List[str] = []
        self._motions: Dict[str, int] = {}

    # ── 配置热更新（apply_config → on_config_change） ─────────────

    def update_config(self, cfg: Dict[str, Any]) -> None:
        from .settings import normalize

        with self._lock:
            self.cfg = normalize(cfg)
            self.gaze.cfg = self.cfg
            self.idle.cfg = self.cfg
            self.lipsync.cfg = self.cfg
            self.perf.cfg = self.cfg
            self.perf.window = max(10, int(self.cfg.get("stats_window_size", 120)))
            if not self.cfg.get("adaptive_fps", True):
                self.perf.render_scale = float(self.cfg.get("render_scale", 1.0))

    # ── 意图写入（任意线程） ──────────────────────────────────────

    def submit(self, kind: str, **payload: Any) -> None:
        now = self._clock()
        with self._lock:
            if kind == "mouse":
                self.gaze.set_mouse(float(payload.get("nx", 0)),
                                    float(payload.get("ny", 0)), now)
                self.idle.note_activity(now)
            elif kind == "mouse_leave":
                self.gaze.mouse_leave(now)
            elif kind == "face":
                self.gaze.set_face(dict(payload.get("data") or {}), now)
                self.idle.set_face_active(True)
            elif kind == "face_lost":
                self.gaze.clear_face()
                self.idle.set_face_active(False)
            elif kind == "speaking":
                on = bool(payload.get("on", False))
                self._speaking = on
                self.idle.set_speaking(on, now)
                expr = str(self.cfg.get("speak_expression") or "")
                if on and expr:
                    self._pending.append(ModelAction("expression", expr))
                elif not on:
                    self._pending.append(ModelAction("reset_expression"))
            elif kind == "activity":
                self.idle.note_activity(now)
            elif kind == "visible":
                self._visible = bool(payload.get("on", True))
            elif kind == "model_loaded":
                self._model_loaded = bool(payload.get("on", True))
                self._expressions = list(payload.get("expressions") or [])
                self._motions = dict(payload.get("motions") or {})
            elif kind == "expression":
                self._pending.append(ModelAction(
                    "expression", str(payload.get("value") or "")))
                self.idle.note_activity(now)
            elif kind == "motion":
                self._pending.append(ModelAction(
                    "motion", str(payload.get("group") or ""),
                    priority=int(payload.get("priority", 1)),
                    index=int(payload.get("index", 0))))
                self.idle.note_activity(now)
            elif kind == "blink":
                self._pending.append(ModelAction("blink"))
            elif kind == "reset_expression":
                self._pending.append(ModelAction("reset_expression"))
            elif kind == "reset_pose":
                self._pending.append(ModelAction("reset_pose"))
            elif kind == "rms":
                self.lipsync.set_rms(float(payload.get("value", 0)))
                self.idle.note_activity(now)
            elif kind == "emotion":
                expr = EmotionMapper.resolve(self.cfg, str(payload.get("value") or ""))
                if expr:
                    self._pending.append(ModelAction("expression", expr))

    # ── 帧计算（渲染线程） ────────────────────────────────────────

    def step(self, dt: float = 1 / 60) -> FrameCommand:
        now = self._clock()
        with self._lock:
            cfg = dict(self.cfg)
            visible = self._visible
            speaking = self._speaking
            model_loaded = self._model_loaded
            pending = self._pending
            self._pending = []
            face_fresh = self.gaze.face_is_fresh(now)
            self.idle.set_face_active(face_fresh)
            self.perf.set_rss(_rss_mb())

        cmd = FrameCommand()
        cmd.should_render = self.perf.should_render(
            dt, visible=visible, idle=False,
            target_fps=float(cfg.get("fps", 60)))
        cmd.render_scale = self.perf.render_scale
        cmd.target_fps = float(cfg.get("idle_fps", 30)) if (
            self.idle.is_idle and not speaking) else float(cfg.get("fps", 60))
        cmd.actions.extend(self._safe_actions(pending, cfg))
        cmd.gaze_source = "off"

        if not visible and cfg.get("frame_skip_on_hidden", True):
            return cmd

        params, source = self.gaze.step(now, dt)
        cmd.params.extend(params)
        cmd.gaze_source = source
        cmd.idle, idle_actions = self.idle.step(now)
        cmd.actions.extend(self._safe_actions(idle_actions, cfg))

        mouth = self.lipsync.step(dt) if cfg.get("enable_audio_sync", False) or speaking else 0.0
        cmd.lip_rms = mouth
        if mouth > 0.001:
            cmd.params.append(ParamWrite(P_MOUTH_OPEN_Y, clamp(mouth, 0.0, 1.0)))

        stats = self.perf.stats()
        stats.gaze_source = source
        stats.idle = cmd.idle
        stats.render_scale = cmd.render_scale
        stats.model_loaded = model_loaded
        stats.face_active = face_fresh
        stats.speaking = speaking
        self._last_stats = stats
        return cmd

    def _safe_actions(self, actions: Sequence[ModelAction],
                      cfg: Dict[str, Any]) -> List[ModelAction]:
        """过滤掉模型里不存在的表情 / 动作组，避免每次都抛异常刷日志。"""
        out: List[ModelAction] = []
        for act in actions:
            if act.kind == "expression" and act.value:
                if self._expressions and act.value not in self._expressions:
                    continue
            if act.kind == "motion" and act.value:
                if self._motions and act.value not in self._motions:
                    continue
                if self._motions:
                    act.index = act.index % max(1, int(self._motions[act.value]))
            out.append(act)
        return out

    @property
    def stats(self) -> FrameStats:
        return getattr(self, "_last_stats", FrameStats())

    def status(self) -> Dict[str, Any]:
        """给 /api/live2d/status：不依赖 Qt / 模型是否已加载。"""
        with self._lock:
            cfg = dict(self.cfg)
            expressions = list(self._expressions)
            motions = dict(self._motions)
        s = self.stats.to_dict()
        s.update({
            "gaze_enabled": bool(cfg.get("gaze_enabled", True)),
            "gaze_when_no_face": bool(cfg.get("gaze_when_no_face", True)),
            "face_tracking": bool(cfg.get("is_face_detected", False)),
            "idle_enabled": bool(cfg.get("idle_enabled", True)),
            "expressions": expressions,
            "motion_groups": motions,
            "settings_groups": _group_summary(),
            "visible": self._visible,
        })
        return s


def _rss_mb() -> float:
    """进程常驻内存；psutil 不可用时降级到 resource / 0。"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        pass
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux 上报 KB，macOS 上报 bytes
        return rss / 1024.0 if rss > 1e7 else rss / 1024.0
    except Exception:
        return 0.0


def _group_summary() -> List[Dict[str, Any]]:
    from .settings import groups
    return groups()
