/**
 * 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
 * 重新生成: python scripts/api/generate.py
 */

declare namespace API {
  interface ApiResponse<T = unknown> {
    ok?: boolean;
    code?: number;
    message?: string;
    data?: T | null;
    request_id?: string;
    ts?: number;
  }

  interface ASRRequest {
    audio: string;
    format?: string;
    is_final?: boolean;
  }

  interface ASRResultData {
    text?: string;
  }

  interface AbilityStatus {
    initialized?: boolean;
    provider?: string;
    detail?: string;
  }

  interface AuditServiceData {
    id?: string;
    name?: string;
    running?: boolean;
    tools?: AuditToolData[];
  }

  interface AuditToolData {
    service?: string;
    method?: string;
    label?: string;
    parameters?: Record<string, any>;
    required?: string[];
  }

  interface AuditTreeData {
    services?: AuditServiceData[];
    total_tools?: number;
  }

  interface Body_patch_section_api_config__section__patch {
    payload?: ConfigPatchRequest;
    values?: Record<string, any> | null;
  }

  interface CPUInfoData {
    name?: string;
    tier?: string;
    score?: number;
    cores?: number;
    mhz?: number;
  }

  interface CharacterAttributesData {
    name?: string;
    title?: string;
    nickname_for_user?: string;
    personality?: string;
    background?: string;
    speech_style?: string;
    catchphrases?: string[];
    rules?: string[];
    topics_allowed?: string[];
    topics_forbidden?: string[];
    affection_level?: number;
    mood?: string;
    random_words?: string[];
    action_verbs?: string[];
    emotion_adjectives?: string[];
  }

  interface CharacterCreateRequest {
    id: string;
    name: string;
    title?: string;
    nickname_for_user?: string;
    personality?: string;
    background?: string;
    speech_style?: string;
    topics_allowed?: string[] | null;
    topics_forbidden?: string[] | null;
    catchphrases?: string[] | null;
    rules?: string[] | null;
    random_words?: string[] | null;
    action_verbs?: string[] | null;
    emotion_adjectives?: string[] | null;
    mood_modifiers?: Record<string, string> | null;
    affection?: number;
    mood?: number;
  }

  interface CharacterInfoData {
    id: string;
    name?: string;
    status?: string;
    attributes?: CharacterAttributesData | null;
    state?: CharacterStateData | null;
  }

  interface CharacterListData {
    characters?: CharacterInfoData[];
    total?: number;
    current?: string | null;
  }

  interface CharacterStateData {
    mood?: number;
    affection?: number;
    total_messages?: number;
    total_tasks?: number;
    last_interaction?: number;
    pending_tasks?: number;
  }

  interface CharacterStateUpdateRequest {
    mood?: number | null;
    affection?: number | null;
  }

  interface CharacterUpdateRequest {
    name?: string | null;
    title?: string | null;
    nickname_for_user?: string | null;
    personality?: string | null;
    background?: string | null;
    speech_style?: string | null;
    catchphrases?: string[] | null;
    rules?: string[] | null;
    topics_allowed?: string[] | null;
    topics_forbidden?: string[] | null;
    affection_level?: number | null;
    mood_modifiers?: Record<string, string> | null;
    random_words?: string[] | null;
    action_verbs?: string[] | null;
    emotion_adjectives?: string[] | null;
  }

  interface ChatOptions {
    text: string;
    source?: string;
    session_id?: string;
    route?: string | null;
    stream?: boolean;
    max_tokens?: number;
    temperature?: number;
  }

  interface ChatResultData {
    text?: string;
    route?: string;
    character_id?: string;
    mood?: number;
    commands_executed?: unknown[];
    tokens_estimate?: number;
    elapsed_ms?: number;
  }

  interface CommandResultData {
    success?: boolean;
    results?: Record<string, any>[];
    summary?: string;
    rounds?: number;
    stop_reason?: string;
  }

  interface CommandRunRequest {
    text: string;
    wait?: boolean;
  }

  /** 局部更新某个 section，只传要改的字段。 */
  interface ConfigPatchRequest {
    values?: Record<string, any>;
  }

  interface ConfigSaveRequest {
    file_path?: string | null;
  }

  interface DetailedMemoryItem {
    id?: string;
    content?: string;
    score?: number;
    role?: string;
    created_at?: number;
  }

  interface DeviceInfoData {
    cpu?: CPUInfoData;
    gpu?: GPUInfoData;
    overall?: Record<string, any>;
    recommended_fps?: number;
    ram_mb?: number;
  }

  interface FlushRequest {
    session_id?: string | null;
  }

  interface GPUInfoData {
    name?: string;
    device_id?: string;
    tier?: string;
    score?: number;
    vendor_id?: string;
  }

  interface GcData {
    decay?: boolean;
    log_flushed?: boolean;
    memory_flushed?: boolean;
  }

  interface GcRequest {
    decay?: boolean;
    flush_log?: boolean;
    flush_memory?: boolean;
  }

  interface HTTPValidationError {
    detail?: ValidationError[];
  }

  interface HealthData {
    status?: string;
    web?: Record<string, any>;
    scheduler?: Record<string, any>;
    main_thread?: Record<string, any>;
    memory?: Record<string, any>;
    services?: Record<string, any>;
  }

  interface InfoData {
    name?: string;
    version?: string;
    config_path?: string;
    data_dir?: string;
    log_dir?: string;
    python?: string;
    adapters?: Record<string, any>;
  }

  interface LoggerLevelData {
    level?: string;
    levels?: string[];
  }

  interface LoggerStatsData {
    total?: number;
    dropped?: number;
    queue?: number;
    file_enabled?: boolean;
    by_level?: Record<string, number>;
  }

  interface MemoryLayersData {
    short_term?: string;
    long_term?: string;
    detailed?: DetailedMemoryItem[];
  }

  interface MemorySearchData {
    query?: string;
    items?: DetailedMemoryItem[];
    total?: number;
  }

  interface MemorySearchRequest {
    query: string;
    top_k?: number;
    session_id?: string;
  }

  interface MemoryStatsData {
    records?: number;
    compressed?: number;
    tokens_estimate?: number;
    backend?: string;
    short_term_days?: number;
  }

  interface MessageAppendRequest {
    role?: string;
    content?: string;
    source?: string;
  }

  interface MessageItem {
    role?: string;
    content?: string;
    timestamp?: number;
    source?: string;
  }

  interface MessageListData {
    messages?: MessageItem[];
    total?: number;
  }

  interface PipelineSwitchRequest {
    provider: string;
    config?: Record<string, any> | null;
  }

  interface PptDownloadData {
    file_name?: string;
    file_path?: string;
    size?: number;
    content_base64?: string;
  }

  interface PptJobData {
    task_id?: string;
    state?: string;
    result?: Record<string, any>;
    error?: string;
  }

  interface PptOutlineData {
    title?: string;
    subtitle?: string;
    slide_count?: number;
    deck?: Record<string, any>;
  }

  /** 生成大纲。 */
  interface PptOutlineRequest {
    topic: string;
    pages?: number;
    template_id?: string;
    audience?: string;
    scenario?: string;
    style?: string;
    material?: string;
  }

  interface PptRenderData {
    ok?: boolean;
    file_path?: string;
    file_name?: string;
    slide_count?: number;
    template_id?: string;
    message?: string;
    task_id?: string;
  }

  /** 按已有大纲渲染 pptx。 */
  interface PptRenderRequest {
    deck?: Record<string, any>;
    topic?: string;
    pages?: number;
    template_id?: string;
    style?: string;
    colors?: Record<string, string>;
    file_name?: string;
    material?: string;
  }

  interface PptTemplateListData {
    total?: number;
    templates?: Record<string, any>[];
  }

  interface RequestStatusData {
    llm?: AbilityStatus;
    tts?: AbilityStatus;
    asr?: AbilityStatus;
    ready?: boolean;
  }

  interface ServiceActionData {
    id: string;
    state: string;
  }

  interface ServiceConfigUpdateRequest {
    config?: Record<string, any>;
  }

  interface ServiceInfoData {
    id: string;
    name?: string;
    description?: string;
    state?: string;
    main_thread?: boolean;
    config?: Record<string, any> | null;
  }

  interface ServiceListData {
    services?: ServiceInfoData[];
    total?: number;
  }

  interface ServiceStartRequest {
    args?: unknown[] | null;
    kwargs?: Record<string, any> | null;
  }

  interface ServiceUIDescription {
    id: string;
    name?: string;
    description?: string;
    fields?: {
      type: string;
      key: string;
      default: any;
      label: string;
      description?: string;
      options?: string[];
      [key: string]: any;
    }[];
  }

  interface SessionCreateRequest {
    name: string;
    character_id?: string;
  }

  interface SessionInfoData {
    id: string;
    name?: string;
    character_id?: string;
    created_at?: number;
    updated_at?: number;
    message_count?: number;
    metadata?: Record<string, any>;
  }

  interface SessionListData {
    sessions?: SessionInfoData[];
    total?: number;
    current?: string | null;
  }

  interface SkillExecuteData {
    id: string;
    ok?: boolean;
    result?: Record<string, any> | null;
    error?: string | null;
  }

  interface SkillExecuteRequest {
    params?: Record<string, any>;
  }

  interface SkillInfoData {
    id: string;
    name?: string;
    description?: string;
    version?: string;
    author?: string;
    license?: string;
    exec_type?: string;
    active?: boolean;
    executable?: boolean;
    reason?: string;
  }

  interface SkillListData {
    skills?: SkillInfoData[];
    total?: number;
    pending?: Record<string, string>;
  }

  interface SlotActionData {
    id: string;
    ok: boolean;
  }

  interface SlotCreateRequest {
    name: string;
    slot_id?: string | null;
  }

  interface SlotInfoData {
    id: string;
    name?: string;
    meta?: SlotMeta;
  }

  interface SlotListData {
    slots?: SlotInfoData[];
    total?: number;
    current?: string | null;
  }

  interface SlotMeta {
    create_time?: string;
    update_time?: string;
    last_chat?: string;
    description?: string;
    snapshot_path?: string;
  }

  interface StatsData {
    uptime_sec?: number;
    log?: Record<string, any>;
    scheduler?: Record<string, any>;
    websocket?: Record<string, any>;
    memory?: Record<string, any>;
  }

  interface SwitchResultData {
    success?: boolean;
    type?: string;
    name?: string;
    config?: Record<string, any> | null;
    errors?: string[];
  }

  interface TTSRequest {
    text: string;
    format?: string;
  }

  interface TTSResultData {
    audio?: string;
    format?: string;
    bytes?: number;
  }

  interface TaskStatusData {
    task_id: string;
    state?: string;
    result?: unknown;
    error?: string | null;
    elapsed_ms?: number;
  }

  interface ToolData {
    services?: Record<string, any>;
    total?: number;
  }

  interface ValidationError {
    loc: Array<string | number>;
    msg: string;
    type: string;
    input?: unknown;
    ctx?: Record<string, unknown>;
  }

  type LogSource= "ai_service" | "backend" | "frontend" | "network" | "system" | "unknown";

  interface LogRecord {
    timestamp?: string;
    level:str
    log_name:str
    message:str
    source?: LogSource;
    stack_trace?: string;
    metadata?: Record<string, any>;
  }

}
