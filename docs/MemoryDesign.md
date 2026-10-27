# 记忆系统设计：分层、模糊检索与可恢复归档

> 本文把源码现状和目标设计分开。五层逻辑记忆、评分融合与 Memento 快照属于建议演进，不表示当前已完整实现。

## 1. 当前实现（按 dev 源码）

关键模块：
- src_py/modules/memory/main.py：HybridMemorySystem 单例、短期上下文流程、压缩编排和后台任务引用管理。
- managers.py：EmbeddingManager、MemoryBackendManager，选择 embedding adapter 与存储后端；含 hash embedding fallback。
- storage/base.py：记忆存储抽象接口。
- storage/sqlite.py、storage/markdown.py：SQLite/FAISS 与 Markdown 存储实现。
- storage/models.py：记忆和压缩记忆模型。
- rag/：BM25 与 FAISS 稠密检索、RAG 配置。
- modules/context/user.py：会话上下文与 prompt 输入。
- resources/defaults/memory.sql：memories、compressed_memories、faiss_id_map 的 schema。

当前 API 逻辑层是 short_term、long_term、detailed，并非五个物理层。API 文档暴露 layers、short、long、search、compressed、stats、decay、flush 和单条 delete 操作。

已识别的限制和风险：
1. SQLite + FAISS 路径分别维护元数据和向量索引；两者无法共享原子事务，需明确修复/重建流程。
2. adapter 不可用时使用的 hash embedding 是可运行兜底，不应宣称具备高质量语义能力。
3. Markdown fallback 与 SQLite backend 需保持相同的查询/删除/会话隔离语义。
4. 当前 RAG 默认 disabled；BM25 的 split-by-whitespace 分词没有中文质量保证。
5. importance、access_count、last_access_time 与 decay/reinforce 可实现基础衰减/强化，但不等同于矛盾解决或明确的长期遗忘协议。
6. compressed_memories 保存原始 ID 列表与压缩内容；压缩原文删除、缓存失效和恢复快照中的删除传播尚需定义。

## 2. 设计目标

- 在有限 prompt token 预算下提供相关、近期、可信、有来源的记忆。
- 分离明确事实、事件、自动推断、压缩摘要与原始档案。
- 支持查询、更正、过期、删除、导出和审计。
- 低置信、冲突或过期内容不应被强行当作事实。
- provider/FAISS/RAG 故障时安全降级，不允许跨 session 泄露或静默编造。
- 初期继续使用现有 SQLite/FAISS/Markdown，不以新增数据库/服务作为前提。

## 3. 五层逻辑记忆

~~~text
当前输入与最近消息 (working context)
             |
             v
L1 工作记忆 / 短期上下文
             |
             v
L2 情节记忆 / 时间事件、决策、承诺
             |
             v
L3 语义记忆 / 稳定事实、偏好、实体关系
             |
             v
L4 摘要记忆 / 会话或主题压缩，保留 source range
             |
             v
L5 冷档案 / 原始对话、不可变归档与回溯
~~~

| 层 | 用途 | 生命周期 | 默认注入 prompt |
|---|---|---|---|
| L1 工作记忆 | 当前轮与短期连贯性 | 有界 ring buffer / 会话结束落盘 | 是 |
| L2 情节记忆 | 何时发生、约定和决策 | 长期保留，可衰减 | 相关时 |
| L3 语义记忆 | 稳定偏好与事实 | 带置信度、来源和有效期 | 高置信且相关时 |
| L4 摘要记忆 | 长对话压缩和主题索引 | 可重建、版本化 | 作为候选 |
| L5 冷档案 | 回溯、纠错、导出 | 按用户保留策略 | 默认否 |

五层是逻辑分区，不要求五个独立数据库。第一阶段可在 metadata 中引入 memory_type、confidence、valid_from、valid_until、source_ids、embedding_version 等字段，但必须使用 schema version/migration，不得静默改用户数据库。

## 4. 记忆对象与来源链

推荐概念字段如下，示例不是当前 API 的真实响应：

~~~json
{
  "id": "memory-id",
  "session_id": "session-id",
  "kind": "episodic",
  "content": "用户约定下周二复盘项目",
  "source": {"type": "message", "ids": ["message-id-1"]},
  "confidence": 0.91,
  "importance": 0.72,
  "created_at": 0,
  "valid_from": 0,
  "valid_until": null,
  "last_access_time": 0,
  "access_count": 2,
  "status": "active",
  "supersedes": [],
  "embedding_version": "provider:model:dim",
  "metadata": {}
}
~~~

规则：
- 自动推断必须标记为推断，不伪装成用户明确陈述。
- 保存 source message IDs 或源范围，确保可以追溯到原文。
- 更正事实时建立 supersedes/contradicts 关系；不要让冲突值无序共存。
- 过期和删除应在存储查询阶段过滤，不依赖 prompt 指令。
- 每种 memory kind 应有 retention、最大 token、注入场景与删除策略。

## 5. 模糊记忆与多路召回

模糊检索的目标是使用多种证据找候选，不是无约束地猜。先做授权与 session 范围过滤，再做召回/排序。

1. 精确/元数据：ID、实体、精确词、会话范围、时间范围和状态。
2. 词法检索：BM25/关键词；中文、日文和多语言必须有合适 tokenizer，不可只依赖空格分词。
3. 语义检索：embedding + FAISS，校验维数、归一化和 embedding fingerprint。
4. 时间信号：recency、有效期、源消息时间范围、事件参与者。
5. 置信和重要度：用户明确陈述与确认事实高于单次自动推断。
6. 融合/重排：优先对比 Reciprocal Rank Fusion (RRF)；reranker 作为可选层，需质量/延迟基准后再开启。

可配置评分式仅为设计起点：

~~~text
score = w_sem * semantic
      + w_lex * lexical
      + w_recency * recency
      + w_importance * importance
      + w_confidence * confidence
      - w_conflict * conflict_penalty
~~~

各项需归一化；权重应由评估数据确定，不可直接宣称该公式最优。

### 置信与拒绝策略

- 高于高阈值：作为有来源的事实候选，可注入上下文。
- 中间区间：作为提示性上下文，必要时要求模型使用不确定措辞或追问。
- 低于低阈值：不注入，或仅列作待用户确认候选。
- 发现事实冲突而无明确时间顺序：标记冲突，优先询问用户。
- 低分不意味着事实不存在；回答应能承认没有可靠记忆。

## 6. 遗忘、强化和压缩

- 衰减使用上次衰减时间戳与 elapsed intervals，避免重复任务调度造成额外漂移。
- 明确固定/用户确认的偏好和未履约承诺不能只按 access_count 淘汰。
- 访问强化设置 cap 和冷却，避免热门记忆永久霸占 top-K。
- 压缩按新增消息数、累计 token 或时间窗口触发；不能依赖固定长度 deque 的当前长度模数。
- 压缩产生新 revision，记录 source range/original_ids、模型与 prompt 版本、前后 token 数和结果 hash。
- 压缩失败回退到规则摘要或保留原文，不阻塞主对话，不能删除唯一原始记忆。
- GC 分批且支持 dry-run：先列候选，确认策略后才执行。

## 7. Memento：记忆/存档快照

当前 SaveSlotManager 使用 index.yaml 和每槽 data.yaml。目标是加入不可变 revision，而不是覆盖唯一状态文件。

~~~text
Slot
  ├─ manifest (schema_version, slot_id, revision, parent_revision, checksum)
  ├─ revisions/
  │    ├─ rev-000001 (sections + hashes)
  │    └─ rev-000002 (sections + hashes)
  └─ current (原子更新的 revision 指针)
~~~

保存流程：
1. 收集一致的领域状态并构造 Snapshot DTO。
2. 写临时 revision；保证路径在 slot 根内，限制文件数和总大小。
3. 各 section 序列化并计算 SHA-256，写 manifest。
4. 从临时目录重新读取并验证。
5. 原子发布 revision，最后更新 current；失败时旧 current 保持有效。
6. 记录操作主体、slot、revision、动作和结果，审计日志不包含完整聊天正文。

恢复流程：
1. 校验 schema、hash、路径、文件大小和 section 类型。
2. 生成 dry-run：目标 revision、将被覆盖的 section、未知字段和迁移结果。
3. 记录 before revision 并创建保护快照。
4. 在隔离状态构建恢复数据，通过校验后再交接给运行管理器。
5. 成功后更新 current；失败回滚运行状态。
6. 重放删除墓碑与用户数据清除记录，确保旧快照不复活已删除记忆。

兼容规则：
- 旧 index.yaml/data.yaml 保留只读兼容读取器。
- 快照 schema 版本与应用版本分开。
- 用户显式保护/导出的版本不自动清理。
- restore/delete 是高影响操作，必须确认并审计。

## 8. SQLite/FAISS 一致性

1. 每条可检索 memory 的元数据和 vector mapping 需一致。
2. 删除后清理 vector 与 mapping；部分失败进入 repair queue。
3. 保存 provider/model/dim/normalization 版本，禁止混用不同 embedding space。
4. 启动执行轻量检查；完整 rebuild 放后台任务。
5. SQLite 与 FAISS 不共享事务，必须有明确写入顺序和补偿策略，不能宣称跨两者原子提交。
6. Markdown 与 SQLite backend 遵循相同 MemoryStorageBase 行为，并进行 adapter contract checks。
7. 先按 session/owner 范围过滤，再对候选排序，禁止先做全局 top-K 再过滤。

## 9. Prompt 预算

- 预算由 system prompt、角色设定、最近消息、召回记忆和输出预留共同组成。
- 在 token 预算内裁剪，top_k 不等于 token 限额。
- 去重相同事实，冲突事实显式标记来源/时间。
- 每条注入记忆保留简短 source ID、时间和置信度，便于排障。
- api.md 约定 detail_top_k=0 可跳过 detailed layer；需要在实现验证该行为确实降低延迟。

## 10. 质量指标

- Recall@K、MRR、nDCG、无命中率、冲突率、错误注入率、用户纠正率。
- embedding/lexical/dense/fusion latency、候选数量、prompt token 增量。
- 删除传播延迟、孤儿 mapping、rebuild 成败、压缩失败率和 token 节省。
- 评估样本需覆盖中/日/英、多语言混合、同义改写、错别字、旧事实替换、相似实体、跨 session 隔离与删除后不复活。

## 11. 演进阶段

- M0 正确性：会话隔离、删除传播、维数和 embedding 版本校验、索引诊断。
- M1 召回基线：构建评估集，记录现有 lexical/dense 行为，比较 RRF。
- M2 逻辑分层：增加 kind/source/confidence/validity schema migration，保持旧 API 兼容。
- M3 压缩生命周期：增量计数触发、版本记录和回退。
- M4 Memento：manifest、不可变 revision、dry-run restore、墓碑重放和旧格式迁移。
- M5 性能：可选 reranker、缓存、批量 embedding、后台 rebuild；仅在基准证明收益时启用。


## 12. 与上下文构建的集成契约

记忆存储、检索候选和 LLM prompt 是三个不同责任：
- MemoryStore 保存事实/情节/摘要和来源。
- Retriever 只负责按 scope 检索候选，不决定最终把什么喂入模型。
- MemoryRanker 做融合、冲突标注、有效期过滤和置信度评估。
- PromptBuilder 根据本轮请求、角色、session window 和 token budget 决定实际注入集合。

完整上下文分离与数据流见 [ContextArchitecture.md](ContextArchitecture.md)。

### 每轮检索的输入/输出

输入至少包括 \`session_id\`、\`character_id\`、当前 query、时间基准、允许的 memory kinds 与检索预算。输出应是有来源的候选清单，而不是预先串起来的“长期记忆全文”。

候选必须有：memory_id、kind、source_ids、score、confidence、validity、conflict group、embedding_version。来源与置信度缺失的旧记录可按 legacy 候选处理，但不能自动升级为高可信事实。

### 层间生命周期规则

- L1 是受 token 和 message count 双限制的会话工作集；它不是长期存储的唯一副本。
- L2/L3 由来源消息提取，并保留 provenance；用户明确更正优先于自动推断。
- L4 摘要可重建；每个摘要记录源消息范围和输入 revision。
- L5 冷档案默认只供按需追溯，不自动塞入 prompt。
- 压缩只产生摘要/压缩记录，不应悄悄抹掉仍受保留策略保护的 source messages。
- 删除按 memory id 和 source lineage 传播，清理检索缓存和索引，同时在 restore 时重放删除墓碑。

### 对话系统不能把检索当作授权

记忆候选、文件内容和工具结果都是数据，不是 system policy。即使 retrieved memory 内容包含“执行某个 shell 命令”，也不能改变 ToolContext 的 allowlist；高风险执行由独立授权层决定。


## 类人记忆曲线与遗忘机制

五层逻辑记忆的"生命周期与权重"由强度模型定义：幂律保持率、稳定度 S、间隔效应强化、失误惩罚、active/faded/archived 状态机、固化流水线、冲突覆盖、遗忘画像，以及软遗忘与硬删除的分离。完整设计、参考实现和评估方案见 [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md)；与存档的整合见 [MementoMemoryIntegration.md](MementoMemoryIntegration.md)。本文关于删除传播和墓碑的规则优先于任何遗忘逻辑。
