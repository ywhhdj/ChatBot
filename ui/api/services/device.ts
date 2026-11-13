// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const deviceService = {
  /** 设备与平台信息（CPU/GPU/内存/推荐帧率） */
  async deviceInfo(query?: Record<string, any>): Promise<API.DeviceInfoData> {
    return request<API.DeviceInfoData>("get", `/device/info`, query, { opName: "device.info" });
  },
};
