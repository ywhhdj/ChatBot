"""类人遗忘曲线：强度模型（**纯函数**）。

依据 `docs/MemoryCurveAndForgetting.md` §6，全部公式集中在此，
Rust 侧 `native/src/memory.rs` 是同一组公式的 SIMD/批量实现。

公式一览
────────
```
R(Δ, S) = 1 / (1 + Δ / (9·S))                 §6.1 幂律保持率
S0 = BASE_S[layer] × (1 + 3·imp) × (1 + 1.5·sal)   受 S_MAX 限制   §6.2
spacing = 0.1 + 0.9·(1 − R_now)                    间隔效应        §6.3
massed  = 0.2 若距上次强化 < 10 分钟，否则 1        突击惩罚        §6.3
gain    = 1.2 × usage_weight × spacing × massed × (1 + 0.5·imp)
S'      = min(S_MAX, S·(1 + gain))
lapse   : S' = max(0.25, S × 0.5)，lapse_count += 1，不重置时间轴
final   = relevance × (floor[layer] + (1 − floor[layer]) × R_eff)  §8.1
```

为什么是纯函数
──────────────
`M1-03` 要求"属性测试全过"。任何一处偷偷读 `time.time()`、
读配置单例、或写数据库，属性测试就变成集成测试，且回放不可复现。
所以所有时间都**由调用方传入**，本模块不持有任何时钟。

参数校准声明
────────────
这些常数是设计起点（文档明确写了"须用本项目回放数据校准"），
不是已验证的最优值。`M1-06` 评估集出来之前不得宣称收益。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional

from .layers import (
    MASSED_WINDOW_SECONDS,
    USAGE_WEIGHT,
    LayerPolicy,
    MemoryLayer,
    UsageKind,
    policy_of,
)

# ─────────────────────────────────────────────────────────────
# 常数（与 domain/layers.kernel_constants() 一致）
# ─────────────────────────────────────────────────────────────

RETENTION_NINE = 9.0
SPACING_BASE = 0.1
SPACING_RANGE = 0.9
MASSED_FACTOR = 0.2
GAIN_BASE = 1.2
IMPORTANCE_GAIN = 0.5
IMPORTANCE_S0 = 3.0
SALIENCE_S0 = 1.5
LAPSE_FACTOR = 0.5
LAPSE_MIN_S = 0.25
WAKE_R_FLOOR = 0.5
WAKE_GAIN_FACTOR = 0.5
JITTER_AMPLITUDE = 0.05

#: 强度下限。S 不能到 0，否则 R 除零；也不能无限大。
MIN_STABILITY = 0.25


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))


def _safe_days(value: float) -> float:
    """负 Δ（时钟回拨）按 0 处理 —— M1-01 验收项。"""
    if not math.isfinite(value) or value < 0:
        return 0.0
    return float(value)


# ─────────────────────────────────────────────────────────────
# 状态
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Strength:
    """一条记忆的强度状态。frozen：更新返回新对象。"""

    memory_id: str = ""
    layer: MemoryLayer = MemoryLayer.EPISODIC
    #: 稳定度（天）
    stability: float = 1.0
    #: 上次强化时刻（**天**，不是秒；由 MemoryClock 提供）
    last_reinforced_day: float = 0.0
    importance: float = 0.4
    salience: float = 0.0
    lapse_count: int = 0
    #: 用户明确固定（"记住/别忘了"）→ R 恒为 1
    pinned: bool = False
    #: 状态缓存列；以 `retention()` 的结果为准
    state: str = "active"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "layer": self.layer.value,
            "stability": self.stability,
            "last_reinforced_day": self.last_reinforced_day,
            "importance": self.importance,
            "salience": self.salience,
            "lapse_count": self.lapse_count,
            "pinned": self.pinned,
            "state": self.state,
        }


# ─────────────────────────────────────────────────────────────
# §6.1 保持率
# ─────────────────────────────────────────────────────────────


def retention(delta_days: float, stability: float, *, pinned: bool = False) -> float:
    """`R(Δ, S) = 1 / (1 + Δ / (9·S))`。

    `pinned` 记忆 R 恒为 1。S<=0 时按最小稳定度处理而不是抛异常——
    脏数据不该让整轮检索崩掉。
    """
    if pinned:
        return 1.0
    s = max(MIN_STABILITY, float(stability)) if math.isfinite(stability) else MIN_STABILITY
    delta = _safe_days(delta_days)
    return 1.0 / (1.0 + delta / (RETENTION_NINE * s))


def retention_of(record: Strength, now_day: float, *, jitter: bool = False) -> float:
    """从状态算当前保持率。可选确定性抖动（§6.5）。"""
    delta = now_day - record.last_reinforced_day
    base = retention(delta, record.stability, pinned=record.pinned)
    if not jitter or record.pinned:
        return base
    return _clamp01(base * (1.0 + deterministic_jitter(record.memory_id, now_day)))


FNV_OFFSET_64 = 0xCBF29CE484222325
FNV_PRIME_64 = 0x100000001B3
_U64_MASK = (1 << 64) - 1


def fnv1a64(text: str) -> int:
    """FNV-1a 64。与 Rust `native/src/memory.rs` 逐位一致。

    为什么不用 hashlib.sha256：Rust 标准库没有 SHA 实现，
    引入 crate 会拉起额外依赖（违反"不下载依赖"约束）。
    FNV-1a 只需几行整数运算，两边可静态比对，且对
    "同一天同一条记忆得到同一抖动"这个用途完全够 —— 它不需要密码学强度。
    """
    h = FNV_OFFSET_64
    for byte in str(text).encode("utf-8"):
        h ^= byte
        h = (h * FNV_PRIME_64) & _U64_MASK
    return h


def deterministic_jitter(memory_id: str, day: float) -> float:
    """`f(hash(memory_id, day))` → ±5%。

    同一天同一条记忆结果固定 → 测试与离线回放可复现。
    默认关闭，按角色 `ForgettingProfile` 开启。
    """
    raw = f"{memory_id}:{int(math.floor(_safe_days(day)))}"
    value = fnv1a64(raw) / float(1 << 64)
    return (value * 2.0 - 1.0) * JITTER_AMPLITUDE


# ─────────────────────────────────────────────────────────────
# §6.2 初始稳定度
# ─────────────────────────────────────────────────────────────


def initial_stability(
    layer: Any,
    importance: float = 0.4,
    salience: float = 0.0,
) -> float:
    """`S0 = BASE_S × (1 + 3·imp) × (1 + 1.5·sal)`，受 S_MAX 限制。"""
    policy: LayerPolicy = policy_of(layer)
    imp = _clamp01(importance)
    sal = _clamp01(salience)
    raw = policy.base_s * (1.0 + IMPORTANCE_S0 * imp) * (1.0 + SALIENCE_S0 * sal)
    return min(policy.s_max, max(MIN_STABILITY, raw))


def new_strength(
    memory_id: str,
    layer: Any,
    now_day: float,
    *,
    importance: float = 0.4,
    salience: float = 0.0,
    pinned: bool = False,
) -> Strength:
    return Strength(
        memory_id=str(memory_id),
        layer=policy_of(layer).layer,
        stability=initial_stability(layer, importance, salience),
        last_reinforced_day=_safe_days(now_day),
        importance=_clamp01(importance),
        salience=_clamp01(salience),
        pinned=bool(pinned),
        state="active",
    )


# ─────────────────────────────────────────────────────────────
# §6.3 强化与失误
# ─────────────────────────────────────────────────────────────


def reinforcement_gain(
    *,
    r_now: float,
    usage: UsageKind,
    importance: float,
    massed: bool,
    wake_factor: float = 1.0,
) -> float:
    """增益系数 `gain`（不含 S 本身）。抽成函数便于属性测试。"""
    weight = USAGE_WEIGHT.get(usage, 0.0)
    spacing = SPACING_BASE + SPACING_RANGE * (1.0 - _clamp01(r_now))
    massed_factor = MASSED_FACTOR if massed else 1.0
    return (
        GAIN_BASE * weight * spacing * massed_factor
        * (1.0 + IMPORTANCE_GAIN * _clamp01(importance))
        * float(wake_factor)
    )


def reinforce(
    record: Strength,
    now_day: float,
    usage: UsageKind,
    *,
    now_seconds: Optional[float] = None,
    last_reinforce_seconds: Optional[float] = None,
    awakened: bool = False,
) -> Strength:
    """成功使用一次 → 提升 S，并推进时间轴。

    `massed` 判定用**秒**（10 分钟窗口），而 R 用**天** —— 两套单位
    刻意分开：把 10 分钟换算成天再比会丢精度，且容易写错量级。

    `awakened`（faded/archived 被唤醒）：R 从不低于 0.5 起算，
    增益乘 0.5，避免一次命中就回到高稳定度（§8.2）。
    """
    now = _safe_days(now_day)
    delta_days = max(0.0, now - record.last_reinforced_day)
    r_now = retention(delta_days, record.stability, pinned=record.pinned)
    if awakened:
        r_now = min(r_now, WAKE_R_FLOOR)

    massed = False
    if now_seconds is not None and last_reinforce_seconds is not None:
        elapsed = float(now_seconds) - float(last_reinforce_seconds)
        massed = 0.0 <= elapsed < MASSED_WINDOW_SECONDS

    gain = reinforcement_gain(
        r_now=r_now,
        usage=usage,
        importance=record.importance,
        massed=massed,
        wake_factor=WAKE_GAIN_FACTOR if awakened else 1.0,
    )
    policy = policy_of(record.layer)
    new_s = min(policy.s_max, record.stability * (1.0 + gain))
    return replace(
        record,
        stability=max(MIN_STABILITY, new_s),
        last_reinforced_day=now,
        state="active",
    )


def lapse(record: Strength) -> Strength:
    """失误：S 减半、lapse_count +1，**不重置时间轴**（§6.3）。"""
    return replace(
        record,
        stability=max(LAPSE_MIN_S, record.stability * LAPSE_FACTOR),
        lapse_count=record.lapse_count + 1,
    )


# ─────────────────────────────────────────────────────────────
# §8.1 排序
# ─────────────────────────────────────────────────────────────


def final_score(relevance: float, r_eff: float, layer: Any) -> float:
    """`final = relevance × (floor + (1 − floor) × R_eff)`。

    **只改变权重，不改变召回集合**（§8.1）。影子模式下可并行算两种
    排序对比差异，不影响任何用户可见结果。
    """
    floor = policy_of(layer).rank_floor
    rel = max(0.0, float(relevance)) if math.isfinite(relevance) else 0.0
    r = _clamp01(r_eff)
    return rel * (floor + (1.0 - floor) * r)


def rank_candidates(
    candidates: Any,
    now_day: float,
    *,
    jitter: bool = False,
) -> list:
    """给候选列表算 `final_score` 并排序（纯函数）。

    每项至少要有 `relevance` 与 `strength`（或 `r_eff`）；
    缺失的按保守值处理，不抛异常。
    """
    scored = []
    for item in candidates or []:
        d = item if isinstance(item, dict) else {}
        strength = d.get("strength")
        if isinstance(strength, Strength):
            r_eff = retention_of(strength, now_day, jitter=jitter)
            layer = strength.layer
        else:
            r_eff = _clamp01(d.get("r_eff", 1.0))
            layer = d.get("layer", MemoryLayer.EPISODIC)
        rel = d.get("relevance", 0.0)
        score = final_score(rel, r_eff, layer)
        scored.append((float(score), item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ─────────────────────────────────────────────────────────────
# §7 状态机
# ─────────────────────────────────────────────────────────────


class MemoryState(str):
    ACTIVE = "active"
    FADED = "faded"
    ARCHIVED = "archived"


STATE_ACTIVE_THRESHOLD = 0.5
STATE_FADED_THRESHOLD = 0.2
FADED_RELEVANCE_THRESHOLD = 0.75
ARCHIVED_RELEVANCE_THRESHOLD = 0.9


def state_of(r_eff: float, *, pinned: bool = False) -> str:
    """状态由 R **派生**，`state` 列只是缓存（§7）。"""
    if pinned:
        return MemoryState.ACTIVE
    r = _clamp01(r_eff)
    if r >= STATE_ACTIVE_THRESHOLD:
        return MemoryState.ACTIVE
    if r >= STATE_FADED_THRESHOLD:
        return MemoryState.FADED
    return MemoryState.ARCHIVED


def injection_gate(state: str, relevance: float, *, explicit_recall: bool = False) -> bool:
    """门控（§8.2）。返回是否允许进 prompt 候选。

    archived 只有显式回忆或高置信线索才放行；放行后按"再巩固"处理
    （强化增益减半，见 `reinforce(awakened=True)`）。
    """
    rel = _clamp01(relevance)
    if state == MemoryState.ACTIVE:
        return True  # relevance 阈值沿用现有检索阈值，此处不重复定义
    if state == MemoryState.FADED:
        return rel >= FADED_RELEVANCE_THRESHOLD
    if state == MemoryState.ARCHIVED:
        return explicit_recall or rel >= ARCHIVED_RELEVANCE_THRESHOLD
    return False


def is_gc_candidate(
    *,
    state: str,
    r_eff: float,
    age_days: float,
    covered_by_summary: bool,
    importance: float,
    layer: Any,
    pinned: bool,
) -> bool:
    """GC dry-run 候选（§7）。**条件缺一不可**。

    语义层且 importance>=0.7 有"身份下限"：最低降到 archived，
    不进入 GC 候选。
    """
    if pinned or state != MemoryState.ARCHIVED:
        return False
    if _clamp01(r_eff) >= 0.05 or _safe_days(age_days) <= 90:
        return False
    if not covered_by_summary or _clamp01(importance) >= 0.5:
        return False
    if policy_of(layer).layer == MemoryLayer.SEMANTIC and _clamp01(importance) >= 0.7:
        return False
    return policy_of(layer).gc_eligible
