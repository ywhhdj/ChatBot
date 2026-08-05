import notification from "@/utils/notification";
import { websocket } from "./websocket";

enum RecordEventType {
  START = "record.start",
  STOP = "record.stop",
  AUDIO_CHUNK = "record.audio_chunk",
  ASR_RESULT = "record.asr_result",
}

export class StreamRecord{
  private mediaRecorder: MediaRecorder | null = null;
  private audioContext: AudioContext | null = null;
  private isRecording: boolean = false;
  private accumulatedText: string = '';
  private chunkInterval: number = 160; // ms

  public onStartRecording?: (text: string) => void;

  constructor() {
    this.registerEventListeners();
  }

  async startRecording(
    onRecordingStarted?: (text: string) => void,
  ): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      }
    }).catch((error) => {
      notification.showError({
        title: '录音失败',
        message: "请检查录音权限",
      });
    });
    if (!stream) {
      return;
    }
    this.audioContext = new AudioContext({ sampleRate: 16000 });
    this.mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus'
    });

    // 通知后端开始录音
    websocket.send({
      type: RecordEventType.START,
    });

    this.isRecording = true;
    this.accumulatedText = '';
    let chunkIndex = 0;

    // 处理音频数据
    this.mediaRecorder.ondataavailable = async (event) => {
      if (event.data.size > 0 && this.isRecording) {
        const arrayBuffer = await event.data.arrayBuffer();
        const base64 = this.arrayBufferToBase64(arrayBuffer);
        websocket.send<WebSocketAPI.RecordAudioChunkData>({
          type: RecordEventType.AUDIO_CHUNK,
          data: {
            audio: base64,
            is_final: false,
          },
        });
        chunkIndex++;
      }
    };

    // 每 160ms 收集一次音频
    this.mediaRecorder.start(this.chunkInterval);
    this.onStartRecording = onRecordingStarted;
  }

  get getAccumulatedText() {
    return this.accumulatedText;
  }

  clearAccumulatedText(): void {
    this.accumulatedText = '';
  }

  async stopRecording(): Promise<string> {
    if (!this.isRecording) {
      return '';
    }
    this.isRecording = false;
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }
    websocket.send<WebSocketAPI.RecordAudioChunkData>({
      type: RecordEventType.AUDIO_CHUNK,
      data: {
        audio: '',          // 空字符串表示没有新音频
        is_final: true,     // 标记为最后一块
      },
    });
    websocket.send({
      type: RecordEventType.STOP,
    });
    return new Promise((resolve) => {
      websocket.registerEventListener(RecordEventType.STOP, (data: {
        text: string
      }) => {
        this.accumulatedText = data.text;
        resolve(data.text);
      });
    });
  }
  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      const byte = bytes[i];
      if (byte === undefined) {
        continue;
      }
      binary += String.fromCharCode(byte);
    }
    return btoa(binary);
  }
  private registerEventListeners() {
    websocket.registerEventListener(RecordEventType.ASR_RESULT, (data) => {
      this.accumulatedText += data.text;
      this.onStartRecording?.(data.text);
    });
  }

  private base64ToBlob(base64: string, mimeType: string): Blob {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  }
}