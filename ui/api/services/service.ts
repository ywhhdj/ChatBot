// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const serviceService = {
  /** 服务列表（支持 running_only） */
  async listServices(query?: Record<string, any>): Promise<API.ServiceListData> {
    return request<API.ServiceListData>("get", `/service`, query, { opName: "service.list" });
  },

  /** 所有服务工具定义 */
  async listTools(query?: Record<string, any>): Promise<API.ToolData> {
    return request<API.ToolData>("get", `/service/tools`, query, { opName: "service.list_tools" });
  },

  /** 服务详情 */
  async getService(service_id: string, query?: Record<string, any>): Promise<API.ServiceInfoData> {
    return request<API.ServiceInfoData>("get", `/service/${service_id}`, query, { opName: "service.get", pathParams: { service_id } });
  },

  /** 单服务工具定义 */
  async serviceTools(service_id: string, query?: Record<string, any>): Promise<API.ToolData> {
    return request<API.ToolData>("get", `/service/${service_id}/tools`, query, { opName: "service.tools", pathParams: { service_id } });
  },

  /** 服务 UI 描述 */
  async serviceUi(service_id: string, query?: Record<string, any>): Promise<API.ServiceUIDescription> {
    return request<API.ServiceUIDescription>("get", `/service/${service_id}/ui`, query, { opName: "service.ui", pathParams: { service_id } });
  },

  /** 注册服务实例 */
  async registerService(service_id: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/service/${service_id}/register`, body, { opName: "service.register", pathParams: { service_id } });
  },

  /** 启动服务 */
  async startService(service_id: string, body: API.ServiceStartRequest): Promise<API.ServiceActionData> {
    return request<API.ServiceActionData>("post", `/service/${service_id}/start`, body, { opName: "service.start", pathParams: { service_id } });
  },

  /** 停止服务 */
  async stopService(service_id: string, body?: Record<string, any> | null): Promise<API.ServiceActionData> {
    return request<API.ServiceActionData>("post", `/service/${service_id}/stop`, body, { opName: "service.stop", pathParams: { service_id } });
  },

  /** 读取服务配置 */
  async getConfig(service_id: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/service/${service_id}/config`, query, { opName: "service.get_config", pathParams: { service_id } });
  },

  /** 更新服务配置（兼容直接传裸配置对象） */
  async updateConfig(service_id: string, body: API.ServiceConfigUpdateRequest | Record<string, any>): Promise<Record<string, any>> {
    const payload: API.ServiceConfigUpdateRequest =
      Object.prototype.hasOwnProperty.call(body, "config")
        ? (body as API.ServiceConfigUpdateRequest)
        : { config: body as Record<string, any> };
    return request<Record<string, any>>("put", `/service/${service_id}/config`, payload, { opName: "service.update_config", pathParams: { service_id } });
  },

  /** 应用配置（停 → 启） */
  async applyConfig(service_id: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("put", `/service/${service_id}/config/apply`, body, { opName: "service.apply_config", pathParams: { service_id } });
  },
};
