// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const systemService = {
  /** Web、调度器、主线程、记忆与服务健康状态 */
  async health(query?: Record<string, any>): Promise<API.HealthData> {
    return request<API.HealthData>("get", `/system/health`, query, { opName: "system.health" });
  },

  /** 版本、配置路径与数据目录 */
  async info(query?: Record<string, any>): Promise<API.InfoData> {
    return request<API.InfoData>("get", `/system/info`, query, { opName: "system.info" });
  },

  /** uptime、日志、任务、连接与记忆统计 */
  async stats(query?: Record<string, any>): Promise<API.StatsData> {
    return request<API.StatsData>("get", `/system/stats`, query, { opName: "system.stats" });
  },

  /** 触发记忆衰减/清理与日志排空 */
  async gc(body: API.GcRequest): Promise<API.GcData> {
    return request<API.GcData>("post", `/system/gc`, body, { opName: "system.gc" });
  },

  /** 轻量连通性探测 */
  async ping(query?: Record<string, any>): Promise<string> {
    return request<string>("get", `/system/ping`, query, { opName: "system.ping" });
  },
};
