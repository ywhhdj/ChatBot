export {};

declare global {
  interface Window {
    qtwebview?: {
      api?: {
        /**
         * 调用后端操作
         * @param method 操作名（如 "system.health"）
         * @param payload 请求参数
         * @param timeout 超时时间（毫秒），可选，默认由后端决定
         * @returns 后端统一信封 { ok, code, message, data, request_id, ts }
         */
        call: (
          method: string,
          payload?: Record<string, any>,
          timeout?: number
        ) => Promise<any>;
      };
    };
    qt?: {
      webChannelTransport: any;
    };
    QWebChannel: {
      new (transport: any, callback: (channel: any) => void): any;
    };
  }
}
