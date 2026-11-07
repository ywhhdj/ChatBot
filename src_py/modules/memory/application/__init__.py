"""记忆应用层：检索编排、使用事件、固化 dry-run。

编排层只依赖 `domain` 与 `ports`，不反向依赖具体存储实现。
"""

from .consolidation import (
    ConsolidationAction,
    ConsolidationConfig,
    ConsolidationPlanner,
    ConsolidationReport,
)
from .gc import GCCandidate, GCReport, MemoryGCService
from .retention import ActionResult, MemoryRetentionService, RetentionReject
from .ranker import MemoryRanker, RetrievalPlan, RetrievalReport
from .usage import MemoryUsageEvent, MemoryUsageQueue, get_usage_queue

__all__ = [
    "MemoryRanker", "RetrievalPlan", "RetrievalReport",
    "MemoryUsageEvent", "MemoryUsageQueue", "get_usage_queue",
    "ConsolidationPlanner", "ConsolidationConfig", "ConsolidationReport",
    "ConsolidationAction",
    "MemoryRetentionService", "RetentionReject", "ActionResult",
    "MemoryGCService", "GCReport", "GCCandidate",
]
