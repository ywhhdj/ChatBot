"""Live2D 画布：离屏 OpenGL 渲染 + QLabel 显示"""
from __future__ import annotations

import os
import time
from queue import Queue
from threading import Lock, Thread
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import copy
from pathlib import Path

import live2d.v3 as live2d
import numpy as np
from pygame import mixer
from OpenGL import GL
from PyQt6.QtCore import (
    QObject, QPoint, QSize, Qt, QThread, QTimer, QWaitCondition, QMutex,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QImage, QMouseEvent, QOffscreenSurface, QOpenGLContext, QPixmap,
    QSurfaceFormat,
)
from PyQt6.QtWidgets import QLabel

from ...logger import logger
from .audio import AsyncChunkPlayer, AsyncRmsMeter, WavHandler
from .behavior import BehaviorEngine, FrameCommand
from .settings import normalize, parse_canvas_size


def compile_shader(shader_src: str, shader_type):
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, shader_src)
    GL.glCompileShader(shader)
    if GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) != GL.GL_TRUE:
        msg = GL.glGetShaderInfoLog(shader).decode("utf-8", "replace")
        GL.glDeleteShader(shader)
        raise RuntimeError(f"Shader compile error: {msg}")
    return shader


def create_program(vs, fs):
    v = compile_shader(vs, GL.GL_VERTEX_SHADER)
    f = compile_shader(fs, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, v)
    GL.glAttachShader(program, f)
    GL.glLinkProgram(program)
    GL.glDetachShader(program, v)
    GL.glDetachShader(program, f)
    GL.glDeleteShader(v)
    GL.glDeleteShader(f)
    if GL.glGetProgramiv(program, GL.GL_LINK_STATUS) != GL.GL_TRUE:
        raise RuntimeError(str(GL.glGetProgramInfoLog(program)))
    return program


def create_vao(v_pos, uv_coord) -> Tuple[int, int, int]:
    """返回 (vao, vbo, uvbo)，让调用方能在卸载时显式 glDeleteBuffers。"""
    vao = GL.glGenVertexArrays(1)
    vbo = GL.glGenBuffers(1)
    uvbo = GL.glGenBuffers(1)
    GL.glBindVertexArray(vao)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, v_pos.nbytes, v_pos, GL.GL_DYNAMIC_DRAW)
    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, 0, None)
    GL.glEnableVertexAttribArray(0)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, uvbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, uv_coord.nbytes, uv_coord, GL.GL_DYNAMIC_DRAW)
    GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, 0, None)
    GL.glEnableVertexAttribArray(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
    GL.glBindVertexArray(0)
    return vao, vbo, uvbo

_live2d_init_lock = Lock()
_live2d_initialized = False


class OffscreenRenderer(QObject):
    """离屏渲染线程。所有 GL 资源都在本线程创建与释放。"""

    imageReady = pyqtSignal(QImage)
    frameDone = pyqtSignal(float)          # 帧耗时(ms)，回灌 PerformanceGovernor

    def __init__(
        self,
        fps: float = 60.0,
        width: int = 800,
        height: int = 600,
        share_context=None,
        cleanup_callback: Optional[Callable[[], None]] = None,
        render_scale: float = 1.0,
        opacity: float = 1.0,
    ):
        super().__init__()
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.fps = float(fps)
        self.share_context = share_context
        self.frame_interval_ms = max(1, int(1000 / max(1.0, self.fps)))
        self.render_scale = max(0.4, min(1.0, float(render_scale)))
        self.opacity = max(0.0, min(1.0, float(opacity)))

        self.__running = False
        self.__render_callback: Optional[Callable[[int, int], None]] = None
        self.__mutex: Optional[QMutex] = None
        self.__cond: Optional[QWaitCondition] = None
        self.__request_render = False
        self.rotation_angle = 0.0
        self.rotate_program = None
        self.quad_vao = None
        self._quad_vbo = None
        self._quad_uvbo = None
        self.temp_fbo = None
        self.__cleanup_callback = cleanup_callback
        self.__thread: Optional[QThread] = None
        self.__prepared = False
        # 尺寸/缩放变化由渲染线程消费，避免跨线程动 FBO
        self._target_size: Optional[Tuple[int, int]] = None
        self._target_scale: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self.__thread is not None and self.__thread.isRunning()

    def set_rotation_angle(self, angle: float):
        self.rotation_angle = float(angle) % 360.0

    def set_opacity(self, opacity: float) -> None:
        self.opacity = max(0.0, min(1.0, float(opacity)))

    def set_fps(self, fps: float) -> None:
        self.fps = max(1.0, float(fps))
        self.frame_interval_ms = max(1, int(1000 / self.fps))

    def set_size(self, width: int, height: int) -> None:
        self._target_size = (max(1, int(width)), max(1, int(height)))

    def set_render_scale(self, scale: float) -> None:
        self._target_scale = max(0.4, min(1.0, float(scale)))

    # ---------- GL 资源 ----------

    def __init_rotate_resources(self):
        vs = """#version 330 core
            layout(location = 0) in vec2 a_position;
            layout(location = 1) in vec2 a_texCoord;
            out vec2 v_texCoord;
            uniform float rotation_angle;
            void main() {
                gl_Position = vec4(a_position, 0.0, 1.0);
                float angle = radians(rotation_angle);
                mat2 m = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
                vec2 c = a_texCoord - vec2(0.5, 0.5);
                v_texCoord = m * c + vec2(0.5, 0.5);
            }
        """
        fs = """#version 330 core
            in vec2 v_texCoord;
            uniform sampler2D canvas;
            uniform float opacity;
            out vec4 FragColor;
            void main() {
                vec4 color = texture(canvas, v_texCoord);
                color *= opacity;
                FragColor = color;
            }
        """
        self.rotate_program = create_program(vs, fs)
        vertices = np.array([
            -1, 1, -1, -1, 1, -1,
            -1, 1, 1, -1, 1, 1,
        ], dtype=np.float32).reshape(6, 2)
        uvs = np.array([
            0, 1, 0, 0, 1, 0,
            0, 1, 1, 0, 1, 1,
        ], dtype=np.float32).reshape(6, 2)
        self.quad_vao, self._quad_vbo, self._quad_uvbo = create_vao(vertices, uvs)

    def __rotate_fbo(self, src_fbo) -> QImage:
        w, h = src_fbo.width(), src_fbo.height()
        if self.temp_fbo is None or self.temp_fbo.width() != w or self.temp_fbo.height() != h:
            if self.temp_fbo:
                self.temp_fbo.release()
                del self.temp_fbo
            self.temp_fbo = self.__create_fbo(w, h)
        self.temp_fbo.bind()
        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glUseProgram(self.rotate_program)
        GL.glUniform1f(GL.glGetUniformLocation(self.rotate_program, "rotation_angle"),
                       self.rotation_angle)
        GL.glUniform1f(GL.glGetUniformLocation(self.rotate_program, "opacity"),
                       self.opacity)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, src_fbo.texture())
        GL.glUniform1i(GL.glGetUniformLocation(self.rotate_program, "canvas"), 0)
        GL.glBindVertexArray(self.quad_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
        image = self.temp_fbo.toImage()
        self.temp_fbo.release()
        return image

    # ---------- 生命周期 ----------

    def start(self):
        if self.is_running:
            return
        if not self.__prepared:
            self.prepare()
        self.__running = True
        thread = QThread()
        self.moveToThread(thread)
        self.__thread = thread
        thread.started.connect(self.__render_loop)
        thread.finished.connect(self.deleteLater)
        thread.start()

    def stop(self):
        self.__running = False
        thread = self.__thread
        if thread is None:
            return
        if not thread.isRunning():
            self.__thread = None
            return
        try:
            if self.__cond is not None and self.__mutex is not None:
                self.__mutex.lock()
                self.__request_render = True
                self.__cond.wakeAll()
                self.__mutex.unlock()
        except Exception:
            pass
        thread.quit()
        thread.wait(3000)
        self.__thread = None

    def set_render_callback(self, callback):
        self.__render_callback = callback

    def request_render(self):
        if self.__mutex is None:
            return
        self.__mutex.lock()
        self.__request_render = True
        try:
            self.__cond.wakeOne()  # type: ignore[union-attr]
        except Exception:
            pass
        self.__mutex.unlock()

    def prepare(self):
        if self.__prepared:
            return
        fmt = QSurfaceFormat()
        fmt.setMajorVersion(3)
        fmt.setMinorVersion(3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        fmt.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        self.format = fmt
        self.surface = QOffscreenSurface()
        self.surface.setFormat(fmt)
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("Failed to create offscreen surface")
        self.__mutex = QMutex()
        self.__cond = QWaitCondition()
        self.__prepared = True

    def __create_context(self):
        ctx = QOpenGLContext()
        if self.share_context:
            ctx.setShareContext(self.share_context)
        ctx.setFormat(self.format)
        if not ctx.create():
            raise RuntimeError("Failed to create OpenGL context")
        if not ctx.makeCurrent(self.surface):
            raise RuntimeError("Failed to make OpenGL context current")
        return ctx

    def __create_fbo(self, width: int, height: int):
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid FBO size: {width}x{height}")
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat

        f = QOpenGLFramebufferObjectFormat()
        f.setAttachment(QOpenGLFramebufferObject.Attachment.NoAttachment)
        f.setTextureTarget(GL.GL_TEXTURE_2D)  # type: ignore
        f.setInternalTextureFormat(GL.GL_RGBA8)  # type: ignore
        f.setSamples(0)
        fbo = QOpenGLFramebufferObject(QSize(width, height), f)
        if not fbo.isValid():
            raise RuntimeError("Failed to create FBO")
        return fbo

    def _fbo_size(self) -> Tuple[int, int]:
        return (max(1, int(self.width * self.render_scale)),
                max(1, int(self.height * self.render_scale)))

    def __render_loop(self):
        context = None
        fbo = None
        try:
            context = self.__create_context()
            w, h = self._fbo_size()
            fbo = self.__create_fbo(w, h)
            self.__init_rotate_resources()
            while self.__running:
                self.__mutex.lock()  # type: ignore[union-attr]
                if not self.__request_render and self.__cond is not None:
                    self.__cond.wait(self.__mutex, self.frame_interval_ms)  # type: ignore[arg-type]
                need = self.__request_render
                self.__request_render = False
                self.__mutex.unlock()  # type: ignore[union-attr]

                # 尺寸 / 缩放变化：在 GL 线程内重建 FBO
                if self._target_size is not None:
                    self.width, self.height = self._target_size
                    self._target_size = None
                    fbo.release()
                    del fbo
                    w, h = self._fbo_size()
                    fbo = self.__create_fbo(w, h)
                    if self.temp_fbo:
                        self.temp_fbo.release()
                        del self.temp_fbo
                        self.temp_fbo = None
                if self._target_scale is not None:
                    self.render_scale = self._target_scale
                    self._target_scale = None
                    fbo.release()
                    del fbo
                    w, h = self._fbo_size()
                    fbo = self.__create_fbo(w, h)
                    if self.temp_fbo:
                        self.temp_fbo.release()
                        del self.temp_fbo
                        self.temp_fbo = None

                if need and self.__render_callback:
                    t0 = time.perf_counter()
                    fbo.bind()
                    GL.glViewport(0, 0, w, h)
                    self.__render_callback(w, h)
                    fbo.release()
                    if abs(self.rotation_angle) > 0.01:
                        image = self.__rotate_fbo(fbo)
                    else:
                        image = fbo.toImage()
                    self.imageReady.emit(image)
                    self.frameDone.emit((time.perf_counter() - t0) * 1000.0)

            if self.__cleanup_callback is not None:
                try:
                    self.__cleanup_callback()
                except Exception as exc:
                    logger.debug(f"[Live2D] cleanup callback failed: {exc}")
        except Exception as exc:
            logger.error(f"[Live2D] render loop failed: {exc}")
        finally:
            try:
                if fbo is not None:
                    fbo.release()
                if self.temp_fbo is not None:
                    self.temp_fbo.release()
                if self.rotate_program:
                    GL.glDeleteProgram(self.rotate_program)
                if self._quad_vbo or self._quad_uvbo:
                    GL.glDeleteBuffers(2, [self._quad_vbo, self._quad_uvbo])
                if self.quad_vao:
                    GL.glDeleteVertexArrays(1, [self.quad_vao])
            except Exception:
                pass
            self.rotate_program = None
            self.quad_vao = self._quad_vbo = self._quad_uvbo = None
            self.temp_fbo = None
            try:
                if context is not None:
                    context.doneCurrent()
                self.surface.destroy()
            except Exception:
                pass


class Live2DCanvas(QLabel):
    """显示窗口 + 交互入口。**不持有可跨线程调用的 model 操作**。"""

    def __init__(
        self,
        model_path: str,
        model_name: str = "Live2D Model",
        main_context=None,
        canvas_size: tuple[int, int] = (1200, 800),
        fps: int = 60,
        enable_audio_sync: bool = False,
        enable_chunk_playback: bool = False,
        audio_sample_rate: int = 44100,
        audio_channels: int = 1,
        audio_sample_width: int = 2,
        lipSync: int = 3,
        scale: float = 1.0,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(model_name)
        self.resize(*canvas_size)
        self.setMouseTracking(True)
        self.setScaledContents(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.main_context = main_context
        self.model_path: str = str(model_path or "")
        self.canvas_size: tuple[int, int] = (int(canvas_size[0]), int(canvas_size[1]))
        self.enable_audio_sync: bool = bool(enable_audio_sync)
        self.enable_chunk_playback = bool(enable_chunk_playback)
        self._audio_sample_rate = int(audio_sample_rate)
        self._audio_channels = int(audio_channels)
        self._audio_sample_width = int(audio_sample_width)

        self.running = False
        self.model: Optional[Any] = None      # 仅渲染线程读写
        self.wavehand: Optional[WavHandler] = None
        self.rms_meter: Optional[AsyncRmsMeter] = None
        self.chunk_player: Optional[AsyncChunkPlayer] = None
        self._audio_queue: "Queue[str]" = Queue()
        self._audio_thread: Optional[Thread] = None
        self._audio_thread_started = False
        self._hit_timer: Optional[QTimer] = None
        self.__live2d_timer: Optional[QTimer] = None
        self.__renderer: Optional[OffscreenRenderer] = None
        self.__canvas_opacity = 1.0
        self._rotation_angle = 0.0
        self.render_width, self.render_height = self.canvas_size
        self._stopped = False

        self.fps = int(fps)
        self.sleep_intv = max(1, int(1000 / max(1, self.fps)))
        self.scale = float(scale)
        self.dx = 0.0
        self.dy = 0.0
        self.partIds: List[str] = []
        self._last_hit: Optional[str] = None
        self._pending_hit: Optional[Tuple[int, int]] = None
        self._model_reload = False
        self._pending_resize: Optional[Tuple[int, int]] = None
        self._pending_model_flags = False
        self._last_frame_at = time.perf_counter()

        cfg = normalize(settings)
        cfg.update({
            "fps": self.fps,
            "scale": self.scale,
            "enable_audio_sync": self.enable_audio_sync,
            "enable_chunk_playback": self.enable_chunk_playback,
            "audio_sample_rate": self._audio_sample_rate,
            "audio_channels": self._audio_channels,
            "audio_sample_width": self._audio_sample_width,
            "lip_sync_gain": float(lipSync),
        })
        self.settings: Dict[str, Any] = cfg
        self.engine = BehaviorEngine(cfg)

        self.__dragging = False
        self.__drag_global_pos = QPoint()
        self.__drag_window_pos = QPoint()
        self._held_params: Dict[str, float] = {} 

    # ---------- 渲染结果 ----------

    def __on_image_ready(self, image: QImage):
        self.setPixmap(QPixmap.fromImage(image))
        # 空闲降帧 / 性能自适应，定时器间隔动态跟随引擎目标
        cmd_fps = float(getattr(self.engine.stats, "fps", 0) or 0)
        target = float(self.settings.get("idle_fps", 30)) if self.engine.idle.is_idle else float(self.settings.get("fps", 60))
        if self.settings.get("adaptive_fps", True) and cmd_fps > 0 and not self.engine.idle.is_idle:
            target = min(target, max(15.0, cmd_fps))
        interval = max(1, int(1000 / max(1.0, target)))
        if self.__live2d_timer is not None and self.__live2d_timer.interval() != interval:
            self.__live2d_timer.setInterval(interval)
        self._sync_render_scale()

    def _sync_render_scale(self) -> None:
        if self.__renderer is None:
            return
        desired = float(self.engine.perf.render_scale)
        if abs(desired - self.__renderer.render_scale) > 0.01:
            self.__renderer.set_render_scale(desired)

    def __on_frame_done(self, frame_ms: float) -> None:
        self.engine.perf.note_frame(frame_ms, time.monotonic())

    def __release_live2d_resources(self):
        """只在渲染线程、GL 上下文仍 current 时调用。"""
        global _live2d_initialized
        try:
            self.model = None
            self.wavehand = None
            live2d.dispose()
        except Exception as exc:
            logger.debug(f"[Live2D] dispose failed: {exc}")
        finally:
            with _live2d_init_lock:
                _live2d_initialized = False   # B40
        self.engine.submit("model_loaded", on=False)

    # ---------- 生命周期 ----------

    def init(self) -> None:
        try:
            if self.settings.get("enable_audio_sync") or self.settings.get("enable_chunk_playback"):
                # 分块播放仍需要 mixer；纯 RMS 模式不必初始化全局 mixer
                mixer.init(
                    frequency=self._audio_sample_rate,
                    size=-16,
                    channels=self._audio_channels
                )
        except Exception as exc:
            logger.warning(f"[Live2D] pygame mixer init skipped: {exc}")

        try:
            w = max(1, self.width() or self.canvas_size[0])
            h = max(1, self.height() or self.canvas_size[1])
            self.render_width, self.render_height = w, h
            self.__renderer = OffscreenRenderer(
                width=w, height=h, fps=self.fps,
                share_context=self.main_context,
                cleanup_callback=self.__release_live2d_resources,
                render_scale=float(self.settings.get("render_scale", 1.0)),
                opacity=float(self.settings.get("opacity", 1.0)),
            )
            self.__renderer.set_rotation_angle(self._rotation_angle)
            self.load_model(self.model_path)
            self.__renderer.set_render_callback(self.__draw_live2d)
            self.__renderer.prepare()
            self.__renderer.imageReady.connect(self.__on_image_ready)
            self.__renderer.frameDone.connect(self.__on_frame_done)
            self.__live2d_timer = QTimer(self)
            self.__live2d_timer.timeout.connect(self.__on_tick)
            self._init_audio()
            self._stopped = False
            self._apply_window_settings()
        except Exception as exc:
            logger.error(f"[Live2D] init failed: {exc}")
            self.model = None
            raise
    def _init_audio(self) -> None:
        self.wavehand = WavHandler()
        if self.enable_audio_sync:
            self.rms_meter = AsyncRmsMeter(
                is_async=True,
                sample_width=self._audio_sample_width,
                channels=self._audio_channels
            )
            if self.enable_chunk_playback:
                self.chunk_player = AsyncChunkPlayer(is_async=True)
        else:
            self._audio_thread = Thread(
                target=self.__sync_lip_sync,
                name="live2d-lipsync",
                daemon=True
            )

    def __on_tick(self) -> None:
        if self.__renderer is not None and self.running:
            self.__renderer.request_render()

    def start(self):
        self.running = True
        self.engine.submit("visible", on=self.isVisible())
        if self.__renderer is not None and not self.__renderer.is_running:
            self.__renderer.start()
        if self._audio_thread is not None and not self._audio_thread_started:
            self._audio_thread.start()
            self._audio_thread_started = True
        if self.enable_audio_sync:
            if self.rms_meter:
                self.rms_meter.start()
            if self.chunk_player:
                self.chunk_player.start()
        if self.__live2d_timer is not None:
            self.__live2d_timer.start(self.sleep_intv)

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self.running = False
        if self.__live2d_timer is not None:
            self.__live2d_timer.stop()
        if self.__renderer is not None:
            self.__renderer.stop()     # cleanup 在渲染线程内做
        if self.enable_audio_sync:
            if self.rms_meter:
                self.rms_meter.stop()
            if self.chunk_player:
                self.chunk_player.stop()
        else:
            if self._audio_thread is not None and self._audio_thread_started:
                self._audio_thread.join(timeout=1)
            self._audio_thread = None
            self._audio_thread_started = False
        self.wavehand = None
        try:
            mixer.quit()
        except Exception:
            pass

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)   # B49

    def showEvent(self, event):
        self.engine.submit("visible", on=True)
        super().showEvent(event)

    def hideEvent(self, event):
        self.engine.submit("visible", on=False)
        super().hideEvent(event)

    def enterEvent(self, event):
        self._update_mouse(event)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.engine.submit("mouse_leave")
        super().leaveEvent(event)

    # ---------- 模型（渲染线程） ----------
    def set_expression_held(self, param: str, value: float = 1.0) -> None:
        with self.engine._lock:  # 借用引擎锁，不新增锁
            if value:
                self._held_params[param] = float(value)
            else:
                self._held_params.pop(param, None)

    def clear_expressions_held(self) -> None:
        with self.engine._lock:
            self._held_params.clear()
    
    def contextMenuEvent(self, event):
        """无边框窗口需要右键菜单来退出或切换设置"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #555; }
            QMenu::item:selected { background-color: #4a4a4a; }
        """)
        
        act_reset = QAction("重置姿态", self)
        act_reset.triggered.connect(lambda: self.submit("reset_pose"))
        menu.addAction(act_reset)
        
        act_reload = QAction("重新加载模型", self)
        act_reload.triggered.connect(lambda: self.load_model(self.model_path))
        menu.addAction(act_reload)
        
        menu.addSeparator()
        
        act_close = QAction("退出", self)
        act_close.triggered.connect(self.close)
        menu.addAction(act_close)
        
        menu.exec(event.globalPos())
    
    def _hold_expression_params(self, exp_name: str):
        """读取动态生成的 exp3.json，把 VTS 参数加入持续保持列表"""
        if self.model is None:
            return
        
        base_dir = os.path.dirname(self.model_path)
        # 优先读取兼容文件里定义的 File 路径
        compat_path = os.path.join(base_dir, "_compat.model3.json")
        json_to_read = compat_path if os.path.exists(compat_path) else self.model_path
        
        try:
            with open(json_to_read, "r", encoding="utf-8") as f:
                data = json.load(f)
            for e in data.get("Expressions", []):
                if e.get("Name") == exp_name:
                    file_path = os.path.join(base_dir, e.get("File"))
                    if os.path.exists(file_path):
                        with open(file_path, "r", encoding="utf-8") as ef:
                            exp_data = json.load(ef)
                        # 清空之前的保持状态（VTS 表情通常是互斥的）
                        self._held_params.clear()
                        for p in exp_data.get("Parameters", []):
                            pid = p["Id"]
                            if pid.startswith("key"):
                                self._held_params[pid] = float(p.get("Value", 1.0))
                    break
        except Exception as exc:
            logger.debug(f"[Live2D] 解析表情参数失败: {exc}")
    
    def _prepare_compat_model(self) -> str:
        """兼容 VTS 导出结构：优先读取临时配置，无则动态扫描生成（无硬编码）"""
        if not self.model_path or not os.path.exists(self.model_path):
            return self.model_path

        base_dir = os.path.dirname(self.model_path)
        compat_path = os.path.join(base_dir, "_compat.model3.json")

        # 1. 优先检查是否存在临时兼容 JSON，并判断是否过期
        if os.path.exists(compat_path):
            try:
                compat_mtime = os.path.getmtime(compat_path)
                src_mtime = os.path.getmtime(self.model_path)
                is_outdated = src_mtime > compat_mtime
                
                if not is_outdated:
                    for folder in ("Exp3", "Animation"):
                        d = os.path.join(base_dir, folder)
                        if os.path.isdir(d):
                            for fn in os.listdir(d):
                                if os.path.getmtime(os.path.join(d, fn)) > compat_mtime:
                                    is_outdated = True
                                    break
                        if is_outdated:
                            break
                
                if not is_outdated:
                    return compat_path
                else:
                    logger.info("[Live2D] 检测到模型或动作文件更新，重新生成兼容配置...")
            except Exception as exc:
                logger.debug(f"[Live2D] 检查兼容文件状态失败: {exc}")

        # 2. 重新扫描并生成
        try:
            with open(self.model_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error(f"[Live2D] 读取原始 model3.json 失败: {exc}")
            return self.model_path

        changed = False

        # --- A. 扫描 Exp3 文件夹 ---
        exp_dir = os.path.join(base_dir, "Exp3")
        if os.path.isdir(exp_dir):
            if "Expressions" not in data:
                data["Expressions"] = []
            existing_exprs = {e.get("Name") for e in data["Expressions"] if isinstance(e, dict)}
            for fn in os.listdir(exp_dir):
                if fn.endswith(".exp3.json"):
                    name = fn[:-len(".exp3.json")]
                    if name not in existing_exprs:
                        data["Expressions"].append({"Name": name, "File": f"Exp3/{fn}"})
                        changed = True

        # --- B. 动态解析 cdi3.json，自动提取 VTS key 参数并生成表情 ---
        display_info = data.get("FileReferences", {}).get("DisplayInfo")
        if display_info:
            cdi_path = os.path.join(base_dir, display_info)
            if os.path.exists(cdi_path):
                try:
                    with open(cdi_path, "r", encoding="utf-8") as f:
                        cdi_data = json.load(f)
                    params = cdi_data.get("Parameters", [])
                    
                    if "Expressions" not in data:
                        data["Expressions"] = []
                    existing_names = {e.get("Name") for e in data["Expressions"] if isinstance(e, dict)}
                    
                    for p in params:
                        pid = p.get("Id", "")
                        pname = p.get("Name", "")
                        # 动态识别：以 key 开头，且名字里有实际意义的（过滤掉分割线）
                        if pid.startswith("key") and pname and not pname.startswith("■"):
                            # 移除 "1. 黑脸" 前面的序号，变成 "黑脸"
                            clean_name = pname.split(".")[-1].strip() if "." in pname else pname
                            auto_exp_name = f"_auto_{pid}.exp3.json"
                            exp_path = os.path.join(base_dir, auto_exp_name)
                            
                            # 自动生成标准的 exp3.json 文件
                            exp_content = {
                                "Type": "Live2D Expression",
                                "FadeInTime": 0.1,
                                "FadeOutTime": 0.1,
                                "Parameters": [{"Id": pid, "Value": 1.0, "Blend": "Add"}]
                            }
                            with open(exp_path, "w", encoding="utf-8") as f:
                                json.dump(exp_content, f, ensure_ascii=False)
                            
                            if clean_name not in existing_names:
                                data["Expressions"].append({"Name": clean_name, "File": auto_exp_name})
                                existing_names.add(clean_name)
                                changed = True
                except Exception as e:
                    logger.error(f"[Live2D] 解析 displayInfo 失败: {e}")

        # --- C. 扫描 Animation 文件夹 ---
        ani_dir = os.path.join(base_dir, "Animation")
        if os.path.isdir(ani_dir):
            if "Motions" not in data:
                data["Motions"] = {}
            if "Idle" not in data["Motions"]:
                data["Motions"]["Idle"] = []
            
            existing_motions = {m.get("File") for ml in data["Motions"].values() for m in ml if isinstance(m, dict)}
            
            for fn in os.listdir(ani_dir):
                if fn.endswith(".motion3.json"):
                    rel_path = f"Animation/{fn}"
                    if rel_path not in existing_motions:
                        group = "Idle" if "IDLE" in fn.upper() else "Gesture"
                        if group not in data["Motions"]:
                            data["Motions"][group] = []
                        data["Motions"][group].append({"File": rel_path, "FadeInTime": 0.5, "FadeOutTime": 0.5})
                        changed = True

        if changed or os.path.exists(compat_path):
            try:
                with open(compat_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"[Live2D] 已更新兼容版模型配置: {compat_path}")
                return compat_path
            except Exception as exc:
                logger.error(f"[Live2D] 生成兼容文件失败: {exc}")

        return self.model_path
    def __ensure_model_loaded(self) -> None:
        global _live2d_initialized
        if self._model_reload:
            self._model_reload = False
            try:
                self.model = None
            except Exception:
                pass
        if self.model is None:
            with _live2d_init_lock:
                if not _live2d_initialized:
                    live2d.init()
                    if getattr(live2d, "LIVE2D_VERSION", 3) == 3:
                        live2d.glInit()
                    live2d.enableLog(False)
                    _live2d_initialized = True
            if not self.model_path:
                return
            if not os.path.exists(self.model_path):
                logger.error(f"[Live2D] 模型文件不存在: {self.model_path}")
                return
            # 动态生成兼容版配置
            compat_path = self._prepare_compat_model()
            
            model = live2d.LAppModel()
            # 加载兼容后的模型文件
            model.LoadModelJson(compat_path) 
            model.Resize(self.render_width, self.render_height)
            model.SetAutoBlinkEnable(bool(self.settings.get("auto_blink", True)))
            model.SetAutoBreathEnable(bool(self.settings.get("auto_breath", True)))
            try:
                model.StartRandomMotion()
            except Exception:
                pass
            self.model = model
            try:
                self.partIds = list(model.GetPartIds() or [])
            except Exception:
                self.partIds = []
            # 只把模型里**真实存在**的表情/动作组交给引擎，避免每帧刷异常
            expr = self._safe_ids("GetExpressionIds", "GetExpressionCount")
            groups: Dict[str, int] = {}
            try:
                raw = model.GetMotionGroups() if hasattr(model, "GetMotionGroups") else {}
                if isinstance(raw, dict):
                    groups = {str(k): max(1, int(v)) for k, v in raw.items()}
            except Exception:
                pass
            self.engine.submit("model_loaded", on=True, expressions=expr, motions=groups)
            self._apply_model_transform()

    def _safe_ids(self, list_fn: str, count_fn: str) -> List[str]:
        if self.model is None:
            return []
        try:
            getter = getattr(self.model, list_fn, None)
            if callable(getter):
                value = getter()
                if isinstance(value, (list, tuple)):
                    return [str(x) for x in value]
        except Exception:
            pass
        return []

    def _apply_model_transform(self) -> None:
        """把 scale / offset / rotation 应用到模型（渲染线程）。"""
        if self.model is None:
            return
        try:
            # Cubism SDK 的 LAppModel 未统一暴露 SetScale，逐方法容错
            for name, value in (
                ("SetScale", float(self.settings.get("scale", 1.0))),
                ("SetOffsetX", float(self.settings.get("offset_x", 0))),
                ("SetOffsetY", float(self.settings.get("offset_y", 0))),
            ):
                fn = getattr(self.model, name, None)
                if callable(fn):
                    fn(value)
        except Exception as exc:
            logger.debug(f"[Live2D] transform not applicable: {exc}")

    def load_model(self, model_json_path: str):
        if not model_json_path:
            return
        if not os.path.exists(str(model_json_path)):
            raise FileNotFoundError(f"模型文件不存在: {model_json_path}")
        self.model_path = str(model_json_path)
        self._model_reload = True       # 渲染线程执行，主线程不碰 model
        self.engine.submit("activity")

    def __apply_command(self, cmd: FrameCommand) -> None:
        """把帧指令逐条应用到 model（**只在渲染线程**）。"""
        if self.model is None:
            return
        for p in cmd.params:
            try:
                if p.mode == "add":
                    self.model.AddParameterValue(p.name, p.value, 1.0)
                else:
                    self.model.SetParameterValue(p.name, p.value, 1.0)
            except Exception:
                pass
        for act in cmd.actions:
            try:
                if act.kind == "expression" and act.value:
                    self.model.SetExpression(act.value)
                    self._hold_expression_params(act.value)
                elif act.kind == "motion" and act.value:
                    self.model.StartMotion(act.value, act.index, act.priority)
                elif act.kind == "blink":
                    self.model.SetParameterValue("ParamEyeLOpen", 0.0, 1.0)
                    self.model.SetParameterValue("ParamEyeROpen", 0.0, 1.0)
                elif act.kind == "reset_expression":
                    self.model.ResetExpression()
                    self._held_params.clear()
                elif act.kind == "reset_pose":
                    self.model.ResetPose()
            except Exception as exc:
                logger.debug(f"[Live2D] action {act.kind} failed: {exc}")

    def __draw_live2d(self, width: int, height: int):
        now = time.perf_counter()
        dt = max(1 / 240, min(0.25, now - self._last_frame_at))
        self._last_frame_at = now
        self.__ensure_model_loaded()
        if self._pending_resize:
            w, h = self._pending_resize
            self._pending_resize = None
            self.render_width, self.render_height = w, h
            if self.model is not None:
                try:
                    self.model.Resize(w, h)
                except Exception:
                    pass
        cmd = self.engine.step(dt)
        if not cmd.should_render:
            return
        self._consume_rms()
        self._do_hit_test()
        self._apply_model_flags()
        self.__apply_command(cmd)
        if self.model is None:
            return
        live2d.clearBuffer()
        try:
            self.model.Update()
            self.model.Draw()
        except Exception as exc:
            logger.debug(f"[Live2D] draw failed: {exc}")

    def _consume_rms(self) -> None:
        """把异步 RMS Meter 的最新值喂给引擎（只传数字，不碰 model）。"""
        if self.rms_meter is None:
            return
        try:
            if self.rms_meter.update():
                self.engine.submit("rms", value=self.rms_meter.get_rms())
        except Exception:
            pass

    # ---------- 音频 ----------

    @property
    def _audio_ready(self) -> bool:
        return self.running and (self.rms_meter is not None or self.wavehand is not None)

    def sync_play(self, audio_path: str):
        try:
            mixer.music.load(audio_path)
            mixer.music.play()
        except Exception as exc:
            logger.warning(f"[Live2D] audio play failed: {exc}")
            return
        if self.wavehand is not None:
            self.wavehand.Start(audio_path)
        self.engine.submit("speaking", on=True)

    def __sync_lip_sync(self) -> None:
        while self.running:
            if not self._audio_queue.empty():
                audio_path = self._audio_queue.get()
                self.engine.submit(
                    "motion",
                    group=str(self.settings.get("speak_motion_group") or "Speak"),
                    priority=3
                )
                self.sync_play(audio_path)
            else:
                if self.wavehand is not None and self.wavehand.Update():
                    self.engine.submit("rms", value=self.wavehand.GetRms())
            time.sleep(0.02)   # 50Hz 足够，且不再碰 model

    def pull_audio(self, audio_path: str):
        if not self.enable_chunk_playback:
            self._audio_queue.put(audio_path)
        self.engine.submit("activity")

    def push_audio_chunk(self, chunk: bytes) -> None:
        if self.rms_meter:
            self.rms_meter.push_chunk(chunk)
            if self.enable_chunk_playback and self.chunk_player:
                self.chunk_player.push_chunk(chunk)
        elif self.wavehand is not None:
            self.engine.submit("rms", value=_quick_rms(chunk))
        self.engine.submit("activity")

    def configure_audio_format(self, sample_rate: int, channels: int, sample_width: int) -> None:
        if sample_rate <= 0 or channels <= 0:
            return
        self._audio_sample_rate = int(sample_rate)
        self._audio_channels = int(channels)
        self._audio_sample_width = int(sample_width)
        if self.rms_meter:
            self.rms_meter.set_audio_format(sample_width=sample_width, channels=channels)
        desired = (sample_rate, -16, channels)
        try:
            if mixer.get_init() == desired:
                return
            mixer.quit()
            mixer.init(frequency=sample_rate, size=-16, channels=channels)
        except Exception as exc:
            logger.debug(f"[Live2D] mixer reconfigure skipped: {exc}")

    # ---------- 人脸 / 交互（主线程只提交意图） ----------

    def apply_face_data(self, data):
        payload = {
            "yaw": float(getattr(data, "yaw", 0.0)),
            "pitch": float(getattr(data, "pitch", 0.0)),
            "roll": float(getattr(data, "roll", 0.0)),
            "eye_left": float(getattr(data, "eye_left", 1.0)),
            "eye_right": float(getattr(data, "eye_right", 1.0)),
            "mouth_y": float(getattr(data, "mouth_y", 0.0)),
        }
        self.engine.submit("face", data=payload)   # B52：不再跨线程写 model

    def face_data_lost(self):
        """动捕超时/关闭 → 立刻回落到鼠标视线。"""
        self.engine.submit("face_lost")

    def _update_mouse(self, event) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        p = event.position()
        nx = (p.x() / w) * 2.0 - 1.0
        ny = (p.y() / h) * 2.0 - 1.0
        self.engine.submit("mouse", nx=nx, ny=ny)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._update_mouse(event)
            if self.settings.get("hit_test_enabled", True):
                p = event.position()
                self._pending_hit = (int(p.x()), int(p.y()))
            if self.settings.get("drag_enabled", True):
                self.__dragging = True
                self.__drag_global_pos = event.globalPosition().toPoint()
                self.__drag_window_pos = self.pos()
            self.engine.submit("activity")
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._update_mouse(event)     # 眼睛随鼠标，不依赖动捕
        if self.__dragging and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.__drag_global_pos
            self.move(self.__drag_window_pos + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.__dragging:
            self.__dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        expr = str(self.settings.get("double_click_expression") or "")
        if expr:
            self.engine.submit("expression", value=expr)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_R:
            self.engine.submit("reset_pose")
        elif k == Qt.Key.Key_E:
            self.engine.submit("reset_expression")
        elif k == Qt.Key.Key_B:
            self.engine.submit("blink")
        elif k == Qt.Key.Key_Space:
            self.engine.submit("activity")
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                   Qt.Key.Key_I, Qt.Key.Key_U):
            patch = dict(self.settings)
            if k == Qt.Key.Key_Left:
                patch["offset_x"] = float(patch.get("offset_x", 0)) - 0.1
            elif k == Qt.Key.Key_Right:
                patch["offset_x"] = float(patch.get("offset_x", 0)) + 0.1
            elif k == Qt.Key.Key_Up:
                patch["offset_y"] = float(patch.get("offset_y", 0)) + 0.1
            elif k == Qt.Key.Key_Down:
                patch["offset_y"] = float(patch.get("offset_y", 0)) - 0.1
            elif k == Qt.Key.Key_I:
                patch["scale"] = float(patch.get("scale", 1.0)) + 0.1
            elif k == Qt.Key.Key_U:
                patch["scale"] = max(0.2, float(patch.get("scale", 1.0)) - 0.1)
            self.set_settings(patch)
        super().keyPressEvent(event)

    def getHitFeedback(self, x: int, y: int) -> Optional[str]:
        """只读最近一次命中结果；实际 HitPart 在渲染线程执行"""
        self._pending_hit = (int(x), int(y))
        return self._last_hit

    def _do_hit_test(self) -> None:
        if self._pending_hit is None or self.model is None:
            return
        x, y = self._pending_hit
        self._pending_hit = None
        try:
            hits = self.model.HitPart(x, y, False) or []
            self._last_hit = str(hits[0]) if hits else None
            if self._last_hit:
                group = str(self.settings.get("click_motion_group") or "")
                if group:
                    self.engine.submit("motion", group=group, priority=2)
            if self._last_hit and self.settings.get("hit_feedback_enabled", False):
                # 只在开启时改乘色，且由引擎在下一帧 reset_pose 还原
                self.engine.submit("reset_pose")
        except Exception as exc:
            logger.debug(f"[Live2D] hit test failed: {exc}")
            self._last_hit = None

    def resizeEvent(self, event):
        w, h = max(1, event.size().width()), max(1, event.size().height())
        self.render_width, self.render_height = w, h
        self._pending_resize = (w, h)   # model.Resize 交给渲染线程
        if self.__renderer is not None:
            self.__renderer.set_size(w, h)   # FBO 同步重建
        super().resizeEvent(event)

    # ---------- 外观与设置（主线程） ----------

    def set_rotation_angle(self, angle: float):
        self._rotation_angle = float(angle) % 360.0
        if self.__renderer:
            self.__renderer.set_rotation_angle(self._rotation_angle)

    def set_opacity(self, opacity: float) -> None:
        self.__canvas_opacity = max(0.0, min(1.0, float(opacity)))
        self.setWindowOpacity(self.__canvas_opacity)   # 整窗
        if self.__renderer:
            self.__renderer.set_opacity(self.__canvas_opacity)  # 旋转路径 shader

    def set_settings(self, cfg: Dict[str, Any]) -> None:
        """热应用配置（由 on_config_change 调用，无需重启服务）。"""
        new = normalize(cfg)
        old = dict(self.settings)
        self.settings = new
        self.engine.update_config(new)
        self.fps = max(1, int(new.get("fps", 60)))
        self.sleep_intv = max(1, int(1000 / self.fps))
        if self.__renderer is not None:
            self.__renderer.set_fps(self.fps)
            self.__renderer.set_opacity(float(new.get("opacity", 1.0)))
            self.__renderer.set_render_scale(float(new.get("render_scale", 1.0)))
            self.__renderer.set_rotation_angle(float(new.get("rotation", 0.0)))
        if self.__live2d_timer is not None:
            self.__live2d_timer.setInterval(self.sleep_intv)
        self.setWindowOpacity(float(new.get("opacity", 1.0)))
        self.set_rotation_angle(float(new.get("rotation", 0.0)))
        if new.get("model_path") != old.get("model_path") and new.get("model_path"):
            try:
                self.load_model(str(new["model_path"]))
            except (OSError, ValueError) as exc:
                logger.warning(f"[Live2D] 模型热切换失败: {exc}")
        if new.get("canvas_size") != old.get("canvas_size"):
            w, h = parse_canvas_size(new.get("canvas_size"))
            self.canvas_size = (w, h)
            self.resize(w, h)
        self._apply_window_settings()
        self._sync_model_flags()

    def _sync_model_flags(self) -> None:
        """auto_blink / auto_breath 变化在下一渲染帧生效（渲染线程内）。"""
        self._pending_model_flags = True

    def _apply_model_flags(self) -> None:
        if not self._pending_model_flags or self.model is None:
            return
        self._pending_model_flags = False
        try:
            self.model.SetAutoBlinkEnable(bool(self.settings.get("auto_blink", True)))
            self.model.SetAutoBreathEnable(bool(self.settings.get("auto_breath", True)))
        except Exception as exc:
            logger.debug(f"[Live2D] model flags skipped: {exc}")

    def _apply_window_settings(self) -> None:
        from PyQt6.QtCore import Qt as _Qt
        flags = _Qt.WindowType.Widget
        if self.settings.get("frameless", True):
            flags |= _Qt.WindowType.FramelessWindowHint
        if self.settings.get("always_on_top", True):
            flags |= _Qt.WindowType.WindowStaysOnTopHint
        if self.settings.get("hide_taskbar", True):
            flags |= _Qt.WindowType.Tool
        if self.settings.get("click_through", False):
            flags |= _Qt.WindowType.WindowTransparentForInput
        try:
            was_visible = self.isVisible()
            self.setWindowFlags(flags)
            self.setAttribute(
                _Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                bool(self.settings.get("click_through", False))
            )
            # Qt: setWindowFlags 会隐式 hide，热应用配置时恢复可见状态
            if was_visible:
                self.show()
        except Exception as exc:
            logger.debug(f"[Live2D] window flags skipped: {exc}")

    def get_status(self) -> Dict[str, Any]:
        """给 /api/live2d/status；纯读引擎状态，不碰 model。"""
        data = self.engine.status()
        data.update({
            "model_path": self.model_path,
            "render_width": self.render_width,
            "render_height": self.render_height,
            "rotation": self._rotation_angle,
            "opacity": self.__canvas_opacity,
            "running": self.running,
            "audio_sync": self.enable_audio_sync,
            "chunk_playback": self.enable_chunk_playback,
        })
        return data

    def submit(self, kind: str, **payload: Any) -> None:
        """外部（API / devtools）注入意图的统一入口。"""
        self.engine.submit(kind, **payload)
        self._listen_dialogue(kind, payload)

    def _listen_dialogue(self, kind: str, payload: Dict[str, Any]) -> None:
        """对话框事件联动模型：说话开始/结束、情绪表情。"""
        if kind != "dialogue":
            return
        state = str(payload.get("state") or "")
        if state == "speaking":
            self.engine.submit("speaking", on=bool(payload.get("on", True)))
        elif state == "emotion":
            self.engine.submit("emotion", value=str(payload.get("value") or ""))
        elif state == "typing":
            self.engine.submit("activity")


def _quick_rms(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    try:
        pcm = np.frombuffer(chunk, dtype=np.int16)
        if pcm.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(pcm, dtype=np.float64)))) / 32768.0
    except Exception:
        return 0.0
