// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const loggerService = {
  /** 当前日志级别 */
  async getLevel(query?: Record<string, any>): Promise<API.LoggerLevelData> {
    return request<API.LoggerLevelData>("get", `/logger/level`, query, { opName: "logger.get_level" });
  },

  /** 设置日志级别 */
  async setLevel(body: API.LoggerLevelRequest): Promise<API.LoggerLevelData> {
    return request<API.LoggerLevelData>("put", `/logger/level`, body, { opName: "logger.set_level" });
  },

  /** 可用日志级别列表 */
  async listLevels(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/logger/levels`, query, { opName: "logger.list_levels" });
  },

  /** 日志计数与按级别统计 */
  async stats(query?: Record<string, any>): Promise<API.LoggerStatsData> {
    return request<API.LoggerStatsData>("get", `/logger/stats`, query, { opName: "logger.stats" });
  },

  /** 最近日志记录 */
  async records(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/logger/records`, query, { opName: "logger.records" });
  },

  /** 排空日志缓冲 */
  async flush(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/logger/flush`, body, { opName: "logger.flush" });
  },

  /** 接收前端 LogForwarder 批量日志（兼容直接传数组） */
  async appendLog(body: API.LogAppendRequest | API.LogRecord[]): Promise<API.LogAppendData> {
    const payload: API.LogAppendRequest = Array.isArray(body)
      ? { records: body, no_frontend_push: true }
      : body;
    return request<API.LogAppendData>("post", "/logger/append", payload, { opName: "logger.append" });
  },
};
