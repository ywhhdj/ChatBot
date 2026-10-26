# 记忆系统设计（SQLite + FAISS）

## 目标

- `ContentManager` 维护最多 `100` 条会话缓存，并负责构建 LLM prompt。
- `MemorySystem` 提供长期记忆检索、衰减、访问强化, 压缩记忆功能。
- FAISS 只存向量；`faiss_id -> memory_id` 映射保存在 SQLite。
- 总量超过 `10000` 时优先淘汰低分记忆（低重要度、久未访问）。
- SQLite 由单独 worker 线程串行维护，避免线程安全问题。
- 定时衰减重要度，模拟记忆过期。

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

### FAISS（向量层）

- 使用 `IndexIDMap2(IndexFlatIP)`。
- 仅存 `float32` 归一化向量。
- 检索输出 `faiss_id + similarity`，再由 SQLite `faiss_id_map` 反查元数据。

## 线程模型

`SQLiteFAISSStorage` 内部维护 `MemoryWorker`：

- API 接口
  - `add_memories`
  - `retrieve_memory` 
  - `get_short_term`
- 所有 DB 读写通过任务队列进入 worker 串行执行。
- worker 每小时执行一次：
  - 重要度衰减 $importance *= 0.995$
  - 超量淘汰（超过 1w）

## Prompt 构建

`ContextManager` 内 `ContentManager`：

- 缓存最近 100 条消息（短期）。
- 每轮查询时检索长期记忆（默认 top_k=12）。
- 组装消息：
  - system prompt
  - 相关记忆摘要（system message）
  - 最近对话缓存
  - 当前用户输入
