import { WebSocketEvent } from "@/typings/enums";

export default class WebSockets {
  private url: string = "";
  private socket: WebSocket | null = null;
  public heartbeatInterval: number = 30000; // 30秒心跳间隔
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private reconnectDelay: number = 3000;
  private isConnecting: boolean = false;
  private heartbeatIntervalId: number | null = null;
  private _sendCallback: ((data: any) => any) | null = null;

  // 回调存储
  private eventCallbacks: Map<string, Set<(event: any) => void>> = new Map();

  constructor() { }

  set sendCallback(callback: (data: any) => any) {
    this._sendCallback = callback;
  }

  connect(
    url: string,
    onErrorCallback?: (event: Event) => void,
    onCloseCallback?: (event: Event) => void
  ) {
    this.url = url;
    console.log("[WebSocket] address:", url);
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("open", () => {
      this.isConnecting = true;
      console.log("[WebSocket] Connecting to:", url);
      this.reconnectAttempts = 0;
    });

    this.socket.addEventListener("close", (event: CloseEvent) => {
      this.stopHeartbeat();
      console.log("[WebSocket] Disconnected");
      onCloseCallback?.(event);
      this.isConnecting = false;
      this.attemptReconnect();
    });

    this.socket.addEventListener("error", (event: Event) => {
      console.error("[WebSocket] Error:", event);
      onErrorCallback?.(event);
    });
    this.socket.addEventListener("message", (event: MessageEvent<WebSocketAPI.WebSocketResponse>) => {
      let eventData = null;
      if (typeof event.data === "string") {
        eventData = JSON.parse(event.data);
      }
      this.handleMessage(eventData);
    }
    );
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatIntervalId = window.setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.send({ type: WebSocketEvent.HEARTBEAT });
      }
    }, this.heartbeatInterval || 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatIntervalId !== null) {
      clearInterval(this.heartbeatIntervalId);
      this.heartbeatIntervalId = null;
    }
  }

  private handleMessage(event: WebSocketAPI.WebSocketResponse): void {
    try {
      switch (event.type) {
        case "pong":
          break;
        case WebSocketEvent.CONNECT:
          this.emitEvent(event.type, event.data);
          this.startHeartbeat();
          break;
        default:
          console.log("[WebSocket] Received message:", event);
          this.emitEvent(event.type, event.data);
      }
    } catch (error) {
      console.error("[WebSocket] Failed to parse message:", error);
    }
  }

  private attemptReconnect(): void {
    if (
      this.isConnecting ||
      this.reconnectAttempts >= this.maxReconnectAttempts
    ) {
      console.log("[WebSocket] Max reconnection attempts reached");
      return;
    }

    this.isConnecting = true;
    this.reconnectAttempts++;

    console.log(
      `[WebSocket] Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}`
    );

    setTimeout(() => {
      this.socket = new WebSocket(this.url);
    }, this.reconnectDelay * this.reconnectAttempts);
  }

  get readyState(): number | undefined {
    return this.socket?.readyState;
  }

  public registerEventListener(
    eventType: string,
    callback: (data: any) => void
  ): void {
    if (!this.eventCallbacks.has(eventType)) {
      this.eventCallbacks.set(eventType, new Set());
    }
    this.eventCallbacks.get(eventType)!.add(callback);
  }

  public removeEventListener(
    eventType: string,
    callback?: (data: any) => void
  ): void {
    const callbacks = this.eventCallbacks.get(eventType);
    if (callbacks && callback) {
      callbacks.delete(callback);
    } else {
      this.eventCallbacks.delete(eventType);
    }
  }

  private emitEvent(eventType: string, eventData: any = {}): void {
    const callbacks = this.eventCallbacks.get(eventType);
    if (callbacks) {
      callbacks.forEach((callback: (event: any) => void) => {
        try {
          callback(eventData);
        } catch (error) {
          console.error(
            `[WebSocket] Error in event handler for ${eventType}:`,
            error
          );
        }
      });
    }
  }

  public send<T = any>(message: WebSocketAPI.WebSocketRequest<T>): void {
    try {
      if (this.socket?.readyState !== WebSocket.OPEN) {
        throw new Error("[WebSocket] Cannot send message, socket is not open");
      }
      let requestData: WebSocketAPI.WebSocketRequest<T> = {
        type: (message as any).type || "unknown",
        data: message.data,
        timestamp: Date.now(),
      };
      requestData.data = this._sendCallback?.(requestData.data) || requestData.data;
      this.socket.send(JSON.stringify(requestData));
    } catch (error) {
      throw error;
    }
  }

  public close(): void {
    this.stopHeartbeat();
    this.reconnectAttempts = this.maxReconnectAttempts; // 阻止重连
    this.socket?.close();
    this.eventCallbacks.clear();
  }
}