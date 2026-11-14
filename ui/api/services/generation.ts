// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const generationService = {
  /** 查询 LLM/TTS/ASR/图像/OCR/向量能力就绪状态 */
  async status(query?: Record<string, any>): Promise<API.GenerationStatusData> {
    return request<API.GenerationStatusData>("get", `/generation/status`, query, { opName: "generation.status" });
  },

  /** 非流式对话，一次返回完整回复 */
  async chatOnce(body: API.ChatRequest): Promise<API.ChatResultData> {
    return request<API.ChatResultData>("post", `/generation/chat`, body, { opName: "generation.chat" });
  },

  /** SSE 流式对话 */
  // SSE 端点：此处仅给出签名，实际流式消费请用 fetch + ReadableStream
  async chatStream(body: API.ChatStreamRequest): Promise<unknown> {
    return request<unknown>("post", `/generation/chat/stream`, body, { opName: "generation.chat_stream" });
  },

  /** 文本转语音，返回 base64 音频 */
  async tts(body: API.TTSRequest): Promise<API.TTSResultData> {
    return request<API.TTSResultData>("post", `/generation/tts`, body, { opName: "generation.tts" });
  },

  /** 语音转文本，audio 为 base64 音频 */
  async asr(body: API.ASRRequest): Promise<API.ASRResultData> {
    return request<API.ASRResultData>("post", `/asr`, body, { opName: "generation.asr" });
  },

  /** 图像生成（OpenAI / Stability / ComfyUI 协议） */
  async image(body: API.ImageGenerateRequest): Promise<API.ImageGenerateData> {
    return request<API.ImageGenerateData>("post", `/generation/image`, body, { opName: "generation.image" });
  },

  /** 图片文字识别 */
  async ocr(body: API.OCRRecognizeRequest): Promise<API.OCRResultData> {
    return request<API.OCRResultData>("post", `/generation/ocr`, body, { opName: "generation.ocr" });
  },

  /** 批量文本向量化 */
  async embedding(body: API.EmbeddingRequest): Promise<API.EmbeddingData> {
    return request<API.EmbeddingData>("post", `/generation/embedding`, body, { opName: "generation.embedding" });
  },

  /** 执行工具命令文本（策略/沙箱/工作区约束） */
  async command(body: API.CommandRunRequest): Promise<API.CommandResultData> {
    return request<API.CommandResultData>("post", `/command`, body, { opName: "generation.command" });
  },

  /** SSE 任务进度流 */
  // SSE 端点：此处仅给出签名，实际流式消费请用 fetch + ReadableStream
  async progressStream(task_id: string, body?: Record<string, any> | null): Promise<unknown> {
    return request<unknown>("post", `/progress-stream/${task_id}`, body, { opName: "generation.progress_stream", pathParams: { task_id } });
  },
};
