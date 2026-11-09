// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const loggerService = {
  /** Flush */
  async flush(): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/logger/flush");
  },

  /** Get Level */
  async getLevel(): Promise<API.LoggerLevelData> {
    return request<API.LoggerLevelData>("get", "/logger/level");
  },

  /** List Levels */
  async listLevels(): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/logger/levels");
  },

  /** Records */
  async records(query?: {
      limit?: number;
      /** 按级别过滤，如 ERROR */
      level?: string | null;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/logger/records", query);
  },

  /** Set Level */
  async setLevel(body: Record<string, any>): Promise<API.LoggerLevelData> {
    return request<API.LoggerLevelData>("put", "/logger/level", body);
  },

  /** Stats */
  async stats(): Promise<API.LoggerStatsData> {
    return request<API.LoggerStatsData>("get", "/logger/stats");
  },
};
