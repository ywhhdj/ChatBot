// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const commandService = {
  /** Run Command */
  async runCommand(body: API.CommandRunRequest): Promise<API.CommandResultData> {
    return request<API.CommandResultData>("post", "/command", body);
  },
};
