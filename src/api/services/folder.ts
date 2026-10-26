// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const folderService = {
  /** Open Folder */
  async openFolder(type: string): Promise<null> {
    return request<null>("get", `/folder/${type}`);
  },
};
