export enum WebSocketEvent {
  CONNECT = "websocket.connect",
  ERROR = "websocket.error",
  PRIVATE = "websocket.private",
  HEARTBEAT = "websocket.heartbeat",
  PONG = "pong",
  RESULT = "result",
  CHAT = "chat",
  DOWNLOAD_MODEL = "download_model",
  GET_LOG = "get_log",
  GET_AUDIT_LOGS = "get_audit_logs",
  SUBSCRIBE = "subscribe",
  UNSUBSCRIBE = "unsubscribe",
  CANCEL = "cancel",

  // 连接后首帧（CONTROL_EVENTS，不占 inflight）
  REGISTER = "register",

  // 三端设备联动
  DEVICE_HELLO = "device.hello",
  DEVICE_POSE = "device.pose",
  DEVICE_STAGE_EVENT = "device.stage_event",
  DEVICE_PLAY_ANIMATION = "device.play_animation",
  DEVICE_MODEL_SET = "device.model_set",
  DEVICE_TEXT_INPUT = "device.text_input",
  DEVICE_ASR_TEXT = "device.asr_text",

  // 录音 / 识别
  RECORD_START = "record.start",
  RECORD_STOP = "record.stop",
  RECORD_AUDIO_CHUNK = "record.audio_chunk",
  RECORD_ASR_RESULT = "record.asr_result",

  // 流水线事件
  PIPELINE_TEXT_DELTA = "pipeline.text_delta",
  PIPELINE_FINAL_TEXT = "pipeline.final_text",
  PIPELINE_ASR_TEXT = "pipeline.asr_text",
}

export enum LogLevel {
  LOG = "log",
  TRACE = "trace",
  DEBUG = "debug",
  INFO = "info",
  WARN = "warn",
  ERROR = "error",
}
