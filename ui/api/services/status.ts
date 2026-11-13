// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const statusService = {
  /** 查询 LLM/TTS/ASR/图像/OCR/向量能力就绪状态 */
  async status(query?: Record<string, any>): Promise<API.GenerationStatusData> {
    return request<API.GenerationStatusData>("get", `/status`, query, { opName: "generate.status" });
  },
};
