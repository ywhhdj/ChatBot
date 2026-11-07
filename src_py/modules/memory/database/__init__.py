"""SQLite 异步封装（记忆域唯一的数据访问层）。

本包**不含任何向量索引实现**：向量检索统一走 `memory/vector/`
的 `VectorStore` 端口（Milvus），SQLite 只存权威元数据。
"""
