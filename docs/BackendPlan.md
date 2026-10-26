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
