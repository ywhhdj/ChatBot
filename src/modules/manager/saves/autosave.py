"""自动存档与滚动保留（S2-03 / `MementoMemoryIntegration.md` §6 / §8）。

| trigger | 触发 | 保留策略 |
|---|---|---|
| `manual` | 用户点击保存 | 长期，除非用户删除 |
| `quick` | 快捷键 | 单槽覆盖式，但仍写新 revision，保留最近 1–3 个 |
| `auto` | 固定间隔 / 关键事件（固化完成、章节切换） | 滚动保留最近 N（初值 5），不占用户槽位 |
| `pre-restore` | 恢复前保护快照 | 保留到恢复验证成功后 + 缓冲期 |
| `pre-migration` | 迁移之前 | 验证通过后保留一个版本周期 |

硬性边界
────────
* **受磁盘预算约束**：估算 revision 目录体积，超预算直接拒绝新
  自动存档并告警，绝不把用户磁盘写满；
* **有界队列**：同一 slot 的连续事件合并（coalesce），队列满时
  丢最旧的 auto 事件；manual / pre-restore 是强事件，不丢；
* **恢复事务进行中暂停**：由 `SchedulerGate` 判定，事务结束后才恢复；
* **GC 先 dry-run**：本模块只产候选清单，不执行删除。真正删除需要
  单独审批（与 `memory.gc.apply` 一样的纪律）。

为什么"只列不删"
────────────────
`GameSaveArchitecture.md` §8 要求 GC 先 dry-run 输出将删除的
revision、估算字节与引用计数。自动流程若顺手把旧 revision 删了，
一旦用户刚想回档就发现恢复点没了 —— 这是不可撤销的损失。
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ...logger import logger
from . import memento
from .originators import SnapshotTrigger
from .restore import SchedulerGate

DEFAULT_AUTO_KEEP = 5
DEFAULT_QUICK_KEEP = 3
DEFAULT_QUEUE_CAPACITY = 64
#: 默认磁盘预算（字节）。auto revision 总体积超过就停止新建。
DEFAULT_DISK_BUDGET = 512 * 1024 * 1024
#: pre-restore 保护快照在恢复成功后的额外缓冲期（秒）
GUARD_BUFFER_SECONDS = 3600.0

#: 永不自动回收的 trigger
PROTECTED_TRIGGERS = frozenset({
    SnapshotTrigger.MANUAL.value,
    SnapshotTrigger.PRE_RESTORE.value,
    SnapshotTrigger.PRE_MIGRATION.value,
})


@dataclass(frozen=True)
class AutoSaveEvent:
    slot_id: str
    trigger: str = SnapshotTrigger.AUTO.value
    label: str = ""
    branch_id: str = "main"
    #: 触发时的水位（由调用方给，进 manifest 便于排查）
    watermark: float = 0.0
    ts: float = 0.0

    @property
    def strong(self) -> bool:
        """强事件：队列满时也不能丢。"""
        return self.trigger in PROTECTED_TRIGGERS


@dataclass
class AutoSaveStats:
    enqueued: int = 0
    coalesced: int = 0
    dropped: int = 0
    created: int = 0
    rejected_budget: int = 0
    rejected_paused: int = 0
    last_run_ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enqueued": self.enqueued,
            "coalesced": self.coalesced,
            "dropped": self.dropped,
            "created": self.created,
            "rejected_budget": self.rejected_budget,
            "rejected_paused": self.rejected_paused,
            "last_run_ts": self.last_run_ts,
        }


@dataclass(frozen=True)
class RetentionConfig:
    auto_keep: int = DEFAULT_AUTO_KEEP
    quick_keep: int = DEFAULT_QUICK_KEEP
    disk_budget: int = DEFAULT_DISK_BUDGET
    queue_capacity: int = DEFAULT_QUEUE_CAPACITY
    guard_buffer_seconds: float = GUARD_BUFFER_SECONDS
    #: 是否允许 `prune()` 真的删除（默认 False，只 dry-run）
    allow_delete: bool = False


def _dir_size(path: str) -> int:
    """估算目录体积。失败返回 0（少算比崩掉好，预算是保守上限）。"""
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
    except OSError:
        pass
    return total


class AutoSavePolicy:
    """有界队列 + 磁盘预算 + 滚动保留候选。

    不自己起线程：`tick()` 由组合根在空闲定时器里调用。
    这样恢复事务暂停语义是**确定性的**，不存在"定时器恰好在 commit
    中途触发"的竞态 —— 这正是把调度权交给组合根的原因。
    """

    def __init__(
        self,
        *,
        create_snapshot: Callable[..., Dict[str, Any]],
        list_revisions: Callable[[str], List[Dict[str, Any]]],
        root: str = "",
        gate: Optional[SchedulerGate] = None,
        config: Optional[RetentionConfig] = None,
        now: Optional[Callable[[], float]] = None,
        delete_revision: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self._create = create_snapshot
        self._list = list_revisions
        self.root = str(root)
        self.gate = gate
        self.config = config or RetentionConfig()
        self._now = now or time.time
        self._delete = delete_revision
        self._queue: deque = deque()
        self._lock = threading.RLock()
        self._stats = AutoSaveStats()
        self._last_event_ts: Dict[str, float] = {}
        #: 恢复成功时刻，用于 pre-restore 缓冲期
        self._last_restore_ok_ts: float = 0.0

    # ---------- 入队 ----------

    def enqueue(
        self,
        slot_id: str,
        *,
        trigger: str = SnapshotTrigger.AUTO.value,
        label: str = "",
        branch_id: str = "main",
        watermark: float = 0.0,
        min_interval: float = 0.0,
    ) -> bool:
        """提交一次自动存档请求。**不阻塞、不做 IO**。

        `min_interval` 内同 slot 同 trigger 的请求合并（coalesce），
        避免"固化完成"这类事件连发时刷出一串几乎一样的 revision。
        """
        sid = str(slot_id or "")
        if not sid:
            return False
        now = float(self._now())
        event = AutoSaveEvent(
            slot_id=sid, trigger=str(trigger or SnapshotTrigger.AUTO.value),
            label=str(label or ""), branch_id=str(branch_id or "main"),
            watermark=float(watermark), ts=now,
        )
        with self._lock:
            key = f"{sid}|{event.trigger}"
            if min_interval > 0 and now - self._last_event_ts.get(key, 0.0) < min_interval:
                # 合并进已有的同 key 事件：更新水位与标签，不新增
                for existing in self._queue:
                    if (existing.slot_id == sid
                            and existing.trigger == event.trigger):
                        self._queue.remove(existing)
                        self._queue.append(AutoSaveEvent(
                            slot_id=sid, trigger=event.trigger,
                            label=event.label or existing.label,
                            branch_id=event.branch_id,
                            watermark=max(existing.watermark, event.watermark),
                            ts=now,
                        ))
                        break
                self._stats.coalesced += 1
                self._last_event_ts[key] = now
                return True

            self._last_event_ts[key] = now
            if len(self._queue) >= self.config.queue_capacity:
                # 丢最旧的弱事件（auto/quick）；强事件绝不丢
                for index, old in enumerate(self._queue):
                    if not old.strong:
                        del self._queue[index]
                        self._stats.dropped += 1
                        break
                else:
                    self._stats.dropped += 1
                    return False
            self._queue.append(event)
            self._stats.enqueued += 1
        return True

    def note_restore_finished(self, ok: bool) -> None:
        """协调器在事务结束时通知，用于 pre-restore 缓冲期。"""
        if ok:
            with self._lock:
                self._last_restore_ok_ts = float(self._now())

    # ---------- 消费 ----------

    def tick(self, *, max_batch: int = 8) -> Dict[str, Any]:
        """由空闲定时器调用。返回本轮结果报告。"""
        if self.gate is not None and self.gate.paused:
            with self._lock:
                self._stats.rejected_paused += max(0, len(self._queue))
            return {"ok": True, "paused": True, "created": 0, "pending": self.pending()}

        with self._lock:
            batch = [self._queue.popleft()
                     for _ in range(min(int(max_batch), len(self._queue)))]

        created = 0
        failures: List[Dict[str, str]] = []
        for event in batch:
            ok, reason = self._check_budget(event.slot_id)
            if not ok:
                with self._lock:
                    self._stats.rejected_budget += 1
                failures.append({"slot_id": event.slot_id, "reason": reason})
                continue
            try:
                result = self._create(
                    event.slot_id,
                    trigger=event.trigger,
                    label=event.label or f"auto {int(event.ts)}",
                    branch_id=event.branch_id,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append({"slot_id": event.slot_id,
                                 "reason": type(exc).__name__})
                continue
            if isinstance(result, dict) and result.get("ok"):
                created += 1
            else:
                failures.append({
                    "slot_id": event.slot_id,
                    "reason": str((result or {}).get("code", "create_failed")),
                })
            self._put_back_on_failure(event, result, failures)

        with self._lock:
            self._stats.created += created
            self._stats.last_run_ts = float(self._now())
        return {
            "ok": True,
            "paused": False,
            "created": created,
            "failures": failures,
            "pending": self.pending(),
        }

    def _check_budget(self, slot_id: str) -> Tuple[bool, str]:
        if self.config.disk_budget <= 0:
            return True, ""
        used = 0
        try:
            for item in self._list(slot_id) or []:
                rev = str(item.get("revision", "") or "")
                if not rev:
                    continue
                try:
                    path = memento.revision_dir(self.root, slot_id, rev)
                except ValueError:
                    continue
                used += _dir_size(path)
        except Exception:  # noqa: BLE001
            # 预算探测失败不能阻断存档，但要记告警
            logger.warning("[AutoSave] 磁盘预算探测失败，本轮跳过预算检查")
            return True, ""
        if used >= int(self.config.disk_budget):
            return False, f"auto revisions 已用 {used} 字节，达到预算 {self.config.disk_budget}"
        return True, ""

    @staticmethod
    def _put_back_on_failure(event, result, failures) -> None:
        """创建失败时把弱事件记进报告即可，不无限重塞队列。

        自动存档是"尽力而为"；失败重试交给下一次外部触发，
        无限重放会让一次持续故障变成每 tick 一次写盘风暴。
        """
        if isinstance(result, dict) and not result.get("ok") and failures:
            failures[-1]["code"] = str(result.get("code", ""))

    # ---------- 滚动保留（dry-run 优先） ----------

    def prune_candidates(self, slot_id: str) -> Dict[str, Any]:
        """GC dry-run：**只列候选，不删除**（GameSaveArchitecture §8）。"""
        try:
            items = list(self._list(slot_id) or [])
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": type(exc).__name__, "candidates": []}

        current, _, _ = memento.read_current(self.root, slot_id) \
            if self.root else (None, None, "")
        current_rev = current.revision if current else ""
        now = float(self._now())
        guard_valid = (
            self._last_restore_ok_ts <= 0
            or now - self._last_restore_ok_ts < self.config.guard_buffer_seconds
        )

        by_trigger: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            trigger = str(item.get("trigger", "manual") or "manual")
            by_trigger.setdefault(trigger, []).append(item)

        candidates: List[Dict[str, Any]] = []
        reasons: Dict[str, str] = {}
        for trigger, group in by_trigger.items():
            keep = (self.config.auto_keep if trigger == SnapshotTrigger.AUTO.value
                    else self.config.quick_keep if trigger == SnapshotTrigger.QUICK.value
                    else None)
            if keep is None:
                continue
            ordered = sorted(
                group, key=lambda x: str(x.get("revision", "")), reverse=True
            )
            for item in ordered[keep:]:
                rev = str(item.get("revision", "") or "")
                if not rev or rev == current_rev:
                    continue
                # 有后代的 revision 不是叶子：删掉会让 DAG 出现断链
                if self.root and memento.descendants(self.root, slot_id, rev):
                    reasons[rev] = "有后代 revision，需保留以维持 DAG"
                    continue
                try:
                    path = memento.revision_dir(self.root, slot_id, rev) \
                        if self.root else ""
                    size = _dir_size(path) if path else 0
                except ValueError:
                    size = 0
                candidates.append({
                    "revision": rev,
                    "trigger": trigger,
                    "bytes": size,
                    "created_at": item.get("created_at", ""),
                })
        candidates.sort(key=lambda x: x["revision"])
        return {
            "ok": True,
            "slot_id": str(slot_id),
            "candidates": candidates,
            "estimated_release_bytes": sum(x["bytes"] for x in candidates),
            "protected": current_rev,
            "skipped": reasons,
            "applied": False,
        }

    def prune(self, slot_id: str, *, approved: bool = False) -> Dict[str, Any]:
        """执行清理。**默认不动手**：需 `allow_delete=True` + 显式 approved。"""
        report = self.prune_candidates(slot_id)
        if not approved or not self.config.allow_delete:
            report["reason"] = "未审批或 allow_delete=False，仅返回 dry-run"
            return report
        if self._delete is None:
            report["reason"] = "未提供 delete_revision，未删除"
            return report
        removed = []
        for item in report["candidates"]:
            try:
                if self._delete(str(slot_id), item["revision"]):
                    removed.append(item["revision"])
            except Exception:  # noqa: BLE001
                continue
        report["applied"] = True
        report["removed"] = removed
        return report

    # ---------- 诊断 ----------

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            out = self._stats.as_dict()
            out["pending"] = len(self._queue)
            out["capacity"] = self.config.queue_capacity
            out["disk_budget"] = self.config.disk_budget
            out["auto_keep"] = self.config.auto_keep
        return out
