/**
 * 兼容旧 import 路径。
 * 真正的 WebSocket 实现只在 `@/api/websocket/socket`，避免两份拷贝各自漂移
 * （旧副本漏了重连事件绑定、request_id/stream_id 透传与 REGISTER 帧）。
 */
export { default } from "@/api/websocket/socket";
