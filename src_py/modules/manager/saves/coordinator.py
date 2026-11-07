"""存档域组合根（L1-01 / S2-01 / S2-05）。

把契约、领域实现、事务协调器、自动存档策略**装配**起来。
这是唯一允许出现"知道所有具体类型"的地方；其余模块只认端口。

为什么单独一个组合根
────────────────────
`MemoryOriginator` 在 `memory/`，`RestoreCoordinator` 在
`manager/saves/`，`SaveSlotManager` 也在 `manager/saves/`。
若让它们互相 import 并各自取单例，会出现：
* 谁先构造谁不确定（时钟锚点、墓碑快照的时机漂移）；
* 测试无法整体替换成内存库；
* 恢复事务与自动存档各拿一个 gate，暂停语义失效。

组合根显式注入，所有依赖方向单一，测试可整体替换。
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional

from ...logger import audit, logger
from ...utils.file.atomic import atomic_write_json
from ...memory import originator as _memory_originator
from . import memento
from .autosave import AutoSavePolicy, RetentionConfig
from .originators import SnapshotTrigger
from .restore import RestoreCoordinator, SchedulerGate


class SaveCoordinator:
    """对外只有 `restore / snapshot / preview / graph / status` 五个动作。"""

    def __init__(
        self,
        *,
        save_manager: Any,
        root: str,
        conn_factory: Callable[[], sqlite3.Connection],
        config: Optional[RetentionConfig] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self.save_manager = save_manager
        self.root = str(root)
        self._conn_factory = conn_factory
        self._now = now or time.time
        self.gate = SchedulerGate()

        # ── 记忆域 originator ──
        self.memory_originator = _memory_originator.MemoryOriginator(
            conn_factory,
            profile_provider=self._read_profile,
            tombstone_provider=self._read_tombstones,
            now_seconds=self._now,
        )

        # ── 事务协调器 ──
        self.restore_coordinator = RestoreCoordinator(
            self.root,
            originators=[self.memory_originator],
            gate=self.gate,
            create_snapshot=self._create_snapshot,
            set_current=self._set_current,
            read_sections=None,          # 用协调器内建的文件层读取
            audit=self._audit,
            memory_probe=self._memory_probe,
        )

        # ── 自动存档（S2-03）──
        self.autosave = AutoSavePolicy(
            create_snapshot=self._create_snapshot,
            list_revisions=lambda sid: self.save_manager.list_snapshots(sid),
            root=self.root,
            gate=self.gate,
            config=config or RetentionConfig(),
            now=self._now,
            delete_revision=None,        # 默认只 dry-run，不提供删除能力
        )

    # ─────────────────────────────────────────────────────────
    # 对外动作
    # ─────────────────────────────────────────────────────────

    def restore(
        self,
        slot_id: str,
        revision: str = "",
        *,
        branch_id: str = "main",
        label: str = "",
    ) -> Dict[str, Any]:
        report = self.restore_coordinator.restore(
            slot_id, revision, branch_id=branch_id, label=label
        )
        # S2-05：事务结束后恢复调度，并让 pre-restore 缓冲期开始计时
        self.autosave.note_restore_finished(report.ok)
        return report.as_dict()

    def snapshot(
        self,
        slot_id: str = "",
        *,
        trigger: str = SnapshotTrigger.MANUAL.value,
        label: str = "",
        branch_id: str = "main",
    ) -> Dict[str, Any]:
        """创建快照。parent 默认取**最近成功恢复的 revision**（§5 DAG）。"""
        sid = slot_id or getattr(self.save_manager, "_current_slot_id", "") or ""
        active = self.restore_coordinator.active_revision.get(sid, "")
        return self._create_snapshot(
            sid, trigger=trigger, label=label,
            branch_id=branch_id or "main",
            parent_revision=active,
        )

    def preview(self, slot_id: str = "", revision: str = "") -> Dict[str, Any]:
        return self.save_manager.preview_restore(
            slot_id, revision, memory_probe=self._memory_probe
        )

    def graph(self, slot_id: str = "") -> Dict[str, Any]:
        return self.save_manager.revision_graph(slot_id)

    def tick(self) -> Dict[str, Any]:
        """空闲定时器调用：消费自动存档队列。"""
        return self.autosave.tick()

    def enqueue_autosave(self, slot_id: str, **kwargs: Any) -> bool:
        return self.autosave.enqueue(slot_id, **kwargs)

    def prune_candidates(self, slot_id: str = "") -> Dict[str, Any]:
        sid = slot_id or getattr(self.save_manager, "_current_slot_id", "") or ""
        return self.autosave.prune_candidates(sid)

    def status(self) -> Dict[str, Any]:
        return {
            "restore": self.restore_coordinator.status(),
            "autosave": self.autosave.stats(),
            "gate": self.gate.stats(),
            "memory_originator": self.memory_originator.owner,
            "root_configured": bool(self.root),
        }

    # ─────────────────────────────────────────────────────────
    # 注入给事务协调器的适配函数
    # ─────────────────────────────────────────────────────────

    def _create_snapshot(
        self,
        slot_id: str,
        *,
        trigger: str = SnapshotTrigger.MANUAL.value,
        label: str = "",
        branch_id: str = "main",
        parent_revision: str = "",
        **_: Any,
    ) -> Dict[str, Any]:
        """包一层：`SaveSlotManager.create_snapshot` 的返回已是稳定 dict。"""
        try:
            result = self.save_manager.create_snapshot(
                slot_id,
                branch_id=branch_id or "main",
                label=label,
                trigger=trigger,
                parent_revision=parent_revision,
            )
        except TypeError:
            # 兼容旧签名（未升级的 SaveSlotManager）
            result = self.save_manager.create_snapshot(slot_id)
        if isinstance(result, dict) and result.get("ok"):
            self._audit("snapshot.publish", {
                "slot_id": str(slot_id),
                "revision": str(result.get("revision", "")),
                "trigger": str(trigger),
                "branch_id": str(branch_id),
            })
        return result if isinstance(result, dict) else {"ok": False, "code": "bad_result"}

    def _set_current(self, slot_id: str, revision: str) -> bool:
        """原子更新 current 指针。

        只在 **Commit 成功之后**调用；格式与 `memento.publish_revision`
        完全一致，否则 `read_current()` 的校验结论会随写入方变化。
        """
        if not revision:
            return False
        try:
            atomic_write_json(
                memento.current_pointer_path(self.root, slot_id),
                {
                    "revision": str(revision),
                    "slot_id": str(slot_id),
                    "updated_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "consistency_level": "",
                },
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[SaveCoordinator] 指针更新失败: {type(exc).__name__}")
            return False

    def _memory_probe(self, manifest: Any) -> Dict[str, Any]:
        """Preview 用的**只读**运行态探针（S2-04）。

        提供文件层拿不到的三件事：快照之后新增的条数、
        当前生效的墓碑数、当前时钟。绝不写库。
        """
        watermark = 0.0
        try:
            entry = manifest.section_map.get("memory-strength")
            if entry is not None:
                from ...utils.file.atomic import read_json, safe_join

                rev_dir = memento.revision_dir(
                    self.root, str(manifest.slot_id), str(manifest.revision)
                )
                raw = read_json(
                    safe_join(rev_dir, "sections", "memory-strength.json")
                )
                if isinstance(raw, dict):
                    watermark = float(raw.get("watermark", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass

        conn = self._conn_factory()
        created_after = 0
        tombstones = 0
        clock: Dict[str, Any] = {}
        try:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE id > ?", (watermark,)
                ).fetchone()
                created_after = int(row[0] or 0) if row else 0
            except sqlite3.Error:
                pass
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memory_tombstones"
                ).fetchone()
                tombstones = int(row[0] or 0) if row else 0
            except sqlite3.Error:
                pass
            try:
                row = conn.execute(
                    "SELECT kind, anchor_day, active_seconds, game_day "
                    "FROM memory_clock_state WHERE id = 1"
                ).fetchone()
                if row:
                    clock = {
                        "kind": str(row[0]),
                        "anchor_day": float(row[1] or 0.0),
                        "active_days": float(row[2] or 0.0) / 86400.0,
                        "game_day": float(row[3] or 0.0),
                    }
            except sqlite3.Error:
                pass
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        return {
            "will_discard_created_after": created_after,
            "tombstones_to_replay": tombstones,
            "clock": clock,
        }

    def _read_tombstones(self) -> List[Dict[str, Any]]:
        conn = self._conn_factory()
        try:
            try:
                rows = conn.execute(
                    "SELECT memory_id, session_id, digest, deleted_at, reason "
                    "FROM memory_tombstones"
                ).fetchall()
            except sqlite3.Error:
                return []
            keys = ("memory_id", "session_id", "digest", "deleted_at", "reason")
            return [dict(zip(keys, row)) for row in rows]
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _read_profile(self):
        """角色遗忘画像。当前从记忆配置读；缺配置用默认值。"""
        try:
            from ...memory.config import load_memory_config

            raw = load_memory_config().features or {}
            return _memory_originator.ForgettingProfile(
                jitter=bool(raw.get("jitter", False)),
                channel_weights={
                    str(k): float(v)
                    for k, v in (raw.get("channel_weights") or {}).items()
                },
            )
        except Exception:  # noqa: BLE001
            return _memory_originator.DEFAULT_PROFILE

    @staticmethod
    def _audit(action: str, data: Dict[str, Any]) -> None:
        """结构化审计。动作名收敛到稳定低基数（§5），阶段放 metadata。"""
        try:
            normalized = (
                audit.Action.SNAPSHOT_PUBLISH.value
                if action == "snapshot.publish" else
                audit.Action.SNAPSHOT_RESTORE.value
            )
            audit.record(
                normalized,
                decision=audit.Decision.ALLOW.value,
                result=audit.Result.SUCCESS.value,
                metadata={
                    "slot_id": str(data.get("slot_id", "")),
                    "revision": str(data.get("revision", "")),
                    "trigger": str(data.get("trigger", "")),
                    "branch_id": str(data.get("branch_id", "")),
                    "operation_id": str(data.get("operation_id", "")),
                    "state": str(data.get("state", "")),
                    "code": str(data.get("code", "")),
                    "phase": str(action),
                },
                resource=audit.Resource(
                    type=audit.ResourceType.SAVE.value,
                    id=str(data.get("slot_id", "")),
                ),
            )
        except Exception:  # noqa: BLE001
            pass


_coordinator: Optional[SaveCoordinator] = None


def get_save_coordinator(**kwargs: Any) -> SaveCoordinator:
    """组合根单例。**必须显式传依赖**，不暗中取全局单例。"""
    global _coordinator
    if _coordinator is None:
        if "save_manager" not in kwargs or "conn_factory" not in kwargs:
            raise ValueError(
                "首次构造需提供 save_manager / conn_factory / root"
            )
        _coordinator = SaveCoordinator(**kwargs)
    return _coordinator


def reset_save_coordinator() -> None:
    """仅供测试。"""
    global _coordinator
    _coordinator = None
