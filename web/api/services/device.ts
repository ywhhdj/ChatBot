// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const deviceService = {
  /** Device Info */
  async deviceInfo(): Promise<API.DeviceInfoData> {
    return request<API.DeviceInfoData>("get", "/device/info");
  },
};
