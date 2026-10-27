# 后端架构设计

> 基线为 dev 源码。本文把当前能力与目标设计分开，不表示所有目标机制已实现。

## 1. 设计目标与非目标

目标是在桌面/本地应用形态下明确 HTTP/WebSocket、对话编排、模型管道、技能、记忆、存档和基础设施职责，优先保证正确性、可恢复性和可观测性，再优化延迟与吞吐。

非目标：不为架构图而拆微服务；不强制替换 FastAPI、SQLite、FAISS、Qt/Vue；不把供应商细节写入领域层；不把 LLM 输出当作权限策略。

## 2. 当前模块与依赖方向

~~~text
HTTP / SSE / WebSocket / Qt bridge
                 |
                 v
API Controller + DTO + Response Envelope
                 |
                 v
Application orchestration
    |          |          |           |
    v          v          v           v
Conversation  Task       Memory      Session/Save
Router        Manager    Facade      Managers
    |          |          |           |
    v          v          v           v
Pipeline      Services/  SQLite /    YAML / files
Adapters      Skills     FAISS / MD
~~~

依赖方向应向内：协议层调用应用接口，应用层依赖领域接口，基础设施实现接口。

| 模块 | 应负责 | 不应负责 |
|---|---|---|
| modules/api/controllers | 请求解析、DTO 校验、应用服务调用、响应映射 | 直接实现检索算法、文件事务或 provider 生命周期 |
| api/response.py、exceptions.py | 信封、request_id、错误到 HTTP 状态映射 | 将堆栈、密钥或绝对路径回传给调用方 |
| modules/manager | 会话/角色/服务/任务/存档运行时编排 | UI 展示逻辑或供应商特定代码 |
| modules/pipeline | LLM/TTS/ASR/OCR 适配和切换 | 直接持久化所有业务状态 |
| modules/memory | embedding、记忆检索/压缩/生命周期和存储抽象 | 依赖 FastAPI Request/Response |
| modules/context | 管理本轮/会话上下文和 prompt 输入 | 自己定义 HTTP 协议或数据库事务 |
| modules/events | 线程安全通知、订阅和 listener 生命周期 | 作为唯一可靠消息队列或事务日志 |
| modules/tools、services | 工具 schema、授权、沙盒调用、外部服务 | 直接信任 LLM 生成参数 |
| runtime / path utilities | 应用目录、运行生命周期和资源路径 | 在业务模块复制路径规则 |

## 3. 线程与生命周期约束

系统存在 Qt 主线程、WebServer loop、任务调度器、记忆存储队列/worker 与异步事件派发器。跨线程边界必须显式定义。

1. Qt 主线程只负责 UI 事件，不运行常驻 asyncio loop。
2. 若当前线程已有运行中 loop，使用 create_task、run_coroutine_threadsafe 或项目 AsyncDispatch；不能对同一 loop 调用 asyncio.run。
3. 工作线程不得同步等待需要 Qt 主线程派发的工作，否则可能形成互等死锁。
4. 后台任务保存强引用并取回异常；关闭时停止接收新任务、有限等待、协作取消、关闭 provider/存储，再终止 loop。
5. EventBus 是进程内通知通道，不保证持久、恰好一次或跨重启恢复。可靠工作需要任务记录或 repair queue。
6. 文件 IO、同步 SDK 和索引重建不得无界阻塞 Web loop；使用有界线程池/队列并限制并发。
7. 任务取消是协作式语义；同步线程无法被安全强杀，不得向客户端谎报成功取消。
8. 队列必须有容量与过载行为；health check 不应触发模型加载或全盘索引重建。

## 4. 请求生命周期

1. Middleware 生成 request_id；外部传入 ID 需限制长度与字符集。
2. Controller 处理输入 schema、长度、枚举、资源 ID 和文件路径约束。
3. Application service 处理业务状态、授权、幂等、并发和总时限。
4. Adapter 执行 provider/存储 IO；耗时工作返回 task_id 或流式输出，不阻塞请求线程。
5. 统一响应信封输出；异常映射为稳定错误码，内部原因写脱敏日志。
6. 请求结束时清理 context、取消无用子任务，记录 latency/provider/status，不记录秘密正文。

## 5. 对话路由与工具调用

保留项目文档定义的三上下文分离：角色上下文、工具上下文、用户输入上下文；以及 PURE_CHAT、TOOL_CALL、MIXED 双通道。

- Router 只返回有限枚举、置信度、来源和可解释原因。
- 规则命中可直接路由；置信度不足时澄清或调用轻量分类器，避免盲目触发额外的大模型请求。
- LLM 只能提出工具意图。Executor 重新执行权限、参数、路径、资源和速率检查。
- 工具执行设最大步数、总时间、输出字节数与取消传播。
- 工具输出、网页和文件均是不可信数据；回填 prompt 时标记来源，不允许覆盖 system policy。
- 统一 request_id/trace_id 贯穿路由、工具、结果回填和最终答复。
- 工具失败必须返回结构化类别、是否可重试和用户可见提示，不仅返回自由文本。

## 6. Provider 生命周期

当前 pipeline 使用多个 adapter 与 resources/defaults/pipeline.yaml。建议把适配器生命周期标准化为配置验证、初始化、健康检查、调用、关闭五个操作。

切换 provider 的目标流程：
1. 校验 provider 与配置 schema，秘密不写日志。
2. 创建隔离的新实例并初始化、健康检查。
3. 成功后原子切换路由，再关闭旧实例；失败时旧实例保持可用。
4. 配置文件以临时文件写入、校验后原子替换。
5. 每个 provider 独立设置 timeout/retry/backoff；只对明确幂等的操作重试，并避免 client、adapter、scheduler 多层重试相乘。

## 7. 任务与事件

建议统一任务状态：pending → running → succeeded/failed/cancelled/timeout。旧 API 的 done 应映射为终态以兼容既有客户端。

每项任务记录 task_id、kind、时间、进度、request_id、状态、脱敏错误和结果引用。队列满时明确拒绝或返回可重试响应。取消等待中任务应立即生效，运行中的任务通过 cancellation token 协作退出。状态变化可发事件，但事件丢失不影响任务查询。

## 8. 存档一致性与 Memento

当前 SaveSlotManager 使用 index.yaml 和每个槽的 data.yaml，并按 section 组织角色、UI、聊天历史等数据。目标设计采用 Memento 思想，不破坏旧存档读取。

- 不可变 Snapshot 包含 schema_version、slot_id、revision、parent_revision、created_at、各 section hash 与 manifest。
- 写入临时 revision，校验序列化、大小、路径和 hash 后再原子发布 current 指针。
- load 前生成 dry-run 报告；不通过 schema/hash/path 检查时不改变运行状态。
- 恢复开始前保存 before revision；失败时回滚运行态。
- 记忆删除墓碑必须在 restore 时重放，防止旧快照让已删除内容复活。
- 旧 index.yaml/data.yaml 采用只读兼容读取器和显式迁移，不直接覆盖唯一存档。

## 9. API 与兼容性

- REST 使用统一 ApiResponse：ok、code、message、data、request_id、ts。
- 源码的成功 code 为 200；前端 desktop bridge 的 0/200 判定差异应按 P0 修复。
- 资源路由只在一处添加 /api。Controller router 应使用资源前缀，例如 /save，而不是重复声明完整 API 根前缀。
- REST、SSE、WebSocket、Qt bridge 同列在契约清单中。
- 文件名用 basename 并验证最终路径处于允许根目录内。
- 操作型 POST 默认不盲目自动重试；需要幂等时引入 idempotency key。
- 破坏性 API 变更经过兼容窗口，明确旧字段和事件的弃用周期。

## 10. 安全、可观测性与性能

本地 API 默认绑定 loopback；远程监听必须显式启用认证和严格来源限制。密钥普通读取仅返回 configured/遮蔽值，raw access 应移除或受受控调试授权约束。未完成隔离的 shell/任意脚本默认拒绝。异常回传稳定 message 与 request_id，详细信息仅写受控本地日志。

建议先测量再批准的本地初始目标：
- health endpoint P95 < 100 ms，不加载模型/不扫全盘。
- 非模型 API P95 < 200 ms。
- 暖缓存记忆检索 P95 < 150 ms（1 万条以内，embedding 延迟独立记录）。
- WebSocket ping/pong P95 < 50 ms，不含网络抖动。
上述是目标值，不是本分支的实测结果。

降级顺序：可选 reranker/RAG → detailed memory layer → LLM 摘要压缩 → 非核心事件通知。不得降级权限检查、会话隔离、删除语义、索引一致性和存档校验。


## 11. 上下文装配与边界（规范以 ContextArchitecture.md 为准）

当前 \`UserContext\` 是单例，内部 deque 的每条消息含 \`session_id\`，但 \`get_current_messages()\` 返回所有 USER/ASSISTANT 消息，不在 getter 中按 session 过滤；Orchestrator 会使用该入口构造对话 prompt。此处应视为 P0 潜在跨 session 污染风险，不能仅依赖调用方“会正确切换会话”的隐式约定。

目标约束：

- 每个入站请求都构造不可变 \`RequestContext(request_id, trace_id, session_id, character_id, deadline, cancellation)\`。
- ContextStore 按 session 分桶；所有读取窗口、记忆候选、写入、清理和摘要刷新必须显式接收 session_id。
- CharacterContext、SessionContext、InputContext、ToolContext、RetrievedMemoryContext 分开建模。
- PromptBuilder 是纯构建步骤：先过滤 scope/有效期，再解决冲突/排序，最后按 token budget 组装 Prompt DTO。
- 记忆片段不能作为无来源 SYSTEM 文本永久积累在全局对话窗口；它们应保留 memory id/source/confidence 并在每轮按需装配。
- 不持锁调用 LLM、工具、embedding 或磁盘长操作；锁按 session 分片，只保护短暂状态更新。
- 详细方案、伪代码、迁移步骤与验收见 [ContextArchitecture.md](ContextArchitecture.md)。

## 12. 应用服务和领域边界落地顺序

不要一次重写所有现有 manager。按风险建立稳定的应用服务入口：

| 用例 | 应用服务边界 | 主要依赖 | 持久化所有者 |
|---|---|---|---|
| Chat | ChatApplicationService | Router、PromptBuilder、LLM adapter、ToolExecutor、ContextStore | Session/Memory/Character manager |
| Memory query | MemoryApplicationService | scope filter、retriever、ranker、token budget | Memory storage adapter |
| Save snapshot | SaveApplicationService | SnapshotCoordinator、Originator adapters、RestorePlan | 各 domain originator + snapshot repository |
| Provider switch | PipelineApplicationService | Config validator、ProviderFactory、health check | Config manager |
| Task | TaskApplicationService | bounded scheduler、cancellation token、result store | Task registry/store |

Controller 只构造输入 DTO 并调用用例；应用服务负责业务流程；领域模块定义不变量；adapter 负责协议与 IO。若现阶段尚无这些类，先通过现有模块中的薄函数/对象形成显式边界，避免机械地新增十几个空目录。

## 13. 一致性和副作用

- 用户消息、工具调用、工具结果、assistant final 要关联同一 round_id/request_id；失败轮次应有明确状态。
- 不把 EventBus 当事务机制；若“工具已执行但总结失败”，需要保留 tool result 和 round state。
- 对修改状态的用例定义 precondition、执行点、补偿动作和可重放性。
- Save restore、provider switch、记忆重建等长操作需要 operation/task id，阶段状态可查询。
- 持久化失败必须区别“业务动作成功但日志写失败”和“业务事务未成功”；审计不能作为主状态的唯一真相。

## 14. 分层、记忆曲线与存档整合

- 分层规则、端口清单、与现有模块的映射、迁移顺序和自动检查见 [LayeredArchitecture.md](LayeredArchitecture.md)。第 12 节的"应用服务边界"对应其中的 L2。
- 记忆强度（惰性计算的遗忘曲线）、状态机、固化与 GC 见 [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md)。强化只发生在请求成功完成之后，经有界队列异步执行，不进入请求关键路径，不持有会话锁。
- 存档与记忆强度/时钟的整合、时间线与分支见 [MementoMemoryIntegration.md](MementoMemoryIntegration.md)。
- 总体路线与任务依赖见 [OptimizationPlan.md](OptimizationPlan.md)。
- 降级顺序补充：固化与 GC 先于 reranker 关闭；任何降级都不得影响会话隔离、删除语义和存档校验。
