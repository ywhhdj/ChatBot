// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const characterService = {
  /** 角色列表 */
  async listCharacters(query?: Record<string, any>): Promise<API.CharacterListData> {
    return request<API.CharacterListData>("get", `/character`, query, { opName: "character.list" });
  },

  /** 角色预设（情绪映射等） */
  async presets(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/character/presets`, query, { opName: "character.presets" });
  },

  /** 当前角色 */
  async current(query?: Record<string, any>): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("get", `/character/current`, query, { opName: "character.current" });
  },

  /** 创建角色 */
  async createCharacter(body: API.CharacterCreateRequest): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("post", `/character`, body, { opName: "character.create" });
  },

  /** 角色详情 */
  async getCharacter(character_id: string, query?: Record<string, any>): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("get", `/character/${character_id}`, query, { opName: "character.get", pathParams: { character_id } });
  },

  /** 更新角色 */
  async updateCharacter(character_id: string, body: API.CharacterUpdateRequest): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("put", `/character/${character_id}`, body, { opName: "character.update", pathParams: { character_id } });
  },

  /** 删除角色 */
  async deleteCharacter(character_id: string, body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/character/${character_id}`, body, { opName: "character.delete", pathParams: { character_id } });
  },

  /** 切换当前角色 */
  async switchCharacter(character_id: string, body?: Record<string, any> | null): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("post", `/character/${character_id}/switch`, body, { opName: "character.switch", pathParams: { character_id } });
  },

  /** 角色运行状态 */
  async getState(character_id: string, query?: Record<string, any>): Promise<API.CharacterStateData> {
    return request<API.CharacterStateData>("get", `/character/${character_id}/state`, query, { opName: "character.get_state", pathParams: { character_id } });
  },

  /** 更新角色状态 */
  async updateState(character_id: string, body: API.CharacterStateUpdateRequest): Promise<API.CharacterStateData> {
    return request<API.CharacterStateData>("put", `/character/${character_id}/state`, body, { opName: "character.update_state", pathParams: { character_id } });
  },
};
