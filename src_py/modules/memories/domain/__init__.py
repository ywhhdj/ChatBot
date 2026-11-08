"""记忆领域层：分层、强度公式、状态机、融合评分。

**纯 Python 标准库**，不依赖 numpy / pymilvus / Rust / 配置单例，
保证公式可脱离运行时做属性测试（M1-03）。
"""

from .layers import (
    DEFAULT_RETRIEVAL_LAYERS,
    LAYER_ORDER,
    LAYER_POLICY,
    MASSED_WINDOW_SECONDS,
    PROMOTABLE_LAYERS,
    USAGE_WEIGHT,
    LayerPolicy,
    MemoryKind,
    MemoryLayer,
    UsageKind,
    kernel_constants,
    layers_for_query,
    normalize_layer,
    policy_of,
)
from .strength import (
    Strength,
    deterministic_jitter,
    final_score,
    fnv1a64,
    initial_stability,
    injection_gate,
    is_gc_candidate,
    lapse,
    new_strength,
    rank_candidates,
    reinforce,
    reinforcement_gain,
    retention,
    retention_of,
    state_of,
)

__all__ = [
    "MemoryLayer", "MemoryKind", "UsageKind", "LayerPolicy", "LAYER_POLICY",
    "LAYER_ORDER", "DEFAULT_RETRIEVAL_LAYERS", "PROMOTABLE_LAYERS",
    "USAGE_WEIGHT", "MASSED_WINDOW_SECONDS", "policy_of", "normalize_layer",
    "layers_for_query", "kernel_constants",
    "Strength", "retention", "retention_of", "deterministic_jitter", "fnv1a64",
    "initial_stability", "new_strength", "reinforcement_gain", "reinforce",
    "lapse", "final_score", "rank_candidates", "state_of", "injection_gate",
    "is_gc_candidate",
]
