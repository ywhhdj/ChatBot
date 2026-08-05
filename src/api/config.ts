import http from "@/utils/http";

export interface AdvancedConfig {
  install_components: string[];
  code_highlight: {
    enabled: boolean;
    theme: string;
  };
  extra: Record<string, unknown>;
}

export async function openFolder(folderPath: string): Promise<boolean> {
  return http.get<boolean>('/open-folder', { folderPath });
}

export async function getConfig(): Promise<AdvancedConfig> {
  return http.get<AdvancedConfig>('/config');
}

// export interface SystemConfig {
//   log_config: {
//     level: string;
//     dir: string;
//   };
//   network_config: {
//     port: number;
//     timeout: number;
//   };
// }

