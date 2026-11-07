"""MemoryClock 的三种实现（M1-01）。

| kind | 语义 | 适用 |
|---|---|---|
| `wall` | 墙上时钟，单调不减 | 默认；真实时间流逝 |
| `active` | 只累计"应用活跃"时间 | 关机/挂起期间不衰减 |
| `game` | 由存档注入的游戏内时间 | 角色世界有时间轴时 |

验收项（OptimizationPlan M1-01）
──────────────────────────────
* **时钟回拨按 0**：系统改时间/NTP 校时导致 `time.time()` 倒退时，
  `now_day()` 不得跟着倒退，Δ 一律 ≥ 0；
* **单调不减**：连续调用结果不下降；
* **可整体注入假实现**：`FakeClock` 供属性测试与离线回放。

为什么不直接用 `time.time()`
──────────────────────────
`R(Δ,S)` 的 Δ 来自时间轴。若时间轴能倒退，`Δ` 变负会让保持率
**上升** —— 用户改一次系统时间，所有遗忘的记忆集体"返老还童"。
所以这里用 `time.monotonic()` 做增量、用持久化的 `anchor` 做基准，
两者组合出既单调又能跨进程延续的时间轴。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

SECONDS_PER_DAY = 86400.0


@dataclass
class WallClock:
    """墙上时钟：wall_epoch 锚点 + monotonic 增量。

    进程重启后 `anchor` 从持久化状态恢复；若新 epoch 小于锚点
    （系统时间被回拨），保持锚点不变，保证单调。
    """

    anchor_epoch: float = field(default_factory=time.time)
    #: 锚点对应的天数，恢复时用
    anchor_day: float = 0.0
    _lock: Any = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        self._mono0 = time.monotonic()
        self._last_day = float(self.anchor_day)

    def now_seconds(self) -> float:
        with self._lock:
            elapsed = max(0.0, time.monotonic() - self._mono0)
            return float(self.anchor_epoch) + elapsed

    def now_day(self) -> float:
        with self._lock:
            elapsed = max(0.0, time.monotonic() - self._mono0)
            candidate = float(self.anchor_day) + elapsed / SECONDS_PER_DAY
            # 单调不减：任何异常都不能让时间轴倒退
            self._last_day = max(self._last_day, candidate)
            return self._last_day

    def kind(self) -> str:
        return "wall"

    def export(self) -> Dict[str, Any]:
        """给 Memento 快照用的完整状态（S2-01）。"""
        return {
            "kind": "wall",
            "anchor_epoch": float(self.anchor_epoch),
            "anchor_day": float(self.anchor_day),
            "current_day": self.now_day(),
        }

    @classmethod
    def restore(cls, state: Any) -> "WallClock":
        d = state if isinstance(state, dict) else {}
        return cls(
            anchor_epoch=float(d.get("anchor_epoch", time.time()) or time.time()),
            anchor_day=float(d.get("anchor_day", 0.0) or 0.0),
        )


@dataclass
class ActiveClock:
    """只累计活跃时间。挂起/休眠期间 `pause()` 之后不推进。

    `active_seconds` 由持久化状态恢复，进程重启不丢进度。
    """

    active_seconds: float = 0.0
    _running: bool = True
    _last_mono: float = field(default_factory=time.monotonic)
    _lock: Any = field(default_factory=threading.RLock, repr=False)

    def now_seconds(self) -> float:
        return self.active_seconds

    def now_day(self) -> float:
        with self._lock:
            if self._running:
                now = time.monotonic()
                delta = max(0.0, now - self._last_mono)
                self.active_seconds += delta
                self._last_mono = now
            return float(self.active_seconds) / SECONDS_PER_DAY

    def pause(self) -> None:
        with self._lock:
            self.now_day()
            self._running = False

    def resume(self) -> None:
        with self._lock:
            if not self._running:
                self._last_mono = time.monotonic()
                self._running = True

    def kind(self) -> str:
        return "active"

    def export(self) -> Dict[str, Any]:
        return {
            "kind": "active",
            "active_seconds": float(self.active_seconds),
            "current_day": self.now_day(),
        }

    @classmethod
    def restore(cls, state: Any) -> "ActiveClock":
        d = state if isinstance(state, dict) else {}
        return cls(active_seconds=float(d.get("active_seconds", 0.0) or 0.0))


@dataclass
class GameClock:
    """游戏/角色世界时间。由存档显式 `advance()` 推进。

    **不会自己走**：真实时间流逝不代表角色世界过了几天。
    """

    game_day: float = 0.0
    _lock: Any = field(default_factory=threading.RLock, repr=False)

    def advance(self, days: float) -> float:
        with self._lock:
            # 回拨按 0：负增量直接忽略
            self.game_day += max(0.0, float(days))
            return self.game_day

    def now_seconds(self) -> float:
        return self.game_day * SECONDS_PER_DAY

    def now_day(self) -> float:
        return max(0.0, float(self.game_day))

    def kind(self) -> str:
        return "game"

    def export(self) -> Dict[str, Any]:
        return {"kind": "game", "game_day": float(self.game_day),
                "current_day": self.now_day()}

    @classmethod
    def restore(cls, state: Any) -> "GameClock":
        d = state if isinstance(state, dict) else {}
        return cls(game_day=float(d.get("game_day", 0.0) or 0.0))


@dataclass
class FakeClock:
    """测试用假时钟。可自由设置，但 `set()` 拒绝倒退（模拟真实约束）。"""

    day: float = 0.0
    seconds: float = 0.0

    def set(self, day: float) -> None:
        if day < self.day:
            raise ValueError("FakeClock 不允许时间回拨（与 WallClock 语义一致）")
        self.day = float(day)
        self.seconds = self.day * SECONDS_PER_DAY

    def advance(self, days: float) -> None:
        self.set(self.day + max(0.0, float(days)))

    def now_seconds(self) -> float:
        return float(self.seconds)

    def now_day(self) -> float:
        return float(self.day)

    def kind(self) -> str:
        return "fake"


def create_clock(kind: str = "wall", state: Optional[Dict[str, Any]] = None) -> Any:
    """组合根用工厂。未知 kind 一律回退 wall（不抛异常）。"""
    key = str(kind or "wall").strip().lower()
    if key == "active":
        return ActiveClock.restore(state)
    if key == "game":
        return GameClock.restore(state)
    if key == "fake":
        return FakeClock(day=float((state or {}).get("day", 0.0) or 0.0))
    return WallClock.restore(state)
