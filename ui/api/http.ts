declare module "axios" {
  interface AxiosRequestConfig {
    /** 桌面端 bridge 用的 op 名，由代码生成器提供 */
    opName?: string;
    /** 路径参数，桌面端 bridge 会注入 payload（来源：endpoints.json 生成元数据） */
    pathParams?: Record<string, string | number>;
  }
}

/**
 * Shared transport —— FrontendPlan F0-01 / F0-03 / F0-04 / F0-07 / FX-01
 *
 * REST(Axios) 与 Qt WebChannel bridge 共用 `decoder.ts`：
 * - 成功业务码统一 200（src/modules/api/exceptions.py CODE_OK=200），不再有 bridge 判 0 的分支；
 * - 底层只抛出 ApiClientError，不弹通知、不重复解包；通知由页面 workflow 决定；
 * - path 参数从最终 URL 段解析并编码，禁止把 `{session_id}` 这类占位符发给后端；
 * - 取消 / 超时 / 网络错误单独分类，并保留可诊断的 request_id。
 */
import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { CONFIG } from "@/config";
import { isDesktop } from "@/utils/equipment";
import {
  ApiClientError,
  decodeEnvelope,
  isEnvelope,
  toApiClientError,
} from "./decoder";

function getOpName(path: string): string {
  // 去除 baseURL 前缀
  let cleanPath = path;
  if (
    CONFIG.env.API_BASE_URL &&
    cleanPath.startsWith(CONFIG.env.API_BASE_URL)
  ) {
    cleanPath = cleanPath.substring(CONFIG.env.API_BASE_URL.length);
  }
  // 去除 /api 前缀（controllers/__init__.py register_all_routers 的真实前缀）
  if (cleanPath.startsWith("/api")) {
    cleanPath = cleanPath.substring("/api".length);
  }
  // 去掉查询参数
  cleanPath = cleanPath.split("?")[0] as string;

  const parts = cleanPath.split("/").filter(Boolean);
  // 特殊处理：如果路径以版本号开头（如 v1），跳过
  if (parts.length > 0 && /^v\d+$/.test(parts[0] as string)) {
    parts.shift();
  }
  return parts.join(".");
}

/**
 * F0-03：生成 service 已在 URL 中插入实值，但历史调用可能残留 `{xxx}`。
 * 这里用显式 pathParams 实值替换并编码；缺值直接拒绝，绝不发送占位符。
 */
function resolvePathParams(
  path: string,
  params?: Record<string, string | number>
): string {
  return path.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (placeholder, key: string) => {
    const value = params?.[key];
    if (value === undefined || value === null || value === "") {
      throw new ApiClientError({
        kind: "validation",
        code: 1001,
        message: `缺少路径参数 ${key}`,
      });
    }
    return encodeURIComponent(String(value));
  });
}

/** 兼容旧调用方：HttpError 现在收敛为 ApiClientError 的一个别名形态。 */
export class HttpError extends ApiClientError {
  readonly response?: AxiosResponse;

  constructor(code: number, message: string, response?: AxiosResponse) {
    super({
      kind: code <= 0 ? "network" : "internal",
      code,
      status: response?.status,
      message,
    });
    this.response = response;
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

function getBridgeCall():
  | ((name: string, payload?: any, timeout?: number) => Promise<any>)
  | null {
  const api = (window as any).qtwebview?.api;
  return api?.call || null;
}

function headerRequestId(config: AxiosRequestConfig): string | undefined {
  const value = (config.headers as any)?.["X-Request-Id"];
  return typeof value === "string" ? value : undefined;
}

class Http {
  private instance: AxiosInstance | null = null;
  private requestInterceptorId: number | null = null;
  private responseInterceptorId: number | null = null;
  private config: AxiosRequestConfig = DEFAULT_CONFIG;
  private initialized: boolean = false;

  constructor() {}

  public async create(config: Partial<AxiosRequestConfig> = {}): Promise<void> {
    if (this.initialized && this.instance) {
      console.warn("Http instance already created");
      return;
    }
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.instance = axios.create(this.config);
    if (isDesktop()) {
      // 如果桥接尚未就绪，等待 QWebChannel 初始化
      if (!isBridgeReady()) {
        await this.initQtChannel();
      }
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

  async desktopRequest<T = any, D = any, H = {}>(
    config: AxiosRequestConfig<D>
  ): Promise<AxiosResponse<T, D, H>> {
    const { url, method, params, data, opName, pathParams } = config;
    const path = resolvePathParams(url || "", pathParams);
    const op = opName || getOpName(path);

    const payload: any = {};
    // 1) 路径参数（桌面端唯一来源，必须先解析再合并）
    if (pathParams) Object.assign(payload, pathParams);
    // 2) query（GET 和 POST 都可能带）
    if (params) Object.assign(payload, params);
    // 3) body（仅非 GET）
    if (method?.toLowerCase() !== "get" && data) {
      if (typeof data === "string") {
        try {
          Object.assign(payload, JSON.parse(data));
        } catch {
          // 非 JSON 字符串不猜测结构，保持原样由 op 自行处理
          payload.body = data;
        }
      } else {
        Object.assign(payload, data);
      }
    }

    const bridgeCall = getBridgeCall();
    if (!bridgeCall) {
      throw new ApiClientError({
        kind: "not_ready",
        message: "桌面桥接尚未就绪，请稍后重试",
      });
    }

    const timeout = config.timeout || 60000;
    const requestId = headerRequestId(config);
    let raw: unknown;
    try {
      raw = await bridgeCall(op, payload, timeout);
    } catch (err) {
      throw toApiClientError(err, { requestId });
    }

    // 与 REST 共用同一 decoder：成功 code 200，错误保留 request_id 与稳定 code。
    const decoded = decodeEnvelope<T>(raw, { status: 200, requestId });
    return {
      data: decoded,
      status: 200,
      statusText: "OK",
      headers: {},
      config: config as InternalAxiosRequestConfig<D>,
      request: {},
    } as AxiosResponse<T, D, H>;
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
        // 已解包的裸数据（bridge adapter 返回值）由 decoder 原样放行，不会二次解包。
        return decodeEnvelope<any>(response.data, {
          status: response.status,
          requestId: headerRequestId(response.config),
        });
      },
      (error) => {
        const status: number | undefined = error?.response?.status;
        const raw = error?.response?.data;
        const requestId =
          headerRequestId(error?.config) ||
          (isEnvelope(raw) ? (raw as any).request_id : undefined);

        // 后端错误同样是信封：优先用 decoder 保留业务 code 与 request_id。
        if (isEnvelope(raw)) {
          try {
            decodeEnvelope(raw, { status, requestId });
          } catch (decoded) {
            if (decoded instanceof ApiClientError) {
              if (status === 401) localStorage.removeItem("token");
              throw decoded;
            }
          }
        }

        const apiErr = toApiClientError(error, { status, requestId });
        if (status === 401) localStorage.removeItem("token");
        throw apiErr;
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
      Promise.reject(
        new ApiClientError({ kind: "not_ready", message: "请求客户端未初始化" })
      )
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

export interface RequestOptions {
  opName?: string;
  pathParams?: Record<string, string | number>;
  config?: AxiosRequestConfig;
}

export async function request<T = any>(
  method: HttpMethod,
  url: string,
  params?: any,
  options?: RequestOptions
): Promise<T> {
  const cfg: AxiosRequestConfig = {
    ...(options?.config || {}),
    opName: options?.opName,
    pathParams: options?.pathParams,
  };
  return http[method](url, params, cfg) as Promise<T>;
}
