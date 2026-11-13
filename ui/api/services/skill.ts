// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const skillService = {
  /** 技能列表（支持 active_only） */
  async listSkills(query?: Record<string, any>): Promise<API.SkillListData> {
    return request<API.SkillListData>("get", `/skill`, query, { opName: "skill.list" });
  },

  /** 给模型使用的技能提示词 */
  async prompt(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/skill/prompt`, query, { opName: "skill.prompt" });
  },

  /** 重新扫描技能目录 */
  async reload(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/skill/reload`, body, { opName: "skill.reload" });
  },

  /** 技能详情 */
  async getSkill(skill_id: string, query?: Record<string, any>): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("get", `/skill/${skill_id}`, query, { opName: "skill.get", pathParams: { skill_id } });
  },

  /** 启用技能 */
  async activate(skill_id: string, body?: Record<string, any> | null): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("post", `/skill/${skill_id}/activate`, body, { opName: "skill.activate", pathParams: { skill_id } });
  },

  /** 停用技能 */
  async deactivate(skill_id: string, body?: Record<string, any> | null): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("post", `/skill/${skill_id}/deactivate`, body, { opName: "skill.deactivate", pathParams: { skill_id } });
  },

  /** 执行技能（超时 30s，AST 白名单沙盒） */
  async execute(skill_id: string, body: API.SkillExecuteRequest): Promise<API.SkillExecuteData> {
    return request<API.SkillExecuteData>("post", `/skill/${skill_id}/execute`, body, { opName: "skill.execute", pathParams: { skill_id } });
  },
};
