// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const configService = {
  /** 读取配置，可按 section 过滤 */
  async getConfigApi(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/config`, query, { opName: "config.get" });
  },

  /** 配置字段描述 */
  async schema(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/config/schema`, query, { opName: "config.schema" });
  },

  /** 从配置文件重新加载 */
  async reload(body?: Record<string, any> | null): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/config/reload`, body, { opName: "config.reload" });
  },

  /** 持久化配置到磁盘 */
  async save(body: API.ConfigSaveRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("post", `/config/save`, body, { opName: "config.save" });
  },

  /** 局部更新配置段 */
  async patchSection(section: string, body: API.ConfigPatchRequest): Promise<Record<string, any>> {
    return request<Record<string, any>>("patch", `/config/${section}`, body, { opName: "config.patch_section", pathParams: { section } });
  },
};

// ── 页面级前端本地配置：AdvancedConfig / SystemConfig 仅存在于浏览器，
// ── 不对应后端端点（后端 /config 的 section 白名单见 docs/api.md §3.3）。
export interface AdvancedConfig {
  install_components?: string[];
  code_highlight?: { enabled?: boolean; theme?: string };
  extra?: Record<string, any>;
}

export interface SystemConfig {
  log_config?: { level?: string; dir?: string };
  network_config?: { port?: number; timeout?: number };
}

const LOCAL_CONFIG_KEY = "chatbot.page_config";
const DEFAULT_PAGE_CONFIG = { advanced: {}, system: {} } as {
  advanced: AdvancedConfig;
  system: SystemConfig;
};

function readPageConfig(): typeof DEFAULT_PAGE_CONFIG {
  try {
    const raw = localStorage.getItem(LOCAL_CONFIG_KEY);
    return raw ? { ...DEFAULT_PAGE_CONFIG, ...JSON.parse(raw) } : DEFAULT_PAGE_CONFIG;
  } catch {
    return DEFAULT_PAGE_CONFIG;
  }
}

function writePageConfig(next: typeof DEFAULT_PAGE_CONFIG): void {
  localStorage.setItem(LOCAL_CONFIG_KEY, JSON.stringify(next));
}

export async function getAdvancedConfig(): Promise<AdvancedConfig> {
  return readPageConfig().advanced;
}

export async function saveAdvancedConfig(config: AdvancedConfig): Promise<void> {
  writePageConfig({ ...readPageConfig(), advanced: config });
}

export async function getSystemConfig(): Promise<SystemConfig> {
  return readPageConfig().system;
}

export async function saveSystemConfig(config: SystemConfig): Promise<void> {
  writePageConfig({ ...readPageConfig(), system: config });
}
