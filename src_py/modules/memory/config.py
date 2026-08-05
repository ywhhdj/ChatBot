from pydantic import BaseModel
from ..runtime import RuntimePath

class MemoryConfig(BaseModel):
    """记忆配置"""
    compress_min_size: int = 5
    user_is_database: bool = False
    db_path: str = RuntimePath.get_memory_db_path()
    index_path: str = "memory/memory.faiss"
    max_records: int = 10000
    short_term_days: int = 5
    compress_every_n_messages: int = 200
    compress_batch_size: int = 1000
