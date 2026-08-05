declare namespace User {
  type BaseConfig = {
    textSpeed: number;
    bgVolume: number;
    soundVolume: number;
    roleVolume: number;
    bgPath: string;
    soundPath: string;
    historyPath: string;
    animations: {
      snowFlakes: boolean;
    }
  }
  type DialogHistoryType = "message" | "reply";
  type DialogHistoryRole = "user" | "assistant";
  type DialogHistory = {
    id: string;
    type: DialogHistoryType;
    role: DialogHistoryRole;
    content: string;
  }
  type DialogHistoryMap = Record<string, DialogHistory[]> | null;
  type State = {
    config: BaseConfig;
    dialogHistory: DialogHistoryMap;
    clientId: string;
    serviceConfig: Record<API.ServiceName, {
      name: string;
      description?: string;
      value?: boolean | string;
      status?: ServiceStatus;
      config?: UI.ServiceConfigItem[];
    }> | null;
    isAutoSend: boolean;
  }
}