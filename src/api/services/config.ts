// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const configService = {
  /** Get Config Api */
  async getConfig(query?: {
      /** 只取某个配置段 */
      section?: string | null;
      /** true 时返回 api_key 等敏感字段原值 */
      raw?: boolean;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/config", query);
  },

  /** Patch Section */
  async patchSection(section: string, body: API.Body_patch_section_api_config__section__patch): Promise<Record<string, any>> {
    return request<Record<string, any>>("patch", `/config/${section}`, body);
  },

  /** Reload */
  async reload(): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/config/reload");
  },

  /** Save */
  async save(body: API.ConfigSaveRequest | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", "/config/save", body);
  },

  /** Schema */
  async schema(query?: {
      /** 只取某段的字段说明 */
      section?: string | null;
    }): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/config/schema", query);
  },
};
