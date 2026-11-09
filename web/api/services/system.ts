// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const systemService = {
  /** Gc */
  async gc(body: API.GcRequest | null): Promise<API.GcData> {
    return request<API.GcData>("post", "/system/gc", body);
  },

  /** Health */
  async health(): Promise<API.HealthData> {
    return request<API.HealthData>("get", "/system/health");
  },

  /** Info */
  async info(): Promise<API.InfoData> {
    return request<API.InfoData>("get", "/system/info");
  },

  /** Ping */
  async ping(): Promise<string> {
    return request<string>("get", "/system/ping");
  },

  /** Stats */
  async stats(): Promise<API.StatsData> {
    return request<API.StatsData>("get", "/system/stats");
  },
};
