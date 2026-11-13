import websocket from "@/api/websocket/index";
import logger from "@/composables/LogForwarder";
import { WebSocketEvent } from "@/typings/enums";
import notification from "@/utils/notification";
import { useUserStore } from "@/stores/user";

export function registerDefaultWebSocketEvents() {
  websocket.sendCallback = (data: any) => {
    if (data) {
      return {
        ...data,
        client_id: useUserStore().clientId || "",
      };
    } else {
      return {
        client_id: useUserStore().clientId || "",
      };
    }
  };

  websocket.registerEventListener(WebSocketEvent.GET_LOG, (data: any) => {
    logger?.receiveBackendLog({
      log_name: data.log_name,
      timestamp: data.timestamp,
      level: data.level,
      message: data.message,
      source: data.source || "backend",
      metadata: data.metadata,
    });
  });

  websocket.registerEventListener(
    WebSocketEvent.CONNECT,
    (data: WebSocketAPI.WebSocketConnectResponse) => {
      useUserStore().clientId = data.client_id;
      notification.showSuccess({
        title: "连接成功",
        message: "已连接到服务器",
      });
    }
  );
}
