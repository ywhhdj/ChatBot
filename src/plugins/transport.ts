// import { WebSocketEvent } from "@/typings/enums";
// import { asyncCreateScriptTag } from "@/utils/util";
// import { useUserStore } from "@/stores/user";
// import type { App, Plugin } from "vue";

// interface QtApiObject {
// };

// class UnifiedRuntimeTransport {
//   public mode: "desktop" | "web" = "web";
//   public websocket: WebSockets | null = null;
//   private heartbeatIntervalId: number | null = null;

//   async init(): Promise<void> {
//     // this.qtBridge = await this.tryConnectQtBridge();
//     // this.mode = this.qtBridge ? "desktop" : "web";
//     // if (this.qtBridge) {
//     //   this.qtBridge.statusChanged.connect((payloadJson: string) => {
//     //     let payload: unknown = payloadJson;
//     //     try {
//     //       payload = JSON.parse(payloadJson);
//     //     } catch {
//     //       payload = payloadJson;
//     //     }
//     //     this.statusHandlers.forEach((handler) => handler(payload));
//     //   });

//     //   this.qtBridge.taskCompleted.connect((payloadRaw: unknown) => {
//     //     let payload: QtTaskCompleted;
//     //     if (typeof payloadRaw === "string") {
//     //       try {
//     //         payload = JSON.parse(payloadRaw) as QtTaskCompleted;
//     //       } catch {
//     //         return;
//     //       }
//     //     } else {
//     //       payload = payloadRaw as QtTaskCompleted;
//     //     }
//     //     if (!payload.requestId) return;

//     //     const task = this.pending.get(payload.requestId);
//     //     if (!task) return;
//     //     this.pending.delete(payload.requestId);
//     //     if (payload.success) {
//     //       task.resolve(payload.data);
//     //     } else {
//     //       task.reject(new Error(payload.error || "Qt task failed"));
//     //     }
//     //   });
//     //   this.qtBridge.logMessage.connect((text: string) => console.log("[qt]", text));
//     // }
//     await this.initWebSocket();
//   }

//   private async initWebSocket(): Promise<void> {
//     const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

//     this.websocket = new WebSockets(
//       wsUrl,
//       // onConnect
//       (event) => {
//         const response = event.data;
//         if (response.type === WebSocketEvent.CONNECT && response.data) {
//           console.log(response);
//           const wsstore = useUserStore();
//           wsstore.clientId = response.data.client_id;
//           console.log(`[WebSocket] Connected in ${this.mode} mode:`, wsstore.clientId);
//         }
//       },
//       // onError
//       (event: Event) => {
//         console.error("[WebSocket] Error:", event);
//       },
//       // onOpen
//       () => {
//         console.log("[WebSocket] Open");
//         this.startHeartbeat();
//       },
//       // onClose
//       (event: any) => {
//         console.log("[WebSocket] Closed:", event.code, event.reason);
//         const wsstore = useUserStore();
//         wsstore.clientId = '';
//         this.stopHeartbeat();
//       }
//     );
//   }

//   private startHeartbeat(): void {
//     this.stopHeartbeat();
//     this.heartbeatIntervalId = window.setInterval(() => {
//       if (this.websocket?.readyState === WebSocket.OPEN) {
//         this.websocket.send({ type: WebSocketEvent.HEARTBEAT });
//       }
//     }, this.websocket?.heartbeatInterval || 30000);
//   }

//   private stopHeartbeat(): void {
//     if (this.heartbeatIntervalId !== null) {
//       clearInterval(this.heartbeatIntervalId);
//       this.heartbeatIntervalId = null;
//     }
//   }

//   private async tryConnectQtBridge(): Promise<QtApiObject | null> {
//     const qt = window.qt;
//     if (!qt?.webChannelTransport) {
//       return null;
//     }
//     await this.ensureQtWebChannelScript();

//     return await new Promise<QtApiObject | null>((resolve) => {
//       if (!window.QWebChannel) {
//         resolve(null);
//         return;
//       }
//       new window.QWebChannel(
//         qt.webChannelTransport,
//         (channel: { objects?: Record<string, unknown> }) => {
//           resolve(
//             channel.objects?.api as QtApiObject | undefined
//             || null
//           );
//         }
//       );
//     });
//   }

//   private async ensureQtWebChannelScript(): Promise<void> {
//     if (window.QWebChannel) {
//       return;
//     }
//     await asyncCreateScriptTag("qrc:///qtwebchannel/qwebchannel.js");
//   }
// }

// const transport = new UnifiedRuntimeTransport();

// export const installruntimeTransportPlugin: Plugin = {
//   install(app: App) {
//     void transport.init();
//   },
// };

// export default transport;
