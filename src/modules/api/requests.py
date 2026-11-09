"""请求模型（api文档.md 各章节的请求体）。

约定
────
* 所有模型都给默认值，避免前端少传一个字段就 422。
* 不确定的结构用 `Dict[str, Any]` 透传，不让 API 层成为业务变更的瓶颈。
"""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from ..models import Role

class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())


# ───────────────────────── 系统 ─────────────────────────
class GcRequest(_Base):
    decay: bool = True          # 触发记忆衰减
    flush_log: bool = True      # 排空日志
    flush_memory: bool = True   # 排空记忆后台写入


# ───────────────────────── 配置 ─────────────────────────
class ConfigPatchRequest(_Base):
    """局部更新某个 section，只传要改的字段。"""

    values: Dict[str, Any] = Field(default_factory=dict)


class ConfigSaveRequest(_Base):
    file_path: Optional[str] = None


# ───────────────────────── 服务 ─────────────────────────
class ServiceConfigUpdateRequest(_Base):
    id: str = Field(..., description="服务 ID")
    config: Dict[str, Any] = Field(default_factory=dict)


class ServiceStartRequest(_Base):
    kwargs: Optional[Dict[str, Any]] = None


# ───────────────────────── 日志 ─────────────────────────
class LoggerLevelRequest(_Base):
    level: str = "INFO"


# ───────────────────────── 对话 / 推理 ─────────────────────────
class ChatRequest(_Base):
    text: str
    source: Literal["text", "asr", "ocr"] = "text"                 # text | asr | ocr
    session_id: str = "default"
    route: Optional[str] = None          # pure_chat | tool_call | mixed，None=自动路由
    stream: bool = False                 # api.md 6 节：非流式端点也可显式声明
    max_tokens: int = 1024
    temperature: float = 0.7


class ChatStreamRequest(ChatRequest):
    """流式对话（SSE）。与 ChatRequest 同构，仅 stream 默认 True。"""

    stream: bool = True


class TTSRequest(_Base):
    text: str
    format: str = "mp3"


class ASRRequest(_Base):
    audio: str = Field(..., description="base64 编码的音频字节")
    format: str = "wav"
    is_final: bool = True


class CommandRunRequest(_Base):
    text: str = Field(..., description="命令文本，如 `skill --id weather --city 深圳`")
    wait: bool = True


# ───────────────────────── 会话 ─────────────────────────
class SessionCreateRequest(_Base):
    name: str
    character_id: str = ""


class MessageAppendRequest(_Base):
    role: str = Role.USER
    content: str = ""
    source: str = "text"


class FlushRequest(_Base):
    session_id: Optional[str] = None


# ───────────────────────── 存档 ─────────────────────────
class SlotCreateRequest(_Base):
    name: str
    slot_id: Optional[str] = None


class SlotSectionUpdateRequest(_Base):
    data: Dict[str, Any] = Field(default_factory=dict)
    slot_id: str = ""


class SlotSyncRequest(_Base):
    session_id: Optional[str] = None


# ───────────────────────── 角色 ─────────────────────────
class CharacterCreateRequest(_Base):
    id: str
    name: str
    title: str = ""
    nickname_for_user: str = ""
    personality: str = ""
    background: str = ""
    speech_style: str = ""
    topics_allowed: Optional[List[str]] = None
    topics_forbidden: Optional[List[str]] = None
    catchphrases: Optional[List[str]] = None
    rules: Optional[List[str]] = None
    random_words: Optional[List[str]] = None
    action_verbs: Optional[List[str]] = None
    emotion_adjectives: Optional[List[str]] = None
    mood_modifiers: Optional[Dict[str, str]] = None
    affection: int = 50
    mood: int = 4


class CharacterUpdateRequest(_Base):
    name: Optional[str] = None
    title: Optional[str] = None
    nickname_for_user: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    speech_style: Optional[str] = None
    catchphrases: Optional[List[str]] = None
    rules: Optional[List[str]] = None
    topics_allowed: Optional[List[str]] = None
    topics_forbidden: Optional[List[str]] = None
    affection_level: Optional[int] = None
    mood_modifiers: Optional[Dict[str, str]] = None
    random_words: Optional[List[str]] = None
    action_verbs: Optional[List[str]] = None
    emotion_adjectives: Optional[List[str]] = None


class CharacterStateUpdateRequest(_Base):
    mood: Optional[int] = None
    affection: Optional[int] = None


# ───────────────────────── 记忆 ─────────────────────────
class MemorySearchRequest(_Base):
    query: str
    top_k: int = 8
    session_id: str = "default"


class MemoryLayersRequest(_Base):
    session_id: str = "default"
    detail_top_k: int = 8
    summary_limit: int = 8
    query: str = ""


# ───────────────────────── 技能 ─────────────────────────
class SkillExecuteRequest(_Base):
    params: Dict[str, Any] = Field(default_factory=dict)


# ───────────────────────── WebSocket ─────────────────────────
class WebSocketRequest(_Base):

    type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    client_id: str = ""


# ───────────────────────── 任务 ─────────────────────────
class TaskCancelRequest(_Base):
    """取消任务（尽力而为，同步任务无法强杀）。"""

    reason: str = ""

# ───────────────────────── PPT ─────────────────────────
class PptOutlineRequest(_Base):
    """生成大纲。"""

    topic: str
    pages: int = 10
    template_id: str = ""
    audience: str = ""
    scenario: str = ""
    style: str = ""
    material: str = ""


class PptRenderRequest(_Base):
    """按已有大纲渲染 pptx。"""

    deck: Dict[str, Any] = Field(default_factory=dict)
    topic: str = ""
    pages: int = 10
    template_id: str = ""
    style: str = ""
    colors: Dict[str, str] = Field(default_factory=dict)
    file_name: str = ""
    material: str = ""

# ───────────────────────── 供应商 ─────────────────────────
class ProviderSwitchRequest(_Base):
    provider: str
    config: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = Field(
        default=None, 
        description="指定模型 id；缺省用该 provider 的第一个模型"
    )

class ProviderDownloadRequest(_Base):
    model_id: Optional[str] = None
    force: bool = False


# ───────────────────────── 图像生成 ─────────────────────────
class ImageGenerateRequest(_Base):
    prompt: str
    size: str = "1024x1024"
    n: int = 1
    response_format: str = "url"
    provider: Optional[str] = None
    model_id: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

# ───────────────────────── 热键 / 快捷键 ─────────────────────────
class HotkeyValidateRequest(_Base):
    """录制中实时校验；action 为正在编辑的动作（排除自身冲突）。"""

    combo: str = ""
    action: str = ""


class HotkeyUpdateRequest(_Base):
    combo: str = ""
    revision: Optional[int] = None


class HotkeyBatchUpdateRequest(_Base):
    bindings: Dict[str, str] = Field(default_factory=dict)
    revision: Optional[int] = None


class HotkeyResetRequest(_Base):
    revision: Optional[int] = None