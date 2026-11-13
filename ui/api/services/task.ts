// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const taskService = {
  /** 查询后台任务状态与结果 */
  async getTask(task_id: string, query?: Record<string, any>): Promise<API.TaskStatusData> {
    return request<API.TaskStatusData>("get", `/task/${task_id}`, query, { opName: "task.get", pathParams: { task_id } });
  },

  /** 取消任务（尽力而为） */
  async cancelTask(task_id: string, body: API.TaskCancelRequest): Promise<API.TaskStatusData> {
    return request<API.TaskStatusData>("post", `/task/${task_id}/cancel`, body, { opName: "task.cancel", pathParams: { task_id } });
  },
};
