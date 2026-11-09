// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const serviceService = {
  /** Get Config */
  async getConfig(service_id: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/service/${service_id}/config`);
  },

  /** Get Service */
  async getService(service_id: string): Promise<API.ServiceInfoData> {
    return request<API.ServiceInfoData>("get", `/service/${service_id}`);
  },

  /** List Services */
  async listServices(query?: {
    /** 只返回运行中的服务 */
    running_only?: boolean;
  }): Promise<API.ServiceListData> {
    return request<API.ServiceListData>("get", "/service", query);
  },

  /** List Tools */
  async listTools(): Promise<API.ToolData> {
    return request<API.ToolData>("get", "/service/tools");
  },

  /** Service Tools */
  async serviceTools(service_id: string): Promise<API.ToolData> {
    return request<API.ToolData>("get", `/service/${service_id}/tools`);
  },

  /** Service Ui */
  async serviceUi(service_id: string): Promise<API.ServiceUIDescription> {
    return request<API.ServiceUIDescription>(
      "get",
      `/service/${service_id}/ui`
    );
  },

  /** Start Service */
  async startService(
    service_id: string,
    body: API.ServiceStartRequest | null
  ): Promise<API.ServiceActionData> {
    return request<API.ServiceActionData>(
      "post",
      `/service/${service_id}/start`,
      body
    );
  },

  /** Stop Service */
  async stopService(service_id: string): Promise<API.ServiceActionData> {
    return request<API.ServiceActionData>(
      "post",
      `/service/${service_id}/stop`
    );
  },

  /** Update Config */
  async updateConfig(
    service_id: string,
    body: Record<string, any>
  ): Promise<Record<string, any>> {
    return request<Record<string, any>>(
      "put",
      `/service/${service_id}/config`,
      body
    );
  },
};
