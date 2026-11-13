// 此文件由 scripts/api/generate_frontend_services.py 自动生成，请勿手动编辑。
// 契约源：resources/configs/api/endpoints.json（由 generate_api_contract.py 生成）
// 重新生成：python scripts/api/generate_frontend_services.py
import { request } from "../http";

export const apiService = {
  /** 服务 → 方法 → 参数 能力树 */
  async tree(query?: Record<string, any>): Promise<API.AuditTreeData> {
    return request<API.AuditTreeData>("get", `/audit/tree`, query, { opName: "audit.tree" });
  },

  /** 扁平工具清单 */
  async tools(query?: Record<string, any>): Promise<Record<string, any>> {
    return request<Record<string, any>>("get", `/audit/tools`, query, { opName: "audit.tools" });
  },

  /** PPT 模板列表 */
  async templates(query?: Record<string, any>): Promise<API.PptTemplateListData> {
    return request<API.PptTemplateListData>("get", `/ppt/templates`, query, { opName: "ppt.templates" });
  },

  /** 生成内容大纲（不渲染） */
  async outline(body: API.PptOutlineRequest): Promise<API.PptOutlineData> {
    return request<API.PptOutlineData>("post", `/ppt/outline`, body, { opName: "ppt.outline" });
  },

  /** 提交渲染后台任务，返回 task_id */
  async render(body: API.PptRenderRequest): Promise<API.PptRenderData> {
    return request<API.PptRenderData>("post", `/ppt/render`, body, { opName: "ppt.render" });
  },

  /** 提交渲染后台任务（render 的显式异步别名） */
  async renderAsync(body: API.PptRenderRequest): Promise<API.PptRenderData> {
    return request<API.PptRenderData>("post", `/ppt/render/async`, body, { opName: "ppt.render_async" });
  },

  /** 查询渲染任务 */
  async jobStatus(task_id: string, query?: Record<string, any>): Promise<API.PptJobData> {
    return request<API.PptJobData>("get", `/ppt/job/${task_id}`, query, { opName: "ppt.status", pathParams: { task_id } });
  },

  /** 取回产出文件（base64 + 路径） */
  async download(file_name: string, query?: Record<string, any>): Promise<API.PptDownloadData> {
    return request<API.PptDownloadData>("get", `/ppt/download/${file_name}`, query, { opName: "ppt.download", pathParams: { file_name } });
  },
};
