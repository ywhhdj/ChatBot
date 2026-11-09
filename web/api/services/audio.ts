// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const audioService = {
  /** Asr */
  async asr(body: API.ASRRequest): Promise<API.ASRResultData> {
    return request<API.ASRResultData>("post", "/asr", body);
  },

  /** Tts */
  async tts(body: API.TTSRequest): Promise<API.TTSResultData> {
    return request<API.TTSResultData>("post", "/tts", body);
  },
};
