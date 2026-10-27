# 后端架构优化计划

> 本计划仅定义设计和后续实施工作。未合并代码或未执行的测试不得标记为完成。

## 1. 原则

- 先修契约、路由、线程和数据完整性，再升级检索质量。
- 不引入新基础设施，除非可复现指标证明必要。
- 每个任务包含兼容策略、失败路径、观测指标和回滚方案。
- API 必须先固定契约，再更新前端类型/服务；生成文件不得手工漂移。

## 2. P0：协议与安全正确性

| ID | 工作项 | 产出 | 验收 |
|---|---|---|---|
| B0-01 | 统一后端成功 code 与前端 bridge 解包 | 响应契约、共享解包规则 | Axios/Qt bridge 对 code=200 与错误信封有相同判断 |
| B0-02 | 消除重复 /api 路由前缀 | 路由注册规则与清单 | OpenAPI/实际路由中每条 API 只有一个 API 前缀 |
| B0-03 | 基于控制器和 DTO 校准 api.md | REST/SSE/WS 清单 | 文档与实际注册路由零差异 |
| B0-04 | 收敛 raw secret 与异常泄露 | 秘密字段策略 | 普通请求不回显明文密钥；500 不回传内部异常详情 |
| B0-05 | 审查 loopback、CORS、request_id | 安全基线 | request_id 有长度/字符校验；远程模式需认证 |
| B0-06 | 工具执行安全规则 | capability/allowlist/sandbox 契约 | shell/未隔离语言默认拒绝，超时/输出限制定义清楚 |
| B0-07 | 审查后台任务/线程关闭 | 生命周期检查表 | 无未回收 task 异常；shutdown 有界且无互等死锁 |

## 3. P1：存档、记忆与任务可靠性

| ID | 工作项 | 产出 | 验收 |
|---|---|---|---|
| B1-01 | 定义 snapshot schema/version/manifest | Memento format | 旧 index.yaml/data.yaml 可读取，未知 schema 安全拒绝 |
| B1-02 | 原子发布存档 revision | temp→validate→publish 流程 | 故障注入不损坏旧 current revision |
| B1-03 | 恢复预演和回滚 | RestorePlan DTO | hash/schema/path 失败时运行态不改变 |
| B1-04 | SQLite/FAISS 对齐诊断 | index health report | 检测孤儿元数据、丢失映射、维数不匹配并可重建 |
| B1-05 | 记忆删除完整传播 | tombstone/delete protocol | 向量、映射、压缩引用、缓存和 snapshot restore 均不复活 |
| B1-06 | embedding 版本化 | fingerprint/migration plan | provider/model/dim 改变时不混用向量，可后台重建 |
| B1-07 | 统一任务状态机 | Task state transition table | 终态不被后续事件覆盖；取消/超时可解释 |
| B1-08 | 结构化日志和审计 | event schema | request_id 可串联任务，日志无秘密和私人正文 |

## 4. P2：检索质量和性能

| ID | 工作项 | 产出 | 验收 |
|---|---|---|---|
| B2-01 | 精确/词法/稠密多路召回 | Retriever interface | 单一路失败时有可解释降级 |
| B2-02 | RRF/reranker 离线对照 | 中日英评估集和报告 | 报告 Recall@K、MRR/nDCG、延迟与内存 |
| B2-03 | 中文分词与多语言策略 | Tokenizer design | 中文不只依赖空格分词，基准可重现 |
| B2-04 | 自适应 prompt token budget | Budget policy | 不超 token 预算，保留来源与置信度 |
| B2-05 | 记忆衰减/GC dry-run | Retention policy | 可预演、可解释、可监测、批次执行 |
| B2-06 | 本地性能基线 | Benchmark report | 冷/暖 P50/P95、内存和队列深度可复测 |

## 5. 依赖

~~~text
B0-01 → B0-02 → B0-03 → API 生成源统一
B0-04 → B0-06
B0-07 → B1-07
B1-01 → B1-02 → B1-03
B1-04 → B1-05 → B1-06
B1-08 → B2-01 → B2-02 → B2-04
~~~

## 6. Definition of Done

每个实现 PR 必须包括：设计差异、旧 API/数据兼容方式、正常/异常/超时/取消/并发/重启恢复测试、观测字段与敏感数据清单、迁移/回滚说明，以及自动生成文件的权威源与生成命令。

- [x] 已阅读 dev 分支 docs 目录、API 文档、记忆相关模块、响应/异常、路由控制器、前端 HTTP/service、存档与配置文件。
- [x] 已建立独立文档分支，避免未经审查直接改 dev。
- [ ] 提交文档后核查 Markdown 相对链接和接口差异措辞。
- [ ] 路由前缀/desktop bridge 成功码等问题需在独立代码 PR 实现并测试。
- [ ] 遵守仓库约束：不下载依赖、不运行构建/测试。


## 7. 上下文隔离与 Memento 专项任务

补充任务以具体模块为单位，不代表本 PR 已修改实现。

### P0-C：修复上下文隔离设计

| ID | 任务 | 目标文件/模块 | 验收 |
|---|---|---|---|
| C0-01 | 建立 RequestContext DTO | pipeline/chat.py、orchestrator.py 周边 | 一次请求的 id/session/character/deadline 全链路显式传递 |
| C0-02 | ContextStore 按 session 分桶 | context/user.py 或新 context store | A/B session 并发时窗口不会混入另一 session 的消息 |
| C0-03 | PromptBuilder 纯化 | pipeline/orchestrator.py | system/character/tool/memory/history/input 各段可单独测试与计 token |
| C0-04 | 记忆注入去副作用 | context/user.py、memory/main.py | memory snippets 不无限追加；重建 context 无旧摘要残留 |
| C0-05 | session switch/clear 生命周期 | manager/session、orchestrator | 只清指定 session；迟到流不会覆盖切换后会话 |

### P1-S：存档 Memento

| ID | 任务 | 产出 | 验收 |
|---|---|---|---|
| S1-01 | 明确 Slot/Checkpoint/Full snapshot 语义 | GameSaveArchitecture.md、DTO | API/UI 显示 capture scope 和 consistency_level |
| S1-02 | 为 Originator 定义 snapshot adapter | session/character/memory/config managers | 不读取私有变量；缺少 adapter 的 domain 不宣称完整捕获 |
| S1-03 | manifest、schema version 和 hash | SnapshotRepository | damage/unknown schema 被安全拒绝 |
| S1-04 | staging 与原子发布 | SnapshotCoordinator | 发布中断时旧 current revision 仍可恢复 |
| S1-05 | RestorePlan/prepare/commit/rollback | RestoreCoordinator | preview 无副作用；prepare 失败无部分状态切换 |
| S1-06 | 删除墓碑与快照恢复 | memory + snapshot restore | 旧 snapshot 不恢复已删除的记忆 |
| S1-07 | 保留/GC 与磁盘预算 | snapshot repository | current/protected revision 不会被 GC；dry-run 可检查 |

Memento 全部流程、目录、manifest 示例与错误场景见 [GameSaveArchitecture.md](GameSaveArchitecture.md)。不得把现有只保存路径指针的 data.yaml 直接作为 Full snapshot。

## 8. 性能验收增补

- ContextStore 使用 per-session lock；不让不同 session 因全局锁串行。
- PromptBuilder 的 token 预算和 memory query 时间分别统计。
- Snapshot 创建可并发读取但不能无限并发复制大型记忆/音频资产；使用有界队列和磁盘空间预检查。
- 对 restore/provider switch/index rebuild 建立 operation_id 和 deadline，UI 轮询/订阅时不保持阻塞 HTTP 请求。
- 仅在测量证实收益后启用缓存、批量 embedding、索引增量更新或 reranker。

## 9. 记忆曲线、分层与存档整合任务

新增任务 ID（`A*` 治理、`L*` 分层、`M*` 记忆曲线、`S2-*` 存档整合）及阶段、依赖、开关见 [OptimizationPlan.md](OptimizationPlan.md)。与本文既有任务的关系：

- B2-05（记忆衰减/GC dry-run）对应 M2-07，其模型由 [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md) 定义。
- B2-04（自适应 token budget）与 M2-01（R 参与排序）联动，需一并评估。
- B1-04/05/06 是 M2-08（GC apply）的前置。
- C0-02（ContextStore 分桶）是强化/固化启用 character scope 的前置，在此之前只启用 session scope。
- S1-02/03 完成后才能开展 S2-01（MemoryOriginator 含强度与时钟）。