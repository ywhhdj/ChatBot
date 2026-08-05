export { }
declare global {
  interface Window {
    qt?: {
      webChannelTransport?: unknown;
    };
    QWebChannel?: new (
      transport: unknown,
      callback: (channel: any) => void
    ) => unknown;
    qt_channel?: any;
    __qt_api__?: Record<string, <T = any>(...args: any[]) => Promise<T>>;
  }
}