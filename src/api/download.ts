import { registerEventListeners, unregisterAllEventListeners, websocket } from "@/events/event/websocket";
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
  onRunning?: (data: { model_name: API.ModelName, download: boolean, progress: number }) => void;
  onCompleted?: (data: { model_name: API.ModelName, download: boolean, message: string }) => void;
  onError?: (data: { model_name: API.ModelName, download: boolean, message: string }) => void;
}

export function downloadModel(options: {
  callbacks: DownloadModelCallback
} & API.DownloadModelOptions) {
    const events = {
      [DownloadModelEvent.RUNNING]: options.callbacks.onRunning,
      [DownloadModelEvent.ERROR]: options.callbacks.onError,
    } as Record<DownloadModelEvent, (data: any) => void>;
    registerEventListeners(events);
    const complete = (data: any) => {
      unregisterAllEventListeners(events);
      options.callbacks.onCompleted?.(data);
    };
  events[DownloadModelEvent.COMPLETED] = complete;
  websocket?.send<API.DownloadModelOptions>({
    type: WebSocketEvent.DOWNLOAD_MODEL,
    data: {
      model_name: options.model_name,
      save_path: options.save_path,
    }
  });
}