// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const greaterService = {
  /** 图像生成（OpenAI / Stability / ComfyUI 协议） */
  async imageGenerate(body: API.ImageGenerateRequest): Promise<API.ImageGenerateData> {
    return request<API.ImageGenerateData>("post", `/image/generations`, body, { opName: "generate.image" });
  },

  /** 图片文字识别 */
  async ocr(body: API.OCRRecognizeRequest): Promise<API.OCRResultData> {
    return request<API.OCRResultData>("post", `/ocr`, body, { opName: "generate.ocr" });
  },

  /** 批量文本向量化 */
  async embedding(body: API.EmbeddingRequest): Promise<API.EmbeddingData> {
    return request<API.EmbeddingData>("post", `/embedding`, body, { opName: "generate.embedding" });
  },

  /** SSE 任务进度流 */
  // SSE 端点：此处仅给出签名，实际流式消费请用 fetch + ReadableStream
  async progressStream(task_id: string, body?: Record<string, any> | null): Promise<unknown> {
    return request<unknown>("post", `/progress-stream/${task_id}`, body, { opName: "generate.progress_stream", pathParams: { task_id } });
  },
};

/** 兼容别名：生成组亦可按 greaterService 导入 */
export const generateService = greaterService;
