// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const providersService = {
  /** 能力、可选 provider、当前选中与用量 */
  async listDescribe(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/providers/adapters`, query, { opName: "providers.list_describe" });
  },

  /** 各能力供应商配置（敏感字段已掩码） */
  async allConfigs(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/providers/configs`, query, { opName: "providers.all_configs" });
  },

  /** 某能力下的 provider 清单 */
  async listProviders(adapter: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/providers/${adapter}`, query, { opName: "providers.list_providers", pathParams: { adapter } });
  },

  /** 读取 provider 配置（已掩码） */
  async getProvider(adapter: string, provider: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/providers/${adapter}/${provider}`, query, { opName: "providers.get_provider", pathParams: { adapter, provider } });
  },

  /** provider 完整状态与本地模型文件状态 */
  async status(adapter: string, provider: string, query?: Record<string, any>): Promise<API.ProviderStatusData> {
    return request<API.ProviderStatusData>("get", `/providers/${adapter}/${provider}/status`, query, { opName: "providers.status", pathParams: { adapter, provider } });
  },

  /** 切换 provider / 模型 */
  async switch(adapter: string, body: API.ProviderSwitchRequest): Promise<API.SwitchResultData> {
    return request<API.SwitchResultData>("post", `/providers/adapters/${adapter}/switch`, body, { opName: "providers.switch", pathParams: { adapter } });
  },

  /** 停止当前 provider，保留能力门面 */
  async stopAdapter(adapter: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/providers/${adapter}/stop`, body, { opName: "providers.stop", pathParams: { adapter } });
  },

  /** 触发本地模型下载（进度走 WebSocket） */
  async downloadModel(adapter: string, provider: string, body: API.ProviderDownloadRequest): Promise<API.DownloadStartData> {
    return request<API.DownloadStartData>("post", `/providers/${adapter}/${provider}/download`, body, { opName: "providers.download", pathParams: { adapter, provider } });
  },
};
