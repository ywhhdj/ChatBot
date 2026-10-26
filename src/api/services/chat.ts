// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const chatService = {
  /** Chat Once */
  async chatOnce(body: API.ChatOptions): Promise<API.ChatResultData> {
    return request<API.ChatResultData>("post", "/chat", body);
  },

  /** Chat Stream */
  async chatStream(body: API.ChatOptions): Promise<unknown> {
    return request("post", "/chat/stream", body);
  },
};
