import os
from pathlib import Path
import time
from threading import Lock
from typing import Optional, Union
try:
    import cv2
    from mediapipe.tasks.python.core.base_options import BaseOptions
    from mediapipe.tasks.python.vision.core.image import Image, ImageFormat
    from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
    from mediapipe.tasks.python.vision.face_landmarker import (
        FaceLandmarker,
        FaceLandmarkerOptions,
        FaceLandmarkerResult,
    )
    from numpy import array, degrees, atan2, asin
except ImportError:
    raise ImportError("mediapipe 未安装，无法使用人脸检测功能")


from .models import ResultFaceData

def calculate_euler_angles(matrix) -> tuple[float, float, float]:
    if matrix is None:
        return 0.0, 0.0, 0.0
    r11 = matrix[0][0]
    r21 = matrix[1][0]
    r31 = matrix[2][0]
    r32 = matrix[2][1]
    r33 = matrix[2][2]
    if hasattr(matrix, '__getitem__') and len(matrix) >= 3:
        r = array(matrix)
        if r.shape == (4, 4):
            r = r[:3, :3]  # 提取旋转部分
        elif r.shape == (3, 3):
            pass
        else:
            return 0.0, 0.0, 0.0
    else:
        return 0.0, 0.0, 0.0
    try:
        # 计算yaw (绕Z轴)
        yaw = degrees(atan2(r[1, 0], r[0, 0]))
        
        # 计算pitch (绕Y轴)，限制在[-90°, 90°]范围内
        sin_pitch = -r[2, 0]
        sin_pitch = max(-1.0, min(1.0, sin_pitch))  # 防止asin输入超出[-1,1]
        pitch = degrees(asin(sin_pitch))
        # 计算roll (绕X轴)
        roll = degrees(atan2(r[2, 1], r[2, 2]))
        return pitch, yaw, roll
    except (ValueError, IndexError) as e:
        return 0.0, 0.0, 0.0

def build_face_data(result: FaceLandmarkerResult, mirror: bool = False):
    if not result or not result.face_blendshapes or len(result.face_blendshapes) == 0:
        return None
    
    # 提取blendshapes
    bs = {b.category_name: b.score for b in result.face_blendshapes[0]}
    
    # 提取旋转矩阵并计算欧拉角
    matrix = None
    if result.facial_transformation_matrixes and len(result.facial_transformation_matrixes) > 0:
        matrix = result.facial_transformation_matrixes[0]
    pitch, yaw, roll = calculate_euler_angles(matrix)
    # 镜像模式调整：水平翻转会反转yaw和roll的符号
    if mirror:
        yaw = -yaw
        roll = -roll
    # 计算眼部闭合度和嘴巴张开度（可调整系数）
    eye_left = max(0.0, min(1.0, 1.0 - (bs.get("eyeBlinkLeft", 0.0) * 1.5)))
    eye_right = max(0.0, min(1.0, 1.0 - (bs.get("eyeBlinkRight", 0.0) * 1.5)))
    mouth_y = min(1.0, bs.get("jawOpen", 0.0) * 2.5)  # 限制最大为1.0
    return ResultFaceData(
        eye_left=eye_left,
        eye_right=eye_right,
        mouth_y=mouth_y,
        pitch=pitch,
        yaw=yaw,
        roll=roll,
    )

def create_options(
    model_path: str,
    result_callback,
    running_mode=VisionTaskRunningMode.LIVE_STREAM,
) -> FaceLandmarkerOptions:
    return FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=running_mode,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        result_callback=result_callback,
    )

class FaceTracker:
    def __init__(self,
            model_path: Union[str, Path],
            source: Union[int, str] = 0,
            mirror: bool = False,
            fps: int = 30
        ):
        self.model_path = str(model_path)
        self.source = source
        self.mirror = mirror #是否镜像
        self.fps = max(1, fps)

        self.cap: Optional[cv2.VideoCapture] = None
        self.landmarker: Optional[FaceLandmarker] = None
        self.__latest: Optional[ResultFaceData] = None
        self.__lock = Lock()
        self.__ts = int(time.monotonic() * 1000)
        self.__running = False
        self.__initialized = False

    def check_model(self) -> bool:
        if self.model_path:
            if os.path.exists(self.model_path):
                return True
            else:
                return False
        else:
            return False
        
    def __del__(self):
        self.close()

    def __on_result(self, result: FaceLandmarkerResult, _output_image, _timestamp_ms: int):
        data = build_face_data(result)
        if data is None:
            return
        with self.__lock:
            self.__latest = data

    def init(self):
        if self.__initialized:
            return
        if not self.check_model():
            raise RuntimeError("Model not found")
        self.cap=cv2.VideoCapture(self.source)
        options = create_options(self.model_path, self.__on_result, VisionTaskRunningMode.LIVE_STREAM)
        self.landmarker = FaceLandmarker.create_from_options(options)
        self.__initialized = True

    def __submit_frame(self):
        if self.cap is None or self.landmarker is None:
            return False
        ok, frame = self.cap.read()
        if not ok:
            return False
        if self.mirror:
            frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)
        self.__ts += 1
        self.landmarker.detect_async(mp_image,self.__ts)
        return True

    def poll_result(self):
        with self.__lock:
            data = self.__latest
            self.__latest = None
        return data

    def close(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.landmarker:
            self.landmarker.close()
            self.landmarker = None
        cv2.destroyAllWindows()

    def stop(self) -> None:
        self.__running = False
        if self.cap:
            self.cap.release()

    def start(self) -> None:
        if not self.__initialized:
            self.init()
            self.__initialized = True
        self.__running = True
        interval = round(1.0 / self.fps,2)
        try:
            while self.__running:
                self.__submit_frame()
                time.sleep(interval)
        finally:
            self.close()

    def set_source(self, source: Union[int, str]):
        if source == self.source:
            return
        self.source = source
        self.cap=cv2.VideoCapture(source)

    def set_fps(self, fps: int) -> None:
        self.fps = max(1, fps)

    def set_mirror(self, mirror: bool) -> None:
        self.mirror = mirror