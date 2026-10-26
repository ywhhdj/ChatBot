"""Live2D 画布：离屏 OpenGL 渲染 + QLabel 显示。"""

from __future__ import annotations

import math
import os
import time
from queue import Queue
from threading import Thread
from typing import Optional

import live2d.v3 as live2d
import numpy as np
import pygame
from OpenGL import GL
from PyQt6.QtCore import QObject, QPoint, QSize, Qt, QThread, QTimer, QWaitCondition, pyqtSignal
from PyQt6.QtGui import (
    QImage,
    QMouseEvent,
    QOffscreenSurface,
    QOpenGLContext,
    QPixmap,
    QSurfaceFormat,
)
from PyQt6.QtWidgets import QLabel

from .audio import AsyncChunkPlayer, AsyncRmsMeter, WavHandler


def compile_shader(shader_src: str, shader_type):
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, shader_src)
    GL.glCompileShader(shader)
    status = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
    if status != GL.GL_TRUE:
        msg = GL.glGetShaderInfoLog(shader).decode("utf-8")
        GL.glDeleteShader(shader)
        raise Exception(f"Shader compile error: {msg}")
    return shader


def create_program(vs, fs):
    vertex_shader = compile_shader(vs, GL.GL_VERTEX_SHADER)
    frag_shader = compile_shader(fs, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader)
    GL.glAttachShader(program, frag_shader)
    GL.glLinkProgram(program)
    GL.glDetachShader(program, vertex_shader)
    GL.glDetachShader(program, frag_shader)
    GL.glDeleteShader(vertex_shader)
    GL.glDeleteShader(frag_shader)
    status = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if status != GL.GL_TRUE:
        msg = GL.glGetProgramInfoLog(program)
        raise RuntimeError(msg)
    return program


def create_vao(v_pos, uv_coord):
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
    return vao


class OffscreenRenderer(QObject):
    imageReady = pyqtSignal(QImage)

    def __init__(
        self,
        fps: float = 60.0,
        width: int = 800,
        height: int = 600,
        share_context=None,
        cleanup_callback=None
    ):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.share_context = share_context
        self.frame_interval_ms = max(1, int(1000 / max(1.0, fps)))

        self.__running = False
        self.__render_callback = None
        self.__mutex = None
        self.__cond = None
        self.__request_render = False
        self.rotation_angle = 0.0
        self.rotate_program = None
        self.quad_vao = None
        self.temp_fbo = None
        # GL 资源（live2d）必须在渲染线程内释放，通过回调在线程末尾调用
        self.__cleanup_callback = cleanup_callback

        # 线程对象与主循环状态独立维护，stop() 前可能从未 start()
        self.__thread: Optional[QThread] = None
        self.__prepared = False

    def set_rotation_angle(self, angle: float):
        self.rotation_angle = angle % 360.0

    @property
    def is_running(self) -> bool:
        return self.__thread is not None and self.__thread.isRunning()

    # ---------- GL 资源 ----------

    def __init_rotate_resources(self):
        vertex_shader = """#version 330 core
            layout(location = 0) in vec2 a_position;
            layout(location = 1) in vec2 a_texCoord;
            out vec2 v_texCoord;
            uniform float rotation_angle;
            void main() {
                gl_Position = vec4(a_position, 0.0, 1.0);
                float angle = radians(rotation_angle);
                mat2 rotationMatrix = mat2(cos(angle), -sin(angle),
                                           sin(angle),  cos(angle));
                vec2 centeredTexCoord = a_texCoord - vec2(0.5, 0.5);
                v_texCoord = rotationMatrix * centeredTexCoord + vec2(0.5, 0.5);
            }
        """
        fragment_shader = """#version 330 core
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
        self.rotate_program = create_program(vertex_shader, fragment_shader)

        vertices = np.array(
            [
                -1, 1,
                -1, -1,
                1, -1,
                -1, 1,
                1, -1,
                1, 1,
            ],
            dtype=np.float32,
        ).reshape(6, 2)
        uvs = np.array(
            [
                0, 1,
                0, 0,
                1, 0,
                0, 1,
                1, 0,
                1, 1,
            ],
            dtype=np.float32,
        ).reshape(6, 2)
        self.quad_vao = create_vao(vertices, uvs)

    def __rotate_fbo(self, src_fbo) -> QImage:
        width = src_fbo.width()
        height = src_fbo.height()
        if self.temp_fbo is None or self.temp_fbo.width() != width or self.temp_fbo.height() != height:
            if self.temp_fbo:
                self.temp_fbo.release()
            self.temp_fbo = self.__create_fbo(width, height)
        self.temp_fbo.bind()
        GL.glViewport(0, 0, width, height)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        GL.glUseProgram(self.rotate_program)
        rot_loc = GL.glGetUniformLocation(self.rotate_program, "rotation_angle")
        GL.glUniform1f(rot_loc, self.rotation_angle)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, src_fbo.texture())
        tex_loc = GL.glGetUniformLocation(self.rotate_program, "canvas")
        GL.glUniform1i(tex_loc, 0)

        GL.glBindVertexArray(self.quad_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

        image = self.temp_fbo.toImage()
        self.temp_fbo.release()
        return image

    # ---------- 生命周期 ----------

    def start(self):
        """启动渲染线程。B27：重复调用安全，已运行则跳过。"""
        if self.is_running:
            return
        if not self.__prepared:
            self.prepare()

        self.__running = True
        thread = QThread()
        self.moveToThread(thread)
        self.__thread = thread
        thread.started.connect(self.__render_loop)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def stop(self):
        self.__running = False
        thread = self.__thread
        if thread is None:
            return
        if not thread.isRunning():
            self.__thread = None
            return
        # 唤醒等待中的渲染循环，让它尽快退出
        try:
            if self.__cond is not None:
                self.__cond.wakeAll()
        except Exception:
            pass
        thread.quit()
        thread.wait()
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

    def set_fps(self, fps: float):
        self.fps = fps
        self.frame_interval_ms = max(1, int(1000 / max(1.0, fps)))

    def prepare(self):
        if self.__prepared:
            return
        self.format = QSurfaceFormat()
        self.format.setMajorVersion(3)
        self.format.setMinorVersion(3)
        self.format.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        self.format.setOption(QSurfaceFormat.FormatOption.DeprecatedFunctions)
        self.format.setDepthBufferSize(0)
        self.format.setStencilBufferSize(0)
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.format)
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("Failed to create offscreen surface")

        from PyQt6.QtCore import QMutex

        self.__mutex = QMutex()
        self.__cond = QWaitCondition()
        self.__prepared = True

    def __create_context(self):
        context = QOpenGLContext()
        if self.share_context:
            context.setShareContext(self.share_context)
        context.setFormat(self.format)
        if not context.create():
            raise RuntimeError("Failed to create OpenGL context")
        if not context.makeCurrent(self.surface):
            raise RuntimeError("Failed to make OpenGL context current")
        return context

    def __create_fbo(self, width: int, height: int):
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid FBO size: {width}x{height}")
        from PyQt6.QtOpenGL import QOpenGLFramebufferObjectFormat, QOpenGLFramebufferObject

        fbo_format = QOpenGLFramebufferObjectFormat()
        fbo_format.setAttachment(QOpenGLFramebufferObject.Attachment.NoAttachment)
        fbo_format.setTextureTarget(GL.GL_TEXTURE_2D)  # type: ignore
        fbo_format.setInternalTextureFormat(GL.GL_RGBA8)  # type: ignore
        fbo_format.setSamples(0)
        fbo = QOpenGLFramebufferObject(QSize(width, height), fbo_format)
        if not fbo.isValid():
            raise RuntimeError("Failed to create FBO")
        return fbo

    def __render_loop(self):
        """渲染线程主循环。GL 资源（含 live2d）都在本线程内创建与释放。"""
        context = self.__create_context()
        try:
            fbo = self.__create_fbo(self.width, self.height)
            self.__init_rotate_resources()
            while self.__running:
                if self.__mutex is not None:
                    self.__mutex.lock()
                    if not self.__request_render and self.__cond is not None:
                        self.__cond.wait(self.__mutex, 100)
                    need_render = self.__request_render
                    self.__request_render = False
                    self.__mutex.unlock()
                else:
                    need_render = False

                if need_render and self.__render_callback:
                    fbo.bind()
                    GL.glViewport(0, 0, self.width, self.height)
                    self.__render_callback(self.width, self.height)
                    fbo.release()
                    if abs(self.rotation_angle) > 0.01:
                        image = self.__rotate_fbo(fbo)
                    else:
                        image = fbo.toImage()
                    self.imageReady.emit(image)
                QThread.msleep(self.frame_interval_ms)

            # live2d.dispose() 必须在 GL 上下文仍 current 的本线程内调用
            if self.__cleanup_callback is not None:
                try:
                    self.__cleanup_callback()
                except Exception:
                    pass

            fbo.release()
            if self.temp_fbo:
                self.temp_fbo.release()
                self.temp_fbo = None
            if self.rotate_program:
                GL.glDeleteProgram(self.rotate_program)
                self.rotate_program = None
            if self.quad_vao:
                GL.glDeleteVertexArrays(1, [self.quad_vao])
                self.quad_vao = None
        finally:
            context.doneCurrent()
            self.surface.destroy()


class Live2DCanvas(QLabel):
    LIVE2D_INITIALIZED: bool = False

    def __init__(
        self,
        model_path: str,
        model_name: str = "Live2D Model",
        main_context=None,
        canvas_size: tuple[int, int] = (1200, 800),
        fps: int = 30,
        enable_audio_sync: bool = False,
        enable_chunk_playback: bool = False,
        audio_sample_rate: int = 44100,
        audio_channels: int = 1,
        audio_sample_width: int = 2,
        lipSync: int = 3,
        scale: float = 1.0,
    ) -> None:
        super().__init__()
        self.setWindowTitle(model_name)
        self.resize(*canvas_size)
        self.setFixedSize(*canvas_size)
        self.setMouseTracking(True)
        self.setScaledContents(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.main_context = main_context
        self.model_path: str = model_path
        self.canvas_size: tuple[int, int] = (int(canvas_size[0]), int(canvas_size[1]))
        self.enable_audio_sync: bool = enable_audio_sync

        self.enable_chunk_playback = enable_chunk_playback
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels
        self._audio_sample_width = audio_sample_width

        self.running: bool = False
        self.model: Optional[live2d.LAppModel] = None
        self.wavehand: Optional[WavHandler] = None
        self.rms_meter: Optional[AsyncRmsMeter] = None
        self.chunk_player: Optional[AsyncChunkPlayer] = None
        self._audio_queue: "Queue[str]" = Queue()
        self._audio_thread: Optional[Thread] = None
        self._audio_thread_started = False  # B31
        self._hit_timer: Optional[QTimer] = None
        self.__live2d_timer: Optional[QTimer] = None
        self.__renderer: Optional[OffscreenRenderer] = None
        self.__canvas_opacity: float = 1.0
        # B32：统一属性名
        self._rotation_angle: float = 0.0
        # B30：首帧前 resizeEvent 可能没触发过
        self.render_width = self.canvas_size[0]
        self.render_height = self.canvas_size[1]
        self._stopped = False  # B28：stop() 一次性守卫

        self.fps: int = fps
        self.sleep_intv = max(1, int(1000 / max(1, self.fps)))
        self.lipSync: int = lipSync
        self.dx: float = 0.0
        self.dy: float = 0.0
        self.scale: float = scale
        self.currentTopClickedPartId: Optional[str] = None
        self.partIds: list[str] = []
        self.radius_per_frame: float = math.pi * 0.5 / 120
        self.total_radius = 0

        self.__dragging = False
        self.__drag_global_pos = QPoint()
        self.__drag_window_pos = QPoint()

    # ---------- 渲染结果 ----------

    def __on_image_ready(self, image):
        self.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def __release_live2d_resources(self):
        """B28：在渲染线程内释放 live2d（GL 上下文仍 current）。"""
        try:
            self.model = None
            self.wavehand = None
            live2d.dispose()
        except Exception:
            pass

    # ---------- 生命周期 ----------

    def init(self) -> None:
        pygame.mixer.init(
            frequency=self._audio_sample_rate, size=-16, channels=self._audio_channels
        )
        try:
            w = max(1, self.width() or self.canvas_size[0])
            h = max(1, self.height() or self.canvas_size[1])
            self.render_width = w
            self.render_height = h
            self.__renderer = OffscreenRenderer(
                width=w,
                height=h,
                share_context=self.main_context,
                cleanup_callback=self.__release_live2d_resources,
            )
            self.load_model(self.model_path)
            self.__renderer.set_render_callback(self.__draw_live2d)
            self.__renderer.prepare()
            self.__renderer.imageReady.connect(self.__on_image_ready)
            self.__live2d_timer = QTimer(self)
            self.__live2d_timer.timeout.connect(self.__renderer.request_render)
            if self.enable_audio_sync:
                self.rms_meter = AsyncRmsMeter(is_async=self.enable_audio_sync)
                if self.enable_chunk_playback:
                    self.chunk_player = AsyncChunkPlayer(is_async=self.enable_chunk_playback)
            else:
                self.wavehand = WavHandler()
                self._audio_thread = Thread(target=self.__sync_lip_sync, daemon=True)
            self._stopped = False
        except Exception as e:
            print(e)
            self.model = None

    def start(self):
        self.running = True
        if self.__renderer is not None and not self.__renderer.is_running:
            self.__renderer.start()
        # B31：Thread 只能 start 一次
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
            self.__renderer.stop()

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
        self.model = None
        # B28：只退 mixer，不要 pygame.quit()（它是全局的，会波及别处）
        try:
            pygame.mixer.quit()
        except Exception:
            pass

    def closeEvent(self, event):
        self.stop()
        event.accept()

    # ---------- 模型 ----------

    def __ensure_model_loaded(self):
        """在 OpenGL 上下文（渲染线程）中调用。"""
        if self.model is None:
            if not self.LIVE2D_INITIALIZED:
                live2d.init()
                if live2d.LIVE2D_VERSION == 3:
                    live2d.glInit()
                live2d.enableLog(False)
                self.LIVE2D_INITIALIZED = True
            if not self.model_path:
                return
            self.model = live2d.LAppModel()
            self.model.LoadModelJson(self.model_path)
            self.model.Resize(self.render_width, self.render_height)
            self.model.SetAutoBlinkEnable(True)
            self.model.SetAutoBreathEnable(True)
            self.model.StartRandomMotion()
            self.partIds = self.model.GetPartIds()

    def load_model(self, model_json_path: str):
        if not os.path.exists(model_json_path):
            raise FileNotFoundError(f"模型文件不存在: {model_json_path}")
        self.model_path = model_json_path
        self.model = None  # 延迟到渲染线程加载

    def __update_wavehand(self):
        if self.wavehand and self.wavehand.Update():
            self.model.AddParameterValue(  # type: ignore[union-attr]
                live2d.StandardParams.ParamMouthOpenY,
                self.wavehand.GetRms() * self.lipSync,
            )
        elif self.rms_meter and self.rms_meter.update():
            self.model.AddParameterValue(  # type: ignore[union-attr]
                live2d.StandardParams.ParamMouthOpenY,
                self.rms_meter.get_rms() * self.lipSync,
            )

    def __draw_live2d(self, width, height):
        self.__ensure_model_loaded()
        if self.model is None:
            return
        live2d.clearBuffer()
        self.model.Update()
        self.__update_wavehand()
        self.model.Draw()

    # ---------- 音频 ----------

    @property
    def _audio_ready(self) -> bool:
        """B33：不再依赖 self.model（它由渲染线程懒加载，首帧前恒为 None）。"""
        return self.running and (self.rms_meter is not None or self.wavehand is not None)

    def sync_play(self, audio_path: str):
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        if self.wavehand is not None:
            self.wavehand.Start(audio_path)

    def __sync_lip_sync(self) -> None:
        while self.running:
            if self.wavehand and self.model and not pygame.mixer.music.get_busy():
                if not self._audio_queue.empty():
                    audio_path = self._audio_queue.get()
                    self.model.StartMotion(
                        "Speak", 0, live2d.MotionPriority.FORCE,
                        lambda: self.sync_play(audio_path),
                    )
            time.sleep(0.01)

    def pull_audio(self, audio_path: str):
        if not self.enable_chunk_playback:
            self._audio_queue.put(audio_path)

    def push_audio_chunk(self, chunk: bytes) -> None:
        if self.rms_meter:
            self.rms_meter.push_chunk(chunk)
            if self.enable_chunk_playback and self.chunk_player:
                self.chunk_player.push_chunk(chunk)

    def configure_audio_format(self, sample_rate: int, channels: int, sample_width: int) -> None:
        if sample_rate <= 0 or channels <= 0:
            return
        self._audio_sample_rate = sample_rate
        self._audio_channels = channels
        self._audio_sample_width = sample_width
        if self.enable_audio_sync and self.rms_meter:
            self.rms_meter.set_audio_format(sample_width=sample_width, channels=channels)
        # 仅支持 16-bit PCM
        if sample_width != 2:
            return
        desired = (sample_rate, -16, channels)
        try:
            current = pygame.mixer.get_init()
        except Exception:
            current = None
        if current == desired:
            return
        try:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=channels)
        except Exception:
            pass

    # ---------- 人脸 ----------

    def apply_face_data(self, data):
        if self.model is None:
            return
        self.model.SetParameterValue(live2d.StandardParams.ParamEyeLOpen, data.eye_left, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamEyeROpen, data.eye_right, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamMouthOpenY, data.mouth_y, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleX, data.yaw, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleY, data.pitch, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleZ, data.roll, 1)

    # ---------- 交互 ----------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.__dragging = True
            if self.model:
                self.model.SetParameterValue(live2d.StandardParams.ParamMouthOpenY, 0.5, 1)
            self.__drag_global_pos = event.globalPosition().toPoint()
            self.__drag_window_pos = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.__dragging and event.buttons() == Qt.MouseButton.LeftButton:
            if self.model:
                self.model.StartRandomMotion()
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.dx -= 0.1
        elif event.key() == Qt.Key.Key_Right:
            self.dx += 0.1
        elif event.key() == Qt.Key.Key_Up:
            self.dy += 0.1
        elif event.key() == Qt.Key.Key_Down:
            self.dy -= 0.1
        elif event.key() == Qt.Key.Key_I:
            self.scale += 0.1
        elif event.key() == Qt.Key.Key_U:
            self.scale -= 0.1

        if self.model is None:
            return
        if event.key() == Qt.Key.Key_R:
            self.model.StopAllMotions()
            self.model.ResetPose()
        elif event.key() == Qt.Key.Key_E:
            self.model.ResetExpression()

    def getHitFeedback(self, x: int, y: int):
        if self.model:
            hitPartIds = self.model.HitPart(x, y, False)
            if self.currentTopClickedPartId is not None:
                pidx = self.partIds.index(self.currentTopClickedPartId)
                self.model.SetPartOpacity(pidx, 1)
                self.model.SetPartMultiplyColor(pidx, 1.0, 1.0, 1.0, 1)
            if len(hitPartIds) > 0:
                return hitPartIds[0]

    def resizeEvent(self, event):
        self.render_width = event.size().width()
        self.render_height = event.size().height()
        if self.model:
            self.model.Resize(self.render_width, self.render_height)
        super().resizeEvent(event)

    # ---------- 外观 ----------

    def set_rotation_angle(self, angle: float):
        self._rotation_angle = angle % 360.0
        if self.__renderer:
            self.__renderer.set_rotation_angle(self._rotation_angle)
            self.update()

    def set_opacity(self, opacity: float) -> None:
        self.__canvas_opacity = max(0.0, min(1.0, opacity))
        self.setWindowOpacity(self.__canvas_opacity)
        self.update()
