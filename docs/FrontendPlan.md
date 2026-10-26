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
