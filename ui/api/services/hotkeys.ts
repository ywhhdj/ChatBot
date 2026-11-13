// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const hotkeysService = {
  /** 快捷键清单与 revision */
  async listHotkeys(query?: Record<string, any>): Promise<API.HotkeyListData> {
    return request<API.HotkeyListData>("get", `/hotkeys`, query, { opName: "hotkeys.list" });
  },

  /** 录制中实时校验组合键 */
  async validateHotkey(body: API.HotkeyValidateRequest): Promise<API.HotkeyValidateData> {
    return request<API.HotkeyValidateData>("post", `/hotkeys/validate`, body, { opName: "hotkeys.validate" });
  },

  /** 恢复默认快捷键 */
  async resetHotkeys(body: API.HotkeyResetRequest): Promise<API.HotkeyListData> {
    return request<API.HotkeyListData>("post", `/hotkeys/reset`, body, { opName: "hotkeys.reset" });
  },

  /** 批量更新快捷键 */
  async updateHotkeys(body: API.HotkeyBatchUpdateRequest): Promise<API.HotkeyListData> {
    return request<API.HotkeyListData>("put", `/hotkeys`, body, { opName: "hotkeys.batch_update" });
  },

  /** 更新单个快捷键 */
  async updateHotkey(action: string, body: API.HotkeyUpdateRequest): Promise<API.HotkeyListData> {
    return request<API.HotkeyListData>("put", `/hotkeys/${action}`, body, { opName: "hotkeys.update", pathParams: { action } });
  },
};
