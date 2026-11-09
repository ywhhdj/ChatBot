// 此文件由 scripts/api/generate.py 自动生成，请勿手动编辑。
import { request } from "../http";

export const taskService = {
  /** Cancel Task */
  async cancelTask(task_id: string): Promise<API.TaskStatusData> {
    return request<API.TaskStatusData>("post", `/task/${task_id}/cancel`);
  },

  /** Get Task */
  async getTask(task_id: string, query?: {
      /** true 时阻塞等待任务完成 */
      wait?: boolean;
      timeout?: number;
    }): Promise<API.TaskStatusData> {
    return request<API.TaskStatusData>("get", `/task/${task_id}`, query);
  },
};
