"""记忆特性开关（OptimizationPlan §7 / MemoryCurveAndForgetting §15）。

**默认全部关闭**。理由：
* `rerank` 与 `state_transition` 会改变用户可见结果，必须等 M1-06
  离线评估集给出 Recall@K / MRR / 误注入率达标后才能开；
* `consolidation.apply` 会写数据，dry-run 报告先跑够；
* `gc.apply` **永久默认关闭**，硬删除需单独审批，且必须走墓碑协议。

每个开关都从 json 配置读取，代码里只有默认值；
`as_dict()` 用于诊断接口，不含任何秘密。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict


@dataclass(frozen=True)
class MemoryFeatures:
    #: 只计算与记录影子评分，不改变任何用户可见结果（M1-05）
    shadow: bool = False
    #: R 参与排序（M2-01）
    rerank: bool = False
    #: faded/archived 门控（M2-02）
    state_transition: bool = False
    #: 固化实际写入（M2-04）；dry-run 永远可用
    consolidation_apply: bool = False
    #: 硬删除，单独审批，**永久默认关闭**
    gc_apply: bool = False
    #: 确定性抖动（§6.5），按角色 ForgettingProfile 开启
    jitter: bool = False
    #: 使用 Rust 重计算内核；False 时强制纯 Python（用于 A/B 与回放）
    rust_kernel: bool = True

    @classmethod
    def from_dict(cls, raw: Any) -> "MemoryFeatures":
        d = raw if isinstance(raw, dict) else {}
        return cls(
            shadow=bool(d.get("shadow", False)),
            rerank=bool(d.get("rerank", False)),
            state_transition=bool(d.get("state_transition", False)),
            consolidation_apply=bool(d.get("consolidation.apply", False)),
            gc_apply=bool(d.get("gc.apply", False)),
            jitter=bool(d.get("jitter", False)),
            rust_kernel=bool(d.get("rust_kernel", True)),
        )

    def with_overrides(self, **kwargs: Any) -> "MemoryFeatures":
        return replace(self, **kwargs)

    def as_dict(self) -> Dict[str, bool]:
        return {
            "memory.strength.shadow": self.shadow,
            "memory.strength.rerank": self.rerank,
            "memory.forgetting.state_transition": self.state_transition,
            "memory.consolidation.apply": self.consolidation_apply,
            "memory.gc.apply": self.gc_apply,
            "memory.jitter": self.jitter,
            "memory.rust_kernel": self.rust_kernel,
        }


DEFAULT_FEATURES = MemoryFeatures()
