"""向量存储组合根

| 配置 | 行为 |
|---|---|
| `backend=milvus` | 只用 Milvus；不可用则抛 `VectorUnavailable`，由统一 API 标记 `degraded` 并关闭 dense 通道 |
| `backend=test` | 显式选择进程内实现（开发/测试/离线回放），status 里明确写 `degraded=true` |

"""

from __future__ import annotations

from typing import Any, Dict, Literal, Tuple

from ...logger import logger
from .memory_store import InMemoryVectorStore
from .milvus import MilvusUnavailable, MilvusVectorStore
from .models import VectorStoreConfig


class VectorUnavailable(RuntimeError):
    """pass"""


def create_vector_store(
    config: VectorStoreConfig | None = None,
    *,
    dim: int = 384,
    fingerprint: str = "",
    backend: Literal["milvus","test"]|str = "milvus",
) -> Tuple[Any, Dict[str, Any]]:
    """按配置创建向量后端并 `ensure_ready()`。返回 `(store, status)`。

    后端初始化失败时**抛 `VectorUnavailable`**，不返回"看起来能用"
    的替代实例。统一 API 捕获后写进 `status()["vector"]`，
    并把 dense 通道置空 —— 可解释、可观测、不误导。
    """
    cfg = config or VectorStoreConfig(dim=int(dim),backend=backend)
    backend = str(cfg.backend or "milvus").strip().lower()

    if backend == "memory":
        store: Any = InMemoryVectorStore(cfg)
        store.ensure_ready(dim=int(dim), fingerprint=str(fingerprint))
        logger.warning(
            "[VectorStore] 显式使用进程内向量实现；语义检索仅在本进程有效"
        )
        return store, {
            "selected": "memory",
            "degraded": True,
            "fallback_chain": [],
            "config": cfg.as_dict(),
            "stats": store.stats(),
        }

    if backend != "milvus":
        raise VectorUnavailable(f"不支持的向量后端: {backend}")

    store = MilvusVectorStore(cfg)
    if not store.available:
        raise VectorUnavailable("pymilvus 不可用，且未配置显式内存后端")
    try:
        store.ensure_ready(dim=int(dim), fingerprint=str(fingerprint))
    except MilvusUnavailable as exc:
        raise VectorUnavailable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise VectorUnavailable(
            f"Milvus 初始化失败: {type(exc).__name__}"
        ) from exc

    return store, {
        "selected": "milvus",
        "degraded": False,
        "fallback_chain": [],
        "config": cfg.as_dict(),
        "stats": store.stats(),
    }
