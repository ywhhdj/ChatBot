import { LogSource, type LogLevel } from "@/typings/enums";
import http from "@/utils/http";

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

