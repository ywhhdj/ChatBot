// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const commandService = {
  /** 执行工具命令文本（策略/沙箱/工作区约束） */
  async command(body: API.CommandRunRequest): Promise<API.CommandResultData> {
    return request<API.CommandResultData>("post", `/command`, body, { opName: "generate.command" });
  },
};
