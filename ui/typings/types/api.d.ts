declare namespace API {
  type ApiMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';
  type ChatOptions = {
    message: string;
    session_id?: string;
    source?: "text" | "ocr" | "asr";
  }
  type ModelName = "google_facelandmarker" | "umi_ocr" | "paddle_ocr";
  interface DownloadModelOptions {
    model_name: ModelName;
    save_path: string;
  }
  type ServiceStatus = "not_enabled" | "stopped" | "running";
  type ServiceInfoResponse<T = any> = {
    id: string;
    name: string;
    description: string;
    status: ServiceStatus;
    config: T;
    icon?: string;
  }
  type ServiceId = "live2d" | "browser" | "obs" | "qqbot";
  type ServiceConfigItem = {
    type: "boolean" | "string" | "select";
    name: string;
    description?: string;
    value: boolean | string;
    config?: any[];
  } | {};
  type ServiceConfigItems = Record<ServiceId, ServiceConfigItem>;
  type QQBotInfo = {
    id: string;
    username: string;
    avatar: string;
    share_url: string;
    welcome_msg: string;
  }
  type ModelDownloadProgress = {
    model_name: ModelName;
    progress?: number;
    download: boolean;
    message?: string;
  }
  type PipelineType = "llm" | "ocr" | "asr";
  type PipelineConfig = Record<PipelineType, {
    tags: string[];
  } & ServiceConfigItem>
}

declare namespace WebSocketAPI {
  /** 统一出站信封；from_id 是真实发送方 */
  type WebSocketResponse<T = any> = {
    type: string;
    ok?: boolean;
    message?: string;
    data?: T;
    from?: string;
    from_id?: string;
    request_id?: string;
    stream_id?: string;
    ts?: number;
    timestamp?: number;
  }
  interface WebSocketRequest<T = any> {
    type: string
    data?: T | {
      client_id?: string;
      request_id?: string;
      stream_id?: string;
    } & T
    client_id?: string
    request_id?: string
    stream_id?: string
    timestamp?: number
  }
  type WebSocketConnectResponse = {
    client_id: string;
    connected_at: string;
    last_heartbeat: string;
  };
  /** REGISTER 帧 */
  type RegisterData = {
    uid: string;
    device: "mobile" | "desktop" | "unknown";
    token?: string;
  };
  type RegisterResponse = { uid: string; device: string };
  type DeviceFrame = {
    action?: string;
    seq?: number;
    epoch?: number;
    t?: number;
    params?: Record<string, any>;
    from_role?: string;
    from_id?: string;
    uid?: string;
    text?: string;
    source?: string;
    deg?: number;
    direction?: string;
    model_id?: string;
    model_path?: string;
  };
  type RecordEventType = "audio_chunk" | "stop" | "asr_result";
  type RecordAudioChunkData = {
    audio: string;
    is_final: boolean;
  };
}