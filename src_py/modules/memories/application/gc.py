"""记忆 GC apply（M2-08 / B2-05 / `MementoMemoryIntegration.md` §8）。

**永久默认关闭**。`features.gc_apply=True` 且 `approved=True` 才会真正删除，
两者缺一就只返回 dry-run 报告。硬删除是唯一不可撤销的操作，
把它做成"需要两把钥匙"是纪律，不是保守。

删除必须走墓碑协议（B1-05 / ADR-005/010）
────────────────────────────────────────
只删当前行挡不住旧快照恢复 —— 恢复一个删除前的 revision，
那行记忆原样回来。所以 apply 的顺序是：

1. 读正文算 `content_digest`；
2. 写 `memory_tombstones`（**不存正文**，只存 id + 摘要 + 时间 + 原因）；
3. 删记忆行 / 强度行 / 向量 / 压缩引用 / 缓存键；
4. 单事务提交。

顺序反了就拿不到摘要，墓碑退化为弱匹配，可能误删 id 被复用的新记忆。

受保护 revision 依赖检查（§8）
────────────────────────────
待删记忆若被任何**受保护 revision** 引用，默认拒绝。
但用户的删除请求高于备份便利（SecurityAndAuditDesign §8）：
`override_privacy=True` 时允许删，同时必须返回 `artifacts_to_purge`
清单，由调用方按备份策略清理 artifact 或销毁数据密钥。
报告和审计都不记录正文。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..domain import strength as T
from ..domain.layers import MemoryLayer, policy_of
from ..features import MemoryFeatures
from ..integrity import content_digest
from ...logger import audit, logger


@dataclass(frozen=True)
class GCCandidate:
    memory_id: int
    session_id: str
    layer: str
    r_eff: float
    importance: float
    age_days: float
    bytes: int = 0
    covered_by_summary: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "session_id": self.session_id,
            "layer": self.layer,
            "r_eff": round(self.r_eff, 6),
            "importance": round(self.importance, 4),
            "age_days": round(self.age_days, 2),
            "bytes": self.bytes,
            "covered_by_summary": self.covered_by_summary,
        }


@dataclass
class GCReport:
    operation_id: str = ""
    scope: str = ""
    now_day: float = 0.0
    inspected: int = 0
    candidates: List[GCCandidate] = field(default_factory=list)
    blocked_by_revision: List[int] = field(default_factory=list)
    estimated_release_bytes: int = 0
    applied: bool = False
    deleted: List[int] = field(default_factory=list)
    tombstones_written: int = 0
    artifacts_to_purge: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "scope": self.scope,
            "now_day": self.now_day,
            "inspected": self.inspected,
            "candidates": [c.as_dict() for c in self.candidates],
            "blocked_by_revision": list(self.blocked_by_revision),
            "estimated_release_bytes": self.estimated_release_bytes,
            "applied": self.applied,
            "deleted": list(self.deleted),
            "tombstones_written": self.tombstones_written,
            "artifacts_to_purge": list(self.artifacts_to_purge),
            "warnings": list(self.warnings),
        }


class MemoryGCService:
    """GC dry-run / apply。连接由组合根注入。"""

    def __init__(
        self,
        conn_factory: Callable[[], sqlite3.Connection],
        *,
        features: Optional[MemoryFeatures] = None,
        vector_remove: Optional[Callable[[Sequence[int], str], None]] = None,
        protected_revisions: Optional[Callable[[], Sequence[str]]] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._conn_factory = conn_factory
        self.features = features or MemoryFeatures()
        self._vector_remove = vector_remove
        self._protected_revisions = protected_revisions or (lambda: [])
        self._now = now or time.time

    # ─────────────────────────────────────────────────────────
    # dry-run
    # ─────────────────────────────────────────────────────────

    def dry_run(
        self,
        rows: Sequence[Dict[str, Any]],
        *,
        scope: str,
        now_day: float,
        protected_memory_ids: Iterable[int] = (),
    ) -> GCReport:
        """只读候选清单。**六条件缺一不可**（§7）。"""
        blocked = set(int(x) for x in protected_memory_ids)
        report = GCReport(
            operation_id=f"gc-{int(self._now() * 1000)}",
            scope=str(scope), now_day=float(now_day),
            inspected=len(rows),
        )
        protected_revs = [str(x) for x in (self._protected_revisions() or [])]
        if protected_revs:
            report.warnings.append(
                f"{len(protected_revs)} 个受保护 revision 存在；"
                "apply 前需确认待删记忆未被其引用"
            )

        for row in rows:
            try:
                mid = int(row.get("id", row.get("memory_id", 0)))
            except (TypeError, ValueError):
                continue
            if mid in blocked:
                report.blocked_by_revision.append(mid)
                continue
            layer = row.get("layer", MemoryLayer.EPISODIC)
            policy = policy_of(layer)
            last = float(row.get("last_reinforced_day", now_day) or now_day)
            stability = float(row.get("stability", policy.base_s) or policy.base_s)
            r_eff = T.retention(
                max(0.0, float(now_day) - last), stability,
                pinned=bool(row.get("pinned", False)),
            )
            state = T.state_of(r_eff, pinned=bool(row.get("pinned", False)))
            age_days = float(now_day) - float(
                row.get("created_day", now_day) or now_day
            )
            importance = float(row.get("importance", 0.0) or 0.0)
            if not T.is_gc_candidate(
                state=state, r_eff=r_eff, age_days=age_days,
                covered_by_summary=bool(row.get("covered_by_summary", False)),
                importance=importance, layer=layer,
                pinned=bool(row.get("pinned", False)),
            ):
                continue
            report.candidates.append(GCCandidate(
                memory_id=mid,
                session_id=str(row.get("session_id", scope) or scope),
                layer=policy.layer.value,
                r_eff=r_eff, importance=importance, age_days=age_days,
                bytes=int(row.get("bytes", 0) or 0),
                covered_by_summary=bool(row.get("covered_by_summary", False)),
            ))
        report.estimated_release_bytes = sum(c.bytes for c in report.candidates)
        return report

    # ─────────────────────────────────────────────────────────
    # apply
    # ─────────────────────────────────────────────────────────

    def apply(
        self,
        report: GCReport,
        *,
        approved: bool = False,
        override_privacy: bool = False,
        request_id: str = "",
    ) -> GCReport:
        """执行硬删除。**两把钥匙**：features.gc_apply + approved。"""
        if not approved or not self.features.gc_apply:
            report.warnings.append(
                "gc.apply 未开启或未审批，仅返回 dry-run（永久默认关闭）"
            )
            return report
        if not report.candidates:
            report.warnings.append("无候选，未执行")
            return report

        protected_revs = [str(x) for x in (self._protected_revisions() or [])]
        if protected_revs and not override_privacy:
            report.warnings.append(
                "存在受保护 revision，需显式 override_privacy=True "
                "（用户删除请求高于备份便利）"
            )
            return report

        conn = self._conn_factory()
        deleted: List[int] = []
        tombstones = 0
        try:
            conn.execute("BEGIN IMMEDIATE")
            for candidate in report.candidates:
                mid = candidate.memory_id
                row = conn.execute(
                    "SELECT content, session_id FROM memories WHERE id = ?",
                    (mid,),
                ).fetchone()
                if row is None:
                    continue
                # ① 先读正文算摘要，② 再写墓碑 —— 顺序不能反
                digest = content_digest(str(row[0]))
                conn.execute(
                    "INSERT OR IGNORE INTO memory_tombstones("
                    "memory_id, session_id, digest, deleted_at, reason) "
                    "VALUES(?,?,?,?,?)",
                    (mid, str(row[1] or candidate.session_id), digest,
                     float(self._now()), "gc"),
                )
                tombstones += 1
                conn.execute("DELETE FROM memory_strength WHERE memory_id = ?", (mid,))
                conn.execute("DELETE FROM memories WHERE id = ?", (mid,))
                deleted.append(mid)
            conn.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            report.warnings.append(f"apply 失败已回滚: {type(exc).__name__}")
            logger.warning(f"[MemoryGC] apply 失败: {type(exc).__name__}")
            return report
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

        # ③ 向量删除在事务外：外部系统不能参与 SQLite 事务，
        # 失败时墓碑仍在（下次检索会被 filter_resurrected 挡住），
        # 不会出现"行没了但向量还在召回"的静默不一致。
        if self._vector_remove is not None and deleted:
            try:
                self._vector_remove(deleted, report.scope)
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(
                    f"向量删除失败（墓碑已生效，需后台重建）: {type(exc).__name__}"
                )

        report.applied = True
        report.deleted = deleted
        report.tombstones_written = tombstones
        if protected_revs and override_privacy:
            report.artifacts_to_purge = list(protected_revs)
            report.warnings.append(
                "需按备份策略清理上述 revision 的 artifact 或销毁数据密钥"
            )
        self._emit_audit(report, request_id)
        return report

    @staticmethod
    def _emit_audit(report: GCReport, request_id: str) -> None:
        try:
            audit.record(
                audit.Action.MEMORY_GC_APPLY.value,
                request_id=str(request_id or ""),
                session_id=report.scope,
                decision=audit.Decision.ALLOW.value,
                result=audit.Result.SUCCESS.value,
                resource=audit.Resource(
                    type=audit.ResourceType.MEMORY.value,
                    count=len(report.deleted),
                ),
                metadata={
                    "operation_id": report.operation_id,
                    "deleted": len(report.deleted),
                    "tombstones": report.tombstones_written,
                },
            )
        except Exception:  # noqa: BLE001
            pass
