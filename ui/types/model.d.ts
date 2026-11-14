declare namespace Model {
  /** 与 resources/configs/providers/models/*.json 一一对应的能力名 */
  type Capability = "llm" | "tts" | "asr" | "ocr" | "embedding" | "image";

  /** params.scope：init 只在切换时生效，request 随每次请求下发 */
  type Scope = "init" | "request" | "unknown";

  type Value =
    | string
    | number
    | boolean
    | Record<string, any>
    | any[]
    | null
    | undefined;

  type ParamType =
    | "string"
    | "number"
    | "integer"
    | "boolean"
    | "object"
    | "array"
    | "unknown";

  interface EnumOption {
    value: string | number;
    label: string;
  }

  /** 由 provider.status / provider.get 的模型描述归一化出的单个参数 */
  interface ParamSpec {
    key: string;
    type: ParamType;
    label: string;
    description?: string;
    default?: Value;
    enum?: (string | number | EnumOption)[];
    min?: number;
    max?: number;
    step?: number;
    required?: boolean;
    hidden?: boolean;
    scope: Scope;
    ui?: "slider" | "number" | "select" | "text" | "secret" | "json" | "boolean";
    /** 凭据字段：只写不读，不回显、不落盘、不进日志 */
    secret?: boolean;
    /** 端点/连接字段由可信 JSON 决定，前端只读展示且不提交 */
    readonly?: boolean;
  }

  interface ModelItem {
    id: string;
    label: string;
    tags?: string[];
    params?: Record<string, any>;
  }

  interface ProviderMeta {
    label?: string;
    tags?: string[];
    deployment?: string;
    region?: string;
    description?: string;
    docs_url?: string;
  }

  /** provider.list_providers + provider.get + 离线描述归一化结果 */
  interface ProviderItem {
    name: string;
    label: string;
    deployment?: string;
    transport?: string;
    protocol?: string;
    runtime?: string;
    tags?: string[];
    available?: boolean;
    models: ModelItem[];
    meta?: ProviderMeta;
    params?: Record<string, any>;
    offline?: boolean;
  }

  /** provider.get 的 data（api.md §3.6，动态对象） */
  interface ProviderDetail {
    type?: string;
    name?: string;
    config?: Record<string, any>;
    meta?: ProviderMeta;
    models?: ModelItem[];
    selected_model?: string;
    available?: boolean;
    warnings?: string[];
  }

  /** provider.status 的 data，见 API.ProviderStatusData / docs/api.md §3.6 */
  interface ProviderStatus {
    capability?: string;
    name?: string;
    label?: string;
    deployment?: string;
    transport?: string;
    protocol?: string;
    runtime?: string;
    selected_model?: string;
    models?: ModelItem[];
    params?: Record<string, any>;
    ui?: Record<string, any>;
    download?: Record<string, any> | null;
    download_status?: Record<string, any> | null;
    available?: boolean;
    missing_env?: string[];
    warnings?: string[];
  }

  interface AdapterUsage {
    current?: string;
    model?: string;
    initialized?: boolean;
    usage?: Record<string, any>;
  }

  /** 页面级展示预设：能力标题、图标与 galgame 台词 */
  interface CapabilityPreset {
    capability: Capability;
    title: string;
    subtitle: string;
    icon: UI.IconType;
    intro: string;
    tags: string[];
  }

  /** 接口未就绪时的模型描述骨架，只用于展示，不参与任何请求 */
  interface OfflineProvider {
    name: string;
    label: string;
    tags: string[];
    deployment: string;
    models: ModelItem[];
    params?: string[];
  }

  interface OfflineDescription {
    providers: OfflineProvider[];
  }

  type PageState = "loading" | "ready" | "empty" | "error";
  type PendingAction = "load" | "apply" | "stop" | "download" | "refresh" | null;

  interface Notice {
    type: "info" | "success" | "error" | "warning";
    text: string;
  }
}
