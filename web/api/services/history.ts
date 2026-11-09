// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const historyService = {
  /** Append Message */
  async appendMessage(session_id: string, body: API.MessageAppendRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/session/${session_id}/messages`, body);
  },

  /** Create Session */
  async createSession(body: API.SessionCreateRequest): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("post", "/session", body);
  },

  /** Delete Session */
  async deleteSession(session_id: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/session/${session_id}`);
  },

  /** Flush */
  async flush(body: API.FlushRequest | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/session/flush", body);
  },

  /** Get Session */
  async getSession(session_id: string): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("get", `/session/${session_id}`);
  },

  /** List Sessions */
  async listSessions(): Promise<API.SessionListData> {
    return request<API.SessionListData>("get", "/session");
  },

  /** Messages */
  async messages(session_id: string, query?: {
      limit?: number;
    }): Promise<API.MessageListData> {
    return request<API.MessageListData>("get", `/session/${session_id}/messages`, query);
  },

  /** Switch Session */
  async switchSession(session_id: string): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("post", `/session/${session_id}/switch`);
  },
};
