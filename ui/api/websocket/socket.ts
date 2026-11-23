import { WebSocketEvent } from "@/typings/enums";
import { DESKTOP_DEVICE, getToken, getUid } from "@/utils/identity";

type FrameHandler = (data: any, frame: WebSocketAPI.WebSocketResponse) => void;

export default class WebSockets {
  private url: string = "";
  private socket: WebSocket | null = null;
  public heartbeatInterval: number = 30000;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private reconnectDelay: number = 1000;
  private heartbeatIntervalId: number | null = null;
  private reconnectTimer: number | null = null;
  private _sendCallback: ((data: any) => any) | null = null;
  private eventCallbacks: Map<string, Set<FrameHandler>> = new Map();
  private onErrorCallback?: (event: Event) => void;
  private onCloseCallback?: (event: Event) => void;
  private _closedByUser = false;
  private _clientId = "";
  private _uid = "";
  private _registered = false;

  constructor() {
    this._uid = getUid();
  }

  set sendCallback(callback: (data: any) => any) {
    this._sendCallback = callback;
  }

  get uid(): string { return this._uid; }
  get clientId(): string { return this._clientId; }
  get registered(): boolean { return this._registered; }
  get readyState(): number | undefined { return this.socket?.readyState; }

  connect(
    url: string,
    onErrorCallback?: (event: Event) => void,
    onCloseCallback?: (event: Event) => void,
  ): void {
    this.url = url;
    this.onErrorCallback = onErrorCallback;
    this.onCloseCallback = onCloseCallback;
    this._closedByUser = false;
    this.reconnectAttempts = 0;
    this._registered = false;
    this._open();
  }

  private _open(): void {
    this._clearReconnectTimer();
    try {
      const ws = new WebSocket(this.url);
      this.socket = ws;
      this._bind(ws);
    } catch (error) {
      console.error("[WebSocket] connect failed:", error);
      this.attemptReconnect();
    }
  }

  /** 每次建连（含重连）都要绑定，否则重连后是「哑连接」。 */
  private _bind(ws: WebSocket): void {
    ws.addEventListener("open", () => {
      this.reconnectAttempts = 0;
      console.log("[WebSocket] connected:", this.url);
    });
    ws.addEventListener("close", (event: CloseEvent) => {
      if (this.socket !== ws) return;
      this.stopHeartbeat();
      this._registered = false;
      this._clientId = "";
      this.socket = null;
      this.onCloseCallback?.(event);
      this.attemptReconnect();
    });
    ws.addEventListener("error", (event: Event) => {
      console.error("[WebSocket] error:", event);
      this.onErrorCallback?.(event);
    });
    ws.addEventListener("message", (event: MessageEvent<string>) => {
      let frame: WebSocketAPI.WebSocketResponse | null = null;
      try {
        frame = JSON.parse(event.data) as WebSocketAPI.WebSocketResponse;
      } catch (error) {
        console.error("[WebSocket] bad frame:", error);
        return;
      }
      this.handleMessage(frame);
    });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatIntervalId = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        try {
          this.send({ type: WebSocketEvent.HEARTBEAT });
        } catch {
          this.stopHeartbeat();
        }
      }
    }, this.heartbeatInterval || 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatIntervalId !== null) {
      clearInterval(this.heartbeatIntervalId);
      this.heartbeatIntervalId = null;
    }
  }

  private handleMessage(frame: WebSocketAPI.WebSocketResponse): void {
    if (!frame || typeof frame.type !== "string") return;
    const data = frame.data ?? {};

    // 丢弃自己被回灌的设备帧；普通帧 from_id 为空，不受影响
    const from = (frame.from_id || (data as any)?.from_id || "") as string;
    if (from && from === this._clientId) return;

    switch (frame.type) {
      case "pong":
        break;
      case WebSocketEvent.CONNECT:
        this._clientId = String((data as any)?.client_id || "");
        this.emitEvent(frame.type, data, frame);
        this.startHeartbeat();
        // 连接后首帧：REGISTER 属 CONTROL_EVENTS，不占 inflight
        this.sendRegister();
        break;
      case WebSocketEvent.REGISTER:
        this._registered = frame.ok !== false;
        this.emitEvent(frame.type, data, frame);
        break;
      default:
        this.emitEvent(frame.type, data, frame);
    }
  }

  private sendRegister(): void {
    const frame: WebSocketAPI.WebSocketRequest<WebSocketAPI.RegisterData> = {
      type: WebSocketEvent.REGISTER,
      data: { uid: this._uid, device: DESKTOP_DEVICE, token: getToken() },
      timestamp: Date.now(),
    };
    try {
      // 控制帧绕过 sendCallback：不注入 client_id，也不做业务帧校验
      this.socket?.send(JSON.stringify(frame));
    } catch (error) {
      console.error("[WebSocket] register failed:", error);
    }
  }

  private attemptReconnect(): void {
    if (this._closedByUser || this.reconnectTimer !== null) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log("[WebSocket] max reconnection attempts reached");
      return;
    }
    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * 2 ** (this.reconnectAttempts - 1),
      15000,
    );
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this._open();
    }, delay);
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  public registerEventListener(eventType: string, callback: FrameHandler): void {
    if (!this.eventCallbacks.has(eventType)) {
      this.eventCallbacks.set(eventType, new Set());
    }
    this.eventCallbacks.get(eventType)!.add(callback);
  }

  public removeEventListener(eventType: string, callback?: FrameHandler): void {
    const callbacks = this.eventCallbacks.get(eventType);
    if (callbacks && callback) callbacks.delete(callback);
    else this.eventCallbacks.delete(eventType);
  }

  /** 只清回调，不动 socket；应用卸载时显式调用。 */
  public clearEventListeners(): void {
    this.eventCallbacks.clear();
  }

  private emitEvent(
    eventType: string,
    eventData: any,
    frame: WebSocketAPI.WebSocketResponse,
  ): void {
    const callbacks = this.eventCallbacks.get(eventType);
    if (!callbacks) return;
    callbacks.forEach((callback) => {
      try {
        callback(eventData, frame);
      } catch (error) {
        console.error(`[WebSocket] handler for ${eventType} failed:`, error);
      }
    });
  }

  public send<T = any>(message: WebSocketAPI.WebSocketRequest<T>): void {
    const ws = this.socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error("[WebSocket] Cannot send message, socket is not open");
    }
    const rawData = message.data ?? {};
    const data = this._sendCallback?.(rawData) ?? rawData;
    const frame: Record<string, any> = {
      type: message.type || "unknown",
      data,
      timestamp: Date.now(),
    };
    // 顶层关联字段必须透传，否则服务端无法按 request_id 取消 / 分流
    if (message.client_id) frame.client_id = message.client_id;
    if (message.request_id) frame.request_id = message.request_id;
    if (message.stream_id) frame.stream_id = message.stream_id;
    ws.send(JSON.stringify(frame));
  }

  /** 便捷方法：按 uid/device 定向（服务端 send_to_device 的入口参数）。 */
  public sendToDevice(
    uid: string,
    device: "mobile" | "desktop",
    type: string,
    data: Record<string, any> = {},
  ): void {
    this.send({ type, data: { ...data, target_uid: uid, target_device: device } });
  }

  public sendToUid(uid: string, type: string, data: Record<string, any> = {}): void {
    this.send({ type, data: { ...data, target_uid: uid } });
  }

  public close(): void {
    this._closedByUser = true;
    this.stopHeartbeat();
    this._clearReconnectTimer();
    this._registered = false;
    this._clientId = "";
    try {
      this.socket?.close();
    } catch { }
    this.socket = null;
    // 不清空回调：close() 后可能重新 connect，默认处理器仍应有效
  }
}
