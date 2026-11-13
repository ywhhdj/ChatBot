import WebSockets from "@/api/websocket/socket";
import notification from "@/utils/notification";
import { useUserStore } from "@/stores/user";
import { registerDefaultWebSocketEvents } from "./handlers/defaults";

const websocket = new WebSockets();

export function unregisterAllEventListeners(
  types: Record<string, (...args: any[]) => void>
) {
  Object.keys(types).forEach((type) => {
    websocket.removeEventListener(type, types[type as string]);
  });
}

//注册多事件{eventType, callback}
export function registerEventListeners(
  types: Record<string, (event: any) => void>
) {
  Object.keys(types).forEach((type) => {
    const callback = types[type as string] as (...args: any[]) => void;
    if (callback) {
      websocket.registerEventListener(type, callback);
    }
  });
}

export function connectWebSocket(url: string) {
  registerDefaultWebSocketEvents();
  websocket.connect(url, undefined, () => {
    useUserStore().clientId = "";
    notification.showError({
      title: "连接中断",
      message: "连接已中断，请检查后台服务",
    });
  });
}

export function closeWebSocket() {
  websocket.close();
}

export default websocket;