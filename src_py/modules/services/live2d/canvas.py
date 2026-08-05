from __future__ import annotations
from queue import Queue
import live2d.v3 as live2d
from typing import Optional
import time
import math
import pygame
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QMutex, QWaitCondition,QSize,QThread,QObject, QPoint,QPoint
)
from PyQt5.QtGui import (
    QMouseEvent,QKeyEvent,QOpenGLContext,QSurfaceFormat,QOffscreenSurface,QOpenGLFramebufferObject,QImage,QPixmap,QPainter
)
from PyQt5.QtWidgets import QLabel
from threading import Thread
import os
from OpenGL import GL
from typing import Any

from .audio import AsyncRmsMeter,AsyncChunkPlayer,WavHandler


import OpenGL.GL as GL

def compile_shader(shader_src:str, shader_type):
    shader = GL.glCreateShader(shader_type) # 创建着色器对象
    GL.glShaderSource(shader, shader_src) # 绑定着色器源码
    GL.glCompileShader(shader) # 编译着色器
    status = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) # 获取编译状态
    if status != GL.GL_TRUE: # 更明确的检查
        msg = GL.glGetShaderInfoLog(shader).decode("utf-8")
        GL.glDeleteShader(shader) # 编译失败也应删除着色器对象
        raise Exception(f"Shader compile error: {msg}")
    return shader

def create_program(vs, fs):
    vertex_shader = compile_shader(vs, GL.GL_VERTEX_SHADER)
    frag_shader = compile_shader(fs, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader) # 绑定顶点着色器
    GL.glAttachShader(program, frag_shader) # 绑定片元着色器
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

# 创建VAO 顶点数组对象
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

# 创建画布帧缓冲区
def create_canvas_framebuffer(width:int, height:int) -> tuple[Any, Any]:
    old_fbo = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
    fbo = GL.glGenFramebuffers(1)

    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)

    texture = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA,
                    width, height,
                    0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, texture, 0)

    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, old_fbo)
    return fbo, texture

class OffscreenRenderer(QObject):
    imageReady = pyqtSignal(QImage)  # 渲染完成信号，包含渲染好的 QImage
    def __init__(self, fps:float=60.0, width:int=800, height:int=600, share_context=None):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.share_context = share_context
        self.frame_interval_ms = int(1000 / fps)
        self.__cached_image = None

        self.__running = False
        self.__render_callback = None
        self.__mutex = QMutex()
        self.__cond = QWaitCondition()
        self.__request_render = False
        self.rotation_angle = 0.0           # 旋转角度（度）
        # self.opacity = 1.0                  # 透明度 0~1
        self.rotate_program = None          # 旋转/透明度着色器程序
        self.quad_vao = None                # 全屏四边形 VAO
        self.temp_fbo = None                # 临时 FBO（用于旋转后输出）
        self.temp_fbo_texture = None        # 临时 FBO 的纹理（可选）
        # 新增：标记是否已初始化
        self.__initialized = False
    
    def set_rotation_angle(self, angle: float):
        self.rotation_angle = angle % 360.0

    # def set_opacity(self, opacity: float):
    #     self.opacity = max(0.0, min(1.0, opacity))
    
    def __init_rotate_resources(self):
        """创建用于旋转+透明度的着色器程序和全屏四边形 VAO"""
        # 顶点着色器（与你的 OpenGLCanvas 中一致）
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
        # 片段着色器（添加 opacity）
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
        from numpy import array,float32
        # 创建全屏四边形顶点和 UV 坐标
        vertices = array([
            -1,  1,
            -1, -1,
             1, -1,
            -1,  1,
             1, -1,
             1,  1,
        ], dtype=float32).reshape(6, 2)
        uvs = array([
            0, 1,
            0, 0,
            1, 0,
            0, 1,
            1, 0,
            1, 1
        ], dtype=float32)
        self.quad_vao = create_vao(vertices, uvs)

    def __rotate_fbo(self, src_fbo: QOpenGLFramebufferObject) -> QImage:
        """将源 FBO 的内容旋转后输出到临时 FBO，并读取为 QImage"""
        width = src_fbo.width()
        height = src_fbo.height()
        # 确保临时 FBO 尺寸匹配
        if self.temp_fbo is None or self.temp_fbo.width() != width or self.temp_fbo.height() != height:
            if self.temp_fbo:
                self.temp_fbo.release()
            self.temp_fbo = self.__create_fbo(width, height)
        # 绑定临时 FBO
        self.temp_fbo.bind()
        GL.glViewport(0, 0, width, height)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # 使用旋转着色器
        GL.glUseProgram(self.rotate_program)
        # 设置 uniform
        rot_loc = GL.glGetUniformLocation(self.rotate_program, "rotation_angle")
        GL.glUniform1f(rot_loc, self.rotation_angle)
        # op_loc = GL.glGetUniformLocation(self.rotate_program, "opacity")
        # GL.glUniform1f(op_loc, self.opacity)
        # 绑定源纹理（src_fbo 的纹理 ID）
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, src_fbo.texture())
        tex_loc = GL.glGetUniformLocation(self.rotate_program, "canvas")
        GL.glUniform1i(tex_loc, 0)

        # 绘制全屏四边形
        GL.glBindVertexArray(self.quad_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

        # 读取旋转后的图像
        image = self.temp_fbo.toImage()
        self.temp_fbo.release()
        return image

    def start(self):
        """启动渲染线程"""
        self.__running = True
        self.__thread = QThread()
        self.moveToThread(self.__thread)
        self.__thread.started.connect(self.__render_loop)
        self.__thread.finished.connect(self.__thread.deleteLater)
        self.__thread.start()
    
    def stop(self):
        """停止渲染线程"""
        self.__running = False
        self.__cond.wakeAll()
        if self.__thread.isRunning():
            self.__thread.quit()
            self.__thread.wait()
    
    def set_render_callback(self, callback):
        self.__render_callback = callback

    def request_render(self):
        """请求渲染一帧 (非阻塞)"""
        self.__mutex.lock()
        self.__request_render = True
        self.__cond.wakeOne()
        self.__mutex.unlock()
    
    def set_fps(self, fps:float):
        self.fps = fps
        self.frame_interval_ms = int(1000 / fps)
    
    def __resize_fbo(self, fbo:QOpenGLFramebufferObject, width:int, height:int):
        """调整 FBO 大小 (重新创建)"""
        if fbo.width() == width and fbo.height() == height:
            return
        # 重新创建 FBO
        new_fbo = QOpenGLFramebufferObject(
            QSize(width, height),
            QOpenGLFramebufferObject.CombinedDepthStencil
        )
        # 将旧 FBO 内容拷贝到新 FBO  (这里简化处理，直接替换)
        # 实际使用中可根据需要复制纹理
        fbo.release()
        # 注意: Python中无法直接替换对象引用, 这里返回新的FBO让调用者处理
        # 简单起见，我们不在运行时动态调整尺寸，而是在构造时确定。
        raise NotImplementedError("Dynamic resize not implemented in this example")
    
    def prepare(self):
        self.format = QSurfaceFormat()
        self.format.setMajorVersion(3)
        self.format.setMinorVersion(3)
        self.format.setProfile(QSurfaceFormat.CompatibilityProfile) #兼容模式
        self.format.setOption(QSurfaceFormat.DeprecatedFunctions) # 某些Qt版本可能需要此选项以禁用Forward Compatible
        self.format.setDepthBufferSize(0)
        self.format.setStencilBufferSize(0)
        # 创建离屏表面
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.format)
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("Failed to create offscreen surface")

    def __create_context(self):
        """创建 OpenGL 上下文"""
        context = QOpenGLContext()
        if self.share_context:
            context.setShareContext(self.share_context)
        context.setFormat(self.format)
        if not context.create():
            raise RuntimeError("Failed to create OpenGL context")
        if not context.makeCurrent(self.surface):
            raise RuntimeError("Failed to make OpenGL context current")
        # 使上下文当前生效
        context.makeCurrent(self.surface)
        return context

    def __create_fbo(self, width:int, height:int):
        """创建 FBO"""
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid FBO size: {width}x{height}")
        from PyQt5.QtGui import QOpenGLFramebufferObjectFormat
        fbo_format = QOpenGLFramebufferObjectFormat()
        fbo_format.setAttachment(QOpenGLFramebufferObject.NoAttachment)
        fbo_format.setTextureTarget(GL.GL_TEXTURE_2D) # type: ignore
        fbo_format.setInternalTextureFormat(GL.GL_RGBA8) # type: ignore
        fbo_format.setSamples(0)
        fbo = QOpenGLFramebufferObject(
            QSize(width, height),
            fbo_format
        )
        if not fbo.isValid():
            raise RuntimeError("Failed to create FBO")
        return fbo
    
    def __render_loop(self):
        """工作线程主循环"""
         # 创建 OpenGL 上下文
        context = self.__create_context()
        # 创建 FBO
        fbo = self.__create_fbo(self.width, self.height)
        self.__init_rotate_resources()
        # 主渲染循环
        while self.__running:
            self.__mutex.lock()
            if not self.__request_render:
                self.__cond.wait(self.__mutex,100)
            need_render = self.__request_render
            self.__request_render = False
            self.__mutex.unlock()

            if need_render and self.__render_callback:
                # 绑定 FBO 并执行用户绘制代码
                fbo.bind()
                GL.glViewport(0, 0, self.width, self.height)
                # 注意：用户的回调中应该包含 glClear 和模型绘制
                self.__render_callback(self.width, self.height)
                fbo.release()
                if self.__cached_image is None or self.__cached_image.size() != (self.width, self.height):
                    self.__cached_image = QImage(self.width, self.height, QImage.Format.Format_RGBA8888)
                if abs(self.rotation_angle) > 0.01:
                    image = self.__rotate_fbo(fbo)
                else:
                    image = fbo.toImage()
                self.imageReady.emit(image)
            # 控制帧率 (例如每秒 60 帧，可自行调整)
            QThread.msleep(self.frame_interval_ms)
        # 清理资源
        fbo.release()
        if self.temp_fbo:
            self.temp_fbo.release()
        if self.rotate_program:
            GL.glDeleteProgram(self.rotate_program)
        if self.quad_vao:
            GL.glDeleteVertexArrays(1, [self.quad_vao])
        context.doneCurrent()
        self.surface.destroy()
        context.deleteLater()


class Live2DCanvas(QLabel):
    LIVE2D_INITIALIZED: bool = False

    def __init__(
        self,
        model_path:str,
        model_name:str="Live2D Model",
        main_context=None,
        canvas_size:tuple[int,int]=(1200,800),
        fps: int = 30,
        enable_audio_sync: bool = False,
        enable_chunk_playback: bool = False,
        audio_sample_rate: int = 44100,
        audio_channels: int = 1,
        audio_sample_width: int = 2,
        lipSync: int = 3,
        scale: float = 1.0
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
        self.model_path : str = model_path
        self.canvas_size : tuple[int,int] = (int(canvas_size[0]),int(canvas_size[1]))
        self.enable_audio_sync: bool = enable_audio_sync

        self.enable_chunk_playback = enable_chunk_playback
        self._audio_sample_rate = audio_sample_rate
        self._audio_channels = audio_channels
        self._audio_sample_width = audio_sample_width

        self.running : bool = False
        self.model:Optional[live2d.LAppModel] = None
        self.wavehand:Optional[WavHandler] = None
        self.rms_meter:Optional[AsyncRmsMeter]=None
        self.chunk_player:Optional[AsyncChunkPlayer]=None
        self._audio_queue: Queue[str] = Queue()
        self._audio_thread: Optional[Thread] = None
        self._hit_timer: Optional[QTimer] = None
        self.__live2d_timer: Optional[QTimer] = None
        self.__renderer = None
        self.__canvas_opacity: float = 1.0
        self.__rotation_angle: float = 0.0

        # self.__buffer_pixmap = None 
        # self.__current_pixmap = None

        self.fps: int = fps
        self.sleep_intv=int(1000 / self.fps)
        self.lipSync : int = lipSync # 唇同步系数
        self.dx: float = 0.0 # x
        self.dy: float = 0.0 # y
        self.scale: float = scale # 缩放系数
        self.currentTopClickedPartId : Optional[str] = None # 当前点击的partID
        self.partIds : list[str] = [] # 所有partID
        self.radius_per_frame: float = math.pi * 0.5 / 120 # 每次移动的半径
        self.total_radius = 0 # 总旋转角度


        self.__dragging = False # 是否拖动
        self.__drag_global_pos = QPoint()
        self.__drag_window_pos = QPoint()
    
    def __on_image_ready(self, image):
        """接收到渲染图像，显示在界面上"""
        # 转换 QImage 为 QPixmap 显示
        self.setPixmap(QPixmap.fromImage(image).scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
    
    def stop(self):
        """停止渲染线程"""
        self.running = False
        if self.__renderer:
            self.__renderer.stop()
        
        if self.enable_audio_sync and self.rms_meter:
            self.rms_meter.stop()
            if self.chunk_player:
                self.chunk_player.stop()
        else:
            if self._audio_thread:
                self._audio_thread.join(timeout=1)
                self._audio_thread = None
        self.wavehand = None
        self.model = None
        live2d.dispose()
        pygame.quit()

    def closeEvent(self, event):
        """关闭窗口时停止渲染线程"""
        self.stop()
        event.accept()

    def apply_face_data(self,data):
        if self.model is None:
            return
        self.model.SetParameterValue(live2d.StandardParams.ParamEyeLOpen, data.eye_left, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamEyeROpen, data.eye_right, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamMouthOpenY, data.mouth_y, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleX, data.yaw, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleY, data.pitch, 1)
        self.model.SetParameterValue(live2d.StandardParams.ParamAngleZ, data.roll, 1)

    def sync_play(self, audio_path: str):
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        self.wavehand.Start(audio_path) # type: ignore

    # def paintEvent(self, event):
    #     if self.__current_pixmap is None:
    #         return
        
    #     if (self.__buffer_pixmap is None or 
    #         self.__buffer_pixmap.size() != self.size()):
    #         self.__buffer_pixmap = QPixmap(self.size())
    #     painter = QPainter(self)
    #     painter.setRenderHint(QPainter.Antialiasing)
    #     painter.setRenderHint(QPainter.SmoothPixmapTransform)
    #     buffer_painter = QPainter(self.__buffer_pixmap)
    #     buffer_painter.setRenderHint(QPainter.Antialiasing)
    #     buffer_painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
    #     # 绘制当前图像
    #     buffer_painter.setOpacity(self.__canvas_opacity)
        
    #     if abs(self.__rotation_angle) > 0.01:
    #         buffer_painter.save()
    #         buffer_painter.translate(self.width() / 2, self.height() / 2)
    #         buffer_painter.rotate(self._rotation_angle)
    #         rect = QRect(-self.width() // 2, -self.height() // 2, 
    #                     self.width(), self.height())
    #         buffer_painter.drawPixmap(rect, self.__current_pixmap)
    #         buffer_painter.restore()
    #     else:
    #         buffer_painter.drawPixmap(self.rect(), self.__current_pixmap)
            
    #     buffer_painter.end()
        
    #     # 将缓冲pixmap绘制到窗口
    #     painter = QPainter(self)
    #     painter.drawPixmap(0, 0, self.__buffer_pixmap)

    #拖动事件
    def mousePressEvent(self, event:QMouseEvent):
        # 左键点击时开始拖动
        if event.button() == Qt.MouseButton.LeftButton:
            self.__dragging = True
            if self.model:
                #设置随机表情
                self.model.SetParameterValue(live2d.StandardParams.ParamMouthOpenY, 0.5, 1)
            self.__drag_global_pos = event.globalPos()
            self.__drag_window_pos = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def __sync_lip_sync(self) -> None:
        while self.running and self.wavehand and self.model:
            if not pygame.mixer.music.get_busy() and not self._audio_queue.empty():
                audio_path = self._audio_queue.get()
                self.model.StartMotion("Speak", 0, live2d.MotionPriority.FORCE,lambda: self.sync_play(audio_path))
            time.sleep(0.01)

    def mouseMoveEvent(self, event:QMouseEvent):
        # if self.dragging:
        #     DraggableWidget.mouseMoveEvent(self, event)
        if self.__dragging and event.buttons() == Qt.MouseButton.LeftButton:
            if self.model:
                self.model.StartRandomMotion()
            delta = event.globalPos() - self.__drag_global_pos
            new_pos = self.__drag_window_pos + delta
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.__dragging:
            self.__dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
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
        if event.key() == Qt.Key.Key_R:
            self.model.StopAllMotions() #type: ignore
            self.model.ResetPose() #type: ignore
        elif event.key() == Qt.Key.Key_E:
            self.model.ResetExpression() #type: ignore

    def getHitFeedback(self, x: int, y: int):
        if self.model:
            t = time.time()
            hitPartIds = self.model.HitPart(x, y, False)
            if self.currentTopClickedPartId is not None:
                pidx = self.partIds.index(self.currentTopClickedPartId)
                self.model.SetPartOpacity(pidx, 1)
                # model.SetPartScreenColor(pidx, 0.0, 0.0, 0.0, 1.0)
                self.model.SetPartMultiplyColor(pidx, 1.0, 1.0, 1., 1)
            if len(hitPartIds) > 0:
                ret = hitPartIds[0]
                return ret
    
    def resizeEvent(self, event):
        self.render_width = event.size().width()
        self.render_height = event.size().height()
        # 通知渲染器调整 FBO 大小 (本示例中 OffscreenRenderer 未实现动态 resize)
        # 实际使用中需要扩展 OffscreenRenderer 支持动态 resize
        if self.model:
            self.model.Resize(self.width, self.height)
        super().resizeEvent(event)

    def __ensure_model_loaded(self):
        """确保模型已加载 (在 OpenGL 上下文中调用)"""
        if self.model is None:
            # live2d 初始化 (只需做一次)
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

    def load_model(self, model_json_path:str):
        if not os.path.exists(model_json_path):
            raise FileNotFoundError(f"模型文件不存在: {model_json_path}")
        self.model_path = model_json_path
        self.model = None   # 延迟加载
    
    def start(self):
        self.running = True
        if self.__renderer:
            self.__renderer.start()
        if self._audio_thread:
            self._audio_thread.start()
        if self.enable_audio_sync:
            if self.rms_meter:
                self.rms_meter.start()
            if self.chunk_player:
                self.chunk_player.start()
        if self.__live2d_timer:
            self.__live2d_timer.start(self.sleep_intv)
        
    def init(self) -> None:
        pygame.mixer.init(frequency=self._audio_sample_rate, size=-16, channels=self._audio_channels)
        try:
            # 初始化离屏渲染器
            w = max(1, self.width() or self.canvas_size[0])
            h = max(1, self.height() or self.canvas_size[1])
            self.__renderer = OffscreenRenderer(
                width=w,
                height=h,
                share_context=self.main_context
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
                self._audio_thread = Thread(target=self.__sync_lip_sync,daemon=True)
        except Exception as e:
            print(e)
            self.model=None
    
    def __update_wavehand(self):
        if self.wavehand and self.wavehand.Update():
            self.model.AddParameterValue(live2d.StandardParams.ParamMouthOpenY, self.wavehand.GetRms() * self.lipSync) #type: ignore
        elif self.rms_meter and self.rms_meter.update():
            self.model.AddParameterValue(live2d.StandardParams.ParamMouthOpenY, self.rms_meter.get_rms() * self.lipSync) #type: ignore

    def __draw_live2d(self, width, height):
        """绘制 Live2D 模型"""
        self.__ensure_model_loaded()
        if self.model is None:
            return
        live2d.clearBuffer()
        # 更新模型状态 (动画、物理等)
        self.model.Update()
        # 更新波形参数
        self.__update_wavehand()
        # 执行绘制
        self.model.Draw()

    def pull_audio(self,audio_path:str):
        if self.model and not self.enable_chunk_playback:
            self._audio_queue.put(audio_path)

    def push_audio_chunk(self, chunk: bytes) -> None:
        # 仅支持 PCM 16-bit chunk，用于异步响度与播放
        if self.model and self.rms_meter:
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
        # 仅支持16-bit PCM
        if sample_width != 2:
            return
        current = pygame.mixer.get_init()
        desired = (sample_rate, -16, channels)
        if current is not None :
            if current == desired:
                return
            else:
                try:
                    pygame.mixer.quit()
                    pygame.mixer.init(frequency=sample_rate, size=-16, channels=channels)
                except Exception:
                    pass        

    def set_rotation_angle(self, angle: float):
        self._rotation_angle = angle % 360.0
        if self.__renderer:
            self.__renderer.set_rotation_angle(self._rotation_angle)
            # self.__renderer.request_render()
            self.update()
    
    def set_opacity(self, opacity: float) -> None:
        self.__canvas_opacity = max(0.0, min(1.0, opacity))
        self.setWindowOpacity(self.__canvas_opacity)
        self.update()
