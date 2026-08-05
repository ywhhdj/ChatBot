"""
character_system/models.py — 角色系统数据模型

定义角色、角色状态、上下文分离结构。
"""
from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, TypedDict
from enum import Enum
from ..routes.models import RouteType


# ─────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────

class CharacterStatus(str, Enum):
    ACTIVE   = "active"     # 当前正在使用
    IDLE     = "idle"       # 已注册但未使用
    DISABLED = "disabled"   # 用户禁用


class ContextType(str, Enum):
    """上下文类型标识"""
    CHARACTER = "character"  # 角色人设上下文
    TOOL      = "tool"       # 工具/服务上下文
    USER      = "user"       # 用户输入上下文
    MEMORY    = "memory"     # 对话记忆上下文


# ─────────────────────────────────────────────
# 角色数据模型
# ─────────────────────────────────────────────

@dataclass
class CharacterAttributes:
    """角色属性（用于动态构建 prompt）"""
    # 基础信息
    name: str = ""                  # 角色名（如"小青"）
    title: str = ""                 # 称呼/头衔（如"青梅竹马"）
    nickname_for_user: str = ""     # 对用户的称呼（如"主人""亲爱的"）
    
    # 人设
    personality: str = ""           # 性格描述（开朗/高冷/温柔...）
    background: str = ""            # 背景故事
    speech_style: str = ""          # 说话风格（语气词、口头禅）
    catchphrases: List[str] = field(default_factory=list)  # 口头禅列表
    
    # 行为约束
    rules: List[str] = field(default_factory=list)  # 行为规则
    topics_allowed: List[str] = field(default_factory=list)  # 允许话题
    topics_forbidden: List[str] = field(default_factory=list)  # 禁止话题
    
    # 情感参数
    affection_level: int = 50       # 好感度 0-100
    mood: str = "neutral"          # 当前心情
    mood_modifiers: Dict[str, str] = field(default_factory=dict)  # 心情修饰词
    
    # 随机性词汇池（用于抽取增加多样性）
    random_words: List[str] = field(default_factory=list)  # 随机插入的语气词
    action_verbs: List[str] = field(default_factory=list)   # 动作描写池
    emotion_adjectives: List[str] = field(default_factory=list)  # 情感形容词池


@dataclass
class CharacterState:
    """角色运行时状态（切换时保存/恢复）"""
    character_id: str = ""
    status: CharacterStatus = CharacterStatus.IDLE
    
    # 对话记忆（该角色独立的消息历史）
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_memory: int = 20           # 最大记忆条数
    
    # 情感状态
    mood: str = "neutral"
    affection: int = 50
    last_interaction: float = 0.0   # 最后交互时间戳
    
    # 任务执行状态
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)  # 后台任务队列
    task_history: List[Dict[str, Any]] = field(default_factory=list)   # 已执行任务
    
    # 统计
    total_messages: int = 0
    total_tasks: int = 0
    
    def touch(self):
        self.last_interaction = time.time()
    
    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        # 滑动窗口
        if len(self.messages) > self.max_memory:
            self.messages = self.messages[-self.max_memory:]
        self.total_messages += 1
        self.touch()
    
    def get_recent(self, n: int = 10) -> List[Dict[str, str]]:
        """取最近 n 条，转成 {role, content} 格式"""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.messages[-n:]
        ]


@dataclass
class Character:
    """完整角色定义"""
    id: str = ""
    name: str = ""
    attributes: CharacterAttributes = field(default_factory=CharacterAttributes)
    state: CharacterState = field(default_factory=CharacterState)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.state.character_id:
            self.state.character_id = self.id
        if not self.attributes.name:
            self.attributes.name = self.name


# ─────────────────────────────────────────────
# Prompt 片段（按需组合）
# ─────────────────────────────────────────────

class PromptSegment(TypedDict):
    type: str       # ContextType 的字符串值
    priority: int   # 优先级（越小越靠前）
    content: str    # 实际文本


@dataclass
class BuiltPrompt:
    system_prompt: str = ""           # 完整 system prompt
    segments: List[PromptSegment] = field(default_factory=list)
    estimated_tokens: int = 0         # 估算 token 数
    character_id: str = ""            # 当前角色 ID
    route: RouteType = RouteType.PURE_CHAT
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)