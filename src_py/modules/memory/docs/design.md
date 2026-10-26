## 线程模型

`SQLiteFAISSStorage` 内部维护 `MemoryWorker`：

- API 接口
  - `add_memories`
  - `retrieve_memory` 
  - `get_short_term`
  - `get_long_term`
  - `get_detailed`
  - `close`
- 所有 DB 读写通过任务队列进入 worker 串行执行。
- worker 每小时执行一次：
  - 重要度衰减 $importance *= 0.995$
  - 超量淘汰（超过 1w）

## 类人记忆曲线
### 时间衰减
  $$
  recency\_score=\exp\left\{-\frac{time\_since(last\_access\_time)}{decay\_rate}\right\}
  $$
### 访问强化
  $$
  importance(重要度)=importance+width
  $$
### 自然衰减
  $$
  importance(重要度)=importance*width
  $$
### 相似度
  $$
  simillarity(相似度)=cosine\_similarity(vector1, vector2)
  $$

## 评分机制

- 综合分数：

  - 语义相似度（FAISS）
  - 重要度（importance）
  - 时效衰减（last_access_time）

- 记忆分数计算
  $$
  score=simillarity(相似度) *s_width+ r\_width* recency\_score(时间衰减) + i\_width* normalized\_importance(重要度)
  $$

## 数据层

### SQLite（元数据）

`MemorySystem/data/memory.sql`:

- `memories`
- `compressed_memories`
- `faiss_id_map`

#### 记忆表
`memories` 表结构：
| 字段 | 类型 | 键类型 | 描述 |
| --- | --- | --- | --- |
| id | INTEGER | PRIMARY KEY | 记忆 ID |
| session_id | TEXT | 无 | 会话 ID |
| role | TEXT | 无 | 角色 |
| source | TEXT | 无 | 来源 |
| content | TEXT | 无 | 内容 |
| importance | REAL | 无 | 重要度 |
| access_count | INTEGER | 无 | 访问次数 |
| last_access_time | REAL | 无 | 最后访问时间 |
| created_at | REAL | 无 | 创建时间 |
| updated_at | REAL | 无 | 更新时间 |
| tokens | INTEGER | 无 | 主键词元数 |
| metadata | TEXT | 无 | 元数据 |
---

#### 压缩记忆表
`compressed_memories` 表结构：
| 字段 | 类型 | 键类型 | 描述 |
| --- | --- | --- | --- |
| id | TEXT | PRIMARY KEY | 压缩记忆 ID |
| session_id | TEXT | 无 | 会话 ID |
| original_ids | TEXT | 无 | 原始记忆 ID 列表 |
| compressed_content | TEXT | 无 | 压缩内容 |
| summary | TEXT | 无 | 摘要 |
| created_at | REAL | 无 | 创建时间 |
| range_start | REAL | 无 | 范围开始 |
| range_end | REAL | 无 | 范围结束 |

#### FAISS 向量表
`faiss_id_map` 表结构：
| 字段 | 类型 | 键类型| 描述|
| --- | --- | --- | ---|
| faiss_id | INTEGER | PRIMARY KEY | FAISS 向量 ID |
| memory_id | INTEGER | FOREIGN KEY | 关联记忆 ID |