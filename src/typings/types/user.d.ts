declare namespace User {
  type UIConfig = {
    textSpeed: number;
    bgVolume: number;
    soundVolume: number;
    roleVolume: number;
    bgPath: string;
    soundPath: string;
    historyPath: string;
    isAutoSend: boolean;
    animations: {
      snowFlakes: boolean;
      liquid: boolean;
    };
  };

  type DialogHistoryType = "message" | "reply";

  type DialogHistoryRole = "user" | "assistant";

  type DialogHistory = {
    id: string;
    type: DialogHistoryType;
    role: DialogHistoryRole;
    content: string;
  };

  type DialogHistoryMap = Record<string, DialogHistory[]> | null;

  type State = {
    config: UIConfig;
    dialogHistory: DialogHistoryMap;
    clientId: string;
    serviceConfig: Record<string, API.ServiceUIDescription>;
  };
}
