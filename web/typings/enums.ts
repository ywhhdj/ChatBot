export enum WebSocketEvent {
  CONNECT = "connect",
  PRIVATE = "private",
  HEARTBEAT = "heartbeat",
  PONG = "pong",
  CHAT = "chat",
  DOWNLOAD_MODEL = "download_model",
  GET_LOG = "get_log",
}

export enum LogLevel {
  LOG = "log",
  TRACE = "trace",
  DEBUG = "debug",
  INFO = "info",
  WARN = "warn",
  ERROR = "error",
}
