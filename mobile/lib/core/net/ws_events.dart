/// 三端共用的帧字面量，与 `src/modules/events/types.py::WebSocketEventType` 逐字一致
class WsEvent {
  WsEvent._();

  static const String connect = 'websocket.connect';
  static const String heartbeat = 'websocket.heartbeat';
  static const String error = 'websocket.error';
  static const String result = 'result';
  static const String register = 'register';
  static const String chat = 'chat';

  static const String deviceHello = 'device.hello';
  static const String devicePose = 'device.pose';
  static const String deviceStageEvent = 'device.stage_event';
  static const String devicePlayAnimation = 'device.play_animation';
  static const String deviceModelSet = 'device.model_set';
  static const String deviceTextInput = 'device.text_input';
  static const String deviceAsrText = 'device.asr_text';

  static const String recordStart = 'record.start';
  static const String recordStop = 'record.stop';
  static const String recordChunk = 'record.audio_chunk';
  static const String recordAsrResult = 'record.asr_result';
  static const String pipelineTextDelta = 'pipeline.text_delta';
  static const String pipelineFinalText = 'pipeline.final_text';
  static const String pipelineAsrText = 'pipeline.asr_text';
}
