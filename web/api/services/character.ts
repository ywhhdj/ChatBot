// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const characterService = {
  /** Create Character */
  async createCharacter(body: API.CharacterCreateRequest): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("post", "/character", body);
  },

  /** Current */
  async current(): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("get", "/character/current");
  },

  /** Delete Character */
  async deleteCharacter(character_id: string): Promise<Record<string, any>> {
    return request<Record<string, any>>("delete", `/character/${character_id}`);
  },

  /** Get Character */
  async getCharacter(character_id: string): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("get", `/character/${character_id}`);
  },

  /** Get State */
  async getState(character_id: string): Promise<API.CharacterStateData> {
    return request<API.CharacterStateData>("get", `/character/${character_id}/state`);
  },

  /** List Characters */
  async listCharacters(): Promise<API.CharacterListData> {
    return request<API.CharacterListData>("get", "/character");
  },

  /** Presets */
  async presets(): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", "/character/presets");
  },

  /** Switch Character */
  async switchCharacter(character_id: string): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("post", `/character/${character_id}/switch`);
  },

  /** Update Character */
  async updateCharacter(character_id: string, body: API.CharacterUpdateRequest): Promise<API.CharacterInfoData> {
    return request<API.CharacterInfoData>("put", `/character/${character_id}`, body);
  },

  /** Update State */
  async updateState(character_id: string, body: API.CharacterStateUpdateRequest): Promise<API.CharacterStateData> {
    return request<API.CharacterStateData>("post", `/character/${character_id}/state`, body);
  },
};
