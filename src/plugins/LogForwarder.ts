import { pushLog, type LogRecord } from '@/api/logger';
import { DEFAULT_CONFIG } from '@/config';
import { LogLevel, LogSource } from '@/typings/enums';
import type { App, Plugin } from 'vue';

const levelOrder: Record<LogLevel, number> = {
  [LogLevel.TRACE]: 0,
  [LogLevel.DEBUG]: 1,
  [LogLevel.LOG]: 2,
  [LogLevel.INFO]: 3,
  [LogLevel.WARN]: 4,
  [LogLevel.ERROR]: 5,
};

export class LogForwarder {
  public logs = reactive<LogRecord[]>([]);
  public maxLogs = 200;
  public mode: 'real-time' | 'forward' = DEFAULT_CONFIG.logger.mode;

  private flushTimer: number | null = null;
  private isFlushing = false;
  private initialized = false;

  constructor() {
    console.log('LogForwarder 默认启用实时模式')
  }

  init() {
    if (this.initialized || !DEFAULT_CONFIG.logger.enabled) {
      return;
    }
    this.initialized = true;
    this.overrideConsoleMethods();
    window.addEventListener("beforeunload", () => {
      if (this.mode === 'forward') {
        void this.flushImmediately();
      }
    });
  }

  private overrideConsoleMethods() {
    const methods = ["debug", "info", "warn", "error", "log"] as const;
    const origin: Record<string, (...args: unknown[]) => void> = {};
    ["debug", "info", "warn", "error", "log"].forEach((method) => {
      origin[method] = (console as any)[method];
    });

    methods.forEach((method) => {
      const mappedLevel = this.mapConsoleMethodToLevel(method);
      (console as any)[method] = (...args: unknown[]) => {
        this.captureLog(
          mappedLevel,
          args=args
        );
        origin[method]?.apply(console, args);
      };
    });
  }

  private mapConsoleMethodToLevel(method: keyof Console): LogLevel {
    if (method === "debug") return LogLevel.DEBUG;
    if (method === "info") return LogLevel.INFO;
    if (method === "warn") return LogLevel.WARN;
    if (method === "error") return LogLevel.ERROR;
    return LogLevel.LOG;
  }

  public toggleMode() {
    this.mode = this.mode === 'real-time' ? 'forward' : 'real-time';
    if (this.mode === 'real-time') {
      if (this.flushTimer) {
        clearTimeout(this.flushTimer)
        this.flushTimer = null
      }
    } else {
      this.flush();
    }
  }

  private buildRecord(level: LogLevel, args: unknown[]) {
    const message = args.map((arg) => {
        if (typeof arg === "string") return arg;
        try {
          return JSON.stringify(arg);
        } catch {
          return String(arg);
        }
      })
      .join(" ");

    const record: LogRecord = {
      log_name: "web_console",
      timestamp: new Date().toISOString(),
      level,
      message,
      source: LogSource.FRONTEND,
      metadata: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
      },
    };
    return record;
  }

  private captureLog(level?: LogLevel, args?: unknown[],record?: LogRecord) {
    if (!DEFAULT_CONFIG.logger.enabled || this.shouldSkipLevel(level || record?.level || LogLevel.LOG)) {
      return;
    }
    const record_ = record || this.buildRecord(level || LogLevel.LOG, args || []);
    this.logs.push(record_)
    this.trimLogs()
    if (this.mode === 'forward') {
      this.addToQueue(record_)  // 加入发送队列
    }
  }

  private trimLogs() {
    if (this.logs.length > this.maxLogs) {
      this.logs.splice(0, this.logs.length - Math.floor(this.maxLogs * 0.8))
    }
  }

  private shouldSkipLevel(level: LogLevel): boolean {
    return (
      levelOrder[level] < levelOrder[DEFAULT_CONFIG.logger.minLevel as LogLevel]
    );
  }

  private addToQueue(record: LogRecord) {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
    }
    this.flushTimer = window.setTimeout(() => {
      this.flushTimer = null;
      void this.flush();
    }, 80);
  }
  receiveBackendLog(record: LogRecord) {
    this.logs.push(record)
    this.trimLogs()
  }

  async flush() {
    if (this.isFlushing || this.logs.length === 0) {
      return;
    }
    this.isFlushing = true;
    const batch = [...this.logs];
    this.logs = [];

    try {
      await Promise.all(
        batch.map((item) => {
          return pushLog(item);
        })
      );
    } catch {
      this.logs.unshift(...batch);
    } finally {
      this.isFlushing = false;
    }
  }

  async flushImmediately() {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    await this.flush();
  }

  log(entry: LogRecord) {
    this.captureLog(undefined,undefined,entry);
  }

  destroy() {
    if (this.mode === 'forward') {
      void this.flushImmediately();
    }
  }
}

const logger = new LogForwarder();

const vueErrorHandler = (error: unknown, vm: any, info: string) => {
  const errorMessage = error instanceof Error ? error.message : String(error);
  const stackTrace = error instanceof Error ? error.stack : undefined;
  logger.log({
    log_name: 'vue_error',
    level: LogLevel.ERROR,
    message: `Vue component error: ${errorMessage}`,
    source: LogSource.FRONTEND,
    stack_trace: stackTrace,
    metadata: {
      component: vm?.$options?.name || 'UnknownComponent',
      info,
    },
  });
};

const globalErrorHandler = (event: ErrorEvent) => {
  logger.log({
    log_name: 'global_error',
    level: LogLevel.ERROR,
    message: event.message || 'Global error',
    source: LogSource.FRONTEND,
    stack_trace: event.error?.stack,
  });
};

const unhandledRejectionHandler = (event: PromiseRejectionEvent) => {
  logger.log({
    log_name: 'unhandled_rejection',
    level: LogLevel.ERROR,
    message: `Unhandled promise rejection: ${String(event.reason)}`,
    source: LogSource.FRONTEND,
  });
};

export const installLogForwarderPlugin: Plugin = {
  install(app: App) {
    logger.init();
    app.config.errorHandler = vueErrorHandler;
    window.addEventListener('error', globalErrorHandler);
    window.addEventListener('unhandledrejection', unhandledRejectionHandler);
    app.config.globalProperties.$log = logger;
    app.provide('logger', logger);
    app.provide('loggerLogs', logger.logs);
  },
};

export const useLogger = () => logger;

export default logger;
