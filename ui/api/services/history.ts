// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const historyService = {
  /** 会话列表 */
  async listSessions(query?: Record<string, any>): Promise<API.SessionListData> {
    return request<API.SessionListData>("get", `/session`, query, { opName: "session.list" });
  },

  /** 创建会话 */
  async createSession(body: API.SessionCreateRequest): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("post", `/session`, body, { opName: "session.create" });
  },

  /** 等待会话后台写入落盘 */
  async flush(body: API.FlushRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/session/flush`, body, { opName: "session.flush" });
  },

  /** 会话详情 */
  async getSession(session_id: string, query?: Record<string, any>): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("get", `/session/${session_id}`, query, { opName: "session.get", pathParams: { session_id } });
  },

  /** 删除会话 */
  async deleteSession(session_id: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/session/${session_id}`, body, { opName: "session.delete", pathParams: { session_id } });
  },

  /** 切换当前会话 */
  async switchSession(session_id: string, body?: Record<string, any> | null): Promise<API.SessionInfoData> {
    return request<API.SessionInfoData>("post", `/session/${session_id}/switch`, body, { opName: "session.switch", pathParams: { session_id } });
  },

  /** 会话消息列表 */
  async messages(session_id: string, query?: Record<string, any>): Promise<API.MessageListData> {
    return request<API.MessageListData>("get", `/session/${session_id}/messages`, query, { opName: "session.messages", pathParams: { session_id } });
  },

  /** 追加一条消息 */
  async appendMessage(session_id: string, body: API.MessageAppendRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/session/${session_id}/messages`, body, { opName: "session.append", pathParams: { session_id } });
  },
};
