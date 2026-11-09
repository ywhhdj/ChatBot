"""向量存储端口的配置与 DTO。

只依赖标准库：Milvus 适配器与内存适配器都从这里取类型，
避免 `memory/vector/` 内部横向 import 形成环。

**向量后端只有一个生产实现：Milvus。**
`memory` 是显式配置的开发/测试实现，不是自动降级目标 ——
自动降级会让"明明记得却召不回"变成只有压测才能发现的问题。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Literal

from ..domain.layers import MemoryLayer

#: Milvus filter 表达式里允许出现的字面量字符。
#: session_id 可能来自用户输入，**必须白名单**后才拼进 expr，
#: 否则一个带引号的 id 就能改写整条过滤条件（表达式注入）。
SAFE_LITERAL_RE = re.compile(r"^[A-Za-z0-9_.:@/+= \-]{1,128}$")

DEFAULT_COLLECTION = "chatbot_memory"

#: 允许的后端。向量检索只有 Milvus 与显式内存实现。
ALLOWED_BACKENDS = ("milvus", "test")


def safe_literal(value: Any) -> str:
    """把值转成可安全拼进 Milvus expr 的单引号字面量。

    拒绝转义而不是"转义引号"：转义规则随 Milvus 版本变化，
    一旦漏一种引号形式就是注入。白名单没有这个风险。
    """
    text = str(value or "")
    if not SAFE_LITERAL_RE.match(text):
        raise ValueError(f"不安全的 filter 字面量: {text[:32]!r}")
    return "'" + text + "'"


@dataclass(frozen=True)
class VectorHit:
    """一次检索的命中。"""

    memory_id: int
    score: float
    layer: MemoryLayer = MemoryLayer.EPISODIC
    session_id: str = ""

    def as_tuple(self):
        return int(self.memory_id), float(self.score)


@dataclass(frozen=True)
class VectorStoreConfig:
    #: milvus（生产）| memory（显式开发/测试）
    backend: Literal["milvus","test"]|str = "milvus"
    #: Milvus 连接串（http://host:19530 或本地 milvus_demo.db）
    uri: str = ""
    token: str = ""
    db_name: str = "default"
    collection: str = DEFAULT_COLLECTION
    index_type: str = "HNSW"
    metric_type: str = "COSINE"
    consistency_level: str = "Bounded"
    connect_timeout: float = 5.0
    max_batch: int = 1000
    #: 单轮检索 top_k 上限
    max_top_k: int = 100
    dim: int = 384

    @classmethod
    def from_dict(cls, raw: Any) -> "VectorStoreConfig":
        d = raw if isinstance(raw, dict) else {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        cfg = cls(**{k: v for k, v in d.items() if k in known})
        backend = str(cfg.backend or "milvus").strip().lower()
        if backend not in ALLOWED_BACKENDS:
            raise ValueError(
                f"不支持的向量后端 {backend!r}；只允许 {ALLOWED_BACKENDS}。"
                "FAISS 支持已移除，请改用 milvus"
            )
        return cfg

    def as_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "collection": self.collection,
            "index_type": self.index_type,
            "metric_type": self.metric_type,
            "dim": self.dim,
            "max_top_k": self.max_top_k,
            "uri_configured": bool(self.uri),
            "token_configured": bool(self.token),
        }
