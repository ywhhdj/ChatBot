// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const requestService = {
  /** 打开受支持的本地数据目录 */
  async openFolder(type: string, query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/folder/${type}`, query, { opName: "request.open_folder", pathParams: { type } });
  },
};
