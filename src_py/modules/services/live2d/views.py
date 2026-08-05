import os
import sys
from typing import Literal, Optional, Union

from ...events.data import BaseEvent
from ...runtime import get_models_path
from .. import base
from ...logger import logger
from ...events import emit, off, on_event_class,types as eventType,on
from ...manager.service.decorator import Service
from PyQt5.QtCore import QObject
from .. import ServiceId

class Live2DController(QObject):
    """Live2D控制器 - 始终运行在主线程"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.__face_tracker = None
        self._qt_app = None
        self._initialized = False
        self._running = False
    
    def initialize(self, config, canvas_size, fps, enable_audio_sync, enable_chunk_playback):
        """初始化（必须在主线程调用）"""
        if self._initialized:
            return
        from PyQt5.QtWidgets import QApplication
        # 确保QApplication存在
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        
        # 创建画布
        from .canvas import Live2DCanvas
        self.canvas = Live2DCanvas(
            canvas_size=canvas_size,
            model_path=config.model_path,
            fps=fps,
            enable_audio_sync=enable_audio_sync,
            enable_chunk_playback=enable_chunk_playback
        )
        from PyQt5.QtCore import Qt
        self.canvas.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | #type: ignore
            Qt.WindowType.WindowStaysOnTopHint
        ) 
        self.canvas.init()
        logger.info("[Live2D] Canvas initialized in main thread")
        
        # 创建面部追踪
        from .components import FaceTrackerComponent
        self.__face_tracker = FaceTrackerComponent(
            config.media_pipe_face_model_path,
            face_source=0,
            face_fps=30,
            enabled=config.is_face_detected,
        )
        self.__face_tracker.set_process_callback(self.canvas.apply_face_data)
        self.__face_tracker.init()
        logger.info("[Live2D] Face tracker initialized in main thread")
        
        self._initialized = True
    
    def start(self):
        if not self._initialized or not self.canvas:
            logger.error("Live2D not initialized")
            return
        
        if self._running:
            return
        
        self._running = True
        
        self._do_position()
        self.canvas.start()
        self.canvas.show()
        logger.info("[Live2D] Live2D started")
        
        if self.__face_tracker:
            try:
                self.__face_tracker.start()
                logger.info("[Live2D] Face tracker started")
            except Exception as e:
                logger.error(f"[Live2D] Face tracker start error: {e}")
    
    def stop(self):
        self._running = False
        if self.__face_tracker:
            self.__face_tracker.stop()
        if self.canvas:
            self.canvas.hide()
        logger.info("[Live2D] Live2D stopped")
    
    def close(self):
        self._running = False
        if self.__face_tracker:
            self.__face_tracker.close()
            self.__face_tracker = None
        if self.canvas:
            self.canvas.stop()
            self.canvas = None
        self._initialized = False
        logger.info("[Live2D] Live2D closed")
        
    def show(self):
        if self.canvas:
            self.canvas.show()
    
    def hide(self):
        if self.canvas:
            self.canvas.hide()
    
    def _do_position(self):
        if self.canvas:
            from PyQt5.QtWidgets import QApplication
            desktop = QApplication.desktop()
            if not desktop:
                logger.error("QApplication.desktop() is None")
                return
            screen_geometry=desktop.availableGeometry()
            x = screen_geometry.width() - self.canvas.width() - 50
            y = screen_geometry.height() - self.canvas.height() - 50
            self.canvas.move(x, y)
    
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
            self.__face_tracker.set_enabled(enabled)
    
    def set_face_source(self, source):
        if self.__face_tracker:
            self.__face_tracker.set_source(source)
    
    def set_face_fps(self, fps: int):
        if self.__face_tracker:
            self.__face_tracker.set_fps(fps)

@on_event_class([
    (eventType.Live2DEventType.LIVE2D_START, "start"),
    # (eventType.Live2DEventType.LIVE2D_DRAW, "draw"),
    (eventType.Live2DEventType.LIVE2D_AUDIO_PLAY, "put_audio"),
    (eventType.Live2DEventType.LIVE2D_STOP, "stop"),
    (eventType.Live2DEventType.LIVE2D_SET_MODEL, "set_model_path"),
    (eventType.Live2DEventType.LIVE2D_CLOSE, "close"),
])
@Service(id=ServiceId.LIVE2D)
class Live2DView(base._BaseService):
    """
        Parameters:
            model_path: Live2D模型路径
            window_size: 窗口大小
            window_icon_path: 窗口图标路径
            window_title: 窗口标题
            fps: 帧率
            canvas_size: 画布大小
            enable_audio_sync: 是否启用音频同步
            enable_chunk_playback: 是否启用分块播放
            is_face_detected: 是否启用人脸检测
            mediaPipeFace_model_path: 人脸检测模型路径
            face_source: 人脸检测源
            face_fps: 人脸检测帧率
    """
    name = "Live2D"
    description = "Live2D 模型视图"
    
    def get_tools(self) -> list:
        return [
            "set_model_path",
            "set_position"
        ]

    DEFAULT_MEDIAPIPE_FACE_MODEL_PATH = get_models_path("mediapipe/face_landmarker.task")
    DEFAULT_MODEL_PATH = get_models_path("live2d/肥牛/hiyori_pro_mic.model3.json")

    def __init__(
        self,
        model_path: str = str(DEFAULT_MODEL_PATH),
        window_size: Union[Optional[tuple[int, int]], Literal["fullscreen"]] = None,
        window_icon_path: str = "",
        window_title: str = "Live2DModel",
        fps: int = 60,
        canvas_size: tuple[int, int] = (1000, 700),
        enable_audio_sync: bool = False,
        enable_chunk_playback: bool = False,
        is_face_detected: bool = False,
        mediaPipeFace_model_path: str = str(DEFAULT_MEDIAPIPE_FACE_MODEL_PATH),
        face_source: Union[int, str] = 0,
        face_fps: int = 30,
    ) -> None:
        super().__init__()
        from ..config import Live2DConfig
        self.config = Live2DConfig(
            enabled=True,
            model_path=model_path,
            media_pipe_face_model_path=mediaPipeFace_model_path,
            is_face_detected=is_face_detected
        )
        self._window_icon_path = window_icon_path
        self._window_size = window_size
        self._window_title = window_title
        self._fps = fps
        self._running = False
        self.enable_chunk_playback = enable_chunk_playback
        self.enable_audio_sync = enable_audio_sync
        self._canvas_size = canvas_size
        self._did_initial_position = False
        self._closing = False
        self._initialized = False
        self._controller:Optional[Live2DController]=None

    def __ensure_controller(self):
        if self._controller is None:
            # 在主线程创建控制器
            self._controller = emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self.__create_controller,)))
            self._initialized = True

    def __create_controller(self):
        controller = Live2DController()
        controller.initialize(
            self.config,
            self._canvas_size,
            self._fps,
            self.enable_audio_sync,
            self.enable_chunk_playback
        )
        return controller
    
    def set_rotation_angle(self, angle: float):
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_rotation_angle,angle)))
    
    def set_opacity(self, opacity: float):
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_opacity,opacity)))

    def put_audio(self, audio_path: str) -> None:
        assert os.path.exists(audio_path), f"Audio file {audio_path} does not exist"
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.put_audio,audio_path)))

    def put_audio_chunk(self, chunk: bytes) -> None:
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.put_audio_chunk,chunk)))

    def set_model_path(self, model_path: str) -> None:
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_model_path,model_path)))

    def set_face_enabled(self, enabled: bool) -> None:
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_face_enabled,enabled)))

    def set_face_source(self, source: Union[int, str]) -> None:
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_face_source,source)))

    def set_face_fps(self, fps: int) -> None:
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.set_face_fps,fps)))

    def init(self):
        """初始化 - 确保在主线程完成"""
        if self._initialized:
            return
        self.__ensure_controller()
        self._initialized = True

    def start(self) -> None:
        if not self._initialized:
            self.init()
        
        if self._running:
            return
        
        self._running = True
        
        # 通过信号触发主线程操作
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.start,)))
            logger.info("[Live2D] Start signal emitted")
        on(eventType.PipelineEventType.TTS_AUDIO_CHUNK,self.put_audio_chunk)

    def stop(self) -> None:
        if not self._running:
            return
        
        self._running = False
        
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.stop,)))
            logger.info("[Live2D] Stop signal emitted")

    def close(self) -> None:
        self._running = False
        if self._controller:
            emit(BaseEvent(type=eventType.AppEventType.MainThreadDispatcherEventType.RUN_ON_MAIN_THREAD,args=(self._controller.close,)))
            self._controller = None
            self._initialized = False
        logger.info("[Live2D] Closed")
        off(eventType.PipelineEventType.TTS_AUDIO_CHUNK,self.put_audio_chunk)