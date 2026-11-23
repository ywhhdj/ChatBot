"""人脸动捕后端：摄像头 / 视频 → Live2D 参数。

被 ``services/live2d/components.py::FaceTrackerComponent`` 以::

    FaceTracker(str(model_path), source=..., mirror=..., fps=...)
"""
from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

FaceSource = Union[int, str]

# MediaPipe FaceMesh 的关键点索引
_NOSE_TIP, _CHIN = 1, 152
_EYE_L_OUT, _EYE_R_OUT = 33, 263
_MOUTH_L, _MOUTH_R = 61, 291
_LIP_TOP, _LIP_BOTTOM = 13, 14
_LEFT_EYE = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE = (362, 385, 387, 263, 373, 380)
# solvePnP 用的 6 个面部基准点（与 3D 模型对应）
_PNP_IDX = (_NOSE_TIP, _CHIN, _EYE_L_OUT, _EYE_R_OUT, _MOUTH_L, _MOUTH_R)
_PNP_3D = (
    (0.0, 0.0, 0.0),
    (0.0, -63.6, -12.5),
    (-43.3, 32.7, -26.0),
    (43.3, 32.7, -26.0),
    (-28.9, -28.9, -24.1),
    (28.9, -28.9, -24.1),
)

MOCK_SOURCES = ("mock", "synthetic", "fake", "sim", "simulated")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _is_mock(source: FaceSource) -> bool:
    return isinstance(source, str) and source.strip().lower() in MOCK_SOURCES


def _coerce_source(source: FaceSource) -> Union[int, str]:
    if isinstance(source, str):
        s = source.strip()
        if s.lstrip("-").isdigit():
            return int(s)
        return s
    return source


@dataclass
class ResultFaceData:
    yaw: float = 0.0                 # -1..1 → ParamAngleX
    pitch: float = 0.0               # -1..1 → ParamAngleY
    roll: float = 0.0                # -1..1 → ParamAngleZ
    eye_left: float = 1.0            # 0..1  → ParamEyeLOpen
    eye_right: float = 1.0           # 0..1  → ParamEyeROpen
    mouth_y: float = 0.0             # 0..1  → ParamMouthOpenY
    timestamp: float = field(default_factory=time.monotonic)
    source: str = "camera"
    ok: bool = True
    blendshapes: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "yaw": self.yaw, "pitch": self.pitch, "roll": self.roll,
            "eye_left": self.eye_left, "eye_right": self.eye_right,
            "mouth_y": self.mouth_y, "timestamp": self.timestamp,
            "source": self.source, "ok": self.ok,
        }


class FaceTracker:
    """人脸采集 + 参数解算，跑在独立 daemon 线程里。"""

    def __init__(
        self,
        model_path: Union[str, Path],
        source: FaceSource = 0,
        mirror: bool = False,
        fps: int = 30,
        smoothing: float = 0.45,
    ) -> None:
        self.model_path = str(model_path or "")
        self.source: FaceSource = _coerce_source(source)
        self.mirror = bool(mirror)
        self.fps = max(1, min(60, int(fps)))
        self.smoothing = _clamp(smoothing, 0.0, 1.0)

        self._queue: "queue.Queue[ResultFaceData]" = queue.Queue(maxsize=1)
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._initialized = False
        self._available = False
        self.last_error = ""
        self._mode = "mock" if _is_mock(self.source) else "camera"

        self._cap = None                 # cv2.VideoCapture
        self._landmarker = None          # MediaPipe Tasks FaceLandmarker
        self._face_mesh = None           # MediaPipe solutions.face_mesh.FaceMesh
        self._backend = "none"           # tasks | solutions | haar | mock
        self._haar = None
        self._np = None
        self._cv2 = None
        self._prev = ResultFaceData()
        self._frames = 0
        self._t0 = time.monotonic()
        self._lock = threading.Lock()

    # ── 状态 ─────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_running(self) -> bool:
        return bool(self._running and self._thread and self._thread.is_alive())

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def frames(self) -> int:
        return self._frames

    # ── 初始化 ───────────────────────────────────────────────────

    def init(self) -> None:
        if self._initialized:
            return
        if self._mode == "mock":
            self._backend = "mock"
            self._available = True
        else:
            self._prepare_backend()
        self._initialized = True

    def _prepare_backend(self) -> None:
        try:
            import cv2
            import numpy as np

            self._cv2, self._np = cv2, np
        except Exception as exc:  # noqa: BLE001
            self._available = False
            self.last_error = f"cv2/numpy 不可用: {type(exc).__name__}: {exc}"
            self._backend = "none"
            return

        # 1) MediaPipe Tasks FaceLandmarker（需要 .task 模型文件）
        model = Path(self.model_path)
        try:
            from mediapipe.tasks.c import vision as mp_vision
            from mediapipe.tasks.c import BaseOptions

            if model.is_file():
                self._landmarker = mp_vision.FaceLandmarker.create_from_options(
                    mp_vision.FaceLandmarkerOptions(
                        base_options=BaseOptions(model_asset_path=str(model)),
                        running_mode=mp_vision.RunningMode.VIDEO,
                        num_faces=1,
                        output_face_blendshapes=True,
                        output_facial_transformation_matrixes=False,
                    )
                )
                self._backend = "tasks"
            else:
                raise FileNotFoundError(f"模型文件不存在: {model}")
        except Exception as exc:  # noqa: BLE001
            self._landmarker = None
            tasks_err = f"Tasks FaceLandmarker 不可用: {type(exc).__name__}: {exc}"

            # 2) 旧 solutions.face_mesh（不需要模型文件）
            try:
                from mediapipe.solutions import face_mesh as mp_mesh

                self._face_mesh = mp_mesh.FaceMesh(
                    max_num_faces=1, refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self._backend = "solutions"
            except Exception as exc2:  # noqa: BLE001
                self._face_mesh = None
                # 3) cv2 Haar 粗估：只有头方位，眼/嘴给默认值
                try:
                    cascade = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                    self._haar = cv2.CascadeClassifier(cascade)
                    if self._haar.empty():
                        raise RuntimeError("haarcascade 加载失败")
                    self._backend = "haar"
                    self.last_error = (
                        f"{tasks_err}; 已降级到 cv2 Haar（仅头部方位）。"
                        "安装 mediapipe 并下载 face_landmarker.task 可启用完整动捕"
                    )
                except Exception as exc3:  # noqa: BLE001
                    self._backend = "none"
                    self._available = False
                    self.last_error = (
                        f"{tasks_err}; solutions.face_mesh 不可用: "
                        f"{type(exc2).__name__}: {exc2}; Haar 不可用: "
                        f"{type(exc3).__name__}: {exc3}"
                    )
                    return
        self._available = True
        if not self.last_error and self._backend == "tasks":
            self.last_error = ""

    # ── 生命周期 ─────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        if not self._initialized:
            self.init()
        self._stop_evt.clear()
        self._running = True
        self._t0 = time.monotonic()
        self._thread = threading.Thread(
            target=self._loop, name="FaceTracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_evt.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None
        with self._lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

    def close(self) -> None:
        self.stop()
        with self._lock:
            for obj in (self._landmarker, self._face_mesh):
                if obj is not None:
                    try:
                        obj.close()
                    except Exception:
                        pass
            self._landmarker = None
            self._face_mesh = None
            self._haar = None
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._initialized = False
        self._available = False

    def set_source(self, source: FaceSource) -> None:
        source = _coerce_source(source)
        with self._lock:
            changed = source != self.source
            self.source = source
            self._mode = "mock" if _is_mock(source) else "camera"
            if changed and self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
        if changed and self._mode != "mock":
            # 源切换后重新探测后端（例如 mock → 摄像头）
            self._initialized = False
            self._available = False
            self.last_error = ""
            self.init()

    def set_mirror(self, mirror: bool) -> None:
        with self._lock:
            self.mirror = bool(mirror)

    def set_fps(self, fps: int) -> None:
        self.fps = max(1, min(60, int(fps)))

    def set_smoothing(self, smoothing: float) -> None:
        """组件 UI 的「动捕平滑」热应用：0=跟手，1=完全沿用上一帧。"""
        self.smoothing = _clamp(smoothing, 0.0, 1.0)

    def poll_result(self) -> Optional[ResultFaceData]:
        """非阻塞取最新一帧；无新数据返回 ``None``。"""
        latest: Optional[ResultFaceData] = None
        while True:
            try:
                latest = self._queue.get_nowait()
            except queue.Empty:
                break
        return latest

    # ── 采集循环 ─────────────────────────────────────────────────

    def _loop(self) -> None:
        try:
            if self._mode == "mock":
                self._loop_mock()
            elif self._available and self._backend != "none":
                self._loop_camera()
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"采集循环异常: {type(exc).__name__}: {exc}"
        finally:
            self._running = False

    def _interval(self) -> float:
        return 1.0 / self.fps

    def _emit(self, data: ResultFaceData) -> None:
        """EMA 平滑 + 只留最新一帧。"""
        a = 1.0 - self.smoothing
        if a <= 0.0:
            a = 1.0
        p = self._prev
        data.yaw = _clamp(p.yaw + a * (data.yaw - p.yaw), -1.0, 1.0)
        data.pitch = _clamp(p.pitch + a * (data.pitch - p.pitch), -1.0, 1.0)
        data.roll = _clamp(p.roll + a * (data.roll - p.roll), -1.0, 1.0)
        data.eye_left = _clamp(p.eye_left + a * (data.eye_left - p.eye_left), 0.0, 1.0)
        data.eye_right = _clamp(p.eye_right + a * (data.eye_right - p.eye_right), 0.0, 1.0)
        data.mouth_y = _clamp(p.mouth_y + a * (data.mouth_y - p.mouth_y), 0.0, 1.0)
        self._prev = data
        self._frames += 1
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(data)
            except queue.Full:
                pass

    def _loop_mock(self) -> None:
        """确定性合成数据：正弦头动 + 周期眨眼 + 间歇张嘴。"""
        interval = self._interval()
        while not self._stop_evt.is_set():
            t = time.monotonic() - self._t0
            yaw = 0.42 * math.sin(2 * math.pi * t / 3.1)
            pitch = 0.24 * math.sin(2 * math.pi * t / 4.7 + 0.6)
            roll = 0.12 * math.sin(2 * math.pi * t / 6.3 + 1.2)
            # 每 3.7s 眨一次，持续 0.16s
            blink_phase = t % 3.7
            eye = 0.06 if blink_phase < 0.16 else 1.0
            # 说话式张合：2.1s 周期，中间有静音段
            mouth_phase = t % 2.1
            mouth = (0.55 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 0.37))
                     if mouth_phase < 1.25 else 0.0)
            self._emit(ResultFaceData(
                yaw=yaw, pitch=pitch, roll=roll,
                eye_left=eye, eye_right=eye, mouth_y=mouth,
                timestamp=time.monotonic(), source="mock", ok=True,
                blendshapes={"mock": 1.0},
            ))
            self._stop_evt.wait(interval)

    def _open_capture(self):
        cv2 = self._cv2
        if cv2 is None:
            return None
        with self._lock:
            if self._cap is not None and self._cap.isOpened():
                return self._cap
            try:
                cap = cv2.VideoCapture(self.source)
                if not cap.isOpened():
                    cap.release()
                    self.last_error = f"无法打开视频源: {self.source!r}"
                    return None
                self._cap = cap
                return cap
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"VideoCapture 失败: {type(exc).__name__}: {exc}"
                return None

    def _loop_camera(self) -> None:
        cv2, np = self._cv2, self._np
        if cv2 is None or np is None:
            return
        interval = self._interval()
        ts_ms = 0
        fail_streak = 0
        while not self._stop_evt.is_set():
            cap = self._open_capture()
            if cap is None:
                fail_streak += 1
                if fail_streak > 3:
                    # 源不可用时不要疯狂重试；保持线程存活，等 set_source
                    self._stop_evt.wait(1.0)
                else:
                    self._stop_evt.wait(interval)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                fail_streak += 1
                with self._lock:
                    if self._cap is not None:
                        try:
                            self._cap.release()
                        except Exception:
                            pass
                        self._cap = None
                self._stop_evt.wait(interval)
                continue
            fail_streak = 0
            with self._lock:
                mirror = self.mirror
            if mirror:
                frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            data = self._analyze(frame, w, h, ts_ms)
            ts_ms += int(interval * 1000)
            if data is not None:
                self._emit(data)
            self._stop_evt.wait(interval)

    # ── 参数解算 ─────────────────────────────────────────────────

    def _analyze(self, frame, w: int, h: int, ts_ms: int) -> Optional[ResultFaceData]:
        cv2, np = self._cv2, self._np
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pts = None
        blendshapes: Dict[str, float] = {}

        if self._backend == "tasks" and self._landmarker is not None:
            try:
                import mediapipe as mp

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = self._landmarker.detect_for_video(mp_image, ts_ms)
                if result.face_landmarks:
                    lm = result.face_landmarks[0]
                    pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float64)
                for cat in (getattr(result, "face_blendshapes", None) or []):
                    for c in cat:
                        blendshapes[c.category_name] = float(c.score)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"Tasks 推理失败: {type(exc).__name__}: {exc}"
        elif self._backend == "solutions" and self._face_mesh is not None:
            try:
                result = self._face_mesh.process(rgb)
                if result.multi_face_landmarks:
                    lm = result.multi_face_landmarks[0].landmark
                    pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float64)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"face_mesh 推理失败: {type(exc).__name__}: {exc}"
        elif self._backend == "haar" and self._haar is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self._haar.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
                if len(faces):
                    x, y, fw, fh = max(faces, key=lambda b: b[2] * b[3])
                    cx, cy = x + fw / 2.0, y + fh / 2.0
                    return ResultFaceData(
                        yaw=_clamp((cx / w - 0.5) * 2.0, -1.0, 1.0),
                        pitch=_clamp((cy / h - 0.5) * 1.4, -1.0, 1.0),
                        roll=0.0, eye_left=1.0, eye_right=1.0, mouth_y=0.0,
                        timestamp=time.monotonic(), source="haar", ok=True,
                        blendshapes={"backend": 0.0},
                    )
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"Haar 检测失败: {type(exc).__name__}: {exc}"
            return None

        if pts is None or len(pts) < max(_PNP_IDX) + 1:
            return None

        yaw = pitch = roll = 0.0
        try:
            obj = np.array(_PNP_3D, dtype=np.float64)
            img = np.array([pts[i] for i in _PNP_IDX], dtype=np.float64)
            cam = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float64)
            dist = np.zeros((4, 1), dtype=np.float64)
            ok, rvec, _ = cv2.solvePnP(obj, img, cam, dist, flags=cv2.SOLVEPNP_ITERATIVE)
            if ok:
                rmat, _ = cv2.Rodrigues(rvec)
                # 欧拉角（度）→ 归一到 -1..1，阈值 30°
                angles, *_ = cv2.RQDecomp3x3(rmat)
                pitch = _clamp(float(angles[0]) / 30.0, -1.0, 1.0)
                yaw = _clamp(float(angles[1]) / 30.0, -1.0, 1.0)
                roll = _clamp(float(angles[2]) / 30.0, -1.0, 1.0)
        except Exception:
            pass

        def _ear(indices) -> float:
            p = [pts[i] for i in indices]
            vertical = (np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])) / 2.0
            horizontal = np.linalg.norm(p[0] - p[3])
            return float(vertical / horizontal) if horizontal > 1e-6 else 0.3

        ear_l, ear_r = _ear(_LEFT_EYE), _ear(_RIGHT_EYE)
        # EAR 约 0.25~0.35 为睁眼，<0.15 为闭合；线性映射到 0..1
        eye_left = _clamp((ear_l - 0.12) / 0.20, 0.0, 1.0)
        eye_right = _clamp((ear_r - 0.12) / 0.20, 0.0, 1.0)
        lip = float(np.linalg.norm(pts[_LIP_TOP] - pts[_LIP_BOTTOM]))
        mouth_w = float(np.linalg.norm(pts[_MOUTH_L] - pts[_MOUTH_R]))
        mouth_y = _clamp((lip / mouth_w - 0.02) / 0.32, 0.0, 1.0) if mouth_w > 1e-6 else 0.0

        # Tasks 的 blendshape 更准，存在时覆盖
        if blendshapes:
            if "eyeBlinkLeft" in blendshapes:
                eye_left = _clamp(1.0 - blendshapes["eyeBlinkLeft"], 0.0, 1.0)
            if "eyeBlinkRight" in blendshapes:
                eye_right = _clamp(1.0 - blendshapes["eyeBlinkRight"], 0.0, 1.0)
            if "jawOpen" in blendshapes:
                mouth_y = _clamp(blendshapes["jawOpen"], 0.0, 1.0)

        return ResultFaceData(
            yaw=yaw,
            pitch=pitch, 
            roll=roll,
            eye_left=eye_left,
            eye_right=eye_right,
            mouth_y=mouth_y,
            timestamp=time.monotonic(),
            source=self._backend,
            ok=True,
            blendshapes=blendshapes,
        )


__all__ = ["ResultFaceData", "FaceTracker", "MOCK_SOURCES"]
