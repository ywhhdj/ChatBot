// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const saveService = {
  /** 全量存档槽（含未激活） */
  async allSlots(query?: Record<string, any>): Promise<API.SlotListData> {
    return request<API.SlotListData>("get", `/save`, query, { opName: "save.all" });
  },

  /** 恢复事务、自动存档与调度器 gate 状态 */
  async snapshotStatus(query?: Record<string, any>): Promise<API.SnapshotActionData> {
    return request<API.SnapshotActionData>("get", `/save/snapshot/status`, query, { opName: "save.snapshot_status" });
  },

  /** revision DAG（parent_revision / branch_id） */
  async snapshotGraph(query?: Record<string, any>): Promise<API.SnapshotActionData> {
    return request<API.SnapshotActionData>("get", `/save/snapshot/graph`, query, { opName: "save.snapshot_graph" });
  },

  /** 恢复预演（只读、无副作用） */
  async snapshotPreview(body?: Record<string, any> | null): Promise<API.SnapshotActionData> {
    return request<API.SnapshotActionData>("post", `/save/snapshot/preview`, body, { opName: "save.snapshot_preview" });
  },

  /** 创建不可变 Snapshot revision */
  async snapshot(body: API.SnapshotRequest): Promise<API.SnapshotActionData> {
    return request<API.SnapshotActionData>("post", `/save/snapshot`, body, { opName: "save.snapshot" });
  },

  /** 执行恢复事务（失败自动回滚） */
  async snapshotRestore(body: API.SnapshotRequest): Promise<API.SnapshotActionData> {
    return request<API.SnapshotActionData>("post", `/save/snapshot/restore`, body, { opName: "save.snapshot_restore" });
  },

  /** 存档槽列表 */
  async listSlots(query?: Record<string, any>): Promise<API.SlotListData> {
    return request<API.SlotListData>("get", `/save/list`, query, { opName: "save.list_slots" });
  },

  /** 创建存档槽 */
  async createSlot(body: API.SlotCreateRequest): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("post", `/save/create`, body, { opName: "save.create" });
  },

  /** 从会话同步到存档槽 */
  async syncFromSessions(body: API.SlotSyncRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/save/sync`, body, { opName: "save.sync" });
  },

  /** 从存档槽恢复到会话 */
  async restoreToSessions(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/save/restore`, body, { opName: "save.restore" });
  },

  /** 存档槽详情 */
  async getSlot(slot_id: string, query?: Record<string, any>): Promise<API.SlotInfoData> {
    return request<API.SlotInfoData>("get", `/save/${slot_id}`, query, { opName: "save.get", pathParams: { slot_id } });
  },

  /** 删除存档槽 */
  async deleteSlot(slot_id: string, body?: Record<string, any> | null): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("delete", `/save/${slot_id}`, body, { opName: "save.delete", pathParams: { slot_id } });
  },

  /** 切换激活存档槽 */
  async toggleSlot(slot_id: string, body?: Record<string, any> | null): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/${slot_id}/toggle`, body, { opName: "save.toggle", pathParams: { slot_id } });
  },

  /** 写入存档 */
  async saveSlot(slot_id: string, body?: Record<string, any> | null): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/${slot_id}/save`, body, { opName: "save.save", pathParams: { slot_id } });
  },

  /** 加载存档 */
  async loadSlot(slot_id: string, body?: Record<string, any> | null): Promise<API.SlotActionData> {
    return request<API.SlotActionData>("post", `/save/${slot_id}/load`, body, { opName: "save.load", pathParams: { slot_id } });
  },

  /** 更新存档分段 */
  async updateSection(slot_id: string, body: API.SlotSectionUpdateRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("put", `/save/${slot_id}/section`, body, { opName: "save.update_section", pathParams: { slot_id } });
  },
};
