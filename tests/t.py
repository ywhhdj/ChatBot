

# class ImageProcessorPlugin:
#     """图片处理插件（同步）"""
    
#     def __init__(self):
#         self.name = "ImageProcessor"
#         self.health = True
    
#     def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
#         """同步执行方法"""
#         # 模拟CPU密集型操作
#         operation = task_data.get("operation", "resize")
#         time.sleep(0.5)  # 模拟处理时间
        
#         return {
#             "operation": operation,
#             "status": "completed",
#             "result": f"Processed with {operation}"
#         }
    
#     def resize(self, width: int, height: int) -> Dict[str, Any]:
#         """同步方法"""
#         time.sleep(0.3)
#         return {
#             "width": width,
#             "height": height,
#             "status": "resized"
#         }

# # 异步插件示例
# class WebFetcherPlugin:
#     """网络数据获取插件（异步）"""
    
#     def __init__(self):
#         self.name = "WebFetcher"
#         self.health = True
#         self.session = None
    
#     async def initialize(self):
#         """异步初始化"""
#         import aiohttp
#         self.session = aiohttp.ClientSession()
    
#     async def execute(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
#         """异步执行方法"""
#         url = task_data.get("url", "")
        
#         # 模拟网络延迟
#         await asyncio.sleep(0.2)
        
#         return {
#             "url": url,
#             "status": 200,
#             "data": f"Fetched from {url}"
#         }
    
#     async def fetch_data(self, url: str) -> Dict[str, Any]:
#         """异步方法"""
#         await asyncio.sleep(0.3)
#         return {
#             "url": url,
#             "data": {"example": "data"}
#         }
# # from src.manager.task import scheduler,stream_task_scheduler

# class AIDirectStreamPlugin:
#     """AI直接流式插件（无缓冲区）"""
    
#     def __init__(self, plugin_id: str):
#         self.plugin_id = plugin_id
#         self.name = "AIDirectStream"
    
#     # @stream_task_scheduler
#     async def chat_stream(self, prompt: str):
#         """
#         直接聊天流
#         每次yield直接传递给消费者
#         """
#         # 生成响应
#         response_parts = [
#             f"思考您的问题: {prompt}\n\n",
#             "让我为您详细解释...\n\n",
#             "首先，我们需要理解核心概念。\n",
#             "其次，分析相关因素。\n",
#             "最后，得出结论。\n\n"
#         ]
        
#         for i, part in enumerate(response_parts):
#             # 模拟处理时间
#             await asyncio.sleep(0.2)
            
#             # 直接yield，不经过缓冲区
#             yield part
            
#             # 模拟token处理
#             tokens = part.split()
#             for token in tokens:
#                 yield token + " "
#                 await asyncio.sleep(0.01)

#     # @stream_task_scheduler
#     async def generate_large_text(self, topic: str, paragraphs: int = 10) -> AsyncGenerator[str, None]:
#         """
#         生成大文本流
#         可以生成GB级别的文本而不会爆内存
#         """
#         # 生成段落
#         for p in range(paragraphs):
#             paragraph = f"第{p+1}段: 关于{topic}的论述。这是自动生成的文本段落。" * 50
#             paragraph += "\n\n"
            
#             # 直接yield段落
#             yield paragraph
            
#             # 模拟生成延迟
#             await asyncio.sleep(0.1)
        
#         yield f"\n✅ 生成完成，共{paragraphs}段"
    
#     # async def process_stream_with_callback(
#     #     self,
#     #     prompt: str,
#     #     callback: Callable[[str], None]
#     # ):
#     #     """
#     #     处理流式结果并实时回调
#     #     完全无缓冲区
#     #     """
#     #     stream = await scheduler.submit_stream(
#     #         self.chat_stream, prompt, name="带回调的聊天流"
#     #     )
        
#     #     # 直接处理流，不收集到内存
#     #     async for chunk in stream.consume():
#     #         callback(chunk)
        
#     #     return "处理完成"


# async def example_2_ai_direct_chat():
#     """AI直接聊天流示例"""
#     print("\n" + "=" * 60)
#     print("示例2: AI直接聊天流")
#     print("=" * 60)
    
    
#     # 创建插件
#     ai_plugin = AIDirectStreamPlugin("ai_001")
    
#     print("\n🤖 AI直接聊天（无缓冲区）...")
    
#     # 提交流
#     stream = await ai_plugin.chat_stream("什么是人工智能？")
    
#     # 实时显示
#     print("AI回复: ", end="", flush=True)
#     count=1
#     async for chunk in stream.data:
#         print(chunk, end="", flush=True)
    
#     print("\n\n📊 流统计:")
#     stream_stats = stream.get_stats()
#     print(f"   持续时间: {stream_stats['duration']:.2f}s")
    
#     # 大文本生成
#     print("\n📄 大文本生成测试...")
#     stream=await ai_plugin.generate_large_text("人工智能")
#     async for chunk in stream.data:
#         print(chunk, end="", flush=True)
#     print("\n\n📊 流统计:")
#     stream_stats = stream.get_stats()
#     print(f"   持续时间: {stream_stats['duration']:.2f}s")
    
#     # 使用装饰器
#     @stream_task_scheduler
#     async def generate_huge_text():
#         """生成大文本"""
#         for i in range(1000):  # 1000个段落
#             yield f"段落{i}: 这是自动生成的文本内容。\n"
#             if i % 100 == 0:
#                 print(f"   已生成 {i} 段...")
    
#     huge_stream = await generate_huge_text()
    
#     # 只消费前10个段落
#     count = 0
#     async for paragraph in huge_stream.data:
#         count += 1
#         if count >= 10:
#             # 提前停止
#             huge_stream.send_control("stop")
#             break
    
#     print(f"   消费了 {count} 个段落")

# def test_load_config():
#     from src_py._config import load_config
#     config = load_config()
#     print(config.log)
#     assert config is not None

# test_load_config()

# if __name__ == "__main__":
#     from src.services.live2d.views import Live2DView
#     from src.utils.util import normpath
#     from src.constants import RESOURCES_DIRECTORY
#     from PyQt5.QtWidgets import QApplication
#     import sys
#     app=QApplication(sys.argv)
#     model_path=normpath(RESOURCES_DIRECTORY, "models", "live2d/肥牛/hiyori_pro_mic.model3.json")
#     live2d = Live2DView(
#         model_path=model_path,
#         is_face_detected=False,
#         canvas_size=(1200,800)
#     )
#     live2d.init()
#     live2d.start()
#     # win=test_dialogue_component()
#     sys.exit(app.exec_())
    # user=[
    #     "你好",
    #     "你好",
    # ]
    # from src.pipeline.adapters.llm import LLMBaseAdapter
    # from src.App import App
    # app=App()
    # app.run()
    # app.pipeline_manager.llm._intialize_provider()

    # 测试 scheduler 是否是单例
    # is_same = scheduler is TaskSchedular()
    # print(is_same)
    
#     # scheduler.init()
#     # scheduler.start()
#     # asyncio.run(example_2_ai_direct_chat())
# import sys
# from PyQt5.QtWidgets import (
#     QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit
# )
# from PyQt5.QtCore import Qt
# from PyQt5.QtGui import QFont, QPalette, QColor

# # 导入之前找到的可拖动组件基类
# from src.ui.base import DraggableWidget


# class CustomDraggableWidget(DraggableWidget):
#     """
#     自定义可拖动组件，具有垂直布局、头部按钮组和透明棕灰色样式
#     """
#     def __init__(self, title="可拖动组件", text="这里是组件主体显示的文本内容"):
#         super().__init__()
        
#         # 设置窗口基本属性
#         # self.setWindowFlags(Qt.WindowFlags.FramelessWindowHint | Qt.WindowFlags.WindowStaysOnTopHint)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
#         # 创建主布局
#         main_layout = QVBoxLayout()
#         main_layout.setContentsMargins(10, 10, 10, 10)
#         main_layout.setSpacing(8)
        
#         # 创建头部区域
#         header_widget = QWidget()
#         header_widget.setObjectName("header")  # 设置对象名用于CSS选择器
#         header_layout = QHBoxLayout(header_widget)
#         header_layout.setContentsMargins(0, 0, 0, 0)
#         header_layout.setSpacing(5)
        
#         # 头部标题标签
#         self.title_label = QLabel(title)
#         self.title_label.setStyleSheet("""
#             color: white;
#             font-size: 14px;
#             font-weight: bold;
#         """)
        
#         # 创建按钮组容器
#         button_container = QWidget()
#         button_layout = QHBoxLayout(button_container)
#         button_layout.setContentsMargins(0, 0, 0, 0)
#         button_layout.setSpacing(5)
        
#         # 添加按钮到按钮组
#         self.minimize_btn = QPushButton("−")
#         self.minimize_btn.setFixedSize(25, 25)
#         self.minimize_btn.setStyleSheet("""
#             QPushButton {
#                 background-color: rgba(255, 255, 255, 0.2);
#                 border: none;
#                 border-radius: 12px;
#                 color: white;
#                 font-weight: bold;
#                 font-size: 16px;
#             }
#             QPushButton:hover {
#                 background-color: rgba(255, 255, 255, 0.3);
#             }
#         """)
        
#         self.close_btn = QPushButton("×")
#         self.close_btn.setFixedSize(25, 25)
#         self.close_btn.setStyleSheet("""
#             QPushButton {
#                 background-color: rgba(255, 255, 255, 0.2);
#                 border: none;
#                 border-radius: 12px;
#                 color: white;
#                 font-weight: bold;
#                 font-size: 14px;
#             }
#             QPushButton:hover {
#                 background-color: rgba(255, 100, 100, 0.5);
#             }
#         """)
        
#         # 将按钮添加到按钮容器
#         button_layout.addWidget(self.minimize_btn)
#         button_layout.addWidget(self.close_btn)
        
#         # 将标题和按钮组添加到头部布局
#         header_layout.addWidget(self.title_label)
#         header_layout.addStretch()  # 添加弹性空间使按钮组靠右
#         header_layout.addWidget(button_container)
        
#         # 创建身体区域
#         body_widget = QWidget()
#         body_widget.setObjectName("body")
#         body_layout = QVBoxLayout(body_widget)
#         body_layout.setContentsMargins(10, 10, 10, 10)
        
#         # 文本显示区域
#         self.text_display = QTextEdit()
#         self.text_display.setText(text)
#         self.text_display.setReadOnly(True)
#         self.text_display.setStyleSheet("""
#             QTextEdit {
#                 background-color: rgba(96, 91, 91, 0.3);  /* 透明棕灰色 */
#                 border: 1px solid rgba(255, 255, 255, 0.2);
#                 border-radius: 8px;
#                 color: white;
#                 font-size: 12px;
#             }
#         """)
        
#         body_layout.addWidget(self.text_display)
        
#         # 将头部和身体添加到主布局
#         main_layout.addWidget(header_widget)
#         main_layout.addWidget(body_widget)
        
#         # 应用整体样式
#         self.setStyleSheet("""
#             QWidget#header {
#                 background-color: rgba(96, 91, 91, 0.5);  /* 透明棕灰色 */
#                 border-top-left-radius: 10px;
#                 border-top-right-radius: 10px;
#                 border-bottom: 1px solid rgba(255, 255, 255, 0.2);
#             }
#             QWidget#body {
#                 background-color: rgba(96, 91, 91, 0.3);  /* 透明棕灰色 */
#                 border-bottom-left-radius: 10px;
#                 border-bottom-right-radius: 10px;
#             }
#             CustomDraggableWidget {
#                 background-color: rgba(96, 91, 91, 0.3);  /* 透明棕灰色 */
#                 border-radius: 10px;
#                 border: 1px solid rgba(255, 255, 255, 0.2);
#             }
#         """)
        
#         # 设置主布局
#         self.setLayout(main_layout)
        
#         # 连接按钮事件
#         self.minimize_btn.clicked.connect(self.showMinimized)
#         # self.close_btn.clicked.connect(self.close)
        
#         # 设置初始大小
#         self.resize(300, 200)


# def test_custom_draggable_widget():
#     """
#     测试自定义可拖动组件
#     """

    
#     widget = CustomDraggableWidget(
#         title="测试可拖动组件",
#         text="这是一个具有垂直布局、头部按钮组和透明棕灰色样式的可拖动组件。\n您可以拖动头部移动整个组件。"
#     )
#     widget.show()
    
#     return widget


# # 如果直接运行此脚本，则启动测试
# if __name__ == "__main__":
#     # ... existing code ...

#     # 启动测试可拖动组件（如果需要）
#     app = QApplication.instance()
#     if app is None:
#         app = QApplication(sys.argv)
#     widget = test_custom_draggable_widget()
#     sys.exit(app.exec_())
    
#     # scheduler.init()
#     # scheduler.start()
#     # asyncio.run(example_2_ai_direct_chat())

# import sys
# import random
# import numpy as np
# from PyQt5.QtWidgets import *
# from PyQt5.QtCore import *
# from PyQt5.QtGui import *
# from PyQt5.QtOpenGL import *
# from OpenGL.GL import *
# from OpenGL.GLU import *

# class DraggableWidget(QWidget):
#     """可拖动部件的基类"""
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self._is_dragging = False
#         self._drag_offset = QPoint(0, 0)
#         self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint) #type: ignore
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
#     def mousePressEvent(self, event):
#         if event.button() == Qt.MouseButton.LeftButton:
#             self._is_dragging = True
#             self._drag_offset = event.pos()
#             self.setCursor(Qt.CursorShape.ClosedHandCursor)
            
#     def mouseMoveEvent(self, event):
#         if self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
#             new_pos = self.mapToParent(event.pos() - self._drag_offset)
#             self.move(new_pos)
            
#     def mouseReleaseEvent(self, event):
#         if event.button() == Qt.MouseButton.LeftButton:
#             self._is_dragging = False
#             self.setCursor(Qt.CursorShape.ArrowCursor)

# class DesktopPetGLWidget(DraggableWidget):
#     """可拖动的OpenGL桌宠"""
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setGeometry(0, 0, 300, 400)
        
#         # 创建OpenGL窗口
#         # self.gl_widget = DesktopPetOpenGLWidget(self)
        
#         # 设置透明背景
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.addWidget(self.gl_widget)
        
#         # 位置在屏幕右边
#         screen_geometry = QApplication.primaryScreen().geometry()
#         x = screen_geometry.width() - self.width() - 50
#         y = 100
#         self.move(x, y)
        
#         # 鼠标悬停效果
#         self.hover_effect = False
#         self.enterEvent = self.on_enter
#         self.leaveEvent = self.on_leave
        
#     def on_enter(self, event):
#         self.hover_effect = True
#         self.setCursor(Qt.OpenHandCursor)
        
#     def on_leave(self, event):
#         self.hover_effect = False
#         self.setCursor(Qt.ArrowCursor)
        
#     def paintEvent(self, event):
#         # 绘制半透明边框
#         if self.hover_effect:
#             painter = QPainter(self)
#             painter.setRenderHint(QPainter.Antialiasing)
#             painter.setBrush(QBrush(QColor(100, 100, 255, 30)))
#             painter.setPen(QPen(QColor(100, 100, 255, 100), 3))
#             painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

# class DesktopPetOpenGLWidget(QOpenGLWidget):
#     """OpenGL渲染的桌宠"""
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setMinimumSize(200, 300)
        
#         # 动画参数
#         self.angle = 0
#         self.wave_offset = 0
#         self.blink_timer = 0
#         self.eye_open = True
        
#         # 定时器
#         self.animation_timer = QTimer(self)
#         self.animation_timer.timeout.connect(self.update_animation)
#         self.animation_timer.start(30)  # 30fps
        
#     def initializeGL(self):
#         """初始化OpenGL"""
#         glClearColor(0.0, 0.0, 0.0, 0.0)  # 透明背景
#         glEnable(GL_DEPTH_TEST)
#         glEnable(GL_BLEND)
#         glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
#     def resizeGL(self, w, h):
#         """调整大小"""
#         glViewport(0, 0, w, h)
#         glMatrixMode(GL_PROJECTION)
#         glLoadIdentity()
#         gluPerspective(45, w/h, 0.1, 100.0)
#         glMatrixMode(GL_MODELVIEW)
        
#     def paintGL(self):
#         """渲染"""
#         glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
#         glLoadIdentity()
#         gluLookAt(0, 0, 5, 0, 0, 0, 0, 1, 0)
        
#         # 简单的3D桌宠模型
#         self.draw_pet()
        
#     def draw_pet(self):
#         """绘制桌宠"""
#         glPushMatrix()
        
#         # 轻微浮动动画
#         glTranslatef(0, np.sin(self.wave_offset) * 0.1, 0)
        
#         # 旋转动画
#         glRotatef(self.angle, 0, 1, 0)
        
#         # 绘制身体（立方体）
#         glColor4f(0.2, 0.7, 0.9, 0.8)
#         glutSolidCube(1.0)
        
#         # 绘制头部（球体）
#         glPushMatrix()
#         glTranslatef(0, 0.8, 0)
#         glColor4f(1.0, 0.8, 0.6, 0.9)
#         glutSolidSphere(0.4, 20, 20)
        
#         # 绘制眼睛
#         if self.eye_open:
#             glColor4f(0, 0, 0, 1)
#             glPushMatrix()
#             glTranslatef(-0.15, 0.1, 0.3)
#             glutSolidSphere(0.08, 10, 10)
#             glPopMatrix()
            
#             glPushMatrix()
#             glTranslatef(0.15, 0.1, 0.3)
#             glutSolidSphere(0.08, 10, 10)
#             glPopMatrix()
        
#         glPopMatrix()
        
#         glPopMatrix()
        
#     def update_animation(self):
#         """更新动画参数"""
#         self.angle = (self.angle + 1) % 360
#         self.wave_offset += 0.1
        
#         # 眨眼动画
#         self.blink_timer += 1
#         if self.blink_timer > 100:  # 每100帧眨眼一次
#             self.eye_open = not self.eye_open
#             if not self.eye_open:
#                 self.blink_timer = 0
#             else:
#                 self.blink_timer = 80
                
#         self.update()

# class TypewriterTextBox(DraggableWidget):
#     """可拖动的流式打字机文本框"""
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setup_ui()
#         self.windowFlags(Qt.WindowType.Window | Qt.WindowFlags.WindowTitleHint | Qt.WindowFlags.CustomizeWindowHint)
#         # 位置在屏幕中间底部
#         screen_geometry = QApplication.primaryScreen().geometry()
#         x = (screen_geometry.width() - self.width()) // 2
#         y = screen_geometry.height() - self.height() - 100
#         self.move(x, y)
#         self.setStyleSheet("""
#             QWidget {
#                 background-color: rgba(20, 20, 30, 200);
#                 border-radius: 12px;
#                 padding: 10px;
#             }
#         """)
        
#     def setup_ui(self):
#         """设置UI"""
#         self.setFixedSize(500, 200)
        
#         # 创建主布局
#         main_layout = QVBoxLayout(self)
#         main_layout.setContentsMargins(15, 15, 15, 15)
#         main_layout.setSpacing(10)
        
#         # 标题栏
#         title_bar = QHBoxLayout()
#         self.title_label = QLabel("AI助手")
#         self.title_label.setStyleSheet("""
#             QLabel {
#                 color: white;
#                 font-size: 16px;
#                 font-weight: bold;
#                 padding: 5px;
#             }
#         """)
        
#         close_btn = QPushButton("×")
#         close_btn.setFixedSize(20, 20)
#         close_btn.setStyleSheet("""
#             QPushButton {
#                 color: white;
#                 background-color: transparent;
#                 border: none;
#                 font-size: 20px;
#                 font-weight: bold;
#             }
#             QPushButton:hover {
#                 color: #ff6666;
#             }
#         """)
#         # close_btn.clicked.connect(self.close)
        
#         title_bar.addWidget(self.title_label)
#         title_bar.addStretch()
#         title_bar.addWidget(close_btn)
        
#         # 文本显示区域
#         self.text_display = QTextEdit()
#         self.text_display.setReadOnly(True)
#         self.text_display.setStyleSheet("""
#             QTextEdit {
#                 background-color: rgba(20, 20, 30, 200);
#                 color: #e0e0ff;
#                 border: 2px solid #4a4a6a;
#                 border-radius: 8px;
#                 padding: 10px;
#                 font-size: 14px;
#                 font-family: 'Microsoft YaHei', Arial;
#                 line-height: 1.5;
#             }
#         """)
#         self.text_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
#         # 输入区域
#         input_layout = QHBoxLayout()
#         self.input_box = QLineEdit()
#         self.input_box.setPlaceholderText("输入消息...")
#         self.input_box.setStyleSheet("""
#             QLineEdit {
#                 background-color: rgba(30, 30, 40, 200);
#                 color: white;
#                 border: 1px solid #4a4a6a;
#                 border-radius: 5px;
#                 padding: 8px;
#                 font-size: 13px;
#             }
#         """)
        
#         self.send_btn = QPushButton("发送")
#         self.send_btn.setStyleSheet("""
#             QPushButton {
#                 background-color: #5a5a8a;
#                 color: white;
#                 border: none;
#                 border-radius: 5px;
#                 padding: 8px 20px;
#                 font-size: 13px;
#             }
#             QPushButton:hover {
#                 background-color: #6a6a9a;
#             }
#             QPushButton:pressed {
#                 background-color: #4a4a7a;
#             }
#         """)
        
#         input_layout.addWidget(self.input_box)
#         input_layout.addWidget(self.send_btn)
        
#         # 添加到主布局
#         main_layout.addLayout(title_bar)
#         main_layout.addWidget(self.text_display)
#         main_layout.addLayout(input_layout)
        
#         # 定时器用于流式显示
#         self.stream_timer = QTimer()
#         self.stream_timer.timeout.connect(self.stream_next_char)
#         self.full_text = ""
#         self.current_text = ""
#         self.char_index = 0
#         self.is_streaming = False
        
#         # 连接信号
#         self.send_btn.clicked.connect(self.on_send)
#         self.input_box.returnPressed.connect(self.on_send)
        
#     def stream_text(self, text, speed=30):
#         """开始流式显示文本"""
#         if not self.is_streaming:
#             self.full_text = text
#             self.current_text = ""
#             self.char_index = 0
#             self.is_streaming = True
#             self.stream_timer.start(speed)  # 控制速度
            
#     def stream_next_char(self):
#         """流式显示下一个字符"""
#         if self.char_index < len(self.full_text):
#             self.current_text += self.full_text[self.char_index]
#             self.text_display.setPlainText(self.current_text)
            
#             # 自动滚动到底部
#             scrollbar = self.text_display.verticalScrollBar()
#             scrollbar.setValue(scrollbar.maximum())
            
#             self.char_index += 1
#         else:
#             self.stream_timer.stop()
#             self.is_streaming = False
#             self.text_display.append("\n--- 消息结束 ---\n")
            
#     def on_send(self):
#         """发送消息"""
#         text = self.input_box.text().strip()
#         if text:
#             # 显示用户消息
#             self.text_display.append(f"你: {text}\n")
#             self.input_box.clear()
            
#             # 模拟AI回复
#             reply = self.generate_reply(text)
            
#             # 添加延迟后显示AI回复
#             QTimer.singleShot(500, lambda: self.stream_ai_reply(reply))
            
#     def generate_reply(self, user_input):
#         """生成模拟回复"""
#         responses = [
#             f"我理解您说的'{user_input}'，这是一个有趣的话题。让我想想...",
#             f"关于'{user_input}'，我的看法是这取决于具体的情况。",
#             f"感谢您的提问！'{user_input}'确实值得深入探讨。",
#             f"您提到'{user_input}'让我想起了一些相关的知识...",
#             f"对于'{user_input}'，我认为我们可以从多个角度来分析这个问题。"
#         ]
#         return random.choice(responses)
        
#     def stream_ai_reply(self, reply):
#         """流式显示AI回复"""
#         self.text_display.append("AI助手: ")
#         self.stream_text(reply)
        
#     def paintEvent(self, event):
#         """绘制半透明背景"""
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.Antialiasing)
        
#         # 绘制带圆角的半透明背景
#         painter.setBrush(QBrush(QColor(30, 30, 50, 220)))
#         painter.setPen(QPen(QColor(100, 100, 150, 100), 2))
#         painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        
#         # 绘制阴影效果
#         painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
#         painter.drawRoundedRect(3, 3, self.width(), self.height(), 10, 10)

# class DesktopPetApp(QWidget):
#     """主应用程序"""
#     def __init__(self):
#         super().__init__()
#         self.init_ui()
        
#     def init_ui(self):
#         """初始化UI"""
#         # 设置全屏无边框窗口
#         self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint) #type: ignore
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
#         self.showFullScreen()
        
#         # # 创建桌面宠物
#         # self.pet_widget = DesktopPetGLWidget(self)
        
#         # 创建打字机文本框
#         self.text_widget = TypewriterTextBox(self)
        
#         # 设置退出快捷键
#         # QShortcut(QKeySequence("Escape"), self).activated.connect(self.close)
        
#         # 显示测试文本
#         QTimer.singleShot(1000, lambda: self.text_widget.stream_text(
