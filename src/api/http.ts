import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import notification from "@/utils/notification";
import { CONFIG } from "@/config";
import { isDesktop } from "@/utils/equipment";

function getOpName(path: string): string {
  // 去除 baseURL 前缀
  let cleanPath = path;
  if (
    CONFIG.env.API_BASE_URL &&
    cleanPath.startsWith(CONFIG.env.API_BASE_URL)
  ) {
    cleanPath = cleanPath.substring(CONFIG.env.API_BASE_URL.length);
  }
  // 去除 /api 前缀
  if (cleanPath.startsWith("/api")) {
    cleanPath = cleanPath.substring("/api".length);
  }
  // 去掉查询参数
  cleanPath = cleanPath.split("?")[0] as string;

  // 按 / 分割，过滤空段，用点连接
  const parts = cleanPath.split("/").filter(Boolean);
  // 特殊处理：如果路径以版本号开头（如 v1），跳过
  if (parts.length > 0 && /^v\d+$/.test(parts[0] as string)) {
    parts.shift();
  }
  return parts.join(".");
}

/** 初始化 QWebChannel，并将后端 API 对象挂载到 window.__qt_api__ */

export class HttpError extends Error {
  constructor(
    public code: number,
    public message: string,
    public response?: AxiosResponse
  ) {
    super(message);
    this.name = "HttpError";
  }
}

export const STATUS_ERROR: Record<number, string> = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  500: "Internal Server Error",
};

const DEFAULT_CONFIG: AxiosRequestConfig = {
  baseURL: CONFIG.env.API_BASE_URL + "/api",
  timeout: CONFIG.env.TIMEOUT,
  headers: {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
  withCredentials: true,
};

/** 检查桥接是否就绪（优先使用 qtwebview.api.call） */
function isBridgeReady(): boolean {
  return !!window.qtwebview?.api?.call;
}

/** 获取桥接的 call 函数 */
function getBridgeCall():
  | ((name: string, payload?: any, timeout?: number) => Promise<any>)
  | null {
  const api = (window as any).qtwebview?.api;
  return api?.call || null;
}

class Http {
  private instance: AxiosInstance | null = null;
  private requestInterceptorId: number | null = null;
  private responseInterceptorId: number | null = null;
  private config: AxiosRequestConfig = DEFAULT_CONFIG;
  private initialized: boolean = false;
  private useBridge: boolean = false;

  constructor() {}

  public async create(config: Partial<AxiosRequestConfig> = {}): Promise<void> {
    if (this.initialized && this.instance) {
      console.warn("Http instance already created");
      return;
    }
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.instance = axios.create(this.config);
    if (isDesktop()) {
      this.useBridge = true;
      // 如果桥接尚未就绪，等待 QWebChannel 初始化
      if (!isBridgeReady()) {
        await this.initQtChannel();
      }
      // 替换适配器
      this.setupDesktopAdapter();
    }
    this.setupInterceptors();
    this.initialized = true;
  }

  private initQtChannel(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!isDesktop() || (window as any).qt_channel) {
        resolve();
        return;
      }
      try {
        const channel = new window.QWebChannel(
          window.qt!.webChannelTransport,
          (ch: any) => {
            (window as any).qt_channel = ch.objects.qt_channel;
            resolve();
          }
        );
      } catch (e) {
        reject(e);
      }
    });
  }

  /** 替换 axios 默认适配器为桌面端专用适配器 */
  private setupDesktopAdapter<T = any, D = any, H = {}>() {
    if (!this.instance) return;
    const originalAdapter =
      this.instance.defaults.adapter || axios.defaults.adapter;
    this.instance.defaults.adapter = async (config: AxiosRequestConfig<D>) => {
      if (isDesktop()) {
        return this.desktopRequest<T, D, H>(config);
      }
      //@ts-ignore
      return originalAdapter!(config);
    };
  }

  private injectPathParams(payload: any, path: string): void {
    const paramRegex = /\/(\w+)\/(\{(\w+)\})?/g;
    let match;
    while ((match = paramRegex.exec(path)) !== null) {
      const paramName = match[3] || match[1];
      if (paramName && !payload[paramName]) {
        // 从路径中提取实际值（需要在 URL 中保留，这里简化为空）
        // 实际场景中，Axios 会将路径参数替换为实际值，此处无需额外处理
      }
    }
  }

  async desktopRequest<T = any, D = any, H = {}>(
    config: AxiosRequestConfig<D>
  ): Promise<AxiosResponse<T, D, H>> {
    const { url, method, params, data } = config;
    const path = url || "";
    // 不再需要 method，直接生成纯 op 名
    const opName = getOpName(path);

    // 构造 payload
    const payload: any = {};
    if (method?.toLowerCase() === "get") {
      Object.assign(payload, params || {});
    } else {
      Object.assign(payload, data || {});
    }
    // 注入原始路径中的路径参数（如 session_id）
    // 例如 /session/{session_id}/messages → payload.session_id = xxx
    this.injectPathParams(payload, path);

    const bridgeCall = getBridgeCall();
    if (!bridgeCall) {
      throw new HttpError(500, "Bridge call not available");
    }

    try {
      const timeout = config.timeout || 60000; // 后端默认 60s
      const result = await bridgeCall(opName, payload, timeout);

      // 后端统一信封 { ok, code, message, data, request_id, ts }
      if (result && result.ok === true && result.code === 0) {
        return {
          data: result.data as T,
          status: 200,
          statusText: "OK",
          headers: {},
          config: config as InternalAxiosRequestConfig<D>,
          request: {},
        } as AxiosResponse<T, D, H>;
      } else {
        throw new HttpError(
          result?.code || 500,
          result?.message || "Desktop API failed",
          undefined
        );
      }
    } catch (error: any) {
      if (error instanceof HttpError) throw error;
      throw new HttpError(500, error.message || "Desktop API error");
    }
  }

  // ---------- 拦截器 ----------
  private setupInterceptors() {
    if (!this.instance) return;
    this.clearInterceptors();

    this.requestInterceptorId = this.instance.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem("token");
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        if (config.data instanceof FormData) {
          config.headers["Content-Type"] = "multipart/form-data";
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.responseInterceptorId = this.instance.interceptors.response.use(
      (response) => {
        const apiResponse = response.data as API.ApiResponse<unknown>;
        if (
          apiResponse &&
          typeof apiResponse === "object" &&
          "ok" in apiResponse
        ) {
          if (apiResponse.ok === true && apiResponse.code === 200) {
            return apiResponse.data;
          }
          notification.showError({
            title: "请求失败",
            message: apiResponse.message || "Request failed",
          });
          throw new HttpError(
            apiResponse.code || 500,
            apiResponse.message || "Request failed",
            response
          );
        }
        return response.data;
      },
      (error) => {
        if (error.response) {
          const { status, data } = error.response;
          const message =
            data?.message || STATUS_ERROR[status] || "Unknown error";
          if (status === 401) {
            localStorage.removeItem("token");
            console.warn("Authentication failed, please login again");
          }
          throw new HttpError(status, message, error.response);
        } else if (error.request) {
          throw new HttpError(0, "Network error or no response received");
        } else {
          throw new HttpError(
            500,
            error.message || "Request configuration error"
          );
        }
      }
    );
  }

  private clearInterceptors(): void {
    if (this.instance && this.requestInterceptorId !== null) {
      this.instance.interceptors.request.eject(this.requestInterceptorId);
      this.requestInterceptorId = null;
    }
    if (this.instance && this.responseInterceptorId !== null) {
      this.instance.interceptors.response.eject(this.responseInterceptorId);
      this.responseInterceptorId = null;
    }
  }

  // ---------- 公开请求方法 ----------
  private async request<T = any, D = any>(
    config: AxiosRequestConfig<D>
  ): Promise<T> {
    return (
      this.instance?.request(config) ||
      Promise.reject(new Error("Instance not created"))
    );
  }

  public get<T = any, D = any>(
    url: string,
    params?: any,
    config?: AxiosRequestConfig<D>
  ): Promise<T> {
    if (params) {
      return this.request<T>({ url, params, method: "GET", ...config });
    }
    return this.request<T>({ url, method: "GET", ...config });
  }

  public post<T = any, D = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig<D>
  ): Promise<T> {
    return this.request<T>({ url, data, method: "POST", ...config });
  }

  public put<T = any, D = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig<D>
  ): Promise<T> {
    return this.request<T>({ url, data, method: "PUT", ...config });
  }

  public delete<T = any, D = any>(
    url: string,
    config?: AxiosRequestConfig<D>
  ): Promise<T> {
    return this.request<T>({ url, method: "DELETE", ...config });
  }

  public patch<T = any, D = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig<D>
  ): Promise<T> {
    return this.request<T>({ url, data, method: "PATCH", ...config });
  }
}

const http = new Http();
http.create(DEFAULT_CONFIG);
export default http;
type HttpMethod = "get" | "post" | "put" | "delete" | "patch";

export async function request<T = any>(
  method: HttpMethod,
  url: string,
  params?: any
): Promise<T> {
  try {
    const data = await http[method](url, params);
    return data;
  } catch (err: any) {
    return Promise.reject(err);
  }
}
