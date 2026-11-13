// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const audioService = {
  /** 文本转语音，返回 base64 音频 */
  async tts(body: API.TTSRequest): Promise<API.TTSResultData> {
    return request<API.TTSResultData>("post", `/tts`, body, { opName: "generate.tts" });
  },

  /** 语音转文本，audio 为 base64 音频 */
  async asr(body: API.ASRRequest): Promise<API.ASRResultData> {
    return request<API.ASRResultData>("post", `/asr`, body, { opName: "generate.asr" });
  },
};
