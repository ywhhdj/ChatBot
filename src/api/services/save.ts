// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const saveService = {
  /** Create Slot */
  async createSlot(body: API.SlotCreateRequest): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("post", "/save/slots", body);
  },

  /** Delete Slot */
  async deleteSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("delete", `/save/slots/${slot_id}`);
  },

  /** Get Slot */
  async getSlot(slot_id: string): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("get", `/save/slots/${slot_id}`);
  },

  /** List Slots */
  async listSlots(): Promise<API.SlotListData> {
    return request<API.SlotListData>("get", "/save/slots");
  },

  /** Load Slot */
  async loadSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/slots/${slot_id}/load`);
  },

  /** Restore To Sessions */
  async restoreToSessions(): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/save/slots/restore");
  },

  /** Save Slot */
  async saveSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/slots/${slot_id}/save`);
  },

  /** Sync From Sessions */
  async syncFromSessions(body: API.SlotSyncRequest | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/save/slots/sync", body);
  },

  /** Toggle Slot */
  async toggleSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/slots/${slot_id}/toggle`);
  },

  /** Update Section */
  async updateSection(slot_id: string, body: API.SlotSectionUpdateRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("put", `/save/slots/${slot_id}/section`, body);
  },
};
