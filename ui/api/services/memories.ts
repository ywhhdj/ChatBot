// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const memoriesService = {
  /** 分层记忆（short_term / long_term / detailed） */
  async layers(query?: Record<string, any>): Promise<API.MemoryLayersData> {
    return request<API.MemoryLayersData>("get", `/memories/layers`, query, { opName: "memories.layers" });
  },

  /** 短期记忆摘要 */
  async shortTerm(query?: Record<string, any>): Promise<API.MemoryShortTermData> {
    return request<API.MemoryShortTermData>("get", `/memories/short`, query, { opName: "memories.short_term" });
  },

  /** 长期记忆 */
  async longTerm(query?: Record<string, any>): Promise<API.MemoryLongTermData> {
    return request<API.MemoryLongTermData>("get", `/memories/long`, query, { opName: "memories.long_term" });
  },

  /** 语义 / 相关记忆检索 */
  async search(body: API.MemorySearchRequest): Promise<API.MemorySearchData> {
    return request<API.MemorySearchData>("post", `/memories/search`, body, { opName: "memories.search" });
  },

  /** 压缩记忆列表 */
  async compressed(query?: Record<string, any>): Promise<API.MemoryCompressedListData> {
    return request<API.MemoryCompressedListData>("get", `/memories/compressed`, query, { opName: "memories.compressed" });
  },

  /** 记忆容量统计 */
  async stats(query?: Record<string, any>): Promise<API.MemoryStatsData> {
    return request<API.MemoryStatsData>("get", `/memories/stats`, query, { opName: "memories.stats" });
  },

  /** 手动触发记忆衰减 */
  async decay(body?: Record<string, any> | null): Promise<API.MemoryDecayData> {
    return request<API.MemoryDecayData>("post", `/memories/decay`, body, { opName: "memories.decay" });
  },

  /** 等待后台写入完成 */
  async flush(body?: Record<string, any> | null): Promise<API.MemoryFlushData> {
    return request<API.MemoryFlushData>("post", `/memories/flush`, body, { opName: "memories.flush" });
  },

  /** 设置记忆保留期 / 层级（默认预演） */
  async retention(body: API.MemoryActionRequest): Promise<API.MemoryActionData> {
    return request<API.MemoryActionData>("post", `/memories/retention`, body, { opName: "memories.retention" });
  },

  /** 固定 / 取消固定一条记忆 */
  async pin(body: API.MemoryActionRequest): Promise<API.MemoryActionData> {
    return request<API.MemoryActionData>("post", `/memories/pin`, body, { opName: "memories.pin" });
  },

  /** 唤醒 faded / archived 记忆 */
  async revive(body: API.MemoryActionRequest): Promise<API.MemoryActionData> {
    return request<API.MemoryActionData>("post", `/memories/revive`, body, { opName: "memories.revive" });
  },

  /** 删除单条记忆（墓碑协议） */
  async deleteMemory(memory_id: string, body?: Record<string, any> | null): Promise<API.MemoryDeleteData> {
    return request<API.MemoryDeleteData>("delete", `/memories/${memory_id}`, body, { opName: "memories.delete_memory", pathParams: { memory_id } });
  },
};
