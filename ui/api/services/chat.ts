// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const chatService = {
  /** 非流式对话，一次返回完整回复 */
  async chatOnce(body: API.ChatRequest): Promise<API.ChatResultData> {
    return request<API.ChatResultData>("post", `/chat`, body, { opName: "generate.chat" });
  },

  /** SSE 流式对话 */
  // SSE 端点：此处仅给出签名，实际流式消费请用 fetch + ReadableStream
  async chatStream(body: API.ChatStreamRequest): Promise<unknown> {
    return request<unknown>("post", `/chat/stream`, body, { opName: "generate.chat_stream" });
  },
};
