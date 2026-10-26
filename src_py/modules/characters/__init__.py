"""角色系统导出。

注意：这里**不在导入期**间接拉起 pipeline.manager。
orchestrator 已改为相对导入 `from ..pipeline.manager import LLM`，
但 characters/__init__ 若导入 orchestrator，仍会与 pipeline 形成
"pipeline/chat -> characters -> pipeline/manager" 的环。
因此对 CharacterOrchestrator 做惰性导出（__getattr__）。
"""
from .presets import (
    create_custom,
    create_defaults
)
__all__ = [
    "create_custom",
    "create_defaults",
]


def __getattr__(name):
    if name == "CharacterOrchestrator":
        from ..pipeline.orchestrator import CharacterOrchestrator
        return CharacterOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
