// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const pipelineService = {
  /** All Configs */
  async allConfigs(query?: {
      /** true 时返回敏感字段原值 */
      raw?: boolean;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/pipeline/configs", query);
  },

  /** Get Provider */
  async getProvider(adapter: string, provider: string, query?: {
      /** true 时返回敏感字段原值 */
      raw?: boolean;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/pipeline/adapters/${adapter}/providers/${provider}`, query);
  },

  /** List Adapters */
  async listAdapters(): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/pipeline/adapters");
  },

  /** List Providers */
  async listProviders(adapter: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/pipeline/adapters/${adapter}/providers`);
  },

  /** Stop Adapter */
  async stopAdapter(adapter: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/pipeline/adapters/${adapter}/stop`);
  },

  /** Switch */
  async switch(adapter: string, body: API.PipelineSwitchRequest): Promise<API.SwitchResultData> {
    return request<API.SwitchResultData>("post", `/pipeline/adapters/${adapter}/switch`, body);
  },
};
