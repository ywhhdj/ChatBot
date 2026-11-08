"""分层记忆的领域模型（L1–L5）。

依据 `docs/MemoryDesign.md` §3 / §12 与
`docs/MemoryCurveAndForgetting.md` §6.2 / §8.1。

**纯领域层**：只依赖标准库，不 import numpy / pymilvus / Rust /
sqlite / 配置模块。这样公式与层策略可以脱离整个运行时单测，
也保证"上层不反向依赖下层"。

五层是**逻辑分区，不是五个数据库**
──────────────────────────────
第一阶段只要求每条记忆带 `layer` / `kind` / `confidence` /
`valid_from` / `valid_until` / `source_ids` / `embedding_version`，
共用同一个存储与索引，靠查询期的 scope + layer 过滤实现隔离。
强行拆五个库只会带来五份一致性问题。

为什么把 BASE_S / S_MAX / floor 放在这里
────────────────────────────────────
这些是**业务常量**，不是可调配置项。散落在 Rust 与 Python 两处
迟早会漂移（改了一边忘了另一边），所以：
* Python 侧权威定义在本文件；
* Rust 侧 `native/src/memory.rs` 用 `kernel_constants()` 暴露同一组值，
  Python 启动时 `check_constants()` 比对，不一致就降级到纯 Python
  并告警 —— 绝不静默用两套参数算排序。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Optional, Tuple


class MemoryLayer(str, Enum):
    """五层逻辑记忆。值是存储里的稳定字符串，不要改。"""

    #: L1 工作记忆：当前轮与短期连贯性，有界 ring buffer
    WORKING = "working"
    #: L2 情节记忆：何时发生、约定和决策
    EPISODIC = "episodic"
    #: L3 语义记忆：稳定偏好与事实
    SEMANTIC = "semantic"
    #: L4 摘要记忆：会话/主题压缩，可重建、版本化
    SUMMARY = "summary"
    #: L5 冷档案：原始对话、不可变归档与回溯
    ARCHIVE = "archive"


#: 层名 → 数字层级，用于排序与展示
LAYER_ORDER: Dict[MemoryLayer, int] = {
    MemoryLayer.WORKING: 1,
    MemoryLayer.EPISODIC: 2,
    MemoryLayer.SEMANTIC: 3,
    MemoryLayer.SUMMARY: 4,
    MemoryLayer.ARCHIVE: 5,
}


class MemoryKind(str, Enum):
    """记忆对象类型（MemoryDesign §4）。"""

    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    COMMITMENT = "commitment"
    DECISION = "decision"
    SUMMARY = "summary"
    RAW = "raw"
    INFERRED = "inferred"


class UsageKind(str, Enum):
    """使用事件类型（MemoryCurveAndForgetting §6.3 / §8.3）。"""

    #: 进了 prompt（最弱）
    INJECTED = "injected"
    #: 回复明显引用
    REFERENCED = "referenced"
    #: 用户确认或主动提起（最强）
    CONFIRMED = "confirmed"
    #: 取出后被拒绝 / 用户纠正"不对"
    LAPSE = "lapse"


USAGE_WEIGHT: Dict[UsageKind, float] = {
    UsageKind.INJECTED: 0.3,
    UsageKind.REFERENCED: 0.7,
    UsageKind.CONFIRMED: 1.0,
    UsageKind.LAPSE: 0.0,
}

#: >=10 分钟才算间隔复习，否则算突击（massed penalty）
MASSED_WINDOW_SECONDS = 600


@dataclass(frozen=True)
class LayerPolicy:
    """一层的遗忘与注入策略。**frozen**：运行时不可改，改要走迁移。"""

    layer: MemoryLayer
    #: 初始稳定度基数（天）
    base_s: float
    #: 稳定度上限（天）
    s_max: float
    #: 排序时 R 的下限权重 `floor[layer]`
    rank_floor: float
    #: 默认注入 prompt
    inject_by_default: bool
    #: 该层单条注入的 token 上限（0 = 不注入）
    max_inject_tokens: int
    #: 保留天数；None = 按用户策略长期保留
    retention_days: Optional[float] = None
    #: 是否允许成为 GC 候选
    gc_eligible: bool = False


#: 权威策略表（与 Rust `kernel_constants()` 一一对应）
LAYER_POLICY: Dict[MemoryLayer, LayerPolicy] = {
    MemoryLayer.WORKING: LayerPolicy(
        layer=MemoryLayer.WORKING,
        base_s=1.0, s_max=30.0, rank_floor=0.2,
        inject_by_default=True, max_inject_tokens=1024,
        retention_days=2.0, gc_eligible=False,
    ),
    MemoryLayer.EPISODIC: LayerPolicy(
        layer=MemoryLayer.EPISODIC,
        base_s=1.0, s_max=30.0, rank_floor=0.2,
        inject_by_default=True, max_inject_tokens=512,
        retention_days=None, gc_eligible=True,
    ),
    MemoryLayer.SEMANTIC: LayerPolicy(
        layer=MemoryLayer.SEMANTIC,
        base_s=30.0, s_max=720.0, rank_floor=0.6,
        inject_by_default=True, max_inject_tokens=256,
        retention_days=None, gc_eligible=False,
    ),
    MemoryLayer.SUMMARY: LayerPolicy(
        layer=MemoryLayer.SUMMARY,
        base_s=7.0, s_max=120.0, rank_floor=0.4,
        inject_by_default=True, max_inject_tokens=768,
        retention_days=None, gc_eligible=False,
    ),
    MemoryLayer.ARCHIVE: LayerPolicy(
        layer=MemoryLayer.ARCHIVE,
        base_s=7.0, s_max=120.0, rank_floor=0.0,
        inject_by_default=False, max_inject_tokens=0,
        retention_days=None, gc_eligible=False,
    ),
}

#: 参与默认检索的层。ARCHIVE 只有显式查询才进（§7 / §8.2）。
DEFAULT_RETRIEVAL_LAYERS: FrozenSet[MemoryLayer] = frozenset({
    MemoryLayer.WORKING,
    MemoryLayer.EPISODIC,
    MemoryLayer.SEMANTIC,
    MemoryLayer.SUMMARY,
})

#: 允许提升为 semantic 的来源层（§9：提升不得跨 scope）
PROMOTABLE_LAYERS: FrozenSet[MemoryLayer] = frozenset({
    MemoryLayer.EPISODIC,
    MemoryLayer.SUMMARY,
})


def policy_of(layer: Any) -> LayerPolicy:
    """取层策略。未知值一律按 EPISODIC（最保守：衰减最快）。

    不能抛异常：存储里可能留有旧数据或拼错的字符串，
    检索链路不该因为一条脏数据整体失败。
    """
    try:
        key = MemoryLayer(str(layer))
    except (ValueError, TypeError):
        key = MemoryLayer.EPISODIC
    return LAYER_POLICY[key]


def normalize_layer(value: Any) -> MemoryLayer:
    """把旧版 `short_term / long_term / detailed / compressed` 映射到五层。

    M0-01 要求的核实结论（记录在 PLAN.md §3.8）：

    | 旧字段 | 映射 | 理由 |
    |---|---|---|
    | `short_term` | `WORKING` | 有界 deque，会话结束落盘 |
    | `long_term` | `SEMANTIC` | 高置信稳定事实/偏好 |
    | `detailed` | `EPISODIC` | 带时间与来源的原始事件明细 |
    | `compressed_memories` | `SUMMARY` | 有 source range、可重建 |
    | 归档/导出原文 | `ARCHIVE` | 默认不进检索 |

    这是**读取映射**，不写回用户数据库；schema migration 由
    `memory/migrations.py` 显式执行。
    """
    text = str(value or "").strip().lower()
    aliases = {
        "1": MemoryLayer.WORKING, "l1": MemoryLayer.WORKING,
        "short_term": MemoryLayer.WORKING, "short": MemoryLayer.WORKING,
        "working": MemoryLayer.WORKING,
        "2": MemoryLayer.EPISODIC, "l2": MemoryLayer.EPISODIC,
        "detailed": MemoryLayer.EPISODIC, "detail": MemoryLayer.EPISODIC,
        "episodic": MemoryLayer.EPISODIC,
        "3": MemoryLayer.SEMANTIC, "l3": MemoryLayer.SEMANTIC,
        "long_term": MemoryLayer.SEMANTIC, "long": MemoryLayer.SEMANTIC,
        "semantic": MemoryLayer.SEMANTIC,
        "4": MemoryLayer.SUMMARY, "l4": MemoryLayer.SUMMARY,
        "compressed": MemoryLayer.SUMMARY, "summary": MemoryLayer.SUMMARY,
        "compressed_memories": MemoryLayer.SUMMARY,
        "5": MemoryLayer.ARCHIVE, "l5": MemoryLayer.ARCHIVE,
        "archive": MemoryLayer.ARCHIVE, "cold": MemoryLayer.ARCHIVE,
        "archived": MemoryLayer.ARCHIVE,
    }
    return aliases.get(text, MemoryLayer.EPISODIC)


def kernel_constants() -> Dict[str, float]:
    """导出给 Rust kernel 做一致性校验的扁平常量表。

    key 形如 `episodic.base_s`。Rust 侧 `kernel_constants()` 必须返回
    完全相同的键值；`compute/kernel.check_constants()` 在启动时比对。
    """
    out: Dict[str, float] = {
        "massed_window_s": float(MASSED_WINDOW_SECONDS),
        "spacing_base": 0.1,
        "spacing_range": 0.9,
        "massed_factor": 0.2,
        "gain_base": 1.2,
        "importance_gain": 0.5,
        "importance_s0": 3.0,
        "salience_s0": 1.5,
        "retention_nine": 9.0,
        "lapse_factor": 0.5,
        "lapse_min_s": 0.25,
        "wake_r_floor": 0.5,
        "wake_gain_factor": 0.5,
        "jitter_amplitude": 0.05,
        "usage.injected": USAGE_WEIGHT[UsageKind.INJECTED],
        "usage.referenced": USAGE_WEIGHT[UsageKind.REFERENCED],
        "usage.confirmed": USAGE_WEIGHT[UsageKind.CONFIRMED],
    }
    for layer, policy in LAYER_POLICY.items():
        prefix = layer.value
        out[f"{prefix}.base_s"] = float(policy.base_s)
        out[f"{prefix}.s_max"] = float(policy.s_max)
        out[f"{prefix}.rank_floor"] = float(policy.rank_floor)
    return out


def layers_for_query(*, explicit_recall: bool = False) -> Tuple[MemoryLayer, ...]:
    """一次检索该查哪些层。

    `explicit_recall=True`（"你还记得…吗"）才把 ARCHIVE 放进来，
    且仍要过 §8.2 的高置信门控 —— 放进候选不等于注入。
    """
    base = tuple(DEFAULT_RETRIEVAL_LAYERS)
    if explicit_recall:
        return base + (MemoryLayer.ARCHIVE,)
    return base
