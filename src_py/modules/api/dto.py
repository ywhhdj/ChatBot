"""响应数据模型（api文档.md 各章节的 `data` 结构）。

与 `requests.py` 分工：

    requests.py  请求体（前端 → 后端）
    models.py    响应 data（后端 → 前端，外层信封见 `response.ApiResponse`）

`controllers/system.py` 用的是 `from ..models import ...`，
`controllers/skill.py` 原代码写 `from ..requests import SkillInfoData ...`
（响应模型错放在 requests 里），这里统一归位到 models.py。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from ..models import Role


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())


# ───────────────────────── 系统 ─────────────────────────
class ComponentHealth(_Base):
    ready: bool = False
    detail: Dict[str, Any] = Field(default_factory=dict)


class HealthData(_Base):
    status: str = "healthy"           # healthy | degraded | unhealthy
    web: Dict[str, Any] = Field(default_factory=dict)
    scheduler: Dict[str, Any] = Field(default_factory=dict)
    main_thread: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)
    services: Dict[str, Any] = Field(default_factory=dict)


class InfoData(_Base):
    name: str = "ChatBot"
    version: str = "0.1.0"
    config_path: str = ""
    data_dir: str = ""
    log_dir: str = ""
    python: str = ""
    adapters: Dict[str, Any] = Field(default_factory=dict)


class StatsData(_Base):
    uptime_sec: float = 0.0
    log: Dict[str, Any] = Field(default_factory=dict)
    scheduler: Dict[str, Any] = Field(default_factory=dict)
    websocket: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)


class GcData(_Base):
    decay: bool = False
    log_flushed: bool = False
    memory_flushed: bool = False


# ───────────────────────── 配置 ─────────────────────────
class ConfigSchemaItem(_Base):
    name: str
    description: Optional[str] = None
    value: Any = None


# ───────────────────────── 管道 ─────────────────────────
class ProviderInfo(_Base):
    name: str
    config: Optional[Dict[str, Any]] = None


class AdapterInfo(_Base):
    type: str
    providers: List[str] = Field(default_factory=list)
    current: Optional[str] = None


class SwitchResultData(_Base):
    success: bool = False
    type: str = ""
    name: str = ""
    config: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)


# ───────────────────────── 服务 ─────────────────────────
class ServiceInfoData(_Base):
    id: str
    name: str = ""
    description: str = ""
    state: str = "stopped"
    main_thread: bool = False
    config: Optional[Dict[str, Any]] = None


class ServiceListData(_Base):
    services: List[ServiceInfoData] = Field(default_factory=list)
    total: int = 0


class ToolData(_Base):
    services: Dict[str, Any] = Field(default_factory=dict)
    total: int = 0


class ServiceActionData(_Base):
    id: str
    state: str

class ServiceUIDescription(_Base):
    id: str
    name: str = ""
    description: str = ""
    fields: List[Dict[str, Any]] = Field(default_factory=list)


# ───────────────────────── 日志 ─────────────────────────
class LogRecordData(_Base):
    level: str = "INFO"
    message: str = ""
    source: str = ""
    ts: float = 0.0


class LoggerStatsData(_Base):
    total: int = 0
    dropped: int = 0
    queue: int = 0
    file_enabled: bool = False
    by_level: Dict[str, int] = Field(default_factory=dict)


class LoggerLevelData(_Base):
    level: str = "INFO"
    levels: List[str] = Field(default_factory=list)


# ───────────────────────── 对话 / 推理 ─────────────────────────
class ChatResultData(_Base):
    text: str = ""
    route: str = ""
    character_id: str = ""
    mood: int = 4
    commands_executed: List[Any] = Field(default_factory=list)
    tokens_estimate: int = 0
    elapsed_ms: int = 0


class TTSResultData(_Base):
    audio: str = ""          # base64
    format: str = "mp3"
    bytes: int = 0


class ASRResultData(_Base):
    text: str = ""


class AbilityStatus(_Base):
    initialized: bool = False
    provider: str = ""
    detail: str = ""


class RequestStatusData(_Base):
    llm: AbilityStatus = Field(default_factory=AbilityStatus)
    tts: AbilityStatus = Field(default_factory=AbilityStatus)
    asr: AbilityStatus = Field(default_factory=AbilityStatus)
    ready: bool = False


class CommandResultData(_Base):
    success: bool = False
    results: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    rounds: int = 0
    stop_reason: str = ""


# ───────────────────────── 会话 ─────────────────────────
class SessionInfoData(_Base):
    id: str
    name: str = ""
    character_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    message_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageItem(_Base):
    role: str = Role.USER
    content: str = ""
    timestamp: float = 0.0
    source: str = "text"


class MessageListData(_Base):
    messages: List[MessageItem] = Field(default_factory=list)
    total: int = 0


class SessionListData(_Base):
    sessions: List[SessionInfoData] = Field(default_factory=list)
    total: int = 0
    current: Optional[str] = None


# ───────────────────────── 存档 ─────────────────────────
class SlotMeta(_Base):
    create_time: str = ""
    update_time: str = ""
    last_chat: str = ""
    description: str = ""
    snapshot_path: str = ""


class SlotInfoData(_Base):
    id: str
    name: str = ""
    meta: SlotMeta = Field(default_factory=SlotMeta)


class SlotListData(_Base):
    slots: List[SlotInfoData] = Field(default_factory=list)
    total: int = 0
    current: Optional[str] = None


class SlotActionData(_Base):
    id: str
    ok: bool


# ───────────────────────── 角色 ─────────────────────────
class CharacterAttributesData(_Base):
    name: str = ""
    title: str = ""
    nickname_for_user: str = ""
    personality: str = ""
    background: str = ""
    speech_style: str = ""
    catchphrases: List[str] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)
    topics_allowed: List[str] = Field(default_factory=list)
    topics_forbidden: List[str] = Field(default_factory=list)
    affection_level: int = 50
    mood: str = "平静"
    random_words: List[str] = Field(default_factory=list)
    action_verbs: List[str] = Field(default_factory=list)
    emotion_adjectives: List[str] = Field(default_factory=list)


class CharacterStateData(_Base):
    mood: int = 4
    affection: int = 50
    total_messages: int = 0
    total_tasks: int = 0
    last_interaction: float = 0.0
    pending_tasks: int = 0


class CharacterInfoData(_Base):
    id: str
    name: str = ""
    status: str = "idle"
    attributes: Optional[CharacterAttributesData] = None
    state: Optional[CharacterStateData] = None


class CharacterListData(_Base):
    characters: List[CharacterInfoData] = Field(default_factory=list)
    total: int = 0
    current: Optional[str] = None


# ───────────────────────── 记忆 ─────────────────────────
class DetailedMemoryItem(_Base):
    id: str = ""
    content: str = ""
    score: float = 0.0
    role: str = ""
    created_at: float = 0.0


class MemoryLayersData(_Base):
    short_term: str = ""
    long_term: str = ""
    detailed: List[DetailedMemoryItem] = Field(default_factory=list)


class MemorySearchData(_Base):
    query: str = ""
    items: List[DetailedMemoryItem] = Field(default_factory=list)
    total: int = 0


class CompressedItem(_Base):
    id: str = ""
    summary: str = ""
    created_at: float = 0.0
    original_count: int = 0


class MemoryStatsData(_Base):
    records: int = 0
    compressed: int = 0
    tokens_estimate: int = 0
    backend: str = ""
    short_term_days: int = 2


# ───────────────────────── 技能 ─────────────────────────
class SkillInfoData(_Base):
    id: str
    name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    license: str = ""
    exec_type: str = "none"
    active: bool = False
    executable: bool = True
    reason: str = ""


class SkillListData(_Base):
    skills: List[SkillInfoData] = Field(default_factory=list)
    total: int = 0
    pending: Dict[str, str] = Field(default_factory=dict)


class SkillExecuteData(_Base):
    id: str
    ok: bool = False
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ───────────────────────── 任务 ─────────────────────────
class TaskStatusData(_Base):
    task_id: str
    state: str = "pending"      # pending|running|done|failed|timeout|cancelled
    result: Any = None
    error: Optional[str] = None
    elapsed_ms: int = 0

# ───────────────────────── PPT ─────────────────────────
class PptTemplateData(_Base):
    id: str = ""
    name: str = ""
    description: str = ""
    scenario: str = ""
    colors: Dict[str, str] = Field(default_factory=dict)
    font_title: str = ""
    font_body: str = ""
    title_size: int = 40
    body_size: int = 18


class PptTemplateListData(_Base):
    total: int = 0
    templates: List[Dict[str, Any]] = Field(default_factory=list)


class PptOutlineData(_Base):
    title: str = ""
    subtitle: str = ""
    slide_count: int = 0
    deck: Dict[str, Any] = Field(default_factory=dict)


class PptRenderData(_Base):
    ok: bool = False
    file_path: str = ""
    file_name: str = ""
    slide_count: int = 0
    template_id: str = ""
    message: str = ""
    task_id: str = ""


class PptJobData(_Base):
    task_id: str = ""
    state: str = "pending"
    result: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class PptDownloadData(_Base):
    file_name: str = ""
    file_path: str = ""
    size: int = 0
    content_base64: str = ""

# ───────────────────────── Device ─────────────────────────
class CPUInfoData(_Base):
    name: str = ""
    tier: str = ""
    score: int = 0
    cores: int = 0
    mhz: int = 0

class GPUInfoData(_Base):
    name: str = ""
    device_id: str = ""
    tier: str = ""
    score: int = 0
    vendor_id: str = ""


class DeviceInfoData(_Base):
    cpu: CPUInfoData = Field(default_factory=CPUInfoData)
    gpu: GPUInfoData = Field(default_factory=GPUInfoData)
    overall: Dict[str, Any] = Field(default_factory=dict)
    recommended_fps: int = 0
    ram_mb: int = 0

# ───────────────────────── 审计 ─────────────────────────

class AuditToolData(_Base):
    service: str = ""
    method: str = ""
    label: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)


class AuditServiceData(_Base):
    id: str = ""
    name: str = ""
    running: bool = False
    tools: List[AuditToolData] = Field(default_factory=list)


class AuditTreeData(_Base):
    services: List[AuditServiceData] = Field(default_factory=list)
    total_tools: int = 0