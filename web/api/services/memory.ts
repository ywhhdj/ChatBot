// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const memoryService = {
  /** Compressed */
  async compressed(query?: {
      session_id?: string;
      limit?: number;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/memory/compressed", query);
  },

  /** Decay */
  async decay(): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/memory/decay");
  },

  /** Delete Memory */
  async deleteMemory(memory_id: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/memory/${memory_id}`);
  },

  /** Flush */
  async flush(query?: {
      timeout?: number;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/memory/flush", query);
  },

  /** Layers */
  async layers(query?: {
      session_id?: string;
      /** 留空则不检索详细层，延迟更低 */
      query?: string;
      detail_top_k?: number;
      summary_limit?: number;
    }): Promise<API.MemoryLayersData> {
    return request<API.MemoryLayersData>("get", "/memory/layers", query);
  },

  /** Long Term */
  async longTerm(query?: {
      session_id?: string;
      /** 提供时按语义检索 */
      query?: string;
      limit?: number;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/memory/long", query);
  },

  /** Search */
  async search(body: API.MemorySearchRequest): Promise<API.MemorySearchData> {
    return request<API.MemorySearchData>("post", "/memory/search", body);
  },

  /** Short Term */
  async shortTerm(query?: {
      session_id?: string;
      limit?: number;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/memory/short", query);
  },

  /** Stats */
  async stats(query?: {
      session_id?: string;
    }): Promise<API.MemoryStatsData> {
    return request<API.MemoryStatsData>("get", "/memory/stats", query);
  },
};
