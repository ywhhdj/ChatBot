// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const pipelineService = {
  /** 能力、可选 provider、当前选中与用量 */
  async listAdapters(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/provider/adapters`, query, { opName: "provider.list_adapters" });
  },

  /** 各能力供应商配置（敏感字段已掩码） */
  async allConfigs(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/provider/configs`, query, { opName: "provider.all_configs" });
  },

  /** 某能力下的 provider 清单 */
  async listProviders(adapter: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/provider/adapters/${adapter}/providers`, query, { opName: "provider.list_providers", pathParams: { adapter } });
  },

  /** 读取 provider 配置（已掩码） */
  async getProvider(adapter: string, provider: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/provider/adapters/${adapter}/providers/${provider}`, query, { opName: "provider.get", pathParams: { adapter, provider } });
  },

  /** provider 完整状态与本地模型文件状态 */
  async status(adapter: string, provider: string, query?: Record<string, any>): Promise<API.ProviderStatusData> {
    return request<API.ProviderStatusData>("get", `/provider/adapters/${adapter}/providers/${provider}/status`, query, { opName: "provider.status", pathParams: { adapter, provider } });
  },

  /** 切换 provider / 模型 */
  async switch(adapter: string, body: API.ProviderSwitchRequest): Promise<API.SwitchResultData> {
    return request<API.SwitchResultData>("post", `/provider/adapters/${adapter}/switch`, body, { opName: "provider.switch", pathParams: { adapter } });
  },

  /** 停止当前 provider，保留能力门面 */
  async stopAdapter(adapter: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/provider/adapters/${adapter}/stop`, body, { opName: "provider.stop", pathParams: { adapter } });
  },

  /** 触发本地模型下载（进度走 WebSocket） */
  async downloadModel(adapter: string, provider: string, body: API.ProviderDownloadRequest): Promise<API.DownloadStartData> {
    return request<API.DownloadStartData>("post", `/provider/adapters/${adapter}/providers/${provider}/download`, body, { opName: "provider.download", pathParams: { adapter, provider } });
  },
};
