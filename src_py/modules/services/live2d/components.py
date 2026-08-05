from pathlib import Path
from typing import Callable, Optional, Union

from PyQt5.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QWidget,
)

from ...utils.util import create_daemon_thread
# from ...ui.layout import RowLayout, ColumnLayout
# from ...ui.base import DraggableWidget

# class EnhancedDialogueComponent:
#     __style={
#         "Button":{
#             "default":{
#                 ("border-radius","8px"),
#                 ("border","none"),
#                 ("background","rgba(255, 255, 255, 0.20)"),
#                 ("color","rgba(255, 255, 255, 0.88)"),
#                 ("font-size","12px")
#             },
#             "pressed":{
#                 ("background","rgba(255, 255, 255, 0.45)"),
#             },
#             "hover":{
#                 ("border","1px solid rgba(255, 255, 255, 0.30)"),
#                 ("color","blue"),
#                 ("background","rgba(255, 255, 255, 0.30)"),
#             },
#         },
#         "Label":[
#             ("font-size","12px"),
#             ("color","#E0E0E0"),
#             ("padding","10px"),
#         ],
#     }

#     def __init__(
#         self,
#         instant: bool = False,
#         text_speed: int = 20,
#         max_width: int = 1000,
#     ) -> None:
#         super().__init__()
#         self.setObjectName("dialogue_component")
#         self.setMaximumWidth(max_width)
#         self.setMinimumWidth(320)
#         self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

#         self.typing_timer = QTimer(self)
#         self.typing_timer.timeout.connect(self.__type_next_char)

#         self.dialogue_queue: Queue[str] = Queue()
#         self.current_dialogue = ""
#         self.displayed_text = ""
#         self.char_index = 0
#         self.batch_size = 3
#         self.is_typing = False
#         self.__draggable = True

#         self.instant = instant
#         self.set_typing_speed(text_speed)
#         self.__create_ui()
#         # self._base_stylesheet = """
#         #     QWidget#dialogue_component {
#         #         border-radius: 12px;
#         #         background-color: rgba(0, 0, 0, 0.1);
#         #     }
#         #     QLabel#dialogue_title {
#         #         color: rgba(255, 255, 255, 0.88);
#         #         font-size: 12px;
#         #     }
#         #     QLabel#text_label {
#         #         color: #E0E0E0;
#         #         padding: 10px;
#         #     }
#         #     QPushButton {
#         #         background-color: rgba(255, 255, 255, 0.20);
#         #         border: none
#         #         border-radius: 8px;
#         #         padding: 4px 10px;
#         #         color: white;
#         #         font-size: 12px;
#         #     }
#         #     QPushButton:hover {
#         #         background-color: rgba(255, 255, 255, 0.30);
#         #     }
#         #     QPushButton:pressed {
#         #         background-color: rgba(255, 255, 255, 0.45);
#         #     }
#         # """
#         #构造样式表
#         style=self.__create_stylesheet(self.__style)+"""
#             QWidget#dialogue_component {
#                 border-radius: 12px;
#                 background-color: rgba(30, 30, 30, 0.9);
#             }
#             QLabel#dialogue_title {
#                 color: rgba(255, 255, 255, 0.88);
#                 font-size: 12px;
#             }
#             QLabel#text_label {
#                 color: #E0E0E0;
#                 padding: 10px;
#             }
#         """

#         self.setStyleSheet(style)
#         self.__update_typing_interval()
    
#     #构造样式表
#     def __create_stylesheet(self,stylesheet:dict):
#         """构造样式表"""
#         style=""
#         for widget_type, styles in stylesheet.items():
#             widget_type=widget_type[0].upper()+widget_type[1:]
#             if isinstance(styles, dict):
#                 for (key_, values) in styles.items():
#                     for property_,value in values:
#                         if key_=="default":
#                             style +=f"""
#                                 Q{widget_type} {{
#                                     {property_}: {value};
#                                 }}
#                             """
#                         else:
#                             style +=f"""
#                                 Q{widget_type}:{key_} {{
#                                     {property_}: {value};
#                                 }}
#                         """
#             elif isinstance(styles, list):
#                 for (property_, value) in styles:
#                     style +=f"""
#                         Q{widget_type} {{
#                             {property_}: {value};
#                         }}
#                     """
#         return style
    
#     def __create_ui(self):
#         """创建可拖拽的标题栏"""
#         self.main_layout = ColumnLayout(parent=self,contents_margins=(10, 10, 10, 10), spacing=8)
#         self.header = QWidget(self)
#         self.header.setObjectName("dialogue_header")
#         self.header.setFixedHeight(30)
#         self.header.setStyleSheet("""
#             QWidget#dialogue_header {
#                 background-color: rgba(0, 0, 0, 0.3);
#                 border-top-left-radius: 12px;
#                 border-top-right-radius: 12px;
#             }
#         """)
        
#         # 标题标签
#         self.title_label = QLabel("对话", self.header)
#         self.title_label.setObjectName("dialogue_title")
#         self.title_label.setStyleSheet("""
#             QLabel#dialogue_title {
#                 color: rgba(255, 255, 255, 0.88);
#                 font-size: 12px;
#                 padding-left: 10px;
#             }
#         """)
        
#         # 按钮容器
#         self.button_container = QWidget(self.header)
#         self.button_container.setObjectName("button_container")
#         buttons_params = {
#             "skip": {"text": "跳过", "callback": self.skip_typing},
#             "clear": {"text": "清空", "callback": self.clear},
#             "close": {"text": "×", "callback": self.hide},
#         }
#         for button_name, button_params in buttons_params.items():
#             button = QPushButton(button_params["text"], self.button_container)
#             button.clicked.connect(button_params["callback"])
#             if not hasattr(self, f"{button_name}_button"):
#                 setattr(self, f"{button_name}_button", button)
#             if button_name == "×" and not hasattr(self, f"{button_name}_button"):
#                 self.close_button.setFixedSize(20, 20)
        
#         # 布局
#         header_layout = RowLayout(self.header, contents_margins=(0, 0, 0, 0), spacing=5)
#         button_layout = RowLayout(self.button_container, spacing=5)
#         for button_name, button_params in buttons_params.items():
#             button_layout.addWidget(getattr(self, f"{button_name}_button"))
#         button_layout.addStretch()
        
#         header_layout.addWidget(self.title_label)
#         header_layout.addStretch()
#         header_layout.addWidget(self.button_container)
#         self.text_label = QLabel(self)
#         self.text_label.setObjectName("text_label")
#         self.text_label.setWordWrap(True)
#         self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         self.main_layout.insertWidget(0, self.header)
#         self.main_layout.insertWidget(1, self.text_label)
#         self.resize(1000, 200)
    
#     def set_text_color(self, color: str):
#         """设置文本颜色"""
#         self.text_label.setStyleSheet(f"""
#             QLabel#text_label {{
#                 color: {color};
#                 padding: 10px;
#                 font-size: 14px;
#                 font-family: 'Microsoft YaHei', sans-serif;
#             }}
#         """)
        
#     def set_background_color(self, color: str, opacity: float = 0.8):
#         """设置背景颜色和透明度"""
#         r, g, b = self.__parse_color(color)
#         self.setStyleSheet(f"""
#             QWidget#dialogue_component {{
#                 border-radius: 12px;
#                 background-color: rgba({r}, {g}, {b}, {opacity * 255});
#             }}
#             QLabel#dialogue_title {{
#                 color: rgba(255, 255, 255, 0.88);
#                 font-size: 12px;
#             }}
#             QLabel#text_label {{
#                 color: #E0E0E0;
#                 padding: 10px;
#             }}
#             QPushButton {{
#                 background-color: rgba(255, 255, 255, 0.20);
#                 border: none;
#                 border-radius: 8px;
#                 padding: 4px 10px;
#                 color: white;
#                 font-size: 12px;
#             }}
#             QPushButton:hover {{
#                 border: 1px solid rgba(255, 255, 255, 0.30);
#                 border-radius: 8px;
#                 color:blue;
#                 background-color: rgba(255, 255, 255, 0.30);
#             }}
#             QPushButton:pressed {{
#                 background-color: rgba(255, 255, 255, 0.45);
#             }}
#         """)
        
#     def __parse_color(self, color: str):
#         """解析颜色字符串"""
#         if color.startswith('#'):
#             color = color.lstrip('#')
#             return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
#         elif color.startswith('rgb'):
#             import re
#             match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color)
#             if match:
#                 return tuple(int(match.group(i)) for i in range(1, 4))
#         return (0, 0, 0)  # 默认黑色
        

#     def set_up_ui(self) -> None:
#         main_layout = ColumnLayout(parent=self,contents_margins=(10, 10, 10, 10), spacing=8)
#         header_widget = QWidget()
#         header_widget.setObjectName("header")  # 设置对象名用于CSS选择器
#         header_layout = RowLayout(parent=header_widget,contents_margins=(0, 0, 0, 0),spacing=5)
#         # self.header = QWidget(self)
#         # self.title_label = QLabel("Dialogue", self.header)
#         # self.title_label.setObjectName("dialogue_title")
#         # self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
#         buttons_params={
#             "skip":self.skip_typing,
#             "clear":self.clear
#         }
#         # 创建按钮组容器
#         button_container = QWidget()
#         # button_layout = RowLayout(button_container,spacing=5)
#         # self.button_container = QWidget(self.header)
#         # self.button_container.setObjectName("button_container")
#         buttons:list[QPushButton]=[]
#         for button_name, button_func in buttons_params.items():
#             button = QPushButton(button_name)
#             if button_func:
#                 button.clicked.connect(button_func)
#             buttons.append(button)
#         RowLayout(
#             parent=button_container,
#             contents_margins=None,
#             spacing=5,
#             *buttons
#         )
#         header_layout.addStretch()  # 添加弹性空间使按钮组靠右
#         header_layout.addWidget(button_container)
#         # self.header_layout = RowLayout(self.header,(0, 0, 0, 0),6,self.button_container)
#         # self.header_layout.add_widgets(self.title_label,self.button_container)

#         self.text_label = QLabel(self)
#         self.text_label.setObjectName("text_label")
#         self.text_label.setWordWrap(True)
#         self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
#         main_layout.addWidget(header_widget)
#         main_layout.addWidget(self.text_label)
#         self.resize(300, 200)
#         # root_layout=ColumnLayout(self,(0, 0, 0, 0),8,self.header,self.text_label)

#         # self.header.setVisible(False)

#     def closeEvent(self, event) -> None:
#         self.clear()
#         super().closeEvent(event)

#     def __update_typing_interval(self) -> None:
#         self.typing_timer.setInterval(max(1, int(1000 / self.chars_per_second)))

#     def __type_next_char(self) -> None:
#         if self.char_index >= len(self.current_dialogue):
#             self.__finish_typing()
#             return
#         end_index = min(self.char_index + self.batch_size, len(self.current_dialogue))
#         chunk = self.current_dialogue[self.char_index:end_index]
#         self.displayed_text += chunk
#         self.char_index = end_index
#         self.text_label.setText(self.displayed_text)

#     def __finish_typing(self) -> None:
#         self.typing_timer.stop()
#         self.is_typing = False
#         if not self.dialogue_queue.empty():
#             self.display_text(self.dialogue_queue.get())

#     def display_text(self, text: str, instant: bool = False) -> None:
#         self.instant = instant
#         if self.instant:
#             self.current_dialogue = text
#             self.displayed_text = text
#             self.char_index = len(text)
#             self.is_typing = False
#             self.typing_timer.stop()
#             self.text_label.setText(text)
#             return

#         if self.is_typing:
#             self.dialogue_queue.put(text)
#             return

#         self.current_dialogue = text
#         self.displayed_text = ""
#         self.char_index = 0
#         self.is_typing = True
#         self.typing_timer.start()
#         self.__type_next_char()

#     def skip_typing(self) -> None:
#         if not self.is_typing:
#             return
#         self.displayed_text = self.current_dialogue
#         self.text_label.setText(self.displayed_text)
#         self.__finish_typing()

#     def clear(self) -> None:
#         self.typing_timer.stop()
#         self.is_typing = False
#         self.current_dialogue = ""
#         self.displayed_text = ""
#         self.char_index = 0
#         while not self.dialogue_queue.empty():
#             self.dialogue_queue.get_nowait()
#         self.text_label.setText("")

#     def set_typing_speed(self, speed: int) -> None:
#         self.chars_per_second = max(1, min(100, speed))
#         self.__update_typing_interval()

class FaceTrackerComponent:
    from ...pipeline.adapters.landmarker.face import ResultFaceData
    def __init__(self,
            model_path: Optional[Union[str, Path]]=None,
            process_callback: Optional[Callable[[ResultFaceData], None]]=None,
            mirror: bool = False,
            face_source: Union[int, str] = 0,
            face_fps: int = 30,
            enabled: bool = False
        ):
        self.model_path = model_path
        self.__source = face_source
        self.__fps = face_fps
        self.__enabled = enabled
        self.__process_callback = process_callback
        self.__mirror = mirror
        self.__thread= None
        self.__timer: Optional[QTimer] = None
        self.__face_tracker= None

    def init(self):
        if not self.__enabled:
            return
        if not self.model_path or not self.__process_callback:
            raise ValueError("FaceTrackerTask is not initialized")
        if self.__face_tracker:
            return
        from ...pipeline.adapters.landmarker.face import FaceTracker
        self.__face_tracker = FaceTracker(
            str(self.model_path),
            source=self.__source,
            mirror=self.__mirror,
            fps=self.__fps,
        )
        self.__face_tracker.init()
        if self.__timer is None:
            self.__timer = QTimer()
            self.__timer.timeout.connect(self.__poll_face_data)
    
    def __poll_face_data(self) -> None:
        if not self.__face_tracker:
            return
        data = self.__face_tracker.poll_result()
        if self.__process_callback and data:
            self.__process_callback(data)

    def set_fps(self, fps: int) -> None:
        self.__fps = fps
        if self.__timer is not None:
            self.__timer.setInterval(int(1000 / max(1, self.__fps)))
    
    def start(self) -> None:
        if not self.__enabled:
            return
        if self.__face_tracker is None:
            raise ValueError("FaceTrackerTask is not initialized")
        self.__thread = create_daemon_thread(self.__face_tracker.start,name="fackTracker")
        self.__thread.start()
        if self.__timer is None:
            return
        self.__timer.start(int(1000 / max(1, self.__fps)))
    
    def set_model_path(self, model_path: Union[str, Path]) -> None:
        self.model_path = model_path

    def set_source(self, source: Union[int, str]) -> None:
        self.__source = source
        if self.__face_tracker:
            self.__face_tracker.set_source(source)

    def set_enabled(self, enabled: bool) -> None:
        self.__enabled = enabled
        if self.__enabled:
            self.start()
        else:
            self.stop()
    def set_mirror(self, mirror: bool) -> None:
        self.__mirror = mirror
        if self.__face_tracker:
            self.__face_tracker.set_mirror(mirror)
    
    def stop(self) -> None:
        if self.__face_tracker:
            self.__face_tracker.stop()
        if self.__thread is not None:
            self.__thread.join(timeout=1)
            self.__thread = None
        if self.__timer is not None:
            self.__timer.stop()

    def close(self) -> None:
        self.stop()
        if self.__face_tracker:
            self.__face_tracker.close()
        self.__face_tracker = None

    def set_process_callback(self, process_callback: Callable[[ResultFaceData], None]) -> None:
        self.__process_callback = process_callback
