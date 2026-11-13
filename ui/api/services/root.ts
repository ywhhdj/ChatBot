// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const rootService = {
  /** 端点清单 + OpenAPI schema（动态表单用） */
  async api(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/catalog`, query, { opName: "catalog.api" });
  },
};
