// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const workspaceService = {
  /** 当前工作区、权限档位与输出目录 */
  async info(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/workspace`, query, { opName: "workspace.info" });
  },

  /** 选择目录与权限档位 */
  async select(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/workspace/select`, body, { opName: "workspace.select" });
  },

  /** 显式确认敏感原文暴露 */
  async confirm(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/workspace/confirm`, body, { opName: "workspace.confirm" });
  },

  /** 撤销选择，回到默认工作区 */
  async clear(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/workspace`, body, { opName: "workspace.clear" });
  },
};
