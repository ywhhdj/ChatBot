# 架构决策记录（ADR）

> 提议状态需要维护者批准，不代表当前实现。接受后应记录日期、负责人和具体代码/文档版本。

## ADR-001：保持模块化单体

- 状态：建议接受。
- 背景：当前已按 API、manager、pipeline、memory、services、tools、events 分模块，主要在一个本地应用生命周期内运行。
- 决策：保留模块化单体，以 Protocol/ABC、DTO 与 adapter 隔离存储和 provider。只有部署、性能或故障隔离数据证明必要时才拆进程。
- 收益：适合本地应用，降低运维和分布式一致性成本。
- 代价：需要严格依赖规则；CPU/阻塞任务仍需 worker 隔离。
- 验收：领域模块不依赖 FastAPI/Qt；provider/storage 可替换；不创建无业务意义的空壳层。

## ADR-002：API contract 的唯一权威来源

- 状态：提议，P0。
- 背景：存在后端控制器/DTO、docs/api.md、前端 service/types 和多个生成相关脚本。
- 决策：先由真实控制器与 DTO 校验当前 registered routes，然后选定一个机器可读源或正式生成入口；文档、TS 类型和 service 以同一契约更新。
- 不把重复前缀的错误 URL 固化成正式契约。
- 验收：OpenAPI/注册路由与服务端点、客户端方法、SSE/WS 事件表可自动比对。

## ADR-003：五层逻辑记忆，不预设五个数据库

- 状态：提议。
- 背景：当前 API 暴露 short_term、long_term、detailed；存储包括 memories 与 compressed_memories，RAG 可选。
- 决策：增加工作记忆、情节记忆、语义记忆、摘要记忆和冷档案逻辑层。首阶段继续使用现有 SQLite/FAISS/Markdown，可通过 schema-versioned metadata 表达类别。
- 不采用：现在就引入五套数据库或新向量服务。
- 代价：需 migration、source lineage、删除传播和分层评估。
- 验收：各类记忆有独立生命周期/检索权重；无跨 session 召回；删除可追踪。

## ADR-004：可评估的混合检索

- 状态：提议，先做离线评估。
- 决策：精确/元数据 → 词法检索 → 稠密检索 → RRF 融合；reranker 可选。
- 不采用：以单一 embedding score 断言事实；无基准就默认启动昂贵 reranker。
- 验收：中/日/英评估集报告 Recall@K、MRR 或 nDCG、误注入率、延迟和内存。

## ADR-005：存档采用 Memento/不可变 revision

- 状态：提议，P1。
- 背景：SaveSlotManager 当前使用 index.yaml 和每槽 data.yaml。
- 决策：新增 revision、manifest、checksum 与 dry-run restore；旧格式通过兼容读取器迁移，不覆写唯一可恢复版本。
- 要求：恢复校验 schema/hash/path/size；记忆删除墓碑需在恢复后重放。
- 代价：占磁盘、需要 retention policy 和 schema migration。
- 验收：部分写入不损坏旧快照；失败恢复不改运行状态；旧快照不复活已删记忆。

## ADR-006：安全策略在确定性执行层

- 状态：建议接受。
- 决策：LLM 提供工具意图，不提供授权。执行前依据 capability、schema、用户确认、timeout 和 sandbox policy 再验证。
- 原因：LLM、网页、文件、retrieved memory 和 tool output 都是不可信输入。
- 验收：不存在“模型说允许所以执行”的权限路径；shell/未隔离语言默认拒绝。

## ADR-007：EventBus 不是持久任务队列

- 状态：建议接受。
- 决策：事件总线用于通知；可靠操作以任务状态、持久化记录和 repair queue 表达。
- 验收：事件丢失不会丢失唯一业务事实；任务可查询终态与失败原因。

## ADR-008：性能优化必须先测量

- 状态：建议接受。
- 决策：先建立 latency/queue/memory/retrieval-quality baseline，再启用缓存、批量 embedding、reranker 或额外索引。
- 验收：每项优化报告基线、实际收益、内存成本和降级路径。


## ADR-009：上下文存储按 session 隔离

- 状态：提议，P0。
- 背景：当前 UserContext 为 singleton 并持有共享 deque；消息有 session_id，但 get_current_messages() 没有按 session 过滤。
- 决策：以 SessionContextStore 为所有近期窗口的唯一访问入口；窗口按 session 分桶，prompt 只读取 RequestContext 指定的 session。
- 备选：调用方自己记得筛选；拒绝，因为调用点遗漏会造成隐蔽的数据串线。
- 代价：迁移既有 singleton，维护旧消息兼容，并定义会话切换/清理语义。
- 验收：两个 session 交错并发对话时不出现跨 session 消息、记忆或工具结果。

## ADR-010：游戏存档采用 Memento revision，而不把路径索引误称为完整快照

- 状态：提议，P1。
- 背景：当前 data.yaml 记录路径指针和部分配置；真正的角色、会话和记忆数据由各管理器持有。
- 决策：Slot 继续作为用户入口，新增 Snapshot revision；领域 manager 以 Originator adapter 输出快照，Coordinator 作为 Caretaker 做 staging、manifest/hash、发布和恢复编排。
- 恢复：Preview → Prepare → Commit → Verify；失败时使用 before revision rollback；记忆删除墓碑在恢复后重放。
- 代价：需各模块快照接口、版本迁移、更多磁盘占用和故障注入测试。
- 验收：任何一个 section 导出/校验失败都不发布 Full snapshot；restore preview 无副作用；commit 失败不留下无法解释的混合状态。

## ADR-011：多种 transport 共用契约与 decoder

- 状态：提议，P0。
- 背景：Axios、SSE、WebSocket 和 Qt bridge 的协议包装存在差异，桌面 bridge 的成功码判断与后端不同。
- 决策：共享 DTO/错误语义/decoder；transport 负责网络/消息编码，前端 service 表达领域操作，后端 application service 负责业务。
- 验收：共享 contract matrix 覆盖成功、参数错误、未初始化、超时、取消、断连和重复请求。
