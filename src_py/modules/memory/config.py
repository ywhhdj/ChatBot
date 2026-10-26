"""记忆系统调参。

另外：`compress_every_n_messages` 默认值在 config 里是 200，
而 `HybridMemorySystem.__init__` 的形参默认是 5 —— 两处不一致，
调用方不显式传就会得到与配置完全不同的行为。这里以 config 为准。
"""

from pathlib import Path
from pydantic import BaseModel, Field

from ..runtime import RuntimePath
from .rag.models import RAGConfig


class MemoryConfig(BaseModel):
    """记忆配置"""

    compress_min_size: int = Field(default=5, ge=1, description="触发压缩的最小消息数")
    user_is_database: bool = False
    db_path: str = Field(default_factory=lambda: str(RuntimePath.get_memory_db_path()))
    index_path: str = Field(default_factory=lambda: str(
        Path(RuntimePath.get_memory_db_path()).with_name("memory.faiss")
    ))
    max_records: int = Field(default=10000, ge=100)
    short_term_days: int = Field(default=2, ge=1)
    compress_every_n_messages: int = Field(default=200, ge=1)
    compress_batch_size: int = Field(default=1000, ge=1)
    embedding_dim: int = Field(default=384, ge=1)
    rag:RAGConfig = Field(default_factory=RAGConfig, description="RAG 配置")

    def ensure_parent_dirs(self) -> None:
        for path in (self.db_path, self.index_path):
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
