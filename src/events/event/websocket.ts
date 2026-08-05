import WebSockets from "@/utils/socket";
export const websocket = new WebSockets()

export function unregisterAllEventListeners(types: Record<string, (...args: any[]) => void>) {
  Object.keys(types).forEach(type => {
    websocket.removeEventListener(type, types[type as string]);
  });
}

//注册多事件{eventType, callback}
export function registerEventListeners(types: Record<string, (event: any) => void>) {
  Object.keys(types).forEach(type => {
    const callback = types[type as string] as (...args: any[]) => void;
    if (callback) {
      websocket.registerEventListener(type, callback);
    }
  });
}

