import { registerEventListeners } from "@/events/event/websocket";
import http from "@/utils/http";

export function getServiceList() {
  return http.get<API.ServiceInfoResponse<any[]>[]>("/service/list");
};

export function enableService(serviceId?: string) {
  return http.post<API.ServiceInfoResponse<{
    id: API.ServiceId;
  }>>("/service/enable", {
    id: serviceId,
  });
}

export function startService(serviceId?: string) {
  return http.post("/service/start", {
    id: serviceId,
  });
}

export function stopService(serviceId?: string) {
  return http.post("/service/stop", {
    id: serviceId,
  });
}

export function getServiceConfigInfo(serviceName?: string) {
  return http.get<API.ServiceConfigItem>("/service/config", {
    params: {
      name: serviceName,
    }
  });
}

enum QQBotEventType {
  QQ_BOT_INFO = "qq_bot.info",
}

type QQBotChatCallbacks = {
  onQQBotInfo: (data: API.QQBotInfo) => void;
}

export function qqBotChat(options: {
  callbacks?: QQBotChatCallbacks;
}) {
  const events = {
    [QQBotEventType.QQ_BOT_INFO]: options.callbacks?.onQQBotInfo,
  } as Record<string, (event: any) => void>;
  registerEventListeners(events);
}