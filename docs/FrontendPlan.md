# 前端架构优化计划

## P0 — API 一致性

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| F0-01 | 合并 Axios 与 Qt bridge 的响应解包 | Shared response decoder | 成功 code=200 在两种 transport 结果一致；失败保留 request_id |
| F0-02 | 对齐 service URL 与后端真实路由 | URL/verb/DTO 对照表 | 全部 service 与 api.md 的实际注册路由一致 |
| F0-03 | 修复 bridge path parameter 映射 | 显式 operation metadata 与 mapper | session_id、slot_id、character_id 传入实际值，不发送 URL 占位符 |
| F0-04 | 统一错误对象和通知归属 | ApiClientError contract | 单次失败只有一条通知；取消不误报；超时独立分类 |
| F0-05 | 定义 API 生成单一来源 | generation guide | 类型、service 与源定义一致，不手工编辑生成产物 |

## P1 — 流式交互与状态生命周期

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| F1-01 | 统一 stream 状态机 | stream composable/controller | 状态迁移无冲突，终态只处理一次 |
| F1-02 | 通过 request_id 关联 stream 事件 | event correlation map | 多条并发流的 chunk 不交叉 |
| F1-03 | 页面卸载与重连资源清理 | lifecycle checklist | 订阅、AbortController、WebSocket 和 Blob URL 无遗留 |
| F1-04 | 分离工具结果和聊天消息 | task store/UI contract | tool result/task.update 不污染聊天正文 |
| F1-05 | 以后端状态刷新 store | invalidation strategy | save/session/character/service 变更反映后端最终结果 |

## P2 — 性能、隐私和可访问性

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| F2-01 | 长历史虚拟滚动和增量渲染 | profiling report | chunk 到达时不重绘全消息列表 |
| F2-02 | 秘密字段 UI 规则 | secret-field policy | provider key 不回显、不持久化、不进 console |
| F2-03 | Web/desktop 共用契约测试 | shared contract matrix | 同用例覆盖 Axios 与 Qt bridge |
| F2-04 | loading/empty/error/confirm 状态 | UX checklist | 高影响操作有明确状态和确认 |
| F2-05 | 性能基线 | measured report | 测首屏、滚动、流式刷新、内存和卸载后资源释放 |

## 任务依赖

~~~text
F0-01 + F0-02 + F0-03 → F0-05
F0-01 → F1-01 → F1-02 → F1-03
F0-02 → F1-05
F1-02 → F1-04
F1-03 + F2-01 → F2-05
F0-04 + F2-02 → 安全验收
~~~

## Definition of Done

- 先更新 FrontendDesign.md 和必要的 api.md。
- 写清旧行为/新行为，以及 Web/desktop 两条 transport 的差异。
- 覆盖正常、业务错误、网络错误、timeout、取消、重复点击、卸载和并发情况。
- 自动生成文件与权威源一致；生成命令写入文档。
- 不将服务端秘密存进浏览器存储；通知不是异常处理的替代。
- 遵守仓库约束：本轮不下载依赖、不执行 build/test。


## 4. 前后端交互、上下文与存档 UI 增补

细节契约见 [FrontendBackendContract.md](FrontendBackendContract.md)、上下文规则见 [ContextArchitecture.md](ContextArchitecture.md)、存档流程见 [GameSaveArchitecture.md](GameSaveArchitecture.md)。

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| F0-06 | P0 | 所有聊天与记忆请求显式传 session_id/character_id | 不允许用隐式全局当前会话构建 request |
| F0-07 | P0 | Web/desktop 共用 ApiResponse decoder | 相同响应在 Axios 与 bridge 中产生相同结果 |
| F1-06 | P1 | session/character 切换前中止或 detach 旧 stream | 无迟到事件覆盖当前 store |
| F1-07 | P1 | 为流与后台任务使用 request_id/stream_id/task_id | 所有 chunk/状态都能归属到会话和任务 |
| F1-08 | P1 | 存档列表显示 slot 与 snapshot 类型/版本 | 旧槽不被误标为 Full snapshot |
| F1-09 | P1 | 恢复前展示 RestorePlan | 用户能看见覆盖范围、缺失资产、迁移与警告 |
| F2-06 | P2 | 删除记忆后清理 UI memory cache | 页面、搜索结果和缓存都不显示已删除条目 |
| F2-07 | P2 | 流式消息虚拟化与 token 批量刷新 | 长对话增长时渲染成本有界 |

### 存档交互状态

目标状态机：

~~~text
idle → creating → validating → committed
                     ↘ failed
idle → previewing → ready_to_restore → restoring
                                      ├→ restored
                                      ├→ rolled_back
                                      └→ partial_failure
~~~

前端只根据服务端 operation 状态更新 UI。用户点击“保存”后不能立刻显示已保存；应等待 committed。恢复遇到 partial_failure 时必须呈现明确警告和操作记录，不得当作普通失败 toast 隐藏。

## 增补任务（与总体计划对齐）

任务 FX-01~FX-09（共享 decoder、会话分片、流守卫、services 整理与 ESLint 限制、operation 轮询、存档时间线 UI、保持率 UI、契约单一来源、四 transport 契约矩阵）及依赖见 [OptimizationPlan.md](OptimizationPlan.md) 第 5.5 节。合并时需与本文既有任务 ID 去重。