import { loggerService } from "@/api/services/logger";
import { CONFIG } from "@/config";
import { LogLevel } from "@/typings/enums";
import type { App } from "vue";

export type LogEntry = API.LogRecord & { id: number; time: string };

const levelOrder: Record<LogLevel, number> = {
  [LogLevel.TRACE]: 0,
  [LogLevel.DEBUG]: 1,
  [LogLevel.LOG]: 2,
  [LogLevel.INFO]: 3,
  [LogLevel.WARN]: 4,
  [LogLevel.ERROR]: 5,
};

const fmtTime = (iso: string) => {
  const d = new Date(iso);
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(
    d.getMilliseconds(),
    3
  )}`;
};

export class LogForwarder {
  public logs = shallowRef<LogEntry[]>([]);
  /** UI 最多保留条数（和发送队列解耦，别再被 flush 清空） */
  public maxLogs = 1000;
  public mode: "real-time" | "forward" = CONFIG.logger.mode;

  private sendQueue: API.LogRecord[] = []; // 与展示解耦的发送队列
  private pending: LogEntry[] = []; // 一帧内攒的批
  private rafId: number | null = null;
  private seq = 0;
  private flushTimer: number | null = null;
  private isFlushing = false;
  private initialized = false;

  constructor() {
    console.log("LogForwarder 默认启用实时模式");
  }

  init() {
    if (this.initialized || !CONFIG.logger.enabled) {
      return;
    }
    this.initialized = true;
    this.overrideConsoleMethods();
    window.addEventListener("beforeunload", () => {
      if (this.mode === "forward") {
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
        this.captureLog(mappedLevel, args);
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
    this.mode = this.mode === "real-time" ? "forward" : "real-time";
    if (this.mode === "real-time") {
      if (this.flushTimer) {
        clearTimeout(this.flushTimer);
        this.flushTimer = null;
      }
    } else {
      this.flush();
    }
  }

  private buildRecord(level: LogLevel, args: unknown[]) {
    const message = args
      .map((arg) => {
        if (typeof arg === "string") return arg;
        try {
          return JSON.stringify(arg);
        } catch {
          return String(arg);
        }
      })
      .join(" ");

    const record: API.LogRecord = {
      log_name: "web_console",
      timestamp: new Date().toISOString(),
      level,
      message,
      source: "frontend",
      metadata: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
      },
    };
    return record;
  }

  private captureLog(
    level?: LogLevel,
    args?: unknown[],
    record?: API.LogRecord
  ) {
    if (
      !CONFIG.logger.enabled ||
      this.shouldSkipLevel(level ?? record?.level ?? LogLevel.LOG)
    ) {
      return;
    }
    const rec = record ?? this.buildRecord(level ?? LogLevel.LOG, args ?? []);

    const entry: LogEntry = {
      ...rec,
      id: ++this.seq,
      time: fmtTime(rec.timestamp ?? ""),
    };
    this.pending.push(entry);

    if (this.mode === "forward") this.sendQueue.push(rec);

    // 无论每秒来多少条，UI 一帧最多更新一次
    if (this.rafId === null) {
      this.rafId = requestAnimationFrame(() => {
        this.rafId = null;
        const batch = this.pending;
        this.pending = [];
        if (!batch.length) return;
        let next = this.logs.value.concat(batch);
        if (next.length > this.maxLogs) next = next.slice(-this.maxLogs);
        this.logs.value = next; // 整体替换触发更新
      });
    }
  }

  private shouldSkipLevel(level: LogLevel): boolean {
    return levelOrder[level] < levelOrder[CONFIG.logger.minLevel as LogLevel];
  }

  private pendingFlush = false;

  receiveBackendLog(record: API.LogRecord) {
    this.captureLog(undefined, undefined, record);
  }

  async flush() {
    if (this.isFlushing || !this.sendQueue.length) return;
    this.isFlushing = true;
    const batch = this.sendQueue;
    this.sendQueue = [];
    try {
      await loggerService.appendLog(batch);
    } catch {
      this.sendQueue.unshift(...batch); // 失败回填，不丢日志
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

  log(entry: API.LogRecord) {
    this.captureLog(undefined, undefined, entry);
  }

  destroy() {
    if (this.mode === "forward") {
      void this.flushImmediately();
    }
    this.clear();
  }

  clear() {
    this.pending = [];
    this.logs.value = [];
  }
}

const logger = new LogForwarder();

const vueErrorHandler = (error: unknown, vm: any, info: string) => {
  const errorMessage = error instanceof Error ? error.message : String(error);
  const stackTrace = error instanceof Error ? error.stack : undefined;
  logger.log({
    log_name: "vue_error",
    level: LogLevel.ERROR,
    message: `Vue component error: ${errorMessage}`,
    source: "frontend",
    stack_trace: stackTrace,
    metadata: {
      component: vm?.$options?.name || "UnknownComponent",
      info,
    },
  });
};

const globalErrorHandler = (event: ErrorEvent) => {
  logger.log({
    log_name: "global_error",
    level: LogLevel.ERROR,
    message: event.message || "Global error",
    source: "frontend",
    stack_trace: event.error?.stack,
  });
};

const unhandledRejectionHandler = (event: PromiseRejectionEvent) => {
  logger.log({
    log_name: "unhandled_rejection",
    level: LogLevel.ERROR,
    message: `Unhandled promise rejection: ${String(event.reason)}`,
    source: "frontend",
  });
};

export const initLoggerPlugin = (app: App) => {
  logger.init();
  app.config.errorHandler = vueErrorHandler;
  window.addEventListener("error", globalErrorHandler);
  window.addEventListener("unhandledrejection", unhandledRejectionHandler);
  app.config.globalProperties.$log = logger;
  app.provide("logger", logger);
  app.provide("loggerLogs", logger.logs);
};

export default logger;
