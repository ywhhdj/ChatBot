"""
character_system/models.py — 角色系统数据模型

修复对应清单：C54 C55 C56

C54 同一概念两种类型：`CharacterAttributes.mood` 是情绪名(str)，
    `CharacterState.mood` 是 int。builder 里拿 int 去查 str 键的
    mood_modifiers，恒不匹配 -> 角色心情永远不生效（C16 的根源）。
    这里把分工写死：state.mood 存 int(情绪 id)，attributes.mood 存情绪名(str)。
C55 CharacterState.messages 与 UserContext 是两套历史，职责在此明确划分。
C56 to_dict 用 asdict 会把 Enum/datetime 原样留下，json.dump 直接 TypeError。
"""
from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from ..routes.models import RouteType


def _jsonable(value: Any) -> Any:
    """把 dataclass 转出的结构降级为 JSON 可序列化类型（C56）。"""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
    # 当前心情（情绪名，如 "高兴"）
    mood: str = "平静"           # 当前心情（情绪名，如 "高兴"）
    mood_modifiers: Dict[str, str] = field(default_factory=dict)  # 心情修饰词

    # 随机性词汇池（用于抽取增加多样性）
    random_words: List[str] = field(default_factory=list)  # 随机插入的语气词
    action_verbs: List[str] = field(default_factory=list)   # 动作描写池
    emotion_adjectives: List[str] = field(default_factory=list)  # 情感形容词池


@dataclass
class CharacterState:
    """角色运行时状态（切换时保存/恢复）

    C55：与 UserContext 分工明确，避免两套历史各自裁剪导致不一致：
        - CharacterState.messages —— 该角色的**长期**对话记忆
        - UserContext._messages   —— 本轮/近期上下文 + 记忆系统注入
    """
    character_id: str = ""
    status: CharacterStatus = CharacterStatus.IDLE

    # 对话记忆（该角色独立的消息历史）
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_memory: int = 200           # 最大记忆条数

    # 情感状态
    mood: int = 4                  # 情绪 id（int），取值见 presets.emotion_map
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
    
    def add_task_history(self, task: str):
        self.task_history.append({
            "task": task,
            "timestamp": time.time()
        })
        self.total_tasks += 1
        self.touch()

    def get_recent(self, n: int = 20) -> List[Dict[str, str]]:
        return [
            {
                "role": m["role"], 
                "content": m["content"],
            }
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
    avatar: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.state.character_id:
            self.state.character_id = self.id
        if not self.attributes.name:
            self.attributes.name = self.name
    
    def add_message(self, role: str, content: str):
        self.state.add_message(role, content)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        char = cls(data.get("id", "").strip())
        char.name = data.get("name", "").strip()
        char.attributes = CharacterAttributes(**data.get("attributes", {}))
        char.state = CharacterState(**data.get("state", {}))
        char.created_at = data.get("created_at", 0.0)
        char.updated_at = data.get("updated_at", 0.0)
        return char

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "attributes": _jsonable(asdict(self.attributes)),
            "state": _jsonable(asdict(self.state)),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def sync_mood_name(self) -> None:
        try:
            from .presets import id_to_name
            self.attributes.mood = id_to_name(self.state.mood)
        except Exception:
            pass



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
        return _jsonable(asdict(self))
