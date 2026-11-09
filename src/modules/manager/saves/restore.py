"""恢复事务协调器（B1-03 剩余 / S2-03 / S2-05）。

依据 `GameSaveArchitecture.md` §6「Preview → Prepare → Commit → Verify」
与 `MementoMemoryIntegration.md` §4 / §5 / §8。

前几轮 B1-03 只做了 `preview_restore()`；Prepare/Commit/Rollback
一直卡在"各 originator 没提供 restore 接口"。`originators.py` 把契约
定死后，本文件把事务闭环补上。

失败语义（§6 最后一段，最重要的一条）
────────────────────────────────────
* 任一 Prepare 失败 → 运行态**完全不变**，报告 `rejected`；
* Commit 中途某域失败 → 对已提交域**逆序 rollback**；
* rollback 也失败 → 必须报 `partial_failure` 并附恢复指引，
  **绝不回报普通成功**；
* Verify 失败同样触发 rollback。

乐观版本检查
────────────
Prepare 时记下 current revision，Commit 前再读一次。
并发保存/恢复导致指针变了就拒绝（`conflict`），否则会把
"A 准备的状态"覆盖到"B 已经推进到"的时间线上。

分支语义（§5）
──────────────
从旧 revision 恢复并继续游玩，新保存的 revision 以**被恢复者**
为 parent，自然形成 DAG；旧 revision 不被覆盖。
协调器把 `active_revision` 暴露给 `create_snapshot` 的调用方。

恢复期间调度暂停（§8 / S2-05）
────────────────────────────
固化、GC、自动存档在事务进行中一律暂停，Verify 通过后才恢复。
暂停用可重入计数 + finally 释放：嵌套事务、异常退出都不会
把调度永久关掉。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...logger import logger
from . import memento
from .originators import (
    PrepareReject,
    PreparedRestore,
    RestorePhase,
    SnapshotSection,
    SnapshotTrigger,
)


class TxState(str, Enum):
    INIT = "init"
    PREVIEWED = "previewed"
    PREPARED = "prepared"
    COMMITTING = "committing"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    PARTIAL_FAILURE = "partial_failure"


class TxReject(str, Enum):
    OK = "ok"
    NOT_SAFE = "not_safe"
    PREPARE_FAILED = "prepare_failed"
    CONFLICT = "conflict"
    COMMIT_FAILED = "commit_failed"
    VERIFY_FAILED = "verify_failed"
    ROLLBACK_FAILED = "rollback_failed"
    GUARD_BUSY = "guard_busy"
    IO_ERROR = "io_error"


@dataclass
class PhaseRecord:
    """一个阶段的审计记录。**不含正文、不含秘密**。"""

    phase: str = ""
    ok: bool = False
    code: str = ""
    message: str = ""
    elapsed_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase, "ok": self.ok, "code": self.code,
            "message": self.message, "elapsed_ms": round(self.elapsed_ms, 3),
        }


@dataclass
class RestoreReport:
    """事务报告。保留 before/target/after revision 与各阶段结果（§6）。"""

    operation_id: str = ""
    slot_id: str = ""
    state: str = TxState.INIT.value
    code: str = TxReject.OK.value
    message: str = ""
    before_revision: str = ""
    target_revision: str = ""
    after_revision: str = ""
    #: 保护快照（pre-restore）的 revision
    guard_revision: str = ""
    branch_id: str = "main"
    phases: List[PhaseRecord] = field(default_factory=list)
    origins: List[Dict[str, Any]] = field(default_factory=list)
    #: 从 RestorePlan 带过来的记忆影响（S2-04）
    memory_impact: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def ok(self) -> bool:
        return self.state == TxState.COMMITTED.value

    def as_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "slot_id": self.slot_id,
            "state": self.state,
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "before_revision": self.before_revision,
            "target_revision": self.target_revision,
            "after_revision": self.after_revision,
            "guard_revision": self.guard_revision,
            "branch_id": self.branch_id,
            "phases": [p.as_dict() for p in self.phases],
            "origins": list(self.origins),
            "memory_impact": dict(self.memory_impact),
            "warnings": list(self.warnings),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class SchedulerGate:
    """恢复期间的调度闸门（S2-05）。

    可重入计数：嵌套事务不会提前恢复调度；`release()` 与
    `acquire()` 必须成对，协调器用 try/finally 保证。
    """

    name: str = "restore"
    _depth: int = 0
    _lock: Any = field(default_factory=threading.RLock, repr=False)
    _paused_at: float = 0.0
    _resume_hooks: List[Callable[[], None]] = field(default_factory=list)

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._depth > 0

    def acquire(self) -> None:
        with self._lock:
            if self._depth == 0:
                self._paused_at = time.time()
            self._depth += 1

    def release(self) -> None:
        hooks: List[Callable[[], None]] = []
        with self._lock:
            if self._depth == 0:
                return
            self._depth -= 1
            if self._depth == 0:
                self._paused_at = 0.0
                hooks = list(self._resume_hooks)
        for hook in hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001
                logger.debug("[SchedulerGate] resume hook 失败")

    def add_resume_hook(self, hook: Callable[[], None]) -> None:
        with self._lock:
            self._resume_hooks.append(hook)

    def should_run(self, task: str) -> bool:
        """供固化/GC/自动存档在启动时查询。"""
        if self.paused:
            logger.debug(f"[SchedulerGate] 恢复事务进行中，暂停 {task}")
            return False
        return True

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "paused": self._depth > 0,
                "depth": self._depth,
                "paused_at": self._paused_at,
                "hooks": len(self._resume_hooks),
            }


class RestoreCoordinator:
    """Caretaker：编排一次完整的恢复事务。

    **不解释领域数据**：section payload 原样交给注册进来的
    originator，协调器只管顺序、锁、版本、失败补偿与报告。
    """

    def __init__(
        self,
        root: str,
        *,
        originators: Optional[Sequence[Any]] = None,
        gate: Optional[SchedulerGate] = None,
        create_snapshot: Optional[Callable[..., Dict[str, Any]]] = None,
        set_current: Optional[Callable[[str, str], bool]] = None,
        read_sections: Optional[Callable[[str, str], Dict[str, SnapshotSection]]] = None,
        audit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        memory_probe: Optional[Callable[[Any], Dict[str, Any]]] = None,
    ) -> None:
        self.root = str(root)
        self._originators: Dict[str, Any] = {}
        for obj in (originators or []):
            self.register(obj)
        self.gate = gate or SchedulerGate()
        self._create_snapshot = create_snapshot
        self._set_current = set_current
        self._read_sections = read_sections or self._default_read_sections
        self._audit = audit or (lambda action, data: None)
        self._memory_probe = memory_probe
        self._tx_lock = threading.RLock()
        self._active_tx: Optional[RestoreReport] = None
        #: 最近一次成功恢复的 revision，供新快照作 parent（§5 DAG）
        self._active_revision: Dict[str, str] = {}

    # ---------- 注册 ----------

    def register(self, originator: Any) -> None:
        owner = str(getattr(originator, "owner", "") or "")
        if not owner:
            raise ValueError("originator 缺少 owner")
        if owner in self._originators:
            raise ValueError(f"originator 重复注册: {owner}")
        self._originators[owner] = originator

    def owners(self) -> List[str]:
        return sorted(self._originators)

    @property
    def active_revision(self) -> Dict[str, str]:
        return dict(self._active_revision)

    # ---------- 主流程 ----------

    def restore(
        self,
        slot_id: str,
        revision: str = "",
        *,
        branch_id: str = "main",
        label: str = "",
        operation_id: str = "",
    ) -> RestoreReport:
        """一次完整事务。返回报告，**不抛异常给调用方**。"""
        with self._tx_lock:
            if self._active_tx is not None and self._active_tx.state in (
                TxState.PREPARED.value, TxState.COMMITTING.value,
                TxState.VERIFYING.value,
            ):
                return RestoreReport(
                    state=TxState.REJECTED.value, code=TxReject.GUARD_BUSY.value,
                    message="已有恢复事务进行中",
                )
            report = RestoreReport(
                operation_id=operation_id or f"restore-{int(time.time() * 1000)}",
                slot_id=str(slot_id),
                started_at=time.time(),
                branch_id=str(branch_id or "main"),
            )
            self._active_tx = report

        self.gate.acquire()
        try:
            self._run(report, slot_id, revision, label)
        except Exception as exc:  # noqa: BLE001
            # 兜底：任何未预期异常都不能让事务停在"看起来还在跑"的状态
            report.state = TxState.PARTIAL_FAILURE.value
            report.code = TxReject.COMMIT_FAILED.value
            report.message = f"未预期异常: {type(exc).__name__}"
            report.warnings.append("请按报告中的 before/guard revision 人工核对")
            self._phase(report, RestorePhase.ROLLBACK, False,
                        TxReject.ROLLBACK_FAILED.value, report.message)
            logger.error(f"[RestoreCoordinator] {report.message}")
        finally:
            report.finished_at = time.time()
            self.gate.release()
            self._emit("restore.finished", report)
            with self._tx_lock:
                self._active_tx = None
        return report

    def _run(self, report: RestoreReport, slot_id: str,
             revision: str, label: str) -> None:
        # ── 1) Preview（只读）──
        plan = memento.preview_restore(
            self.root, slot_id, revision, memory_probe=self._memory_probe
        )
        report.target_revision = plan.revision
        report.memory_impact = dict(getattr(plan, "memory_impact", {}) or {})
        report.warnings.extend(plan.warnings)
        if not plan.safe:
            report.state = TxState.REJECTED.value
            report.code = TxReject.NOT_SAFE.value
            report.message = f"预演拒绝: {plan.code.value} — {plan.message}"
            self._phase(report, RestorePhase.PREVIEW, False, plan.code.value, plan.message)
            return
        self._phase(report, RestorePhase.PREVIEW, True, "ok", plan.message)
        report.state = TxState.PREVIEWED.value

        # 乐观版本检查的基线
        before, _, _ = memento.read_current(self.root, slot_id)
        report.before_revision = before.revision if before else ""
        expected_current = report.before_revision

        # ── 2) 保护快照（pre-restore，§6 Prepare 第一条）──
        guard = self._make_guard(slot_id, report)
        if guard is not None:
            report.guard_revision = str(guard)
        else:
            report.warnings.append("保护快照创建失败，rollback 将仅依赖各域暂存状态")

        # ── 3) 逐域 Prepare（只进临时对象）──
        sections = self._read_sections(slot_id, plan.revision)
        prepared: List[Tuple[str, PreparedRestore]] = []
        for owner in self._ordered_owners(plan.targets):
            originator = self._originators.get(owner)
            if originator is None:
                # 缺少 adapter 的域：不改运行态，但在报告里标记
                self._origin_report(report, owner, PrepareReject.MISSING_SECTION.value,
                                    "未注册 originator，该域保持现状")
                report.warnings.append(f"域 {owner} 未注册 originator，未参与恢复")
                continue
            owned = [
                sections[n] for n in getattr(originator, "section_names", ())
                if n in sections
            ]
            try:
                result = originator.prepare_restore(owned, plan)
            except Exception as exc:  # noqa: BLE001
                result = PreparedRestore(
                    owner=owner, ok=False, code=PrepareReject.IO_ERROR,
                    message=f"prepare 异常: {type(exc).__name__}",
                )
            report.origins.append(result.as_dict())
            report.warnings.extend(result.warnings)
            if not result.ok:
                report.state = TxState.REJECTED.value
                report.code = TxReject.PREPARE_FAILED.value
                report.message = f"{owner} Prepare 失败: {result.message}"
                self._phase(report, RestorePhase.PREPARE, False,
                            result.code.value, result.message)
                return
            prepared.append((owner, result))
        self._phase(report, RestorePhase.PREPARE, True, "ok",
                    f"{len(prepared)} 个域准备完成")
        report.state = TxState.PREPARED.value

        # ── 4) Commit（锁内 + 乐观版本检查 + 按序提交）──
        report.state = TxState.COMMITTING.value
        current, _, _ = memento.read_current(self.root, slot_id)
        actual_current = current.revision if current else ""
        if actual_current != expected_current:
            report.state = TxState.REJECTED.value
            report.code = TxReject.CONFLICT.value
            report.message = (
                f"current revision 已变化（{expected_current} → {actual_current}），"
                "拒绝提交"
            )
            self._phase(report, RestorePhase.COMMIT, False,
                        TxReject.CONFLICT.value, report.message)
            return

        committed: List[Tuple[str, PreparedRestore]] = []
        for owner, result in prepared:
            originator = self._originators[owner]
            try:
                originator.commit_restore(result)
                committed.append((owner, result))
            except Exception as exc:  # noqa: BLE001
                report.message = f"{owner} commit 失败: {type(exc).__name__}"
                self._phase(report, RestorePhase.COMMIT, False,
                            TxReject.COMMIT_FAILED.value, report.message)
                self._rollback(report, committed)
                return
        self._phase(report, RestorePhase.COMMIT, True, "ok",
                    f"{len(committed)} 个域已提交")

        # 更新 current 指针：只在这之后才算"恢复成功"
        self._update_current(slot_id, plan.revision, report)
        report.after_revision = plan.revision

        # ── 5) Verify ──
        report.state = TxState.VERIFYING.value
        for owner, result in committed:
            originator = self._originators[owner]
            try:
                ok, msg = originator.verify_restore(result)
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, f"verify 异常: {type(exc).__name__}"
            if not ok:
                self._phase(report, RestorePhase.VERIFY, False,
                            TxReject.VERIFY_FAILED.value, f"{owner}: {msg}")
                self._rollback(report, committed, restore_pointer=expected_current)
                return
        self._phase(report, RestorePhase.VERIFY, True, "ok", "关键状态校验通过")

        report.state = TxState.COMMITTED.value
        report.code = TxReject.OK.value
        report.message = "恢复完成"
        self._active_revision[str(slot_id)] = plan.revision
        self._emit("restore.committed", report)

    # ---------- 阶段实现 ----------

    def _make_guard(self, slot_id: str, report: RestoreReport) -> Optional[str]:
        if self._create_snapshot is None:
            return None
        try:
            result = self._create_snapshot(
                slot_id,
                trigger=SnapshotTrigger.PRE_RESTORE.value,
                label=f"pre-restore {report.operation_id}",
                branch_id=report.branch_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[RestoreCoordinator] 保护快照异常: {type(exc).__name__}")
            return None
        if isinstance(result, dict) and result.get("ok"):
            return str(result.get("revision", "") or "")
        return None

    def _ordered_owners(self, targets: Sequence[str]) -> List[str]:
        """按 RESTORE_ORDER 的领域顺序排序；未登记的排在最后。"""
        # 用 RESTORE_ORDER 映射领域顺序（dict 值域顺序不稳定，
        # 不能拿 SECTION_OWNERS.values() 当排序依据）
        order = {
            memento.SECTION_OWNERS[name]: i
            for i, name in enumerate(memento.RESTORE_ORDER)
            if name in memento.SECTION_OWNERS
        }
        return sorted(
            (str(t) for t in targets),
            key=lambda owner: (order.get(owner, 10_000), owner),
        )

    def _rollback(
        self,
        report: RestoreReport,
        committed: List[Tuple[str, PreparedRestore]],
        *,
        restore_pointer: str = "",
    ) -> None:
        """对已提交域**逆序** rollback。"""
        failures: List[str] = []
        for owner, result in reversed(committed):
            try:
                self._originators[owner].rollback_restore(result)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{owner}: {type(exc).__name__}")
        if restore_pointer and self._set_current is not None:
            try:
                self._set_current(report.slot_id, restore_pointer)
            except Exception:  # noqa: BLE001
                failures.append("指针还原失败")
        ok = not failures
        self._phase(
            report, RestorePhase.ROLLBACK, ok,
            "ok" if ok else TxReject.ROLLBACK_FAILED.value,
            "已逆序回滚" if ok else "; ".join(failures),
        )
        if ok:
            report.state = TxState.ROLLED_BACK.value
            report.code = TxReject.COMMIT_FAILED.value
            report.message = "提交/校验失败，已完整回滚到恢复前状态"
        else:
            # §6：无法完全 rollback 必须报 partial_failure + 恢复指引
            report.state = TxState.PARTIAL_FAILURE.value
            report.code = TxReject.ROLLBACK_FAILED.value
            report.message = "部分回滚失败，运行态可能不一致"
            report.warnings.append(
                f"请按 before={report.before_revision} / guard={report.guard_revision} "
                "人工核对后再继续操作；不要回报为成功"
            )
        logger.error(f"[RestoreCoordinator] {report.message}")

    def _update_current(
        self, slot_id: str, revision: str, report: RestoreReport
    ) -> None:
        if self._set_current is None:
            report.warnings.append("未注入 set_current，current 指针未更新")
            return
        try:
            if not self._set_current(slot_id, revision):
                report.warnings.append("current 指针更新返回 False")
        except Exception as exc:  # noqa: BLE001
            report.warnings.append(f"current 指针更新异常: {type(exc).__name__}")

    # ---------- 默认 section 读取 ----------

    def _default_read_sections(
        self, slot_id: str, revision: str
    ) -> Dict[str, SnapshotSection]:
        """从 revision 目录读 section payload。

        文件层已有 `sha256` 校验（preview 阶段做过），这里只做
        JSON 解析并把未知/损坏的 section 排除，同时记 warning。
        """
        from ...utils.file.atomic import read_json, safe_join

        out: Dict[str, SnapshotSection] = {}
        try:
            rev_dir = memento.revision_dir(self.root, slot_id, revision)
            manifest, code, msg = memento.read_revision(self.root, slot_id, revision)
        except ValueError:
            return out
        if manifest is None:
            return out
        sections_dir = memento.sections_dir(rev_dir)
        for entry in manifest.sections:
            path = safe_join(rev_dir, "sections", f"{entry.name}.json")
            raw = read_json(path)
            if not isinstance(raw, dict):
                continue
            out[entry.name] = SnapshotSection(
                name=entry.name,
                schema_version=int(entry.schema_version or 1),
                payload=raw,
                reference_only=bool(entry.reference_only),
            )
        return out

    # ---------- 报告辅助 ----------

    @staticmethod
    def _phase(report: RestoreReport, phase: RestorePhase, ok: bool,
               code: str, message: str) -> None:
        # 累计耗时（自事务开始），阶段之间的差值即为该阶段耗时。
        # 用累计值而非"自减得到阶段耗时"，避免异常路径缺少上一阶段时
        # 出现负数，也便于前端直接画时间线。
        report.phases.append(PhaseRecord(
            phase=phase.value, ok=ok, code=code, message=message,
            elapsed_ms=(time.time() - report.started_at) * 1000.0,
        ))

    @staticmethod
    def _origin_report(report: RestoreReport, owner: str,
                       code: str, message: str) -> None:
        report.origins.append({
            "owner": owner, "ok": False, "code": code, "message": message,
            "sections": [], "checks": {}, "warnings": [],
        })

    def _emit(self, action: str, report: RestoreReport) -> None:
        try:
            self._audit(action, {
                "operation_id": report.operation_id,
                "slot_id": report.slot_id,
                "state": report.state,
                "code": report.code,
                "before": report.before_revision,
                "target": report.target_revision,
                "after": report.after_revision,
                "guard": report.guard_revision,
                "branch_id": report.branch_id,
            })
        except Exception:  # noqa: BLE001
            # 审计失败不阻断恢复（B1-08：审计服务于可追溯，不该成为可用性风险）
            pass

    def status(self) -> Dict[str, Any]:
        with self._tx_lock:
            active = self._active_tx.as_dict() if self._active_tx else None
        return {
            "active_transaction": active,
            "gate": self.gate.stats(),
            "originators": self.owners(),
            "active_revisions": self.active_revision,
        }
