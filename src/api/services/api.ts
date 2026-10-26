// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const apiService = {
  /** Download */
  async Download(file_name: string): Promise<API.PptDownloadData> {
    return request<API.PptDownloadData>("get", `/api/ppt/download/${file_name}`);
  },

  /** Job Status */
  async JobStatus(task_id: string): Promise<API.PptJobData> {
    return request<API.PptJobData>("get", `/api/ppt/job/${task_id}`);
  },

  /** Outline */
  async Outline(body: API.PptOutlineRequest): Promise<API.PptOutlineData> {
    return request<API.PptOutlineData>("post", "/api/ppt/outline", body);
  },

  /** Render */
  async Render(body: API.PptRenderRequest): Promise<API.PptRenderData> {
    return request<API.PptRenderData>("post", "/api/ppt/render", body);
  },

  /** Render Async */
  async RenderAsync(body: API.PptRenderRequest): Promise<API.PptRenderData> {
    return request<API.PptRenderData>("post", "/api/ppt/render/async", body);
  },

  /** Templates */
  async Templates(): Promise<API.PptTemplateListData> {
    return request<API.PptTemplateListData>("get", "/api/ppt/templates");
  },

  /** Tools */
  async Tools(): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/api/audit/tools");
  },

  /** Tree */
  async Tree(): Promise<API.AuditTreeData> {
    return request<API.AuditTreeData>("get", "/api/audit/tree");
  },

  /** Create Slot */
  async createSlot(body: API.SlotCreateRequest): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("post", "/api/save/slots", body);
  },

  /** Delete Slot */
  async deleteSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("delete", `/api/save/slots/${slot_id}`);
  },

  /** Get Slot */
  async getSlot(slot_id: string): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("get", `/api/save/slots/${slot_id}`);
  },

  /** List Slots */
  async listSlots(): Promise<API.SlotListData> {
    return request<API.SlotListData>("get", "/api/save/slots");
  },

  /** Load Slot */
  async loadSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/api/save/slots/${slot_id}/load`);
  },

  /** Save Slot */
  async saveSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/api/save/slots/${slot_id}/save`);
  },

  /** Toggle Slot */
  async toggleSlot(slot_id: string): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/api/save/slots/${slot_id}/toggle`);
  },
};
