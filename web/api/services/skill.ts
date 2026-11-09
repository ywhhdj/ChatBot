// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const skillService = {
  /** Activate */
  async activate(skill_id: string): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("post", `/skill/${skill_id}/activate`);
  },

  /** Deactivate */
  async deactivate(skill_id: string): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("post", `/skill/${skill_id}/deactivate`);
  },

  /** Execute */
  async execute(skill_id: string, body: API.SkillExecuteRequest | null): Promise<API.SkillExecuteData> {
    return request<API.SkillExecuteData>("post", `/skill/${skill_id}/execute`, body);
  },

  /** Get Skill */
  async getSkill(skill_id: string): Promise<API.SkillInfoData> {
    return request<API.SkillInfoData>("get", `/skill/${skill_id}`);
  },

  /** List Skills */
  async listSkills(query?: {
      /** 只返回已启用技能 */
      active_only?: boolean;
    }): Promise<API.SkillListData> {
    return request<API.SkillListData>("get", "/skill", query);
  },

  /** Prompt */
  async prompt(): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/skill/prompt");
  },

  /** Reload */
  async reload(): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/skill/reload");
  },
};
