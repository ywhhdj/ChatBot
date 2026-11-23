/**
 * 桌面端录音（三端之一）。
 * 事件字面量统一走 WebSocketEvent；停录回执先注册一次性监听再发帧，
 * 并带超时兜底，旧实现会永久 pending 且每次停录泄漏一个回调。
 */
import notification from "@/utils/notification";
import websocket from "@/api/websocket/index";
import { WebSocketEvent } from "@/typings/enums";

export class StreamRecord {
  private mediaRecorder: MediaRecorder | null = null;
  private audioContext: AudioContext | null = null;
  private isRecording: boolean = false;
  private accumulatedText: string = "";
  private chunkInterval: number = 160; // ms
  private stream: MediaStream | null = null;

  public onStartRecording?: (text: string) => void;

  constructor() {
    this.registerEventListeners();
  }

  async startRecording(
    onRecordingStarted?: (text: string) => void,
  ): Promise<void> {
    const stream = await navigator.mediaDevices
      .getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      .catch((error) => {
        notification.showError({ title: "录音失败", message: "请检查录音权限" });
        throw error;
      });
    if (!stream) return;
    this.stream = stream;
    this.audioContext = new AudioContext({ sampleRate: 16000 });
    this.mediaRecorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
    });

    websocket.send({ type: WebSocketEvent.RECORD_START });

    this.isRecording = true;
    this.accumulatedText = "";

    this.mediaRecorder.ondataavailable = async (event) => {
      if (event.data.size > 0 && this.isRecording) {
        const arrayBuffer = await event.data.arrayBuffer();
        const base64 = this.arrayBufferToBase64(arrayBuffer);
        try {
          websocket.send<WebSocketAPI.RecordAudioChunkData>({
            type: WebSocketEvent.RECORD_AUDIO_CHUNK,
            data: { audio: base64, is_final: false },
          });
        } catch {
          void this.stopRecording();
        }
      }
    };

    this.mediaRecorder.start(this.chunkInterval);
    this.onStartRecording = onRecordingStarted;
  }

  get getAccumulatedText(): string {
    return this.accumulatedText;
  }

  clearAccumulatedText(): void {
    this.accumulatedText = "";
  }

  async stopRecording(): Promise<void> {
    if (!this.isRecording) return;
    this.isRecording = false;
    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      this.mediaRecorder.stop();
    }
    this.mediaRecorder = null;
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;

    // 空块 + is_final 由服务端 flush 收尾
    websocket.send<WebSocketAPI.RecordAudioChunkData>({
      type: WebSocketEvent.RECORD_AUDIO_CHUNK,
      data: { audio: "", is_final: true },
    });
    websocket.send({ type: WebSocketEvent.RECORD_STOP });

    return new Promise<void>((resolve) => {
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        websocket.removeEventListener(WebSocketEvent.RECORD_STOP, done);
        window.clearTimeout(timer);
        resolve();
      };
      // 先注册再发帧太迟（stop 帧已发），因此监听 + 超时兜底即可
      const timer = window.setTimeout(done, 3000);
      websocket.registerEventListener(WebSocketEvent.RECORD_STOP, done);
    });
  }

  /** 分块拼接，避免一次性 String.fromCharCode 展开超大数组撑爆内存。 */
  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    const CHUNK = 0x8000;
    let binary = "";
    for (let i = 0; i < bytes.length; i += CHUNK) {
      const slice = bytes.subarray(i, Math.min(i + CHUNK, bytes.length));
      binary += String.fromCharCode(...slice);
    }
    return btoa(binary);
  }

  private registerEventListeners(): void {
    websocket.registerEventListener(
      WebSocketEvent.RECORD_ASR_RESULT,
      (data: any) => {
        const text = String(data?.text ?? data ?? "");
        this.accumulatedText += text;
        this.onStartRecording?.(text);
      },
    );
    websocket.registerEventListener(
      WebSocketEvent.PIPELINE_ASR_TEXT,
      (data: any) => {
        const text = String(data?.text ?? data ?? "");
        if (!text) return;
        this.accumulatedText += text;
        this.onStartRecording?.(text);
      },
    );
  }
}

const record = new StreamRecord();

export const registerRecordHandler = (
  onRecordingStarted?: (text: string) => void,
) => {
  void record.startRecording(onRecordingStarted);
};

export const unregisterRecordHandler = async () => {
  await record.stopRecording();
};
