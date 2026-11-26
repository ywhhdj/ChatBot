from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from ..core.routes.models import RouteType


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


def _coerce_field(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
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

    与 UserContext 分工明确，避免两套历史各自裁剪导致不一致：
        CharacterState.messages —— 该角色的长期对话记忆
        UserContext.messages   —— 本轮/近期上下文 + 记忆系统注入
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
        # 原地裁剪，避免每次超限都复制整段历史（PR-1 性能优化）。
        # max_memory 非法值（<=0）时回落到 200，防止 del 把列表清空。
        limit = self.max_memory if isinstance(self.max_memory, int) and self.max_memory > 0 else 200
        if len(self.messages) > limit:
            del self.messages[:-limit]
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
        if n <= 0:
            return []
        window = self.messages[-n:] if n else []
        return [
            {
                "role": str(m.get("role", "")),
                "content": str(m.get("content", "")),
            }
            for m in window if isinstance(m, dict)
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
        """读档恢复：按字段白名单构造，未知字段直接忽略。"""
        raw = data if isinstance(data, dict) else {}
        char = cls(str(raw.get("id", "") or "").strip())
        char.name = str(raw.get("name", "") or "").strip()
        char.avatar = str(raw.get("avatar", "") or "")

        attr_fields = set(CharacterAttributes.__dataclass_fields__)
        attr_raw = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
        char.attributes = CharacterAttributes(
            **{
                k: _coerce_field(v) for k, 
                v in attr_raw.items() 
                if k in attr_fields
            }
        )

        state_fields = set(CharacterState.__dataclass_fields__)
        state_raw = raw.get("state") if isinstance(raw.get("state"), dict) else {}
        state_kwargs: Dict[str, Any] = {
            k: _coerce_field(v) for k, v in state_raw.items() if k in state_fields
        }
        status = state_kwargs.pop("status", None)
        char.state = CharacterState(**state_kwargs)
        try:
            raw_status = getattr(status, "value", status)
            char.state.status = (
                CharacterStatus(str(raw_status)) if raw_status is not None
                else CharacterStatus.IDLE
            )
        except (ValueError, TypeError):
            char.state.status = CharacterStatus.IDLE
        if not char.state.character_id:
            char.state.character_id = char.id

        try:
            char.created_at = float(raw.get("created_at", 0.0) or 0.0)
            char.updated_at = float(raw.get("updated_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            char.created_at = char.updated_at = time.time()
        char.__post_init__()
        char.sync_mood_name()
        return char

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "attributes": _jsonable(asdict(self.attributes)),
            "state": _jsonable(asdict(self.state)),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "avatar": self.avatar,
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
