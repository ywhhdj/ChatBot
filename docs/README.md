# 硬性约束
- 不下载依赖、不执行构建/测试：只产出工程源码与构建脚本，构建动作由使用者在本地执行。
- 可维护优先：单一职责、接口隔离、模块边界清晰，禁止跨层反向依赖。
- 每次完成一步必须记录进度 PLAN.md 计划

# ChatBot 工程架构设计索引

> 本文档集以 `dev` 源码为事实基线。标记为「目标设计/待办」的内容尚需按实施计划落地；文档描述不代表相应运行功能已经实现。
>
> 范围：架构与计划设计，不修改业务源码。遵循项目约定，不自动安装依赖、不执行构建/测试。

## 1. 目标架构

ChatBot 是一个以 Python 为核心的本地/桌面 AI 助手，包含 FastAPI REST、SSE/WebSocket、Vue 3 + TypeScript 前端、Qt WebChannel bridge、模型管道、工具/技能、服务与外部能力、角色与会话、混合记忆和存档，以及 Rust 扩展提供的调度器与内存总线。

目标是维持模块化单体部署，明确领域边界及 transport/存储适配边界。重点不是增加层数，而是让一次对话、一次记忆查询、一次工具执行、一次存档/恢复都具有明确的输入、所有权、状态、失败语义和验收条件。

核心要求：
- 上下文以请求为作用域，以 session 为隔离边界；禁止从共享全局 deque 构建未过滤的多会话 prompt。
- 角色、用户输入、会话历史、检索记忆、工具能力和工具结果独立建模，再由 PromptBuilder 按优先级和 token 预算装配。
- REST、SSE、WebSocket、Qt bridge 共用业务 DTO、错误语义、身份/权限策略与 request/task 关联。
- 端点以 `resources/config/api/endpoints.json` 为唯一权威源；`/api` 前缀只在注册器添加一次。
- 存储通过模块自己的 Originator/Repository/Adapter 访问；游戏存档通过 Memento snapshot 组合领域快照。
- 安全检查由确定性代码负责；检索和 LLM 不拥有权限；删除墓碑优先于旧存档恢复。
- **所有服务产出与命令执行都受 `security/workspace` 工作区边界约束**。
- 性能优化先建立延迟、队列、内存、检索质量基准，不提前引入微服务或不必要的外部基础设施。

## 2. 源码模块地图（真实路径）

| 路径 | 当前职责 |
|---|---|
| `src_py/main.py`、`modules/app.py` | 进程入口、Application 生命周期与优雅停机 |
| `src_py/modules/api/` | `endpoints.json` 驱动的 loader/registry、网关 op 表、REST 处理函数、统一响应/异常、WebSocket |
| `src_py/modules/core/pipeline/` | chat 入口、编排、LLM/TTS/ASR/OCR/landmarker adapters |
| `src_py/modules/core/context/` | PromptBuilder、token budget、上下文装配与存储 |
| `src_py/modules/core/routes/` | 意图路由与 RouteType |
| `src_py/modules/core/tools/` | 命令解析/校验/策略/执行、技能管理与 AST 沙盒、工具追踪 |
| `src_py/modules/core/native/`、`src_py/native/` | Rust 扩展绑定、调度器、任务状态 |
| `src_py/modules/services/` | 服务基类/管理器/配置；`browser`、`live2d`、`obs`、`qqbot`、`ppt`、`shell`、`knowledge`、`game` |
| `src_py/modules/security/` | 工作区权限、路径边界、敏感脱敏、轨迹保护、服务输出目录 |
| `src_py/modules/manager/session/`、`saves/` | 会话元数据、round record、存档槽与 Memento 快照 |
| `src_py/modules/manager/character.py` | 角色管理与运行状态 |
| `src_py/modules/ memory/` | HybridMemorySystem、embedding、SQLite/Markdown、向量、RAG、压缩 |
| `src_py/modules/providers/` | provider 实体、工厂与适配器 |
| `src_py/modules/events/`、`logger/`、`ui/`、`utils/` | 事件总线、日志与轨迹、Qt 派发与 Bridge、文件/HTTP 工具 |
| `src_py/modules/runtime.py` | 应用/用户数据目录与运行时管理、默认工作区根目录 |
| `resources/config/api/` | `endpoints.json`（路由权威源）、`groups.json`（能力目录） |
| `src/api/services/`、`src/api/http.ts` | 前端领域 API service 和 Axios/Qt bridge 适配 |
| `src/stores/`、`src/router/`、`src/views/` | Pinia 状态、页面路由和 UI |

> 目录勘误：旧索引写的 `modules/pipeline/`、`modules/context/`、`modules/tools/` 实际都在 `modules/core/` 下。

## 3. 文档导航

### 总体和后端
- [BackendDesign.md](BackendDesign.md)：模块依赖方向、进程/线程模型、请求生命周期、provider、任务、服务模型、工具链、shell 服务与工作区输出规范。**以 dev 现行源码为基线。**
- [BackendPlan.md](BackendPlan.md)：分优先级实施工作、依赖关系、验收与回滚。
- [ArchitectureDecisionRecords.md](ArchitectureDecisionRecords.md)：架构决策、备选方案和接受标准。

### 上下文、记忆与存档
- [ContextArchitecture.md](ContextArchitecture.md)：request/session/character/tool/memory 上下文隔离、PromptBuilder、token 预算与迁移。**当前优先审查跨 session 上下文污染风险。**
- [MemoryDesign.md](MemoryDesign.md)：当前记忆实现、五层逻辑记忆、模糊检索、置信/冲突、衰减、压缩、索引一致性和删除语义。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：Slot/路径指针模型与目标 Memento：不可变 Snapshot、manifest/hash、preview/prepare/commit/rollback、旧格式兼容。
- [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)：威胁模型、秘密、工作区三档权限、命令准入双层检查、审计事件、数据删除和恢复风险。

### 前后端契约
- [api.md](api.md)：`endpoints.json` 驱动的 89 个端点、请求/响应、错误码、SSE/WS 事件、shell 命令契约及源码差异。**外部接口的权威清单。**
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
10. **工作区为唯一文件边界**：服务产出、技能输出、shell cwd 与路径参数都必须经 `security/workspace` 判定，禁止绝对路径越界与符号链接逃逸。
11. **先测量再优化**：缓存、RRF、reranker、批量 embedding 和新的索引都要有基线和回滚开关。

## 5. 已确认的源码设计风险

| 优先级 | 观察 | 状态 |
|---|---|---|
| P0 | `UserContext` 是单例，共享 deque；`get_current_messages()` 未按 session_id 过滤，Orchestrator 用其构建 prompt | ⬜ 待办：重构 session-scoped ContextStore + 并发隔离测试 |
| P0 | 后端成功 code 为 200，`src/api/http.ts` 桌面 bridge 判 code=0 | ⬜ 待办：共用响应 decoder |
| P0 | `endpoints.json` 中 save 端点自带 `/api`，注册器又加 `/api` | ✅ 本次修复为资源相对路径 |
| P0 | `services.service.manager` / `services.keys` / `service.decorator` 等失效导入导致启动期 handler 解析失败 | ✅ 本次修复 + 新增兼容层 |
| P1 | WebSocket 注册点使用 `app.websocket("/")`，旧文档写 `/ws` | ✅ 文档已更正 |
| P1 | `groups.json` 有 ppt/audit op，但 `endpoints.json` 未注册 | ✅ 本次补齐 8 个端点 |
| P1 | `data.yaml` 保存路径指针/部分配置，不是全量游戏状态 | ⬜ 待办：区分 Slot 与 Full Snapshot |
| P1 | FAISS 向量索引与 SQLite 元数据无法组成一个原子事务 | ⬜ 待办：index health check / repair |
| P1 | 前端 API service 生成源/类型生成流程需要单一权威 | ⬜ 待办：OpenAPI/DTO/client/doc 契约检查 |
| P1 | `RuntimePath.get_output_dir()` 缺失、PPT 输出目录与下载目录不一致 | ✅ 本次修复，统一到 `<workspace>/ppt` |
| P2 | audit controller 主要列出能力目录，并非完整的安全事件审计日志 | ⬜ 待办：独立定义 actor/action/decision/result 与 retention |

「源码风险」只说明静态审阅的观察和待确认项，不等于本次已修改行为。路由相关问题必须以 `endpoints.json` + 注册器实际结果为最终依据。

## 6. 推荐实施顺序

1. ✅ 以 dev 源码为基线重写后端架构与 API 契约，导出权威端点清单。
2. ✅ 修复服务层失效导入与运行期缺陷；打通 `security/workspace` 到服务产出与命令执行。
3. ✅ 新增 shell 受控服务（平台映射 + 命令白名单 + 危险命令拒绝 + 工作区 cwd）。
4. ⬜ P0：修复 session context 隔离、HTTP/bridge 成功码。
5. ⬜ P0/P1：建立共享 ContextSnapshot/PromptBuilder 契约；统一 request/stream/task ID、错误、取消与 deadline。
6. ⬜ P1：定义 memory provenance/confidence/validity schema migration、索引修复与删除墓碑。
7. ⬜ P1：实现 Snapshot Originator adapters、manifest 与不可变 revisions。
8. ⬜ P1：生成统一前端 API types/services 和 transport contract tests；补齐 save 的 restore/sync/section。
9. ⬜ P2：离线评估多语言混合检索、性能和 token budget；建立审计事件与可观测性。

每一步必须在对应 Plan 中记录代码范围、迁移方案、测试、回滚和验收状态。

## 架构优化增补文档

| 文档 | 内容 |
|---|---|
| [OptimizationPlan.md](OptimizationPlan.md) | 总体计划：阶段、任务、依赖、开关、KPI、风险 |
| [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md) | 类人记忆曲线与遗忘机制（强度模型、状态机、固化、评估） |
| [LayeredArchitecture.md](LayeredArchitecture.md) | 前后端分层、端口、依赖规则、迁移与自动检查 |
| [MementoMemoryIntegration.md](MementoMemoryIntegration.md) | 存档与记忆强度/时钟整合、时间线与分支、自动存档 |
| [reference/](reference/) | 强度模型参考实现与属性测试（仅标准库） |
