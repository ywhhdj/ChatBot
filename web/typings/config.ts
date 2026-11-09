export const SECTIONS = [
  "characters",
  "ui",
  "chat_history",
  "achievements",
  "story",
  "config",
  "memory",
  "session",
  "skill",
  "ppt",
] as const;

export type SectionName = (typeof SECTIONS)[number];

/** 索引型 section：只存指针，不存正文 */
export const INDEX_SECTIONS: SectionName[] = [
  "memory",
  "session",
  "ppt",
  "skill",
];

export const SECTION_LABELS: Record<SectionName, string> = {
  characters: "角色",
  ui: "界面",
  chat_history: "对话记录",
  achievements: "成就",
  story: "剧情",
  config: "配置",
  memory: "记忆",
  session: "会话",
  skill: "技能",
  ppt: "PPT",
};

export interface SlotMeta {
  create_time: string;
  update_time: string;
  last_chat: string;
  description: string;
}

export interface SlotInfo {
  id: string;
  name: string;
  meta: SlotMeta;
  sections: string[];
}