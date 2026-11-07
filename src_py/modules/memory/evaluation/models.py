"""离线回放评估的数据模型（M1-06 / B2-02）。

依据 `OptimizationPlan.md` §5.3 M1-06、§8「测试与评估策略」、
`docs/MemoryDesign.md` §10「质量指标」。

**本目录不产出"达标结论"**：只提供可复算的指标、报告模板与
回放 harness。阈值由 `config/evaluation.json` 给，是否达标由
维护者结合三语评估集判定。没有真实数据就宣称"参数已校准"是
自欺 —— `OptimizationPlan` §6 明确"评估集推迟则 P3 不应开始"。

为什么 case 必须有 `forbidden_ids`
──────────────────────────────
只看 Recall@K 会奖励"什么都往 prompt 里塞"的检索器：
召回高了，但把别的会话的记忆、已删记忆、过期事实一起注进去。
`误注入率` 是唯一能挡住这种退化的指标，所以它是必填字段
（允许显式给空列表，表示"本例无禁止项"，但不能缺省）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: 评估集支持的语言分组
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("zh", "ja", "en")


@dataclass(frozen=True)
class EvaluationCase:
    """一条回放用例。**不含记忆正文**，只含 id 与预期。"""

    case_id: str
    query: str
    session_id: str
    language: str = "zh"
    #: 应当被召回的记忆 id（有序时 nDCG 才有意义）
    relevant_ids: Tuple[str, ...] = ()
    #: 绝不能进 prompt 的 id（跨会话/已删除/过期）
    forbidden_ids: Tuple[str, ...] = ()
    #: 相关度分级（可选），用于 nDCG；缺省按二元相关
    relevance_grades: Tuple[float, ...] = ()
    #: 是否显式回忆（archived 层门控）
    explicit_recall: bool = False
    #: 允许的 token 预算（B2-04）
    token_budget: int = 2048
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["EvaluationCase"]:
        if not isinstance(raw, dict):
            return None
        case_id = str(raw.get("case_id", "") or "").strip()
        query = str(raw.get("query", "") or "").strip()
        session_id = str(raw.get("session_id", "") or "").strip()
        if not case_id or not query or not session_id:
            return None
        lang = str(raw.get("language", "zh") or "zh").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            lang = "zh"
        # forbidden_ids 允许显式空，但字段必须存在
        if "forbidden_ids" not in raw:
            return None
        try:
            grades = tuple(float(x) for x in (raw.get("relevance_grades") or ()))
        except (TypeError, ValueError):
            grades = ()
        try:
            budget = int(raw.get("token_budget", 2048) or 2048)
        except (TypeError, ValueError):
            budget = 2048
        return cls(
            case_id=case_id,
            query=query,
            session_id=session_id,
            language=lang,
            relevant_ids=tuple(str(x) for x in (raw.get("relevant_ids") or ())),
            forbidden_ids=tuple(str(x) for x in (raw.get("forbidden_ids") or ())),
            relevance_grades=grades,
            explicit_recall=bool(raw.get("explicit_recall", False)),
            token_budget=max(1, budget),
            metadata={
                str(k): v for k, v in (raw.get("metadata") or {}).items()
            },
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "session_id": self.session_id,
            "language": self.language,
            "relevant_ids": list(self.relevant_ids),
            "forbidden_ids": list(self.forbidden_ids),
            "relevance_grades": list(self.relevance_grades),
            "explicit_recall": self.explicit_recall,
            "token_budget": self.token_budget,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CaseResult:
    """一个 case 在一种排序策略下的结果。"""

    case_id: str
    language: str
    strategy: str
    returned_ids: Tuple[str, ...] = ()
    #: 注入 prompt 的候选（可能与 returned 不同：门控会再过滤一次）
    injected_ids: Tuple[str, ...] = ()
    recall_at_k: float = 0.0
    #: relevant 为空的 case 不计入 Recall 均值
    recall_counted: bool = True
    mrr: float = 0.0
    ndcg: float = 0.0
    false_injection_rate: float = 0.0
    injected_chars: int = 0
    estimated_tokens: int = 0
    over_budget: bool = False
    elapsed_ms: float = 0.0
    warnings: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "language": self.language,
            "strategy": self.strategy,
            "returned_ids": list(self.returned_ids),
            "injected_ids": list(self.injected_ids),
            "recall_at_k": round(self.recall_at_k, 6),
            "recall_counted": self.recall_counted,
            "mrr": round(self.mrr, 6),
            "ndcg": round(self.ndcg, 6),
            "false_injection_rate": round(self.false_injection_rate, 6),
            "injected_chars": self.injected_chars,
            "estimated_tokens": self.estimated_tokens,
            "over_budget": self.over_budget,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "warnings": list(self.warnings),
        }


@dataclass
class StrategySummary:
    """一种策略在全部/分语言 case 上的汇总。"""

    strategy: str = ""
    total: int = 0
    recall_at_k: float = 0.0
    #: relevant 为空的 case 不计入 Recall 均值
    recall_counted: bool = True
    mrr: float = 0.0
    ndcg: float = 0.0
    false_injection_rate: float = 0.0
    over_budget_rate: float = 0.0
    estimated_tokens_total: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    by_language: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "total": self.total,
            "recall_at_k": round(self.recall_at_k, 6),
            "recall_counted": self.recall_counted,
            "mrr": round(self.mrr, 6),
            "ndcg": round(self.ndcg, 6),
            "false_injection_rate": round(self.false_injection_rate, 6),
            "over_budget_rate": round(self.over_budget_rate, 6),
            "estimated_tokens_total": self.estimated_tokens_total,
            "latency_p50_ms": round(self.latency_p50_ms, 3),
            "latency_p95_ms": round(self.latency_p95_ms, 3),
            "by_language": {
                k: {m: round(v, 6) for m, v in metrics.items()}
                for k, metrics in self.by_language.items()
            },
        }


@dataclass
class EvaluationReport:
    """离线回放报告。**不含记忆正文、不含 query 原文**。"""

    dataset: str = ""
    k: int = 10
    case_count: int = 0
    strategies: List[StrategySummary] = field(default_factory=list)
    #: 影子差异（新旧排序），仅记录，不用于达标判定
    shadow_diff: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)
    verdicts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    #: 是否为合成自检集（**不能用于宣称校准**）
    synthetic: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset,
            "k": self.k,
            "case_count": self.case_count,
            "synthetic": self.synthetic,
            "strategies": [s.as_dict() for s in self.strategies],
            "shadow_diff": dict(self.shadow_diff),
            "thresholds": dict(self.thresholds),
            "verdicts": dict(self.verdicts),
            "warnings": list(self.warnings),
        }
