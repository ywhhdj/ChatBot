"""向量存储端口实现：Milvus（生产）与显式进程内实现（开发/测试）。

没有 FAISS 实现，也没有自动降级链 —— 见 `factory.py`。
"""

from .factory import VectorUnavailable, create_vector_store
from .memory_store import InMemoryVectorStore
from .milvus import MilvusUnavailable, MilvusVectorStore
from .models import ALLOWED_BACKENDS, VectorHit, VectorStoreConfig, safe_literal

__all__ = [
    "create_vector_store", "VectorUnavailable",
    "MilvusVectorStore", "MilvusUnavailable",
    "InMemoryVectorStore", "VectorStoreConfig", "VectorHit",
    "ALLOWED_BACKENDS", "safe_literal",
]
