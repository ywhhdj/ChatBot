# 记忆系统实现说明（当前架构）

> 本文描述 `src_py/modules/memory/` 的**实际**结构。库内向量索引及其
> `faiss_id_map` 映射表已彻底移除，不保留兼容路径；配置里出现旧后端名
> 会直接报错。权威设计见 `docs/MemoryDesign.md` 与
> `docs/MemoryCurveAndForgetting.md`。

## 分层与依赖方向

```
Controller / 其它模块
        │  只调 get_memory_api()
        ▼
MemoryAPI（统一入口：scope、预算、缓存、装配、错误语义、审计）
        │
        ├── Application  MemoryRanker / Retention / GC / Usage / Consolidation
        ├── Domain       layers / strength / scoring / integrity（纯函数）
        └── Adapters     MemoryRepository(SQLite) · VectorStore(Milvus)
                         EmbeddingManager · MemoryKernel(Rust|Python)
```

`MemoryAPI` 是**唯一对外入口**。旧 `HybridMemorySystem` 只做签名兼容，
所有业务逻辑委托给它。controller 不再直接访问 `storage` 的内部属性。

## 线程与事件循环模型

`MemoryRepository` 继承 `AsyncSqlite`：所有 SQL 通过**单线程
ThreadPoolExecutor + threading.Lock** 串行执行，每个写路径显式
`commit()`，复合写（墓碑 + 删行）走 `transaction()` 单事务

周期衰减由组合根在空闲 tick 调 `maybe_decay()`，不在存储内部起后台
协程检索

| 通道 | 实现 | 过滤 |
|---|---|---|
| dense | Milvus `search`，filter 含 `session_id / layer / fingerprint / tombstone` | **服务端先过滤再 ANN** |
| lexical | `MemoryKernel.lexical_scores`（Rust 优先，中文 bigram） | SQL 侧先按 session |
| exact / recency / confidence | SQL 侧候选集内计算 | SQL 侧先按 session |

多路召回经 RRF 融合 → 强度排序（R 参与，开关默认关）→ 状态门控。
`MemoryAPI.search()` 在注入 prompt 前再过一次**复活闸门**（墓碑按
`id + 内容摘要` 匹配，防止 id 复用误杀）。

向量后端不可用时 `status()['vector']['degraded']=True`，dense 通道置空
并在报告里写明原因；**其它通道照常**，不静默替换实现、不假装语义检索正常。

## 评分

- 语义相似度：向量内积（归一化后 cosine 近似）
- 综合分（检索后重排）：`utils.compute_memory_score` =
  `w0*similarity + w1*normalized_importance + w2*recency`
- 强度排序：`final = relevance * (floor + (1-floor) * R(Δ,S))`，
  其中 `R(Δ,S)=1/(1+Δ/(9S))`，公式在 `domain/strength.py`，
  重计算在 Rust `native/src/memory.rs`。

## 数据层（SQLite，权威）

`resources/defaults/memory.sql`：

| 表 | 用途 |
|---|---|
| `memories` | 记忆正文 + schema v2 分层字段（layer/kind/confidence/pinned/...） |
| `compressed_memories` | 压缩摘要与 original_ids |
| `memory_tombstones` | 删除墓碑（id + 内容摘要 + 时间 + 原因，**不存正文**） |
| `memory_strength` | 稳定度、最后强化日、状态、pinned |
| `memory_usage_event` | 使用事件（M1-04） |
| `memory_clock_state` | 时钟锚点（M1-01 / S2-01） |
| `memory_schema_meta` | 迁移进度 |
| `embedding_meta` | embedding 指纹（provider/model/dim/version） |

`memories.id` 与 Milvus 的 `memory_id` 是**同一个值**，没有中间映射表。
所以对齐诊断就是两个 id 集合的差集（B1-04），`VectorStore.list_ids()`
提供服务端 id 列举。

旧库由 `migrations.py` 分批补列并回填，全程写进度、可中断重入。

## 删除语义

隐私删除 = 写墓碑 + 删元数据行 + 删 Milvus 向量，**单事务完成前两步**。
墓碑在快照恢复后重放，防止已删内容复活。容量裁剪走不带墓碑的路径
（否则墓碑会随每次裁剪无限增长）。
