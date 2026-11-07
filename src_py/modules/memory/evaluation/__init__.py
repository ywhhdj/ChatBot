"""离线回放评估：指标、用例、报告、harness（M1-06 / B2-02）。

只用标准库，可在没装向量库 / Rust 内核的机器上复算报告。
**不产出校准结论**：阈值来自 config/evaluation.json，达标与否由
维护者结合真实中/日/英评估集判定。
"""

from .benchmark import BenchPoint, BenchReport, benchmark_kernel, compare_backends
from .harness import (
    STRATEGIES,
    from_ranker,
    load_cases,
    load_thresholds,
    run_evaluation,
    synthetic_cases,
)
from .metrics import (
    estimate_tokens,
    false_injection_rate,
    mean,
    ndcg_at_k,
    passes_thresholds,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from .models import (
    SUPPORTED_LANGUAGES,
    CaseResult,
    EvaluationCase,
    EvaluationReport,
    StrategySummary,
)

__all__ = [
    "STRATEGIES", "SUPPORTED_LANGUAGES", "load_cases", "load_thresholds",
    "run_evaluation", "from_ranker", "synthetic_cases",
    "recall_at_k", "reciprocal_rank", "ndcg_at_k", "false_injection_rate",
    "estimate_tokens", "percentile", "mean", "passes_thresholds",
    "EvaluationCase", "CaseResult", "StrategySummary", "EvaluationReport",
    "benchmark_kernel", "compare_backends", "BenchReport", "BenchPoint",
]
