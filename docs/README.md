# ChatBot 工程设计索引

> 分支基线：dev（审阅提交 c5e6343ec4b3913caaa04e5f6af2c34327213314）
> 范围：只更新设计文档和计划，不修改业务源码。

## 1. 项目现状

ChatBot 是一个以 Python 为核心的本地/桌面 AI 助手，包含 FastAPI REST、SSE/WebSocket、Vue 3 + TypeScript 前端、模型管道适配器、工具/技能系统、会话与存档、混合记忆及本地文件存储。Qt 主线程、WebServer asyncio loop、任务调度器、事件总线和存储 worker 的边界，是后端正确性与性能的关键。

| 路径 | 当前职责 |
|---|---|
| src_py/modules/api/ | FastAPI 服务、REST 控制器、统一响应、异常处理、WebSocket |
| src_py/modules/manager/ | 会话、角色、服务、任务调度和存档运行时管理 |
| src_py/modules/pipeline/ | LLM、TTS、ASR、OCR 适配器及对话路由 |
| src_py/modules/memory/ | 混合记忆、embedding、Markdown/SQLite 存储、FAISS、RAG |
| src_py/modules/context/ | 会话上下文和 prompt 数据 |
| src_py/modules/events/ | 线程安全事件总线与事件类型 |
| src_py/modules/tools/、services/ | 技能执行、工具编排和外部服务 |
| resources/defaults/ | 默认配置、提示词、角色和记忆 SQL schema |
| src/ | Vue 前端入口、页面、状态管理、API service |
| scripts/api/、scripts/gen_api_types.mjs | API 生成/类型相关流程，需统一权威入口 |

## 2. 文档导航

- [后端架构设计](BackendDesign.md)：模块边界、线程、编排、存档、性能与安全。
- [后端实施计划](BackendPlan.md)：P0/P1/P2 任务、依赖、验收与回滚。
- [前端架构设计](FrontendDesign.md)：Vue、Pinia、API service、桌面桥接和流式状态。
- [前端实施计划](FrontendPlan.md)：契约修复、流式交互、状态一致性与性能。
- [记忆系统设计](MemoryDesign.md)：现状、分层、模糊检索、衰减、压缩、归档和删除。
- [API 契约](api.md)：REST、SSE、WebSocket、响应信封及差异记录。
- [安全与审计设计](SecurityAndAuditDesign.md)：威胁模型、密钥、技能执行、事件审计和数据删除。
- [架构决策记录](ArchitectureDecisionRecords.md)：需要评审的方案及其理由。

## 3. 工程硬约束

1. 只依据真实源码断言现状；新机制必须标为目标方案，不能写成已经完成。
2. 分层解耦：Controller 处理协议/输入校验/响应映射，领域逻辑留在应用与管理模块，供应商和存储细节放在适配器。
3. 不跨层反向依赖；领域核心不得依赖 FastAPI、Vue、Qt UI 或具体模型供应商。
4. 先检查 api.md 再改接口；保持路由、字段、错误码、事件名和流式语义兼容，破坏性变更必须有迁移窗口。
5. Qt 主线程不运行常驻 asyncio loop；线程内已有运行中 loop 时不能嵌套 asyncio.run；跨线程派发要显式可追踪。
6. 后台任务必须保存引用、回收异常、设置超时/取消策略并在 shutdown 时有界收尾。
7. 安全检查由确定性代码执行；LLM 输出不得作为授权证明。
8. 记忆元数据、FAISS index 和存档 revision 必须定义一致性、失败补偿、校验与恢复规则。
9. 每个实施任务维护 Plan，写清影响面、验收、失败路径、回滚与数据迁移。
10. 按仓库约定不自动下载依赖、不执行构建/测试；本轮只做 Markdown、链接和契约静态检查。

## 4. 当前源码审阅发现

| 级别 | 问题 | 影响 |
|---|---|---|
| P0 | 后端成功 code 是 200，但 src/api/http.ts 的 desktop bridge 分支判断 code === 0 | 桌面请求可能把成功响应当作失败 |
| P0 | controllers/__init__.py 给所有 router 加 /api；save.py、audit.py 的 router 自带 /api/save、/api/audit | 可能形成 /api/api/... 双前缀；必须用 FastAPI 实际注册路由核实后修正 |
| P1 | api.md 有 SSE 路径示例笔误，未完整列出 PPT/审计等控制器 | 文档与实际注册路径可能漂移 |
| P1 | 前端 HTTP 与 bridge 的信封解包逻辑分开实现 | 错误码、request_id 与通知语义容易分叉 |
| P1 | API 生成脚本/生成产物权威来源待统一 | 后端 DTO、文档和 TS service/types 可能产生漂移 |
| P1 | hash embedding、FAISS 映射、Markdown fallback 与删除传播缺少端到端验收契约 | 可能出现召回质量差、孤儿向量或后端语义不一致 |
| P2 | 存档为 index.yaml + 每槽 data.yaml，缺少完整不可变 revision/恢复预演约定 | 失败恢复、追溯与旧快照删除保护不足 |
| P2 | audit controller 主要列出服务/工具能力，不等于完整安全审计 | 必须另定义记录 actor、动作、决策、结果和保留期 |

以上是文档审阅发现，不代表本次已修复运行行为。涉及实际路由的判断需再以 app.routes/OpenAPI 清单确认。

## 5. 架构方向

- 保持模块化单体，不为“先进”而提前拆微服务。
- 以应用服务、明确的协议/存储端口和适配器降低耦合；拆进程必须由性能或故障隔离数据驱动。
- 记忆按工作、情节、语义、摘要、冷档案划分逻辑层，底层初期继续使用现有 SQLite/FAISS/Markdown。
- 存档借鉴 Memento：不可变版本、manifest、哈希校验、恢复预演、提交/回滚和删除墓碑。
- 统一 request_id/trace_id、结构化任务状态与低基数指标；普通日志不写秘密、完整 prompt 或私人记忆。
- API 契约只保留一个权威来源；生成类型/服务文件不得手工漂移。
- 任何检索权重、缓存或 reranker 优化先建立基准，再决定是否启用。

## 6. 推荐阅读顺序

1. [API 契约](api.md)
2. [后端架构](BackendDesign.md) 与 [前端架构](FrontendDesign.md)
3. [记忆设计](MemoryDesign.md) 与 [安全审计](SecurityAndAuditDesign.md)
4. [后端计划](BackendPlan.md) 与 [前端计划](FrontendPlan.md)
5. [架构决策记录](ArchitectureDecisionRecords.md)
