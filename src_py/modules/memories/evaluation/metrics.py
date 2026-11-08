"""评估指标（纯函数，可脱离运行时复算）。

依据 `OptimizationPlan.md` §9「度量（KPI）」与
`MemoryCurveAndForgetting.md` §16。

指标定义（写清楚口径，避免"同一个名字两种算法"）
────────────────────────────────────────────
* `Recall@K` = |relevant ∩ returned| / |relevant|；
  relevant 为空的 case **跳过该指标**（不按 0 计，也不按 1 计）；
* `MRR` = 1 / 第一个相关结果的名次；没有命中为 0；
* `nDCG@K` = DCG / IDCG，二元相关或按 `relevance_grades` 分级；
  IDCG 为 0 时返回 0（不制造除零）；
* `误注入率` = |forbidden ∩ injected| / |forbidden|；
  forbidden 为空时按 0 计 —— 但 case 必须显式声明该字段；
* `token 成本`：用 `ceil(chars / CHARS_PER_TOKEN)` 做**估算**。
  刻意不用 tokenizer：评估集可能跨中/日/英，引具体 tokenizer
  会让指标随模型变，且违反"不下载依赖"约束。报告里必须标注
  这是估算值，不能当精确计费。

延迟分位数用最近邻插值（不引 numpy）。
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

#: token 估算用的字符/token 比。中英混合的保守折中值。
CHARS_PER_TOKEN = 3.0


def recall_at_k(
    relevant: Sequence[str], returned: Sequence[str], k: int = 10
) -> Tuple[float, bool]:
    """返回 `(值, 是否计入统计)`。relevant 为空时不计入。"""
    rel = set(str(x) for x in relevant)
    if not rel:
        return 0.0, False
    top = [str(x) for x in returned[: max(0, int(k))]]
    hit = len(rel.intersection(top))
    return min(1.0, hit / len(rel)), True


def reciprocal_rank(relevant: Sequence[str], returned: Sequence[str]) -> float:
    rel = set(str(x) for x in relevant)
    if not rel:
        return 0.0
    for rank, doc_id in enumerate(returned, start=1):
        if str(doc_id) in rel:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    relevant: Sequence[str],
    returned: Sequence[str],
    k: int = 10,
    grades: Sequence[float] = (),
) -> float:
    """分级 nDCG。grades 按 relevant_ids 的顺序给出。"""
    rel_list = [str(x) for x in relevant]
    if not rel_list:
        return 0.0
    grade_map: Dict[str, float] = {}
    if grades:
        for doc_id, grade in zip(rel_list, grades):
            try:
                grade_map[doc_id] = max(0.0, float(grade))
            except (TypeError, ValueError):
                grade_map[doc_id] = 1.0
    else:
        grade_map = {doc_id: 1.0 for doc_id in rel_list}

    top = [str(x) for x in returned[: max(0, int(k))]]
    dcg = 0.0
    for rank, doc_id in enumerate(top, start=1):
        gain = grade_map.get(doc_id, 0.0)
        if gain > 0:
            dcg += (2.0 ** gain - 1.0) / math.log2(rank + 1.0)

    ideal = sorted(grade_map.values(), reverse=True)[: max(0, int(k))]
    idcg = sum(
        (2.0 ** g - 1.0) / math.log2(rank + 1.0)
        for rank, g in enumerate(ideal, start=1)
        if g > 0
    )
    if idcg <= 0:
        return 0.0
    return min(1.0, max(0.0, dcg / idcg))


def false_injection_rate(
    forbidden: Sequence[str], injected: Sequence[str]
) -> float:
    forb = set(str(x) for x in forbidden)
    if not forb:
        return 0.0
    inj = set(str(x) for x in injected)
    return len(forb & inj) / len(forb)


def estimate_tokens(chars: int) -> int:
    """估算 token 数。**报告里必须标注为估算**。"""
    if chars <= 0:
        return 0
    return int(math.ceil(float(chars) / CHARS_PER_TOKEN))


def percentile(values: Sequence[float], p: float) -> float:
    """最近邻插值分位数（不引 numpy）。空列表返回 0。"""
    data = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    q = min(1.0, max(0.0, float(p))) * (len(data) - 1)
    lo = int(math.floor(q))
    hi = min(len(data) - 1, lo + 1)
    frac = q - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def mean(values: Sequence[float]) -> float:
    finite = [float(v) for v in values if math.isfinite(float(v))]
    return sum(finite) / len(finite) if finite else 0.0


def passes_thresholds(summary: Dict[str, float], thresholds: Dict[str, float]) -> Dict[str, Any]:
    """按阈值判定。**只给结论，不自动开启任何开关**。

    阈值名形如 `recall_at_k.min`、`false_injection_rate.max`、
    `mrr.min`、`ndcg.min`、`over_budget_rate.max`。
    未配置的指标不参与判定，并在 `skipped` 里列出。
    """
    checks: Dict[str, Dict[str, Any]] = {}
    for metric, threshold in (thresholds or {}).items():
        if "." not in metric:
            continue
        name, direction = metric.rsplit(".", 1)
        value = summary.get(name)
        if value is None:
            continue
        try:
            limit = float(threshold)
        except (TypeError, ValueError):
            continue
        ok = value >= limit if direction == "min" else value <= limit
        checks[metric] = {
            "value": round(float(value), 6),
            "limit": limit,
            "ok": bool(ok),
        }
    configured = {m.rsplit(".", 1)[0] for m in (thresholds or {})}
    skipped = sorted(configured - {m.rsplit(".", 1)[0] for m in checks})
    return {
        "all_pass": bool(checks) and all(c["ok"] for c in checks.values()),
        "checks": checks,
        "skipped": skipped,
    }
