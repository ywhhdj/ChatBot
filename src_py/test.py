import asyncio
import sys
import os
import time
import httpx
import os
import sys

from modules.context.audio import AudioContext
from src_py.modules.core.native import decorator



async def test_connection():
    """测试QQ机器人连接"""
    from modules.services.qqbot.client import QQBotClient
    from modules.config import get_config
    config=get_config()
    bot = QQBotClient(
        appid=config.qqbot.appid,
        secret=config.qqbot.secret
    )
    print("测试WebSocket连接...")
    try:
        await bot.start()
        print("✅ WebSocket连接成功")
        try:
            # info = await bot.get_self_info()
            # print(f"✅ 机器人信息: {info}")
            pass
        except Exception as e:
            print(f"❌ 获取信息失败: {e}")
        # 等待一段时间观察事件
        print("等待事件中... (5秒)")
        while True:
            await asyncio.sleep(1)    
    except Exception as e:
        print(f"❌ 连接失败: {e}")

async def test_network():
    """测试网络连通性"""
    urls = [
        "https://bots.qq.com/app/getAppAccessToken",
        "https://api.sgroup.qq.com/gateway",
        "https://www.baidu.com",  # 对比测试
    ]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in urls:
            try:
                print(f"Testing: {url}")
                response = await client.get(url)
                print(f"  Status: {response.status_code}")
                print(f"  Headers: {response.headers}")
            except Exception as e:
                print(f"  Error: {type(e).__name__}: {e}")
            print()

def test_webservice():
    from modules.app import create_app
    debug_modules="all"
    app=create_app(
        debug=True,
        debug_modules=debug_modules
    )
    app.init()
    app.run()

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_ui(sample_text = """花间一壶酒，独酌无相亲。
举杯邀明月，对影成三人。
月既不解饮，影徒随我身。
暂伴月将影，行乐须及春。"""):
    font_color="#F6F6F6"

    from PyQt5.QtCore import (
        QTimer, Qt, QPropertyAnimation, QEasingCurve, 
        QPoint, pyqtSignal
    )
    from PyQt5.QtGui import QFont, QColor, QPainter
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QLabel, QApplication,QGraphicsDropShadowEffect
    )

    class ModernTypingDisplay(QWidget):
        """极简流式打字机显示组件 - 可拖动"""
        
        typing_finished = pyqtSignal()
        cleared = pyqtSignal()
        
        def __init__(self, parent=None):
            super().__init__(parent)
            
            # 配置参数
            self._typing_speed = 30
            self._batch_size = 5
            self._auto_clear_delay = 5000
            
            # 状态变量
            self._current_text = ""
            self._displayed_text = ""
            self._char_index = 0
            self._is_typing = False
            self._is_showing = False
            
            # 拖动相关
            self._drag_start_pos = QPoint()  # 鼠标按下时的全局位置
            self._window_start_pos = QPoint()  # 窗口按下时的位置
            self._is_dragging = False
            
            # 定时器
            self._typing_timer = QTimer(self)
            self._typing_timer.timeout.connect(self._type_next_chunk)

            
            # 淡出动画
            self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
            self._fade_animation.setDuration(600)
            self._fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
            self._fade_animation.finished.connect(self._on_fade_finished)
            
            # 初始化UI
            self._setup_ui()
        
        def center_on_screen(self):
            """居中显示在屏幕上"""
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            screen_rect = screen.geometry()
            x = (screen_rect.width() - self.width()) // 2
            y = (screen_rect.height() - self.height()) // 2
            self.move(x, y)
            
        def _setup_ui(self):
            """设置UI布局"""
            # 窗口标志
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            self.setMouseTracking(True)
            # 设置窗口大小
            self.resize(850, 380)
            self.setMinimumSize(400, 200)
            
            # 创建文本标签
            self._text_label = QLabel(self)
            self._text_label.setObjectName("typingText")
            self._text_label.setWordWrap(True)
            self._text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self._text_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            
            # 设置字体
            font = QFont()
            # font.setFamilies(['华文彩云', 'STCaiyun', 'KaiTi', 'SimSun'])
            font.setPointSize(22)
            font.setBold(True)
            self._text_label.setFont(font)
            
            # 应用样式
            self._apply_styles()
            
            # 初始状态
            self._text_label.hide()
            
        def _apply_styles(self):
            """应用样式"""
            self._text_label.setStyleSheet("""
                QLabel#typingText {
                    background: transparent;
                    color: #FFD700;
                    padding: 20px;
                    font-size: 22px;
                    font-weight: bold;
                }
            """)
            
            # 添加阴影效果
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(15)
            shadow.setOffset(3, 3)
            shadow.setColor(QColor(218, 165, 32, 180))
            self._text_label.setGraphicsEffect(shadow)
            
        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._text_label.setGeometry(10, 10, self.width() - 20, self.height() - 20)
            
        def _format_text_with_gradient(self, text: str) -> str:
            """格式化文本为花字效果"""
            formatted_text = text.replace('\n', '<br>')
            result = []
            char_index = 0
            i = 0
            
            while i < len(formatted_text):
                char = formatted_text[i]
                if char == '<':
                    tag_end = formatted_text.find('>', i)
                    if tag_end != -1:
                        result.append(formatted_text[i:tag_end + 1])
                        i = tag_end + 1
                        continue
                elif char == '&':
                    entity_end = formatted_text.find(';', i)
                    if entity_end != -1:
                        result.append(formatted_text[i:entity_end + 1])
                        i = entity_end + 1
                        continue
                else:
                    color = font_color
                    result.append(f'<span style="color: {color}; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">{char}</span>')
                    char_index += 1
                    i += 1
                    continue
                i += 1
                    
            return ''.join(result)
            
        def display_text(self, text: str):
            """显示文字 - 流式输出"""
            self._typing_timer.stop()
            
            self._is_typing = False
            self._is_showing = True
            
            self.show()
            self.raise_()
            self.activateWindow()
            self.setWindowOpacity(1.0)
            
            self._text_label.show()
            self._text_label.clear()
            
            self._current_text = text
            self._displayed_text = ""
            self._char_index = 0
            self._is_typing = True
            
            self._typing_timer.start(self._typing_speed)
            
        def _type_next_chunk(self):
            """打字下一批字符"""
            if self._char_index >= len(self._current_text):
                self._finish_typing()
                return
                
            end = min(self._char_index + self._batch_size, len(self._current_text))
            chunk = self._current_text[self._char_index:end]
            
            self._displayed_text += chunk
            self._char_index = end
            
            formatted = self._format_text_with_gradient(self._displayed_text)
            self._text_label.setText(formatted)
            
        def _finish_typing(self):
            """完成打字"""
            self._typing_timer.stop()
            self._is_typing = False
            
            formatted = self._format_text_with_gradient(self._current_text)
            self._text_label.setText(formatted)
            
            self.typing_finished.emit()
                
        def _fade_and_hide(self):
            """淡出并隐藏"""
            self._fade_animation.setStartValue(self.windowOpacity())
            self._fade_animation.setEndValue(0.0)
            self._fade_animation.start()
            
        def _on_fade_finished(self):
            """淡出完成"""
            self.clear()
            self.hide()
            self.setWindowOpacity(1.0)
            self._is_showing = False
                
        def clear(self):
            """清除显示"""
            self._typing_timer.stop()
            self._is_typing = False
            self._current_text = ""
            self._displayed_text = ""
            self._char_index = 0
            
            self._text_label.clear()
            self._text_label.hide()
            
            self.cleared.emit()
            
        def skip_typing(self):
            """跳过打字动画"""
            if self._is_typing:
                self._displayed_text = self._current_text
                formatted = self._format_text_with_gradient(self._current_text)
                self._text_label.setText(formatted)
                self._finish_typing()
                
        def set_typing_speed(self, chars_per_second: int):
            """设置打字速度"""
            speed = max(1, min(200, chars_per_second))
            self._typing_speed = int(1000 / speed)
            
        def set_auto_clear_delay(self, delay_ms: int):
            """设置自动清除延迟"""
            self._auto_clear_delay = max(0, delay_ms)
            
        def show_at_position(self, x: int, y: int):
            """在指定位置显示"""
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            screen_rect = screen.geometry()
            x = max(0, min(x, screen_rect.width() - self.width()))
            y = max(0, min(y, screen_rect.height() - self.height()))
            self.move(x, y)
            
        def mousePressEvent(self, event):
            """鼠标按下事件 - 开始拖动"""
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                # 记录鼠标按下时的全局位置
                self._drag_start_pos = event.globalPosition().toPoint()
                # 记录窗口当前的位置
                self._window_start_pos = self.pos()
                event.accept()
                print(f"开始拖动: 鼠标={self._drag_start_pos}, 窗口={self._window_start_pos}")

        def mouseMoveEvent(self, event):
            """鼠标移动事件 - 拖动中"""
            if self._is_dragging:
                # 计算鼠标移动的距离
                delta = event.globalPosition().toPoint() - self._drag_start_pos
                # 计算窗口新位置 = 窗口原位置 + 鼠标移动距离
                new_pos = self._window_start_pos + delta
                self.move(new_pos)
                event.accept()
                print(f"拖动中: 新位置={new_pos}")
                
        def mouseReleaseEvent(self, event):
            """鼠标释放事件 - 结束拖动"""
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False
                event.accept()
                print(f"拖动结束: 最终位置={self.pos()}")
    
    app = QApplication(sys.argv)
    
    # 创建打字机
    display = ModernTypingDisplay()
    display.center_on_screen()
    
    # 模拟流式输出
    def simulate_stream():
        display.display_text(sample_text)
    
    # 延迟1秒启动模拟
    QTimer.singleShot(1000, simulate_stream)
    
    print("程序启动 - 点击窗口即可拖动")
    sys.exit(app.exec_())

def test_router():
    from collections import OrderedDict
from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any, Dict, Generic, List, Optional, Callable, OrderedDict, Tuple, TypeVar
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from functools import lru_cache

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入原有模型

T = TypeVar("T")

class EnhancedLRUCache(Generic[T]):
    """增强版LRU缓存，支持异步清理和批量操作"""
    
    def __init__(self, cache_ttl: int = 300, capacity: int = 200, 
                 cleanup_interval: int = 60):
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.capacity = capacity
        self._cache_ttl = cache_ttl
        self._last_cleanup = datetime.now()
        self._cleanup_interval = cleanup_interval
        self._hit_count = 0
        self._miss_count = 0
    
    def get(self, key: str) -> Optional[T]:
        if key in self.cache:
            entry = self.cache[key]
            # 检查过期
            if (datetime.now() - entry["timestamp"]).seconds < self._cache_ttl:
                self.cache.move_to_end(key)
                self._hit_count += 1
                return entry["value"]
            else:
                # 惰性删除过期条目
                del self.cache[key]
                self._miss_count += 1
                return None
        self._miss_count += 1
        return None
    
    def put(self, key: str, value: T):
        self.cache[key] = {
            "timestamp": datetime.now(),
            "value": value
        }
        self.cache.move_to_end(key)
        
        # 容量控制
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        
        # 定期清理
        self._periodic_cleanup()
    
    def _periodic_cleanup(self):
        """定期清理过期条目"""
        now = datetime.now()
        if (now - self._last_cleanup).seconds >= self._cleanup_interval:
            self.cleanup()
            self._last_cleanup = now
    
    def cleanup(self):
        """清理所有过期条目"""
        now = datetime.now()
        expired_keys = [
            key for key, value in self.cache.items()
            if (now - value["timestamp"]).seconds > self._cache_ttl
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._hit_count + self._miss_count
        return {
            "size": len(self.cache),
            "capacity": self.capacity,
            "hit_rate": self._hit_count / total if total > 0 else 0,
            "hits": self._hit_count,
            "misses": self._miss_count
        }

class KeywordMatcher:
    """高效的关键词匹配器，使用Trie树结构"""
    
    class TrieNode:
        def __init__(self):
            self.children = {}
            self.is_end = False
            self.service = None
            self.weight = 0.0
    
    def __init__(self):
        self.root = self.TrieNode()
        self._compiled_patterns = []
    
    def build_from_keywords(self, keywords_dict: Dict[str, List[str]], 
                           default_weight: float = 0.85):
        """从关键词字典构建匹配器"""
        for service, keywords in keywords_dict.items():
            for keyword in keywords:
                self._add_keyword(keyword.lower(), service, default_weight)
                # 同时编译正则表达式用于模糊匹配
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                self._compiled_patterns.append((pattern, service, default_weight))
    
    def _add_keyword(self, keyword: str, service: str, weight: float):
        """向Trie树添加关键词"""
        node = self.root
        for char in keyword:
            if char not in node.children:
                node.children[char] = self.TrieNode()
            node = node.children[char]
        node.is_end = True
        node.service = service
        node.weight = weight
    
    def search_exact(self, text: str) -> List[Tuple[str, float]]:
        """精确匹配搜索"""
        results = []
        text_lower = text.lower()
        
        for i in range(len(text_lower)):
            node = self.root
            for j in range(i, len(text_lower)):
                char = text_lower[j]
                if char not in node.children:
                    break
                node = node.children[char]
                if node.is_end:
                    results.append((node.service, node.weight))
        
        return results
    
    def search_regex(self, text: str) -> List[Tuple[str, float]]:
        """正则表达式匹配搜索"""
        results = []
        for pattern, service, weight in self._compiled_patterns:
            if pattern.search(text):
                results.append((service, weight))
        return results
    
    def search(self, text: str) -> List[Tuple[str, float]]:
        """综合搜索，优先精确匹配"""
        exact_results = self.search_exact(text)
        if exact_results:
            return exact_results
        return self.search_regex(text)

# class EnhancedIntentRouter:
#     """增强版意图路由器"""
    
#     def __init__(self, config: Optional[Dict[str, Any]] = None):
#         self.config = config or self._default_config()
        
#         # 使用高效的关键词匹配器
#         self._tool_matcher = KeywordMatcher()
#         self._emotional_matcher = KeywordMatcher()
#         self._init_matchers()
        
#         # 增强的缓存系统
#         self._intent_cache: EnhancedLRUCache[RouteDecisionCache] = \
#             EnhancedLRUCache(
#                 cache_ttl=self.config.get("cache_ttl", 600),
#                 capacity=self.config.get("cache_capacity", 500)
#             )
        
#         # 线程池用于并行处理
#         self._executor = ThreadPoolExecutor(
#             max_workers=self.config.get("max_workers", 4)
#         )
        
#         # 统计信息
#         self.stats = {
#             "total_routes": 0,
#             "pure_chat": 0,
#             "tool_call": 0,
#             "ambiguous": 0,
#             "emotional_tool": 0,
#             "cache_hits": 0,
#             "avg_response_time": 0.0,
#             "response_times": []
#         }
        
#         # 预编译的正则表达式模式
#         self._precompiled_patterns = self._compile_patterns()
    
#     def _default_config(self) -> Dict[str, Any]:
#         return {
#             "cache_ttl": 600,  # 10分钟缓存
#             "cache_capacity": 500,
#             "max_workers": 4,
#             "tool_threshold": 0.80,
#             "emotion_threshold": 0.70,
#             "mixed_threshold": 0.50,
#             "enable_parallel_check": True,
#             "enable_context_awareness": True,
#             "min_confidence_for_llm": 0.30
#         }
    
#     def _init_matchers(self):
#         """初始化关键词匹配器"""
#         tool_keywords = self._init_tool_keywords()
#         emotional_keywords = self._init_emotional_keywords()
        
#         self._tool_matcher.build_from_keywords(tool_keywords)
#         self._emotional_matcher.build_from_keywords(
#             {"emotional": emotional_keywords},
#             default_weight=0.75
#         )
    
#     def _init_tool_keywords(self) -> Dict[str, List[str]]:
#         """初始化工具调用关键词（扩展版本）"""
#         return {
#             "browser": [
#                 "打开网页", "浏览", "搜索", "查资料", "上网",
#                 "open page", "browse", "search", "google", "baidu",
#                 "打开浏览器", "访问网站", "导航到", "跳转到",
#                 "查看网页", "浏览网页", "网上查", "搜一下"
#             ],
#             "obs": [
#                 "直播", "推流", "录制", "画面", "场景",
#                 "stream", "record", "scene", "obs",
#                 "切换场景", "开始直播", "停止录制",
#                 "开播", "下播", "录屏", "屏幕录制"
#             ],
#             "music": [
#                 "放音乐", "播歌", "听歌", "播放",
#                 "play music", "song", "melody",
#                 "来首歌", "放首歌", "音乐", "歌曲",
#                 "暂停", "下一首", "上一首", "音量"
#             ],
#             "reminder": [
#                 "提醒", "闹钟", "定时", "备忘录",
#                 "remind", "alarm", "timer", "schedule",
#                 "记一下", "记住", "别忘", "到时提醒"
#             ],
#             "weather": [
#                 "天气", "气温", "下雨", "晴天",
#                 "weather", "temperature", "forecast",
#                 "天气预报", "多少度", "冷不冷", "热不热"
#             ],
#             "translate": [
#                 "翻译", "convert", "translate",
#                 "翻成", "译成", "怎么读", "什么意思"
#             ],
#             "calculate": [
#                 "计算", "算一下", "等于",
#                 "calculate", "compute", "math",
#                 "加减乘除", "运算", "求值"
#             ],
#             "game": [
#                 "玩游戏", "游戏", "猜谜", "答题",
#                 "game", "quiz", "puzzle",
#                 "玩个游戏", "来一局", "比赛"
#             ],
#             "live2d": [
#                 "live2d", "模型", "角色", "显示",
#                 "隐藏", "换装", "皮肤", "装扮"
#             ],
#             "image": [
#                 "图片", "照片", "截图", "拍照",
#                 "image", "photo", "screenshot",
#                 "生成图片", "画图", "绘图"
#             ],
#             "video": [
#                 "视频", "录像", "播放视频",
#                 "video", "movie", "film",
#                 "看视频", "看电影"
#             ]
#         }
    
#     def _init_emotional_keywords(self) -> List[str]:
#         """初始化情感关键词（扩展版本）"""
#         return [
#             # 情绪表达
#             "难过", "开心", "伤心", "孤独", "寂寞",
#             "焦虑", "害怕", "生气", "委屈", "感动",
#             "幸福", "温暖", "失落", "沮丧", "兴奋",
#             "烦躁", "郁闷", "无聊", "疲惫", "累",
#             "高兴", "快乐", "悲伤", "痛苦", "绝望",
            
#             # 情感需求
#             "陪我", "聊天", "说说话", "倾诉",
#             "安慰", "鼓励", "抱抱", "想你了",
#             "陪陪我", "聊聊天", "谈谈心",
            
#             # 日常生活
#             "今天", "心情", "感觉", "觉得",
#             "最近", "刚才", "刚刚",
            
#             # 英文情感
#             "sad", "happy", "lonely", "miss you",
#             "talk", "chat", "feeling", "mood",
#             "love", "hate", "angry", "tired"
#         ]
    
#     def _compile_patterns(self) -> Dict[str, re.Pattern]:
#         """预编译正则表达式模式"""
#         return {
#             "question_how": re.compile(r"(怎么|如何|怎样)\s*(做|办|弄|搞)"),
#             "question_what": re.compile(r"(什么|哪)\s*(是|有|叫)"),
#             "question_why": re.compile(r"为什么"),
#             "question_request": re.compile(r"能不能|可以不可以|可否"),
#             "command_open": re.compile(r"^(帮我|请|麻烦)\s*(打开|开启|启动)"),
#             "command_music": re.compile(r"^(播放|放|唱)"),
#             "command_reminder": re.compile(r"^(提醒|设置|定)"),
#             "command_translate": re.compile(r"^(翻译|查)")
#         }
    
#     async def route_async(
#         self,
#         user_input: str,
#         context: Optional[Dict[str, Any]] = None,
#         use_llm_for_ambiguous: bool = False,
#         llm_judge_func: Optional[Callable] = None
#     ):
#         """
#         异步路由决策主方法
        
#         Args:
#             user_input: 用户输入
#             context: 上下文信息（可选）
#             use_llm_for_ambiguous: 模糊时是否使用LLM判断
#             llm_judge_func: LLM判断函数
            
#         Returns:
#             RouteDecision: 路由决策
#         """
#         start_time = datetime.now()
#         self.stats["total_routes"] += 1
        
#         # 1. 检查缓存
#         cache_key = self._get_cache_key(user_input, context)
#         cached = self._intent_cache.get(cache_key)
#         if cached:
#             self.stats["cache_hits"] += 1
#             self._update_response_time(start_time)
#             return cached.decision
        
#         # 2. 并行执行规则匹配
#         if self.config["enable_parallel_check"]:
#             rule_result, pattern_result = await asyncio.gather(
#                 asyncio.to_thread(self._quick_rule_match, user_input),
#                 asyncio.to_thread(self._check_special_patterns, user_input)
#             )
#         else:
#             rule_result = self._quick_rule_match(user_input)
#             pattern_result = self._check_special_patterns(user_input)
        
#         # 合并结果
#         decision = self._merge_results(rule_result, pattern_result, context)
        
#         # 3. 如果需要，使用LLM进行二次判断
#         if (decision.route_type == RouteType.AUTO and 
#             use_llm_for_ambiguous and 
#             llm_judge_func and
#             decision.confidence < self.config["min_confidence_for_llm"]):
#             decision = await self._llm_judge_async(user_input, llm_judge_func)
        
#         # 4. 更新统计
#         self.stats[decision.route_type.value] += 1
        
#         # 5. 缓存结果
#         self._intent_cache.put(
#             cache_key,
#             RouteDecisionCache(
#                 timestamp=datetime.now(),
#                 decision=decision
#             )
#         )
        
#         # 6. 记录响应时间
#         self._update_response_time(start_time)
        
#         return decision
    
#     def route(
#         self,
#         user_input: str,
#         context: Optional[Dict[str, Any]] = None,
#         use_llm_for_ambiguous: bool = False,
#         llm_judge_func: Optional[Callable] = None
#     ) -> RouteDecision:
#         """
#         同步路由决策方法
        
#         Args:
#             user_input: 用户输入
#             context: 上下文信息（可选）
#             use_llm_for_ambiguous: 模糊时是否使用LLM判断
#             llm_judge_func: LLM判断函数
            
#         Returns:
#             RouteDecision: 路由决策
#         """
#         start_time = datetime.now()
#         self.stats["total_routes"] += 1
        
#         # 1. 检查缓存
#         cache_key = self._get_cache_key(user_input, context)
#         cached = self._intent_cache.get(cache_key)
#         if cached:
#             self.stats["cache_hits"] += 1
#             self._update_response_time(start_time)
#             return cached.decision
        
#         # 2. 规则匹配
#         rule_result = self._quick_rule_match(user_input)
#         pattern_result = self._check_special_patterns(user_input)
        
#         # 合并结果
#         decision = self._merge_results(rule_result, pattern_result, context)
        
#         # 3. 如果需要，使用LLM进行二次判断
#         if (decision.route_type == RouteType.AUTO and 
#             use_llm_for_ambiguous and 
#             llm_judge_func and
#             decision.confidence < self.config["min_confidence_for_llm"]):
#             decision = self._llm_judge(user_input, llm_judge_func)
        
#         # 4. 更新统计
#         self.stats[decision.route_type.value] += 1
        
#         # 5. 缓存结果
#         self._intent_cache.put(
#             cache_key,
#             RouteDecisionCache(
#                 timestamp=datetime.now(),
#                 decision=decision
#             )
#         )
        
#         # 6. 记录响应时间
#         self._update_response_time(start_time)
        
#         return decision
    
#     def _quick_rule_match(self, user_input: str) -> Dict[str, Any]:
#         """快速规则匹配（优化版本）"""
#         input_lower = user_input.lower()
        
#         # 使用高效的关键词匹配器
#         tool_matches = self._tool_matcher.search(input_lower)
#         emotional_matches = self._emotional_matcher.search(input_lower)
        
#         # 计算置信度
#         tool_confidence = max([w for _, w in tool_matches], default=0.0)
#         emotional_confidence = max([w for _, w in emotional_matches], default=0.0)
        
#         # 提取检测到的服务和意图
#         detected_services = list(set(s for s, _ in tool_matches))
#         detected_intents = ["emotional"] if emotional_confidence > 0 else []
        
#         return {
#             "tool_confidence": tool_confidence,
#             "emotional_confidence": emotional_confidence,
#             "detected_services": detected_services,
#             "detected_intents": detected_intents
#         }
    
#     def _check_special_patterns(self, user_input: str) -> Dict[str, Any]:
#         """检查特殊模式（优化版本）"""
#         result = {"intents": [], "services": []}
        
#         # 使用预编译的正则表达式
#         for name, pattern in self._precompiled_patterns.items():
#             if pattern.search(user_input):
#                 if name.startswith("question"):
#                     result["intents"].append(f"question:{name.split('_')[1]}")
#                 elif name.startswith("command"):
#                     result["services"].append(name.split('_')[1])
        
#         return result
    
#     def _merge_results(
#         self, 
#         rule_result: Dict[str, Any],
#         pattern_result: Dict[str, Any],
#         context: Optional[Dict[str, Any]]
#     ) -> RouteDecision:
#         """合并多个匹配结果"""
#         tool_confidence = rule_result["tool_confidence"]
#         emotional_confidence = rule_result["emotional_confidence"]
        
#         # 合并服务和意图
#         all_services = list(set(
#             rule_result["detected_services"] + pattern_result["services"]
#         ))
#         all_intents = list(set(
#             rule_result["detected_intents"] + pattern_result["intents"]
#         ))
        
#         # 考虑上下文
#         if context and self.config["enable_context_awareness"]:
#             tool_confidence, emotional_confidence = self._apply_context(
#                 tool_confidence, emotional_confidence, context
#             )
        
#         # 决策逻辑
#         if tool_confidence > self.config["tool_threshold"] and \
#            emotional_confidence < self.config["emotion_threshold"]:
#             return RouteDecision(
#                 route_type=RouteType.TOOL_CALL,
#                 confidence=tool_confidence,
#                 detected_intents=all_intents,
#                 suggested_services=all_services,
#                 reason=f"检测到明确工具调用意图: {', '.join(all_services)}"
#             )
        
#         elif emotional_confidence > self.config["emotion_threshold"] and \
#              tool_confidence < self.config["tool_threshold"]:
#             return RouteDecision(
#                 route_type=RouteType.PURE_CHAT,
#                 confidence=emotional_confidence,
#                 detected_intents=["emotional"],
#                 reason="检测到情感表达需求"
#             )
        
#         elif tool_confidence > self.config["mixed_threshold"] and \
#              emotional_confidence > self.config["emotion_threshold"]:
#             return RouteDecision(
#                 route_type=RouteType.AUTO,
#                 confidence=(tool_confidence + emotional_confidence) / 2,
#                 detected_intents=all_intents,
#                 suggested_services=all_services,
#                 reason="情感需求和工具需求混合"
#             )
        
#         else:
#             return RouteDecision(
#                 route_type=RouteType.AUTO,
#                 confidence=max(tool_confidence, emotional_confidence, 0.3),
#                 detected_intents=all_intents,
#                 suggested_services=all_services,
#                 reason="无法明确判断，需要进一步分析"
#             )
    
#     def _apply_context(
#         self,
#         tool_confidence: float,
#         emotional_confidence: float,
#         context: Dict[str, Any]
#     ) -> Tuple[float, float]:
#         """应用上下文调整置信度"""
#         # 如果是连续对话中的后续消息
#         if context.get("conversation_turn", 0) > 3:
#             # 长对话中更倾向于聊天
#             emotional_confidence = min(1.0, emotional_confidence * 1.2)
        
#         # 如果之前是工具调用
#         if context.get("previous_route") == RouteType.TOOL_CALL:
#             # 可能还是工具调用
#             tool_confidence = min(1.0, tool_confidence * 1.1)
        
#         # 如果有情感历史
#         if context.get("emotional_history", False):
#             emotional_confidence = min(1.0, emotional_confidence * 1.3)
        
#         return tool_confidence, emotional_confidence
    
#     async def _llm_judge_async(
#         self, 
#         user_input: str, 
#         llm_func: Callable
#     ) -> RouteDecision:
#         """异步使用LLM进行判断"""
#         try:
#             prompt = f"""请判断用户输入的意图类型，只返回JSON格式。

# 用户输入: "{user_input}"

# 可能的类型:
# - pure_chat: 纯情感聊天、日常对话、无需工具
# - tool_call: 明确需要调用某个工具/服务
# - ambiguous: 不确定

# 严格遵循以下JSON返回格式，不准添加额外说明:
# {{"type": "pure_chat/tool_call/ambiguous", "confidence": 0.0-1.0, "reason": "简短理由"}}
# """
#             # 异步调用LLM
#             result = await asyncio.to_thread(llm_func, prompt)
            
#             # 解析LLM返回
#             try:
#                 data = json.loads(result)
#                 route_type = RouteType(data.get("type", "ambiguous"))
#                 confidence = float(data.get("confidence", 0.5))
                
#                 return RouteDecision(
#                     route_type=route_type,
#                     confidence=confidence,
#                     reason=data.get("reason", "LLM判断")
#                 )
#             except json.JSONDecodeError:
#                 logger.warning(f"LLM返回格式错误: {result}")
#                 return RouteDecision(
#                     route_type=RouteType.AUTO,
#                     confidence=0.3,
#                     reason="LLM判断失败，回退规则"
#                 )
                
#         except Exception as e:
#             logger.error(f"LLM调用失败: {str(e)}")
#             return RouteDecision(
#                 route_type=RouteType.AUTO,
#                 confidence=0.3,
#                 reason=f"LLM调用失败: {str(e)}"
#             )
    
#     def _llm_judge(
#         self, 
#         user_input: str, 
#         llm_func: Callable
#     ) -> RouteDecision:
#         """同步使用LLM进行判断"""
#         try:
#             prompt = f"""请判断用户输入的意图类型，只返回JSON格式。

# 用户输入: "{user_input}"

# 可能的类型:
# - pure_chat: 纯情感聊天、日常对话、无需工具
# - tool_call: 明确需要调用某个工具/服务
# - ambiguous: 不确定

# 严格遵循以下JSON返回格式，不准添加额外说明:
# {{"type": "pure_chat/tool_call/ambiguous", "confidence": 0.0-1.0, "reason": "简短理由"}}
# """
#             result = llm_func(prompt)
            
#             try:
#                 data = json.loads(result)
#                 route_type = RouteType(data.get("type", "ambiguous"))
#                 confidence = float(data.get("confidence", 0.5))
                
#                 return RouteDecision(
#                     route_type=route_type,
#                     confidence=confidence,
#                     reason=data.get("reason", "LLM判断")
#                 )
#             except json.JSONDecodeError:
#                 logger.warning(f"LLM返回格式错误: {result}")
#                 return RouteDecision(
#                     route_type=RouteType.AUTO,
#                     confidence=0.3,
#                     reason="LLM判断失败，回退规则"
#                 )
                
#         except Exception as e:
#             logger.error(f"LLM调用失败: {str(e)}")
#             return RouteDecision(
#                 route_type=RouteType.AUTO,
#                 confidence=0.3,
#                 reason=f"LLM调用失败: {str(e)}"
#             )
    
#     def _get_cache_key(
#         self, 
#         user_input: str, 
#         context: Optional[Dict[str, Any]] = None
#     ) -> str:
#         """生成缓存键（包含上下文）"""
#         normalized = user_input.strip().lower()
#         normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', normalized)
        
#         # 如果包含上下文，加入缓存键
#         if context:
#             context_str = json.dumps(context, sort_keys=True)
#             combined = f"{normalized}:{context_str}"
#             return hashlib.md5(combined.encode()).hexdigest()
        
#         return hashlib.md5(normalized.encode()).hexdigest()
    
#     def _update_response_time(self, start_time: datetime):
#         """更新响应时间统计"""
#         response_time = (datetime.now() - start_time).total_seconds()
#         self.stats["response_times"].append(response_time)
        
#         # 只保留最近100次的响应时间
#         if len(self.stats["response_times"]) > 100:
#             self.stats["response_times"].pop(0)
        
#         # 计算平均响应时间
#         if self.stats["response_times"]:
#             self.stats["avg_response_time"] = sum(
#                 self.stats["response_times"]
#             ) / len(self.stats["response_times"])
    
#     def get_stats(self) -> Dict[str, Any]:
#         """获取详细统计信息"""
#         total = self.stats["total_routes"]
#         cache_stats = self._intent_cache.get_stats()
        
#         return {
#             **self.stats,
#             "cache": cache_stats,
#             "hit_rate": self.stats["cache_hits"] / total if total > 0 else 0,
#             "distribution": {
#                 "pure_chat_pct": self.stats["pure_chat"] / total * 100 if total > 0 else 0,
#                 "tool_call_pct": self.stats["tool_call"] / total * 100 if total > 0 else 0,
#                 "ambiguous_pct": self.stats["ambiguous"] / total * 100 if total > 0 else 0
#             }
#         }
    
#     def clear_cache(self):
#         """清空缓存"""
#         self._intent_cache = EnhancedLRUCache(
#             cache_ttl=self.config.get("cache_ttl", 600),
#             capacity=self.config.get("cache_capacity", 500)
#         )
from modules.services.browser.distiller import DOMDistiller
TEST_HTML = """
<html><head><title>测试商城</title></head><body>
    <nav style="display:none">
        <a href="/hidden">隐藏链接</a>
        <button>隐藏按钮</button>
    </nav>
    <div class="header-wrapper">
        <div class="header">
            <button id="btn-home" aria-label="返回首页">🏠 首页</button>
            <a href="/search?q=手机">搜索手机</a>
            <a href="/search?q=手机">搜手机（重复）</a>
            <a href="/cart" aria-label="购物车">🛒 购物车(3)</a>
            <input type="search" placeholder="搜索您想要的商品" aria-label="搜索框"/>
        </div>
    </div>
    <main>
        <h1>热门商品</h1>
        <div class="product-list">
            <div class="product-card">
                <a href="/p/1001" aria-label="iPhone 15 Pro">iPhone 15 Pro ¥6999</a>
                <span class="desc">A17 Pro 芯片，钛金属机身</span>
                <button class="buy-btn">加入购物车</button>
                <button class="buy-btn">立即购买</button>
            </div>
            <div class="product-card">
                <a href="/p/1002" aria-label="华为 Mate 60">华为 Mate 60 ¥5999</a>
                <span class="desc">麒麟芯片，卫星通信</span>
                <button class="buy-btn">加入购物车</button>
                <button class="buy-btn">立即购买</button>
            </div>
            <div class="product-card">
                <a href="/p/1003" aria-label="小米14 Ultra">小米14 Ultra ¥6499</a>
                <span class="desc">徕卡光学，一英寸大底</span>
                <button class="buy-btn">加入购物车</button>
                <button class="buy-btn">立即购买</button>
            </div>
        </div>
        <div class="pagination">
            <a href="/page/1">1</a>
            <a href="/page/2">2</a>
            <a href="/page/3">3</a>
            <a href="/page/4">4</a>
            <a href="/page/5">5</a>
            <a href="/page/6">6</a>
            <a href="/page/7">7</a>
            <a href="/page/8">8</a>
        </div>
    </main>
    <footer>
        <a href="/about">关于我们</a>
        <a href="/privacy">隐私政策</a>
        <a href="/terms">服务条款</a>
    </footer>
    <div aria-hidden="true">
        <button>不应该出现</button>
        <a href="/spam">垃圾链接</a>
    </div>
</body></html>
"""
async def test_html():
    print("=" * 60)
    print("测试1: HTML 字符串蒸馏")
    print("=" * 60)

    d = DOMDistiller(max_chunk_size=10, similarity_threshold=0.85)

    start = time.time()
    result = d.distill_html(TEST_HTML, url="https://shop.example.com", title="测试商城")
    elapsed = (time.time() - start) * 1000

    print(f"\n⏱ 蒸馏耗时: {elapsed:.1f}ms")
    print(f"📊 原始元素: {result.total_original_elements}")
    print(f"📊 过滤后: {result.total_after_filter}")
    print(f"📊 压缩率: {result.compression_ratio*100:.1f}%")
    print(f"📊 分块数: {len(result.chunks)}")
    print(f"\n{'─' * 40}")
    print(d.format_for_llm(result, chunk_index=0))


async def test_real_page():
    print("\n" + "=" * 60)
    print("测试2: Playwright 真实页面蒸馏")
    print("=" * 60)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.bing.com")
        title = await page.title()

        d = DOMDistiller(max_chunk_size=20)
        start = time.time()
        result = await d.distill_page(page, url=page.url, title=title)
        elapsed = (time.time() - start) * 1000

        print(f"\n⏱ 蒸馏耗时: {elapsed:.1f}ms")
        print(f"📊 原始元素: {result.total_original_elements}")
        print(f"📊 过滤后: {result.total_after_filter}")
        print(f"📊 压缩率: {result.compression_ratio*100:.1f}%")
        print(f"📊 分块数: {len(result.chunks)}")
        print(f"\n{'─' * 40}")
        print(d.format_for_llm(result, chunk_index=0))

        # 展示所有块
        for i, chunk in enumerate(result.chunks):
            print(f"\n--- 区块 {i+1}/{len(result.chunks)} ({len(chunk.elements)} 元素, ~{chunk.total_tokens_estimate} tokens) ---")
            for el in chunk.elements[:5]:
                print(f"  [{el.uid}] <{el.tag}> text=\"{el.text[:40]}\" sel={el.selector}")

        await browser.close()


async def test_compression_comparison():
    """对比不同页面的压缩效果"""
    print("\n" + "=" * 60)
    print("测试3: 压缩效果对比")
    print("=" * 60)

    from playwright.async_api import async_playwright

    urls = [
        ("Bing", "https://www.bing.com"),
        ("GitHub", "https://github.com"),
        ("Hacker News", "https://news.ycombinator.com"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        d = DOMDistiller(max_chunk_size=20)

        print(f"\n{'页面':<15} {'原始':>6} {'过滤后':>6} {'压缩率':>8} {'分块':>4}")
        print("─" * 50)

        for name, url in urls:
            page = await context.new_page()
            try:
                await page.goto(url, timeout=15000)
                result = await d.distill_page(page, url=url, title=await page.title())
                print(f"{name:<15} {result.total_original_elements:>6} {result.total_after_filter:>6} {result.compression_ratio*100:>7.1f}% {len(result.chunks):>4}")
            except Exception as e:
                print(f"{name:<15} ERROR: {e}")
            await page.close()

        await browser.close()

#测试流装饰器
@decorator.sync_task_scheduler(timeout=SYNC_TIMEOUT)
async def main():
    await test_compression_comparison()
    # await test_real_page()
    # await test_compression_comparison()


if __name__ == "__main__":
    import ctypes, json
    lib = ctypes.CDLL("src_py/perf_native.dll")
    buf = ctypes.create_string_buffer(4096)
    _ = lib.detect_performance_buf(buf, len(buf))
    print("buf 版:", json.loads(buf.value.decode("utf-8")))
    # import struct, sys; print(sys.version); print('64bit' if struct.calcsize('P')*8==64 else '32bit')

