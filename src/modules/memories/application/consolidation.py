"""固化（Consolidation）流水线 dry-run
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..domain import strength as _strength
from ..domain.layers import (
    PROMOTABLE_LAYERS,
    MemoryLayer,
    normalize_layer,
    policy_of,
)
from ..features import MemoryFeatures


@dataclass(frozen=True)
class ConsolidationConfig:
    max_items: int = 200
    max_actions: int = 50
    #: 提升为 semantic 所需的"不同日期被强化次数"（§9）
    promotion_min_days: int = 2
    promotion_min_reinforcements: int = 3
    #: 归档阈值 R < 0.2
    archive_threshold: float = 0.2
    #: GC 候选阈值（§7）
    gc_r_threshold: float = 0.05
    gc_min_age_days: float = 90.0
    gc_max_importance: float = 0.5
    #: 是否允许跨 scope 提升。默认 False（§9）
    allow_cross_scope_promotion: bool = False


@dataclass
class ConsolidationAction:
    kind: str
    memory_id: str = ""
    reason: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "memory_id": self.memory_id,
            "reason": self.reason,
            "payload": dict(self.payload),
        }


@dataclass
class ConsolidationReport:
    operation_id: str = ""
    scope: str = ""
    now_day: float = 0.0
    inspected: int = 0
    actions: List[ConsolidationAction] = field(default_factory=list)
    gc_candidates: List[str] = field(default_factory=list)
    estimated_release_bytes: int = 0
    warnings: List[str] = field(default_factory=list)
    applied: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "scope": self.scope,
            "now_day": self.now_day,
            "inspected": self.inspected,
            "actions": [a.as_dict() for a in self.actions],
            "gc_candidates": list(self.gc_candidates),
            "estimated_release_bytes": self.estimated_release_bytes,
            "warnings": list(self.warnings),
            "applied": self.applied,
        }


def _operation_id(scope: str, now_day: float, items: Sequence[Any]) -> str:
    """幂等 id：同 scope + 同时间基准 + 同输入集合 → 同 id。"""
    ids = "|".join(str(x.get("id", "")) for x in items[:32] if isinstance(x, Mapping))
    raw = f"{scope}|{now_day:.6f}|{len(items)}|{ids}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ConsolidationPlanner:
    """纯判定器。**无 IO**。"""

    def __init__(
        self,
        *,
        features: Optional[MemoryFeatures] = None,
        config: Optional[ConsolidationConfig] = None,
    ) -> None:
        self.features = features or MemoryFeatures()
        self.config = config or ConsolidationConfig()

    def plan(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        scope: str,
        now_day: float,
        summary_drafts: Optional[Mapping[str, str]] = None,
    ) -> ConsolidationReport:
        """生成 dry-run 报告。"""
        batch = [dict(x) for x in (items or [])[: self.config.max_items]]
        report = ConsolidationReport(
            operation_id=_operation_id(scope, now_day, batch),
            scope=str(scope),
            now_day=float(now_day),
            inspected=len(batch),
        )
        summary_drafts = dict(summary_drafts or {})

        by_id = {str(x.get("id", "")): x for x in batch}

        # ── 1) 归档：R < 0.2 的明细 ──
        for item in batch:
            r = self._r_of(item, now_day)
            if r < self.config.archive_threshold and not item.get("pinned", False):
                self._add(report, ConsolidationAction(
                    kind="archive",
                    memory_id=str(item.get("id", "")),
                    reason=f"R={r:.3f} < {self.config.archive_threshold}",
                ))

        # ── 2) 提升：≥2 个不同日期被强化 ≥3 次 ──
        for item in batch:
            layer = normalize_layer(item.get("layer"))
            if layer not in PROMOTABLE_LAYERS:
                continue
            days = self._distinct_reinforcement_days(item)
            count = int(item.get("reinforcement_count", 0) or 0)
            if (days >= self.config.promotion_min_days
                    and count >= self.config.promotion_min_reinforcements):
                item_scope = str(item.get("session_id", "") or scope)
                if (not self.config.allow_cross_scope_promotion
                        and item_scope != str(scope)):
                    report.warnings.append(
                        f"拒绝跨 scope 提升: {item.get('id', '')}"
                    )
                    continue
                self._add(report, ConsolidationAction(
                    kind="promote",
                    memory_id=str(item.get("id", "")),
                    reason=f"{days} 个不同日期、{count} 次强化",
                    payload={"from": layer.value, "to": MemoryLayer.SEMANTIC.value},
                ))

        # ── 3) 冲突：同 conflict_group 最新者 supersedes 旧者 ──
        groups: Dict[str, List[Mapping[str, Any]]] = {}
        for item in batch:
            key = str(item.get("conflict_group", "") or "")
            if key:
                groups.setdefault(key, []).append(item)
        for key, members in groups.items():
            if len(members) < 2:
                continue
            ordered = sorted(
                members,
                key=lambda x: float(x.get("created_at", 0.0) or 0.0),
                reverse=True,
            )
            newest = ordered[0]
            for older in ordered[1:]:
                self._add(report, ConsolidationAction(
                    kind="supersede",
                    memory_id=str(older.get("id", "")),
                    reason=f"冲突组 {key} 中有更新事实",
                    payload={"superseded_by": str(newest.get("id", ""))},
                ))

        # ── 4) 摘要聚合（草稿由上层生成，这里只校验来源与版本）──
        for draft_id, text in summary_drafts.items():
            derived = by_id.get(str(draft_id))
            if derived is None:
                report.warnings.append(f"摘要草稿 {draft_id} 无对应来源明细")
                continue
            self._add(report, ConsolidationAction(
                kind="publish_summary",
                memory_id=str(draft_id),
                reason="摘要草稿已附来源范围",
                payload={"derived_from": list(derived.get("source_ids", []) or [])},
            ))

        # ── 5) GC dry-run（只读，绝不删除）──
        for item in batch:
            r = self._r_of(item, now_day)
            state = _strength.state_of(r, pinned=bool(item.get("pinned", False)))
            if _strength.is_gc_candidate(
                state=state,
                r_eff=r,
                age_days=float(now_day) - float(item.get("created_day", now_day) or now_day),
                covered_by_summary=bool(item.get("covered_by_summary", False)),
                importance=float(item.get("importance", 0.0) or 0.0),
                layer=item.get("layer"),
                pinned=bool(item.get("pinned", False)),
            ):
                report.gc_candidates.append(str(item.get("id", "")))
                report.estimated_release_bytes += int(item.get("bytes", 0) or 0)

        return report

    # ---------- 应用（默认关闭）----------

    def apply(
        self,
        report: ConsolidationReport,
        writer: Any = None,
    ) -> ConsolidationReport:
        """把**非破坏性**建议写入。`writer` 由组合根注入。

        GC 永远不在这里执行：硬删除必须走墓碑协议 + 单独审批（M2-08）。
        """
        if not self.features.consolidation_apply:
            report.warnings.append("consolidation.apply 未开启，仅返回 dry-run")
            return report
        if writer is None or not callable(getattr(writer, "apply", None)):
            report.warnings.append("未提供 writer，未写入")
            return report
        safe = [a for a in report.actions if a.kind != "gc_delete"]
        try:
            writer.apply([a.as_dict() for a in safe])
            report.applied = True
        except Exception as exc:  # noqa: BLE001
            report.warnings.append(f"写入失败: {type(exc).__name__}")
        return report

    # ---------- 辅助 ----------

    @staticmethod
    def _r_of(item: Mapping[str, Any], now_day: float) -> float:
        record = item.get("strength")
        if isinstance(record, _strength.Strength):
            return _strength.retention_of(record, now_day)
        last = float(item.get("last_reinforced_day", now_day) or now_day)
        stability = float(item.get("stability", policy_of(item.get("layer")).base_s) or 1.0)
        return _strength.retention(
            max(0.0, float(now_day) - last), stability,
            pinned=bool(item.get("pinned", False)),
        )

    @staticmethod
    def _distinct_reinforcement_days(item: Mapping[str, Any]) -> int:
        raw = item.get("reinforcement_days")
        if isinstance(raw, (list, tuple, set)):
            return len({int(float(x)) for x in raw})
        return 0

    def _add(self, report: ConsolidationReport, action: ConsolidationAction) -> None:
        if len(report.actions) < int(self.config.max_actions):
            report.actions.append(action)
