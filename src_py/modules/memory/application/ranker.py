"""检索编排：多路召回 → RRF → 强度排序 → 门控。

职责边界（§12）
──────────────
* `MemoryStore` 保存事实/情节/摘要和来源；
* `Retriever`（本模块）只负责按 scope 检索候选，**不决定最终喂什么进模型**；
* `PromptBuilder` 根据请求、角色、session window、token budget 决定注入集合；
* 检索结果一律是数据，不是 system policy（§12 最后一段）。

所以 `rank()` 输出的是**带来源与理由的候选清单**，不是拼好的
"长期记忆全文"，也不做任何授权判断。

影子模式
────────────────
`features.shadow=True` 时并行算"旧排序（只看 relevance）"与
"新排序（R 参与）"，把差异写进 `RetrievalReport.shadow_diff`，
但**返回的仍是旧排序**。用户可见结果零变化，可以安全地长期开着采数据。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..compute.kernel import MemoryKernel
from ..domain import scoring as _scoring
from ..domain import strength as _strength
from ..domain.layers import MemoryLayer, layers_for_query, policy_of
from ..features import MemoryFeatures
from ..ports.protocols import MemoryClock, VectorStore

#: 候选提供者：给定 scope，返回 scope 内的候选元数据。
#: 由存储适配器实现；本模块不做 IO，保持可测。
CandidateProvider = Callable[[str, Sequence[MemoryLayer]], List[Dict[str, Any]]]


@dataclass(frozen=True)
class RetrievalPlan:
    session_id: str
    character_id: str = ""
    query: str = ""
    top_k: int = 10
    explicit_recall: bool = False
    #: 检索预算（B2-04）：每路最多取多少条
    per_channel: int = 50
    #: 允许的层
    layers: Tuple[MemoryLayer, ...] = ()
    #: embedding 指纹（B1-06）。向量库查询必须带上，
    #: 否则会把不同模型产出的向量混进同一检索
    fingerprint: str = ""


@dataclass
class RetrievalReport:
    """诊断报告。不进 prompt，只进日志/health。"""

    plan_top_k: int = 0
    channels: Dict[str, int] = field(default_factory=dict)
    fused: int = 0
    gated_out: int = 0
    elapsed_ms: float = 0.0
    kernel_backend: str = ""
    rerank_applied: bool = False
    state_gate_applied: bool = False
    shadow_diff: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "plan_top_k": self.plan_top_k,
            "channels": dict(self.channels),
            "fused": self.fused,
            "gated_out": self.gated_out,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "kernel_backend": self.kernel_backend,
            "rerank_applied": self.rerank_applied,
            "state_gate_applied": self.state_gate_applied,
            "shadow_diff": dict(self.shadow_diff),
            "warnings": list(self.warnings),
        }


class MemoryRanker:
    """检索编排。**无 IO、无锁、无全局状态**。"""

    def __init__(
        self,
        *,
        kernel: Optional[MemoryKernel] = None,
        vector_store: Optional[VectorStore] = None,
        clock: Optional[MemoryClock] = None,
        features: Optional[MemoryFeatures] = None,
        candidate_provider: Optional[CandidateProvider] = None,
    ) -> None:
        self.kernel = kernel or MemoryKernel()
        self.vector_store = vector_store
        self.clock = clock
        self.features = features or MemoryFeatures()
        self.candidate_provider = candidate_provider

    # ---------- 主流程 ----------

    def rank(
        self,
        plan: RetrievalPlan,
        *,
        query_vector: Optional[Sequence[float]] = None,
        candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], RetrievalReport]:
        """返回 `(候选清单, 报告)`。

        `candidates` 可直接注入（测试/上层已查好）；否则调
        `candidate_provider`。两条路径结果语义完全一致。
        """
        started = time.perf_counter()
        report = RetrievalReport(
            plan_top_k=plan.top_k,
            kernel_backend=self.kernel.backend,
        )
        layers = plan.layers or layers_for_query(explicit_recall=plan.explicit_recall)

        if candidates is None:
            if self.candidate_provider is None:
                report.warnings.append("未提供候选源，返回空清单")
                return [], self._finish(report, started)
            try:
                candidates = self.candidate_provider(plan.session_id, layers)
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"候选源失败: {type(exc).__name__}")
                return [], self._finish(report, started)
        candidates = [dict(c) for c in (candidates or [])]

        # ── 1) 多路召回（全部在 scope 内）──
        channels = self._channels(plan, candidates, query_vector)
        report.channels = {name: len(ranked) for name, ranked in channels.items()}

        # ── 2) RRF 融合（重计算走 Rust）──
        names = list(channels.keys())
        weights = [
            _scoring.DEFAULT_CHANNEL_WEIGHTS.get(name, 1.0) for name in names
        ]
        fused = self.kernel.rrf_fuse(
            [channels[name] for name in names], weights, _scoring.RRF_K
        )
        report.fused = len(fused)

        by_id = {str(c.get("id")): c for c in candidates}
        relevance = {doc_id: score for doc_id, score in fused}

        # ── 3) 强度（批量，走 Rust）──
        now_day = self.clock.now_day() if self.clock is not None else 0.0
        r_eff = self._retention(candidates, now_day, report)

        # ── 4) 排序 ──
        old_order = [doc_id for doc_id, _ in fused]
        new_order = self._strength_order(
            old_order, by_id, relevance, r_eff, now_day, report
        )
        order = new_order if self.features.rerank else old_order
        report.rerank_applied = self.features.rerank

        if self.features.shadow and not self.features.rerank:
            report.shadow_diff = self._diff(old_order, new_order)

        # ── 5) 门控 ──
        out: List[Dict[str, Any]] = []
        for doc_id in order:
            item = by_id.get(doc_id)
            if item is None:
                continue
            enriched = dict(item)
            enriched["score"] = float(relevance.get(doc_id, 0.0))
            enriched["r_eff"] = float(r_eff.get(doc_id, 1.0))
            state = _strength.state_of(enriched["r_eff"],
                                       pinned=bool(item.get("pinned", False)))
            enriched["state"] = state
            enriched["layer"] = policy_of(item.get("layer")).layer.value

            if self.features.state_transition:
                report.state_gate_applied = True
                if not _strength.injection_gate(
                    state,
                    enriched["score"],
                    explicit_recall=plan.explicit_recall,
                ):
                    report.gated_out += 1
                    continue
            out.append(enriched)
            if len(out) >= plan.top_k:
                break

        return out, self._finish(report, started)

    # ---------- 各路 ----------

    def _channels(
        self,
        plan: RetrievalPlan,
        candidates: List[Dict[str, Any]],
        query_vector: Optional[Sequence[float]],
    ) -> Dict[str, List[str]]:
        limit = max(1, plan.per_channel)
        ids = [str(c.get("id", "")) for c in candidates]

        # exact：精确词/ID/实体命中
        exact_hits = [
            str(c.get("id", "")) for c in candidates
            if self._exact_hit(plan.query, c)
        ]

        # lexical：TF 余弦（中文 bigram），批量走 Rust
        texts = [str(c.get("content", "") or "") for c in candidates]
        lex_scores = self.kernel.lexical_scores(plan.query, texts)
        lexical = [
            ids[i] for i in sorted(range(len(ids)), key=lambda i: lex_scores[i], reverse=True)
            if lex_scores[i] > 0
        ][:limit]

        # dense：向量库（已服务端 scope 过滤）→ 按分数排序
        dense: List[str] = []
        if self.vector_store is not None and query_vector is not None:
            try:
                hits = self.vector_store.search(
                    query_vector,
                    session_id=plan.session_id,
                    layers=plan.layers or layers_for_query(
                        explicit_recall=plan.explicit_recall
                    ),
                    top_k=limit,
                    fingerprint=str(plan.fingerprint or ""),
                )
                dense = [str(mid) for mid, _score in hits]
            except Exception as exc:  # noqa: BLE001
                # 单路失败要有可解释降级（B2-01），不能整体崩
                dense = []

        # recency：时间信号
        now = self.clock.now_seconds() if self.clock is not None else time.time()
        recency = [
            ids[i] for i in sorted(
                range(len(ids)),
                key=lambda i: float(candidates[i].get("created_at", 0.0) or 0.0),
                reverse=True,
            )
        ][:limit]

        # confidence / importance
        confidence = [
            ids[i] for i in sorted(
                range(len(ids)),
                key=lambda i: (
                    float(candidates[i].get("confidence", 0.0) or 0.0)
                    + float(candidates[i].get("importance", 0.0) or 0.0)
                ),
                reverse=True,
            )
        ][:limit]

        return {
            "exact": exact_hits[:limit],
            "lexical": lexical,
            "dense": dense[:limit],
            "recency": recency,
            "confidence": confidence,
        }

    @staticmethod
    def _exact_hit(query: str, candidate: Mapping[str, Any]) -> bool:
        q = str(query or "").strip()
        if not q:
            return False
        return q in str(candidate.get("content", "") or "") or \
            q == str(candidate.get("id", "") or "")

    # ---------- 强度 ----------

    def _retention(
        self,
        candidates: List[Dict[str, Any]],
        now_day: float,
        report: RetrievalReport,
    ) -> Dict[str, float]:
        ids, deltas, stability, pinned = [], [], [], []
        for c in candidates:
            ids.append(str(c.get("id", "")))
            record = c.get("strength")
            if isinstance(record, _strength.Strength):
                deltas.append(now_day - record.last_reinforced_day)
                stability.append(record.stability)
                pinned.append(record.pinned)
            else:
                last = float(c.get("last_reinforced_day", now_day) or now_day)
                policy = policy_of(c.get("layer"))
                s = float(c.get("stability", policy.base_s) or policy.base_s)
                deltas.append(max(0.0, now_day - last))
                stability.append(s)
                pinned.append(bool(c.get("pinned", False)))
        values = self.kernel.retention_batch(deltas, stability, pinned)
        if self.features.jitter:
            jitters = self.kernel.jitter_batch(ids, now_day)
            values = [
                min(1.0, max(0.0, v * (1.0 + j))) for v, j in zip(values, jitters)
            ]
        return dict(zip(ids, values))

    def _strength_order(
        self,
        old_order: List[str],
        by_id: Dict[str, Dict[str, Any]],
        relevance: Dict[str, float],
        r_eff: Dict[str, float],
        now_day: float,
        report: RetrievalReport,
    ) -> List[str]:
        """批量算 `final_score`（Rust）。"""
        ids = [i for i in old_order if i in by_id]
        rel = [float(relevance.get(i, 0.0)) for i in ids]
        r = [float(r_eff.get(i, 1.0)) for i in ids]
        floors = [policy_of(by_id[i].get("layer")).rank_floor for i in ids]
        scores = self.kernel.final_scores(rel, r, floors)
        return [i for _, i in sorted(
            zip(scores, ids), key=lambda pair: (-pair[0], pair[1])
        )]

    # ---------- 辅助 ----------

    @staticmethod
    def _diff(old_order: List[str], new_order: List[str]) -> Dict[str, Any]:
        old_pos = {doc_id: i for i, doc_id in enumerate(old_order)}
        moved = [
            doc_id for i, doc_id in enumerate(new_order)
            if old_pos.get(doc_id, i) != i
        ]
        return {
            "moved": len(moved),
            "sample": moved[:5],
            "top1_changed": bool(old_order and new_order
                                 and old_order[0] != new_order[0]),
        }

    @staticmethod
    def _finish(report: RetrievalReport, started: float) -> RetrievalReport:
        report.elapsed_ms = (time.perf_counter() - started) * 1000.0
        return report
