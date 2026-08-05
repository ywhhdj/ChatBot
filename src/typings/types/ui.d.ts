declare namespace UI {
  type HomeTab = 'modelprovider' | 'monitor' | 'plugins' | 'services' | 'skills';
  type SettingsTab =
    'general' |
    'background' |
    'log' |
    'text' |
    'sound' |
    'character' |
    'history' |
    'adventure'
  type ServiceTab = 'live2d' | 'qqbot';
  type ModelProviderTab = 'llm' | 'tts' | 'asr';
  type ButtonType = 'big' | 'menu' | 'nav' | 'select' | 'delete' | 'add' | 'save' | 'start' | 'close' | 'home' | 'game' | 'model' | "game";
  type IconType ='record' | "communication" | 'speed'
    | 'microphone'
    | 'none'
    | 'character'
    | 'text'
    | 'background'
    | 'sound'
    | 'history'
    | 'box'
    | 'play'
    | 'save'
    | 'advance'
    | 'close'
    | 'schedule'
    | 'update'
    | 'volume'
    | 'menu'
    | 'home'
    | 'plugin'
    | 'record'
    | 'chat'
    | 'chatgpt'
    | 'deepseek'
    | "chip"
    | "url"
    | "key"
    | "delete"
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
  type NotificationType = 'info' | 'success' | 'error' | 'warning';
  interface NotificationOptions {
    title?: string;
    type?: NotificationType;
    duration?: number;
    avatarUrl?: string;
    message: string;
  }
  interface State {
    currentHomeTab: HomeTab;
    currentSettingsTab: SettingsTab;
    currentModelProvider: ModelProviderTab;
    currentServiceTab: ServiceTab;
  }
  type TempState = {
    bgList: Background[];
    musicList: Music[];
  }
  type ServiceInfo = {
    id: string;
    name: string;
    description: string;
    status: ServiceStatus;
    config: ConfigItem[];
    icon?: string;
  }
  type ServiceConfigItem = {
    type: 'boolean' | 'string' | 'select'
    name: string
    description?: string
    value: boolean | string
    options?: string[]
  }
}