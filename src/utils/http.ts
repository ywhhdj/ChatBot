import logger from "@/plugins/LogForwarder";
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import notification from "./notification";

// ---------- API 映射表 ----------
const apiMap: Record<string, string> = {
  "/open-folder": "open_folder",
  "/service/list": "get_service_info_list",
  "/service/config": "get_service_config",
  "/service/live2d/start": "start_live2d",
  "/service/live2d/stop": "stop_live2d",
};

export function isDesktop(): boolean {
  return !!(window.qt && window.qt.webChannelTransport);
}

/** 初始化 QWebChannel，并将后端 API 对象挂载到 window.__qt_api__ */
async function initQtChannel(): Promise<void> {
  if (!isDesktop() || window.qt_channel) return;

  return new Promise((resolve, reject) => {
    try {
      const channel = new QWebChannel(
        window.qt!.webChannelTransport, (ch: any) => {
        window.qt_channel = ch;
        const backendApi = ch.objects.api;
        if (backendApi) {
          window.__qt_api__ = {};
          // 遍历后端对象的所有属性（包括槽函数），包装成 Promise 返回
          for (const key of Object.keys(backendApi)) {
            if (typeof backendApi[key] === 'function') {
              window.__qt_api__[key] = async <T = any>(...args: any[]): Promise<T> => {
                return await backendApi[key](...args);
              };
            }
          }
        }
        resolve();
      });
    } catch (e) {
      reject(e);
    }
  });
}

export class HttpError extends Error {
  constructor(
    public code: number,
    public message: string,
    public response?: AxiosResponse
  ) {
    super(message);
    this.name = 'HttpError';
  }
}

export const STATUS_ERROR: Record<number, string> = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  500: "Internal Server Error"
};

const DEFAULT_CONFIG: AxiosRequestConfig = {
  baseURL: '/api',
  timeout: Number(import.meta.env.VITE_TIMEOUT) || 10000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  withCredentials: true,
};

// ---------- Http 类 ----------
class Http {
  private instance: AxiosInstance | null = null;
  private requestInterceptorId: number | null = null;
  private responseInterceptorId: number | null = null;
  private config: AxiosRequestConfig = DEFAULT_CONFIG;
  private initialized: boolean = false;

  constructor() { }

  public async create(config: Partial<AxiosRequestConfig> = {}): Promise<void> {
    if (this.initialized && this.instance) {
      console.warn('Http instance already created');
      return;
    }
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.instance = axios.create(this.config);
    if (isDesktop()) {
      await initQtChannel(); // 确保通道就绪
      this.setupDesktopAdapter();
    }
    this.setupInterceptors();
    this.initialized = true;
  }

  /** 替换 axios 默认适配器为桌面端专用适配器 */
  private setupDesktopAdapter<T = any,D = any,H = {}>() {
    if (!this.instance) return;
    const originalAdapter = this.instance.defaults.adapter || axios.defaults.adapter;
    this.instance.defaults.adapter = async (config: AxiosRequestConfig<D>) => {
      if (isDesktop()) {
        return this.desktopRequest<T,D,H>(config);
      }
      //@ts-ignore
      return originalAdapter!(config);
    };
  }

  private getRealPath(url: string): string {
    let path = url;
    if (this.config.baseURL && url.startsWith(this.config.baseURL)) {
      path = url.substring(this.config.baseURL.length);
    }
    path = path.split('?')[0] || '';
    if (path.startsWith('/api')) {
      path = path.substring('/api'.length);
    }
    return path;
  }

  async desktopRequest<T = any, D = any, H = any>(config: AxiosRequestConfig): Promise<AxiosResponse<T, D, H>> {
    const { url, method, params, data } = config;
    const realPath = this.getRealPath(url || '');
    const desktopFnName = apiMap[realPath]; // 从映射表中找

    if (desktopFnName && window?.__qt_api__?.[desktopFnName]) {
      try {
        const requestData = method?.toLowerCase?.() === 'get' ? (params || {}) : (data || {});
        // 不再添加 _request 字段，保持简洁
        const result = await window.__qt_api__[desktopFnName](requestData);
        // 假设桌面API返回 { status, data, message } 格式
        if (result?.status === false) {
          throw new Error(result?.message || 'Desktop API failed');
        }
        // 模拟一个成功的 AxiosResponse
        return {
          data: result?.data ?? result, // 兼容不同返回格式
          status: 200,
          statusText: 'OK',
          headers: {},
          config: config as InternalAxiosRequestConfig<D>,
          request: {},
        } as AxiosResponse<T, D, H>;
      } catch (error: any) {
        throw new HttpError(error?.status || 500, error?.message || 'Desktop API error');
      }
    }
    // 如果没有映射，则回退到标准HTTP请求
    return this.instance!.request(config);
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
          config.headers['Content-Type'] = 'multipart/form-data';
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.responseInterceptorId = this.instance.interceptors.response.use(
      (response) => {
        const apiResponse = response.data as API.ApiResponse<unknown>;
        if (apiResponse.code !== undefined) {
          if (apiResponse.code === 200) {
            return apiResponse.data;
          } else {
            notification.showError({
              title: '请求失败',
              message: apiResponse.message || 'Request failed',
            });
            throw new HttpError(
              apiResponse.code,
              apiResponse.message || 'Request failed',
              response
            );
          }
        } else {
          return response.data;
        }
      },
      (error) => {
        if (error.response) {
          const { status, data } = error.response;
          const message = data?.message || STATUS_ERROR[status] || 'Unknown error';
          if (status === 401) {
            localStorage.removeItem("token");
            console.warn('Authentication failed, please login again');
          }
          throw new HttpError(status, message, error.response);
        } else if (error.request) {
          throw new HttpError(0, 'Network error or no response received');
        } else {
          throw new HttpError(500, error.message || 'Request configuration error');
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
  async request<T = any, D = any>(config: AxiosRequestConfig<D>): Promise<T> {
    return this.instance?.request(config) || Promise.reject(new Error('Instance not created'));
  }

  get<T = any>(url: string, params?: any, config?: AxiosRequestConfig<T>): Promise<T> {
    return this.request<T>({ url, params, method: 'GET', ...config });
  }

  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig<T>): Promise<T> {
    return this.request<T>({ url, data, method: 'POST', ...config });
  }

  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig<T>): Promise<T> {
    return this.request<T>({ url, data, method: 'PUT', ...config });
  }

  delete<T = any>(url: string, config?: AxiosRequestConfig<T>): Promise<T> {
    return this.request<T>({ url, method: 'DELETE', ...config });
  }

  patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig<T>): Promise<T> {
    return this.request<T>({ url, data, method: 'PATCH', ...config });
  }
}

const http = new Http();
http.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: Number(import.meta.env.VITE_TIMEOUT) || 10000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  },
  withCredentials: true,
});

export default http;