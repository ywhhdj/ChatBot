// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const rootService = {
  /** Fallback */
  async fallbackGet(): Promise<unknown> {
    return request("get", "/");
  },
};
