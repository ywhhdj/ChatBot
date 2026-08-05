# Vue 项目结构与代码

## 文件树

```
src/api/
📄 chat.ts
📄 config.ts
📄 download.ts
📄 history.ts
📄 logger.ts
📄 model.ts
📄 services.ts
```

---

## `chat.ts`

```ts
import { registerEventListeners } from "@/events";
import transport from "@/plugins/transport";
import { WebSocketEvent } from "@/typings/enums";

enum ChatEvent {
  TEXT_DELTA = "pipeline.text_delta",
  FINAL_TEXT = "pipeline.final_text",
  AUDIO_CHUNK = "pipeline.audio_chunk",
  FINAL_AUDIO = "pipeline.final_audio",
  ERROR = "pipeline.error",
}

type ChatCallbacks = {
  /** 收到文本增量 */
  onTextDelta: (text: string, progress: number) => void;
  /** 收到最终文本 */
  onFinalText?: (text: string) => void;
  /** 收到音频块 */
  onAudioChunk?: (audioName: string, chunk: ArrayBuffer) => void;
  /** 收到最终音频 */
  onFinalAudio?: (audioName: string, chunksCount: number) => void;
  /** 聊天完成 */
  onComplete?: (text: string, hasAudio: boolean) => void;
  /** 发生错误 */
  onError?: (code: number, message: string) => void;
  /** 用户消息确认 */
  onUserMessage?: (text: string) => void;
}

export function chat(
  options: {
    callbacks: ChatCallbacks;
  } & API.ChatOptions
) {
  const sessionId = options.session_id || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  if (!transport.websocket) {
    console.error('[WebSocket] WebSocket not initialized');
    return;
  }
  const events = {
    [ChatEvent.TEXT_DELTA]: options.callbacks.onTextDelta,
    [ChatEvent.FINAL_TEXT]: options.callbacks.onFinalText,
    [ChatEvent.AUDIO_CHUNK]: options.callbacks.onAudioChunk,
    [ChatEvent.FINAL_AUDIO]: options.callbacks.onFinalAudio,
    [ChatEvent.ERROR]: options.callbacks.onError,
    // [ChatEvent.CHAT]: options.callbacks.onChat,
    // [ChatEvent.STOP]: options.callbacks.onStop,
  } as Record<ChatEvent, (event: any) => void>;
  registerEventListeners(events);
  transport.websocket.send<API.ChatOptions>({
    type: WebSocketEvent.CHAT,
    data: {
      message: options.message,
      session_id: sessionId,
      source: options.source || 'text'
    }
  });
}
```

## `config.ts`

```ts
import http from "@/utils/http";

export interface AdvancedConfig {
  install_components: string[];
  code_highlight: {
    enabled: boolean;
    theme: string;
  };
  extra: Record<string, unknown>;
}

export async function openFolder(folderPath: string): Promise<boolean> {
  return http.get<boolean>('/open-folder', { folderPath });
}

export async function getConfig(): Promise<AdvancedConfig | SystemConfig> {
  return http.get<AdvancedConfig | SystemConfig>('/config');
}

export async function getAdvancedConfig(): Promise<AdvancedConfig> {
  return HttpUtil.get<AdvancedConfig>('/config/advanced');
}

export async function saveAdvancedConfig(payload: AdvancedConfig): Promise<boolean> {
  return HttpUtil.post<boolean>('/config/advanced', payload as unknown as Record<string, unknown>);
}

export interface SystemConfig {
  log_config: {
    level: string;
    dir: string;
  };
  network_config: {
    port: number;
    timeout: number;
  };
}

export async function getSystemConfig(): Promise<SystemConfig> {
  return HttpUtil.get<SystemConfig>('/config/system');
}

export async function saveSystemConfig(payload: Record<string, unknown>): Promise<boolean> {
  return HttpUtil.post<boolean>('/config/system', payload);
}


```

## `download.ts`

```ts
import { registerEventListeners } from "@/events";
import transport from "@/plugins/transport";
import { WebSocketEvent } from "@/typings/enums";

enum DownloadModelEvent {
  STARTED = "download_started",
  RUNNING = "download_running",
  COMPLETED = "download_completed",
  FAILED = "download_failed",
  ERROR = "download_error"
}

type DownloadModelResponse= {
  model_name: string;
  progress?: number;
  message?: string;
}

type DownloadModelCallback = {
  onStarted?: (data: DownloadModelResponse) => void;
  onRunning?: (data: DownloadModelResponse) => void;
  onCompleted?: (data: DownloadModelResponse) => void;
  onFailed?: (data: DownloadModelResponse) => void;
  onError?: (data: DownloadModelResponse) => void;
}

export function downloadModel(options: {
  callbacks: DownloadModelCallback;
} & API.DownloadModelOptions) {
  const events = {
    [DownloadModelEvent.STARTED]: options.callbacks.onStarted,
    [DownloadModelEvent.COMPLETED]: options.callbacks.onCompleted,
    [DownloadModelEvent.FAILED]: options.callbacks.onFailed,
    [DownloadModelEvent.RUNNING]: options.callbacks.onRunning,
  } as Record<string, (data: DownloadModelResponse) => void>;
  registerEventListeners(events);
  transport.websocket?.send<API.DownloadModelOptions>({
    type: WebSocketEvent.DOWNLOAD_MODEL,
    data: options
  });
}
```

## `history.ts`

```ts
import type { HistoryItems } from "@/typings/system-types";
import HttpUtil from "@/utils/http";

export async function getHistory(params?: string[][] | Record<string, string> | string | URLSearchParams, callback?: (data: HistoryItems) => void) {
  const query: Record<string, string> = {};
  if (params && typeof params === 'object' && !Array.isArray(params) && !(params instanceof URLSearchParams)) {
    Object.assign(query, params);
  }
  const res = await HttpUtil.get<HistoryItems>('/history', query);
  if (res) {
    if (callback) {
      return callback(res);
    }
    return res;
  }
}

```

## `logger.ts`

```ts


export enum LogLevel {
  LOG = 'log',
  TRACE = 'trace',
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
}

export enum LogSource {
  FRONTEND = 'frontend',
  BACKEND = 'backend',
  SYSTEM = 'system',
  NETWORK = 'network',
  AI_SERVICE = 'ai_service',
  UNKNOWN = 'unknown',
}

export interface LogRecord {
  log_name: string;
  timestamp?: string;
  level: LogLevel;
  message: string;
  source?: LogSource;
  stack_trace?: string;
  metadata?: Record<string, unknown>;
}

export interface LoggerState {
  current_level: string;
  levels: string[];
}


export async function getLoggerState(): Promise<LoggerState> {
  return http.get<LoggerState>('/logger/levels');
}

export async function setLoggerLevel(level: LogLevel | string): Promise<boolean> {
  return http.put<boolean>('/logger/level', { level: String(level).toUpperCase() });
}

export async function getLoggerRecords(limit = 200): Promise<LogRecord[]> {
  return http.get<LogRecord[]>('/logger/records', { limit: String(limit) });
}

export async function clearLoggerRecords(): Promise<boolean> {
  return http.delete<boolean>('/logger/records');
}

export async function pushLog(record: LogRecord): Promise<boolean> {
  return http.post<boolean>('/logger/push', {
    log_name: record.log_name,
    level: String(record.level).toUpperCase(),
    message: record.message,
    logger: record.source || LogSource.FRONTEND,
  });
}


```

## `model.ts`

```ts
import http from '@/utils/http';

interface LLMConfig {
  model: string;
  apiBaseURL: string;
  apiKey: string;
}

export async function setLLMConfig(config: LLMConfig, callback: (data: boolean) => void) {
  const res = await http.put<boolean>('/llm/setConfig', config);
  if (res) {
    if (callback) {
      return callback(res);
    }
    return res;
  }
}

export async function getLLMProviderList() {
  const res = await http.get<string[]>('/model/list');
  if (res) {
    return res;
  }
  return [];
}

```

## `services.ts`

```ts
import http from "@/utils/http";

export function getServiceList(){
  return http.get<API.ServiceInfoResponse<any[]>[]>("/service/list");
};

export function startLive2DService(serviceId?: string) {
  return http.post<API.ServiceInfoResponse<{
    service_id: string;
    message: string;
  }>>("/service/live2d/start", {
    service_id: serviceId,
  });
}

export function stopLive2DService(serviceId?: string) {
  return http.post<API.ServiceInfoResponse<{
    service_id: string;
    message: string;
  }>>("/service/live2d/stop", {
    service_id: serviceId,
  });
}
```

