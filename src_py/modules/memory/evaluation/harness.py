"""离线回放 harness（M1-06 / B2-02）。

依据 `OptimizationPlan.md` §5.3 M1-06、§6「关键路径」、§8 / §9
与 `BackendDesign.md` B2-02。

这个 harness 解决的是**门槛问题**，不是"替维护者做决定"
──────────────────────────────────────────────
`OptimizationPlan` §6 写死了：`C0-01/03 → M1-04/05/06 → M2-01~04`，
"评估集若被推迟，P3 不应开始，因为遗忘的参数没有数据依据"。
所以本模块提供：三语分组、可复算指标、影子对照、阈值判定、
可重现报告；**但没有真实评估数据时绝不产出"已校准"结论**。

三种对照策略（B2-02）
────────────────────
| strategy | 含义 |
|---|---|
| `dense` | 单路向量检索，作为基线 |
| `rrf` | 五路召回 + RRF 融合，不启用强度 |
| `rrf+strength` | RRF + R 参与排序（`features.rerank=True`） |

对照只看指标差异，不自动改任何开关。

为什么 retriever 是注入的函数
────────────────────────────
评估要能在"真实 Milvus"、"内存库"、"纯桩"三种环境下跑同一套
case。若 harness 直接 import 具体存储，离线回放就只能在装齐
依赖的机器上做，等于把门槛又抬高一次。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ...logger import logger
from . import metrics as M
from .models import (
    SUPPORTED_LANGUAGES,
    CaseResult,
    EvaluationCase,
    EvaluationReport,
    StrategySummary,
)

#: strategy 名 → 说明。报告里带上，便于复核口径
STRATEGIES: Tuple[str, ...] = ("dense", "rrf", "rrf+strength")

DEFAULT_THRESHOLDS: Dict[str, float] = {
    # 这些是**占位起点**，不是已验证的验收线。
    # 维护者须用真实三语评估集校准后写进 config/evaluation.json。
    "recall_at_k.min": 0.0,
    "mrr.min": 0.0,
    "false_injection_rate.max": 1.0,
    "over_budget_rate.max": 1.0,
}

#: retriever 返回 `(候选列表, 诊断 dict)`。
#: 候选至少含 `id` 与 `content`；`content` 只用于估算 token 成本，
#: **不写进报告**（SecurityAndAuditDesign §5：不记录记忆正文）。
Retriever = Callable[[EvaluationCase, str], Tuple[List[Mapping[str, Any]], Dict[str, Any]]]


def load_cases(path: str) -> Tuple[List[EvaluationCase], List[str]]:
    """从 jsonl 加载评估集。**宽松加载、严格字段**。

    单行坏了只跳过并记原因，不让整份评估集打不开；但每个 case
    必须显式给 `forbidden_ids`（含空列表），否则该行拒绝。
    """
    out: List[EvaluationCase] = []
    problems: List[str] = []
    file = Path(path)
    if not file.is_file():
        return out, [f"评估集不存在: {path}"]
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return out, [f"评估集不可读: {type(exc).__name__}"]
    for lineno, line in enumerate(lines, start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            problems.append(f"第 {lineno} 行不是合法 JSON")
            continue
        case = EvaluationCase.from_dict(raw)
        if case is None:
            problems.append(
                f"第 {lineno} 行字段不完整（需 case_id/query/session_id/forbidden_ids）"
            )
            continue
        out.append(case)
    return out, problems


def load_thresholds(path: str = "") -> Dict[str, float]:
    """从 `config/evaluation.json` 读阈值；缺省用占位起点。"""
    target = Path(path) if path else Path(
        os.getenv("MEMORY_CONFIG_DIR", "config")
    ) / "evaluation.json"
    if not target.is_file():
        return dict(DEFAULT_THRESHOLDS)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[Evaluation] 阈值配置解析失败，用默认值: {type(exc).__name__}")
        return dict(DEFAULT_THRESHOLDS)
    thresholds = dict(DEFAULT_THRESHOLDS)
    if not isinstance(raw, dict):
        return thresholds
    items = raw.get("thresholds") or {}
    if not isinstance(items, dict):
        return thresholds
    for key, value in items.items():
        try:
            thresholds[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return thresholds


def _case_result(
    case: EvaluationCase,
    strategy: str,
    candidates: Sequence[Mapping[str, Any]],
    diagnosis: Mapping[str, Any],
    k: int,
    started: float,
) -> CaseResult:
    returned = tuple(str(c.get("id", "")) for c in candidates[:k])
    # 门控后的注入集合：诊断里给了就用，否则与 returned 相同
    injected_raw = diagnosis.get("injected_ids")
    injected = tuple(str(x) for x in injected_raw) \
        if isinstance(injected_raw, (list, tuple)) else returned

    recall, counted = M.recall_at_k(case.relevant_ids, returned, k)
    chars = sum(len(str(c.get("content", "") or "")) for c in candidates[:k])
    tokens = M.estimate_tokens(chars)
    return CaseResult(
        case_id=case.case_id,
        language=case.language,
        strategy=strategy,
        returned_ids=returned,
        injected_ids=injected,
        recall_at_k=recall if counted else 0.0,
        recall_counted=bool(counted),
        mrr=M.reciprocal_rank(case.relevant_ids, returned),
        ndcg=M.ndcg_at_k(case.relevant_ids, returned, k,
                         case.relevance_grades),
        false_injection_rate=M.false_injection_rate(
            case.forbidden_ids, injected
        ),
        injected_chars=chars,
        estimated_tokens=tokens,
        over_budget=tokens > case.token_budget,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
        warnings=tuple(str(x) for x in (diagnosis.get("warnings") or ())[:5]),
    )


def _summarize(strategy: str, results: Sequence[CaseResult]) -> StrategySummary:
    """汇总一种策略。Recall 只统计 `recall_counted=True` 的 case。"""
    recalls = [r.recall_at_k for r in results if r.recall_counted]
    latencies = [r.elapsed_ms for r in results]
    summary = StrategySummary(
        strategy=strategy,
        total=len(results),
        recall_at_k=M.mean(recalls),
        mrr=M.mean([r.mrr for r in results]),
        ndcg=M.mean([r.ndcg for r in results]),
        false_injection_rate=M.mean([r.false_injection_rate for r in results]),
        over_budget_rate=M.mean([1.0 if r.over_budget else 0.0 for r in results]),
        estimated_tokens_total=sum(r.estimated_tokens for r in results),
        latency_p50_ms=M.percentile(latencies, 0.50),
        latency_p95_ms=M.percentile(latencies, 0.95),
    )
    for lang in SUPPORTED_LANGUAGES:
        group = [r for r in results if r.language == lang]
        if not group:
            continue
        summary.by_language[lang] = {
            "total": float(len(group)),
            "recall_at_k": M.mean(
                [r.recall_at_k for r in group if r.recall_counted]
            ),
            "mrr": M.mean([r.mrr for r in group]),
            "false_injection_rate": M.mean(
                [r.false_injection_rate for r in group]
            ),
        }
    return summary


def run_evaluation(
    cases: Sequence[EvaluationCase],
    retriever: Retriever,
    *,
    dataset: str = "",
    k: int = 10,
    strategies: Sequence[str] = STRATEGIES,
    thresholds: Optional[Dict[str, float]] = None,
    synthetic: bool = False,
) -> EvaluationReport:
    """跑一轮回放。**不写任何运行态，不改任何开关**。"""
    k = max(1, int(k))
    limits = dict(thresholds or DEFAULT_THRESHOLDS)
    report = EvaluationReport(
        dataset=str(dataset or ""),
        k=k,
        case_count=len(cases),
        thresholds=limits,
        synthetic=bool(synthetic),
    )
    if not cases:
        report.warnings.append("评估集为空，未产生任何指标")
        return report

    all_results: Dict[str, List[CaseResult]] = {}
    shadow_diffs: List[Dict[str, Any]] = []
    for strategy in strategies:
        results: List[CaseResult] = []
        for case in cases:
            started = time.perf_counter()
            try:
                candidates, diagnosis = retriever(case, strategy)
            except Exception as exc:  # noqa: BLE001
                # 单 case 失败不拖垮整轮，但要可见
                report.warnings.append(
                    f"{strategy}/{case.case_id} 失败: {type(exc).__name__}"
                )
                candidates, diagnosis = [], {"warnings": ["retriever 异常"]}
            results.append(_case_result(
                case, strategy, candidates or [], diagnosis or {}, k, started
            ))
            diff = (diagnosis or {}).get("shadow_diff")
            if isinstance(diff, dict) and diff:
                shadow_diffs.append({
                    "case_id": case.case_id,
                    "strategy": strategy,
                    **diff,
                })
        all_results[strategy] = results
        report.strategies.append(_summarize(strategy, results))

    if shadow_diffs:
        report.shadow_diff = {
            "samples": shadow_diffs[:10],
            "count": len(shadow_diffs),
        }

    for summary in report.strategies:
        plain = summary.as_dict()
        report.verdicts[summary.strategy] = M.passes_thresholds(plain, limits)

    if synthetic:
        report.warnings.append(
            "本次使用合成自检集，结果仅证明 harness 可运行，"
            "**不得用于宣称参数已校准或开启 rerank/state_transition**"
        )
    if not any(c.language != "zh" for c in cases):
        report.warnings.append("评估集缺少日/英用例，三语结论不成立")
    return report


def from_ranker(ranker_factory: Callable[[str], Any]) -> Retriever:
    """把 `MemoryRanker` 包成 Retriever，方便直接接现有实现。

    `ranker_factory(strategy)` 应返回已按该策略配置好的 ranker。
    harness 不 import 具体 ranker，避免评估层反向依赖应用层实现。
    """
    def _retrieve(case: EvaluationCase, strategy: str):
        from ..application.ranker import RetrievalPlan

        ranker = ranker_factory(strategy)
        plan = RetrievalPlan(
            session_id=case.session_id,
            query=case.query,
            top_k=case.token_budget,   # 预算由调用方另做 token 裁剪
            explicit_recall=case.explicit_recall,
        )
        out, diagnosis = ranker.rank(plan)
        return out, diagnosis.as_dict()
    return _retrieve


def synthetic_cases() -> List[EvaluationCase]:
    """内置**合成自检集**：只验证 harness 指标计算是否正确。

    刻意标注 synthetic=True；这几个 case 没有真实语义，
    绝不用于校准遗忘参数或宣称 Recall 达标。
    """
    return [
        EvaluationCase(
            case_id="synth-zh-1", query="天气", session_id="s1", language="zh",
            relevant_ids=("m1", "m2"), forbidden_ids=("x1",),
            token_budget=512,
        ),
        EvaluationCase(
            case_id="synth-ja-1", query="天気", session_id="s1", language="ja",
            relevant_ids=("m3",), forbidden_ids=(), token_budget=512,
        ),
        EvaluationCase(
            case_id="synth-en-1", query="weather", session_id="s1", language="en",
            relevant_ids=("m4",), forbidden_ids=("x2",), token_budget=512,
        ),
    ]
