"""记忆端口（Protocol）与时钟实现。"""

from .clock import ActiveClock, FakeClock, GameClock, WallClock, create_clock
from .protocols import (
    EmbeddingBackend,
    MemoryClock,
    StrengthComputer,
    UsageSink,
    VectorStore,
)

__all__ = [
    "MemoryClock", "VectorStore", "EmbeddingBackend", "StrengthComputer", "UsageSink",
    "WallClock", "ActiveClock", "GameClock", "FakeClock", "create_clock",
]
