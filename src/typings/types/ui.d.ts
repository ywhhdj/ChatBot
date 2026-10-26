declare namespace UI {
  type MoreTab =
    | "modelprovider"
    | "monitor"
    | "plugins"
    | "services"
    | "skills";
  type SettingsTab =
    | "general"
    | "character"
    | "history"
    // | "adventure"
    | "save"
    | "background"
    | "sound"
    | "more";
  type ServiceTab = "live2d" | "qqbot";
  type ModelProviderTab = "llm" | "tts" | "asr";

  type ButtonType =
    | "big"
    | "menu"
    | "nav"
    | "select"
    | "delete"
    | "add"
    | "save"
    | "start"
    | "close"
    | "home"
    | "game"
    | "model"
    | "game";
  type IconType =
    | "code"
    | "aside"
    | "collapse"
    | "list"
    | "more"
    | "skill"
    | "copy"
    | "record"
    | "communication"
    | "speed"
    | "microphone"
    | "none"
    | "character"
    | "text"
    | "background"
    | "sound"
    | "history"
    | "box"
    | "play"
    | "save"
    | "advance"
    | "close"
    | "schedule"
    | "update"
    | "volume"
    | "settings"
    | "home"
    | "plugin"
    | "record"
    | "chat"
    | "chatgpt"
    | "deepseek"
    | "chip"
    | "url"
    | "key"
    | "delete"
    | "log";
  interface MenuItem {
    type?: ButtonType;
    name?: string;
    icon?: IconType;
    clickAction?: () => void;
    children?: MenuItem[];
    iconBg?: string;
  }
  interface Music {
    name: string;
    url: string;
    progress: number;
  }
  interface Background {
    index: number;
    name?: string;
    url: string;
    duration?: number;
  }
  type NotificationType = "info" | "success" | "error" | "warning";
  interface NotificationOptions {
    title?: string;
    type?: NotificationType;
    duration?: number;
    avatarUrl?: string;
    message: string;
  }
  type State = {
    currentTab: {
      settings: SettingsTab;
      modelProvider: ModelProviderTab;
      service: ServiceTab;
      more: MoreTab;
    };
  };
  type TempState = {
    bgList: Background[];
    musicList: Music[];
  };
  type ServiceInfo = {
    id: string;
    name: string;
    description: string;
    status: ServiceStatus;
    config: ConfigItem[];
    icon?: string;
  };
  type ServiceConfigItem = {
    type: "boolean" | "string" | "select";
    name: string;
    description?: string;
    value: boolean | string;
    options?: string[];
  };

  export type ChatRole = "user" | "assistant" | "system";

  export type ToolStatus =
    | "pending"
    | "running"
    | "success"
    | "skipped"
    | "error";

  type ToolCallItem = {
    id: string;
    service: string;
    method: string;
    raw: string;
    status: ToolStatus;
    params: Record<string, any>;
    result?: any;
    error?: string;
    elapsedMs?: number;
    // 用于卡片摘要的人话标题，如 obs.switch_scene -> "切换OBS场景"
    label?: string;
  };

  type ChatMessage = {
    id: string;
    role: ChatRole;
    // assistant 的 markdown 正文；可流式追加
    content: string;
    // 关联的工具体列表（assistant 工具调用过程）
    tools?: ToolCallItem[];
    // 整体状态：思考/调用工具/回答中/完成/失败
    phase?: "thinking" | "tooling" | "answering" | "done" | "error";
    createdAt: number;
  };

  type PanelBlock = {
    id: string;
    kind: "markdown" | "tool" | "tool-summary";
    messageId: string;
    content?: string;
    tool?: ToolCallItem;
    tools?: ToolCallItem[];
  };
}
