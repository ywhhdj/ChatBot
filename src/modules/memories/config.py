"""记忆系统配置（json 驱动，与 api / providers 一致）"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..runtime import RuntimePath
from .rag.models import RAGConfig

MEMORY_CONFIG_ENV = "MEMORY_CONFIG_DIR"
DEFAULT_MEMORY_CONFIG_DIR = "config"


class MemoryConfig(BaseModel):
    """记忆配置。默认值与 `HybridMemorySystem` 形参保持一致。"""

    compress_min_size: int = Field(default=5, ge=1, description="触发压缩的最小消息数")
    user_is_database: bool = True
    db_path: str = Field(default_factory=lambda: str(RuntimePath.get_memory_db_path()))
    max_records: int = Field(default=10000, ge=100)
    short_term_days: int = Field(default=2, ge=1)
    compress_every_n_messages: int = Field(default=200, ge=1)
    compress_batch_size: int = Field(default=1000, ge=1)
    embedding_dim: int = Field(default=384, ge=1)
    rag: RAGConfig = Field(default_factory=RAGConfig, description="RAG 配置")
    #: sqlite（默认，生产）| markdown（显式开发模式）
    storage_backend: str = "sqlite"

    # ── 分层 / 向量后端 / 特性开关 ──
    clock_kind: str = "wall"
    vector: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    consolidation: Dict[str, Any] = Field(default_factory=dict)
    migration_batch_size: int = Field(default=500, ge=1)

    def ensure_parent_dirs(self) -> None:
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # ---------- 派生端口对象（延迟导入，避免配置层反向依赖适配器） ----------

    def vector_config(self):
        from .vector.models import VectorStoreConfig

        raw = dict(self.vector or {})
        raw.setdefault("dim", int(self.embedding_dim))
        return VectorStoreConfig.from_dict(raw)

    def feature_flags(self):
        from .features import MemoryFeatures

        return MemoryFeatures.from_dict(self.features)

    def clock(self, state: Optional[Dict[str, Any]] = None):
        from .ports.clock import create_clock

        return create_clock(self.clock_kind, state)

    def consolidation_config(self):
        from .application.consolidation import ConsolidationConfig

        known = {f for f in ConsolidationConfig.__dataclass_fields__}
        return ConsolidationConfig(**{
            k: v for k, v in (self.consolidation or {}).items() if k in known
        })

from ..runtime import RuntimePath
def load_memory_config(path: str = "") -> MemoryConfig:
    target = Path(path) if path else (
        RuntimePath.get_memories_path("system.json")
    )
    if not target.is_file():
        return MemoryConfig()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        from ..logger import logger

        logger.warning(
            f"[MemoryConfig] {target} 解析失败，使用默认值: {type(exc).__name__}"
        )
        return MemoryConfig()
    if not isinstance(raw, dict):
        return MemoryConfig()
    known = set(MemoryConfig.model_fields)  # type: ignore[attr-defined]
    return MemoryConfig(**{k: v for k, v in raw.items() if k in known})
