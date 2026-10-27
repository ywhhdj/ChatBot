# 硬性约束
- 不下载依赖、不执行构建/测试：只产出工程源码与构建脚本，构建动作由使用者在本地执行。
- 可维护优先：单一职责、接口隔离、模块边界清晰，禁止跨层反向依赖。
- 每次完成一步必须记录进度PLAN.md 计划

# ChatBot 工程架构设计索引

> 本文档集以 \`dev\` 源码为事实基线。标记为“目标设计/提议”的内容尚需按实施计划落地；文档描述不代表相应运行功能已经实现。
>
> 范围：架构与计划设计，不修改业务源码。遵循项目约定，不自动安装依赖、不执行构建/测试。

## 1. 目标架构

ChatBot 是一个以 Python 为核心的本地/桌面 AI 助手，包含 FastAPI REST、SSE/WebSocket、Vue 3 + TypeScript 前端、Qt WebChannel bridge、模型管道、工具/技能、角色与会话、混合记忆和存档。

目标是维持模块化单体部署，明确领域边界及 transport/存储适配边界。重点不是增加层数，而是让一次对话、一次记忆查询、一次工具执行、一次存档/恢复都具有明确的输入、所有权、状态、失败语义和验收条件。

核心要求：
- 上下文以请求为作用域，以 session 为隔离边界；禁止从共享全局 deque 构建未过滤的多会话 prompt。
- 角色、用户输入、会话历史、检索记忆、工具能力和工具结果独立建模，再由 PromptBuilder 按优先级和 token 预算装配。
- REST、SSE、WebSocket、Qt bridge 共用业务 DTO、错误语义、身份/权限策略与 request/task 关联。
- 存储通过模块自己的 Originator/Repository/Adapter 访问；游戏存档通过 Memento snapshot 组合领域快照，不把路径指针误称完整快照。
- 安全检查由确定性代码负责；检索和 LLM 不拥有权限；删除墓碑优先于旧存档恢复。
- 性能优化先建立延迟、队列、内存、检索质量基准，不提前引入微服务或不必要的外部基础设施。

## 2. 源码模块地图

| 路径 | 当前职责 |
|---|---|
| \`src_py/modules/api/\` | FastAPI 服务、REST 控制器、统一响应/异常、WebSocket |
| \`src_py/modules/pipeline/\` | chat 入口、角色/工具编排、LLM/TTS/ASR/OCR adapters |
| \`src_py/modules/context/\` | UserContext、音频等输入上下文 |
| \`src_py/modules/manager/session/\` | 会话元数据、round record 与消息持久化 |
| \`src_py/modules/manager/saves/\` | SaveSlotManager、slot section 与 index/data YAML |
| \`src_py/modules/manager/character.py\` | 角色管理与运行状态 |
| \`src_py/modules/memory/\` | HybridMemorySystem、embedding、SQLite/Markdown、FAISS、RAG、压缩 |
| \`src_py/modules/events/\` | 线程安全事件总线及事件类型 |
| \`src_py/modules/tools/\`、\`services/\` | 技能、工具执行与外部服务 |
| \`src_py/modules/runtime.py\` | 应用/用户数据目录与运行时管理 |
| \`src/api/services/\`、\`src/api/http.ts\` | 前端领域 API service 和 Axios/Qt bridge 适配 |
| \`src/stores/\`、\`src/router/\`、\`src/views/\` | Pinia 状态、页面路由和 UI |

## 3. 文档导航

### 总体和后端
- [BackendDesign.md](BackendDesign.md)：模块依赖方向、线程模型、请求生命周期、provider、任务、存储与安全。
- [BackendPlan.md](BackendPlan.md)：分优先级实施工作、依赖关系、验收与回滚。
- [ArchitectureDecisionRecords.md](ArchitectureDecisionRecords.md)：架构决策、备选方案和接受标准。

### 上下文、记忆与存档
- [ContextArchitecture.md](ContextArchitecture.md)：request/session/character/tool/memory 上下文隔离、PromptBuilder、token 预算与迁移。**当前优先审查跨 session 上下文污染风险。**
- [MemoryDesign.md](MemoryDesign.md)：当前记忆实现、五层逻辑记忆、模糊检索、置信/冲突、衰减、压缩、索引一致性和删除语义。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：当前 Slot/路径指针模型与目标 Memento：不可变 Snapshot、manifest/hash、preview/prepare/commit/rollback、旧格式兼容。
- [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)：威胁模型、秘密、技能沙盒、审计事件、数据删除和恢复风险。

### 前后端契约
- [api.md](api.md)：外部路径、请求/响应、错误码、SSE/WS 事件及源码差异。
- [FrontendBackendContract.md](FrontendBackendContract.md)：REST/SSE/WebSocket/Qt bridge 统一契约、ID 语义、超时/取消/幂等和 API 生成流程。
- [FrontendDesign.md](FrontendDesign.md)：Vue/Pinia/API service、桌面桥接、流式请求和 UI 资源生命周期。
- [FrontendPlan.md](FrontendPlan.md)：契约对齐、流式隔离、上下文绑定、存档 UI 和性能工作。

## 4. 核心设计约束

1. **单一职责**：Controller 做协议校验/映射；Application Service 协调用例；Domain Manager 维护业务不变量；Adapter 负责具体 provider/文件/DB/transport。
2. **依赖朝内**：领域层不依赖 FastAPI、Vue、Qt widget、具体 LLM SDK 或具体向量库。
3. **上下文不共享隐式状态**：每个请求显式传 request_id/session_id/character_id；每条消息保留 session_id/source/role；检索先过滤 scope。
4. **会话与存档分离**：Session 是对话容器，Slot 是用户存档入口，Snapshot 是不可变的一致性版本。
5. **transport 共享契约**：Axios/Qt bridge 不可分别定义成功码；SSE/WS 的流事件需 request_id/stream_id 与明确终态。
6. **异步有界**：工作队列、连接并发、模型工具步数、响应字节、音视频大小、总 deadline 均有限制；后台任务有状态与异常回收。
7. **数据变更可恢复**：记忆索引和元数据有修复流程；快照是 stage/validate/publish；恢复是 preview/prepare/commit/verify。
8. **删除高于恢复**：隐私删除 tombstone 必须在压缩、缓存、备份和 restore 后仍然有效。
9. **可审计而不泄露**：通过 request/task/op id 关联事件；普通日志不记录完整 prompt、记忆正文和 secret。
10. **先测量再优化**：缓存、RRF、reranker、批量 embedding 和新的索引都要有基线和回滚开关。

## 5. 已确认的源码设计风险

| 优先级 | 观察 | 处置方向 |
|---|---|---|
| P0 | \`UserContext\` 是单例，共享 deque；\`get_current_messages()\` 未按 session_id 过滤，而 Orchestrator 使用此消息集合构建 prompt | 优先重构 session-scoped ContextStore，增加并发交错隔离测试 |
| P0 | 后端成功 code 当前为 200，而 \`src/api/http.ts\` 桌面 bridge 分支判断 code=0 | 共用响应 decoder |
| P0 | Controller registration 统一加 \`/api\`，save/audit router 自身也含 \`/api\` 前缀 | 导出真实路由清单并修正重复前缀 |
| P1 | WebSocket 注册点使用 \`app.websocket("/")\`，旧文档写 \`/ws\` | 通过 server mount 和实际客户端确认唯一稳定路径 |
| P1 | \`data.yaml\` 保存路径指针/部分配置，不是全量游戏状态 | 区分 Slot 与 Full Snapshot，提供 originator snapshot adapters |
| P1 | FAISS 向量索引与 SQLite 元数据无法组成一个原子事务；embedding 有 hash fallback | index health check、版本指纹、repair/rebuild 和评估集 |
| P1 | 前端 API service 生成源/类型生成流程需要单一权威 | OpenAPI/DTO/client/doc 契约检查 |
| P2 | audit controller 当前主要列出能力目录，并非完整的安全事件审计日志 | 独立定义 actor/action/decision/result 与 retention |

“源码风险”只说明静态审阅的观察和待确认项，不等于本次已修改行为。路由相关问题必须以应用的实际注册路径/OpenAPI 导出为最终依据。

## 6. 推荐实施顺序

1. P0：修复 session context 隔离、HTTP/bridge 成功码、重复路由前缀，并生成权威 API route inventory。
2. P0/P1：建立共享 ContextSnapshot/PromptBuilder 契约；为 SSE/WS/Qt bridge 统一 request/stream/task ID、错误、取消与 deadline。
3. P1：定义 memory provenance/confidence/validity schema migration、索引修复与删除墓碑。
4. P1：建立 Snapshot Originator adapters、manifest 与不可变 revisions；实现 preview/prepare/commit/rollback，而非直接覆盖 data.yaml。
5. P1：生成统一前端 API types/services 和 transport contract tests。
6. P2：离线评估多语言混合检索、性能和 token budget；按基准启用 RRF/reranker/cache。
7. P2：建立审计事件与可观测性，梳理保留期、脱敏和导出策略。

每一步必须在对应 Plan 中记录代码范围、迁移方案、测试、回滚和验收状态。

## 架构优化增补文档

| 文档 | 内容 |
|---|---|
| [OptimizationPlan.md](OptimizationPlan.md) | 总体计划：阶段、任务、依赖、开关、KPI、风险 |
| [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md) | 类人记忆曲线与遗忘机制（强度模型、状态机、固化、评估） |
| [LayeredArchitecture.md](LayeredArchitecture.md) | 前后端分层、端口、依赖规则、迁移与自动检查 |
| [MementoMemoryIntegration.md](MementoMemoryIntegration.md) | 存档与记忆强度/时钟整合、时间线与分支、自动存档 |
| [reference/](reference/) | 强度模型参考实现与属性测试（仅标准库） |
