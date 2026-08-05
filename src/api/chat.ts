import { registerEventListeners, unregisterAllEventListeners, websocket } from "@/events/event/websocket";
import { WebSocketEvent } from "@/typings/enums";
import { StreamRecord } from "@/events/event/record";

enum ChatEvent {
  TEXT_DELTA = "pipeline.text_delta",
  FINAL_TEXT = "pipeline.final_text",
  AUDIO_CHUNK = "pipeline.audio_chunk",
  FINAL_AUDIO = "pipeline.final_audio",
  ERROR = "pipeline.error",
}

type ChatCallbacks = {
  /** 收到文本增量 */
  onTextDelta: (data:{
    text: string,
    progress: number
  }) => void;
  /** 收到最终文本 */
  onFinalText?: (data: {
    text: string
  }) => void;
  /** 收到音频块 */
  onAudioChunk?: (data: {
    audioName: string,
    chunk: ArrayBuffer
  }) => void;
  /** 收到最终音频 */
  onFinalAudio?: (data: {
    audioName: string,
    chunksCount: number
  }) => void;
  /** 聊天完成 */
  onComplete?: (data: string) => void;
  /** 发生错误 */
  onError?: (data: {
    code: number,
    message: string
  }) => void;
}



export function chat(
  options: {
    callbacks: ChatCallbacks;
  } & API.ChatOptions
) {
  const sessionId = options.session_id || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  
  const events = {
    [ChatEvent.TEXT_DELTA]: options.callbacks.onTextDelta,
    [ChatEvent.AUDIO_CHUNK]: options.callbacks.onAudioChunk,
    [ChatEvent.FINAL_AUDIO]: options.callbacks.onFinalAudio,
    [ChatEvent.ERROR]: options.callbacks.onError,
    // [ChatEvent.CHAT]: options.callbacks.onChat,
    // [ChatEvent.STOP]: options.callbacks.onStop,
  } as Record<ChatEvent, (event: any) => void>;
  function complete(data: any) {
    unregisterAllEventListeners(events);
    options.callbacks.onComplete?.(data);
  }
  events[ChatEvent.FINAL_TEXT] = complete;
  registerEventListeners(events);
  websocket.send<{
    message: string,
    session_id: string,
    source: string
  }>({
    type: WebSocketEvent.CHAT,
    data: {
      message: options.message,
      session_id: sessionId,
      source: options.source || 'text'
    }
  });
}

