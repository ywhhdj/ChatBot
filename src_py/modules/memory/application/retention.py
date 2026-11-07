"""记忆保留/固定/唤醒服务

职责边界
────────
纯应用服务：**不 import FastAPI、不认 pydantic、不碰全局单例**。
控制器负责协议校验/映射，本层只接受普通参数并返回普通 dict。
这样网关 op 与 HTTP 路由共用同一份业务语义。

scope 先过滤
──────────────────────────────
每个动作都先核对 `memories.session_id == 请求的 session_id`。
不做"先更新再发现越界" —— 那已经改了别的会话的数据。
不符返回稳定 reason code，不泄漏"这个 id 到底存不存在于别的会话"
（避免用接口枚举他人记忆 id）。

revive 为什么这么算
──────────────────────────
"faded/archived 被成功使用，则 R 视为不低于 0.5 起算，
且强化增益乘 0.5"。由 `R(Δ,S)=1/(1+Δ/(9S)) >= 0.5`
解得 `S >= Δ/9`。所以唤醒时把稳定度抬到
`max(S, Δ/9, MIN_STABILITY)`，**但不重置时间轴**
（重置等于假装这段时间没过，会让所有记忆一夜返老还童）。
增益减半不在这里做 —— 它由下一次 `MemoryUsageEvent`
的 `awakened=True` 标记触发（见 `domain/strength.reinforce`）。
"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..domain import strength as _strength
from ..domain.layers import MemoryLayer, normalize_layer, policy_of
from ...logger import audit, logger

MIN_STABILITY = _strength.MIN_STABILITY
RETENTION_NINE = _strength.RETENTION_NINE


class RetentionReject(str, Enum):
    """稳定拒绝码。"""

    OK = "ok"
    BAD_ID = "bad_id"
    BAD_SCOPE = "bad_scope"
    NOT_FOUND = "not_found"
    BAD_LAYER = "bad_layer"
    BAD_VALUE = "bad_value"
    IO_ERROR = "io_error"
    NO_CHANGE = "no_change"


@dataclass
class ActionResult:
    """统一结果。字段与 `MemoryActionData` DTO 一一对应。"""

    memory_id: int = 0
    session_id: str = ""
    action: str = ""
    applied: bool = False
    code: str = RetentionReject.OK.value
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "session_id": self.session_id,
            "action": self.action,
            "applied": self.applied,
            "code": self.code,
            "before": dict(self.before),
            "after": dict(self.after),
            "warnings": list(self.warnings),
        }


class MemoryRetentionService:
    """三个动作的服务实现。连接由组合根注入，不取单例。"""

    def __init__(
        self,
        conn_factory: Callable[[], sqlite3.Connection],
        *,
        clock: Optional[Any] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._conn_factory = conn_factory
        self.clock = clock
        self._now = now or time.time

    # ─────────────────────────────────────────────────────────
    # 公共入口
    # ─────────────────────────────────────────────────────────

    def pin(
        self, memory_id: Any, session_id: str, *, pinned: bool = True,
        dry_run: bool = False, request_id: str = "",
    ) -> Dict[str, Any]:
        return self._mutate(
            "pin", memory_id, session_id, dry_run=dry_run,
            request_id=request_id,
            mutate=lambda conn, mid, before: self._apply_pin(
                conn, mid, bool(pinned), before
            ),
        )

    def revive(
        self, memory_id: Any, session_id: str, *, dry_run: bool = False,
        request_id: str = "",
    ) -> Dict[str, Any]:
        return self._mutate(
            "revive", memory_id, session_id, dry_run=dry_run,
            request_id=request_id,
            mutate=lambda conn, mid, before: self._apply_revive(
                conn, mid, before, float(self.clock.now_day())
                if self.clock is not None else 0.0
            ),
        )

    def set_retention(
        self,
        memory_id: Any,
        session_id: str,
        *,
        retention_days: float = 0.0,
        layer: str = "",
        dry_run: bool = True,
        request_id: str = "",
    ) -> Dict[str, Any]:
        try:
            days = float(retention_days)
        except (TypeError, ValueError):
            return ActionResult(
                action="retention", code=RetentionReject.BAD_VALUE.value,
                warnings=["retention_days 不可解析"],
            ).as_dict()
        if not math.isfinite(days) or days < 0:
            return ActionResult(
                action="retention", code=RetentionReject.BAD_VALUE.value,
                warnings=["retention_days 必须 >= 0"],
            ).as_dict()
        target_layer = ""
        if layer:
            try:
                target_layer = MemoryLayer(str(layer).strip().lower()).value
            except ValueError:
                return ActionResult(
                    action="retention", 
                    code=RetentionReject.BAD_LAYER.value,
                    warnings=[f"未知 layer: {layer}"],
                ).as_dict()
        return self._mutate(
            "retention", memory_id, session_id, dry_run=dry_run,
            request_id=request_id,
            mutate=lambda conn, mid, before: self._apply_retention(
                conn, mid, before, days, target_layer
            ),
        )

    # ─────────────────────────────────────────────────────────
    # 事务骨架
    # ─────────────────────────────────────────────────────────

    def _mutate(
        self,
        action: str,
        memory_id: Any,
        session_id: str,
        *,
        dry_run: bool,
        request_id: str,
        mutate: Callable[[sqlite3.Connection, int, Dict[str, Any]], Tuple[Dict[str, Any], List[str]]],
    ) -> Dict[str, Any]:
        try:
            mid = int(memory_id)
        except (TypeError, ValueError):
            return ActionResult(
                action=action, code=RetentionReject.BAD_ID.value,
                warnings=["memory_id 不可解析"],
            ).as_dict()
        if mid <= 0:
            return ActionResult(
                action=action, code=RetentionReject.BAD_ID.value,
                warnings=["memory_id 必须为正整数"],
            ).as_dict()
        sid = str(session_id or "default")

        conn = self._conn_factory()
        try:
            before = self._read_state(conn, mid, sid)
            if before.get("reject"):
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                return ActionResult(
                    memory_id=mid, session_id=sid, action=action,
                    code=before["reject"],
                    warnings=[before.get("message", "目标不可操作")],
                ).as_dict()
            after, warnings = mutate(conn, mid, before)
            if dry_run:
                # dry-run 只读：不 COMMIT，直接 ROLLBACK 掉可能有的临时写
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                warnings.append("dry-run，未写入")
                result = ActionResult(
                    memory_id=mid, session_id=sid, action=action,
                    applied=False, before=before, after=after,
                    warnings=warnings,
                )
            else:
                conn.execute("COMMIT")
                result = ActionResult(
                    memory_id=mid, session_id=sid, action=action,
                    applied=not any(w.startswith("no_change") for w in warnings),
                    before=before, after=after, warnings=warnings,
                )
            self._emit_audit(action, result, request_id)
            return result.as_dict()
        except Exception as exc:  # noqa: BLE001
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            logger.warning(f"[MemoryRetention] {action} 失败: {type(exc).__name__}")
            return ActionResult(
                memory_id=mid, session_id=sid, action=action,
                code=RetentionReject.IO_ERROR.value,
                warnings=[f"操作失败: {type(exc).__name__}"],
            ).as_dict()
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _read_state(
        self, conn: sqlite3.Connection, mid: int, sid: str
    ) -> Dict[str, Any]:
        """读当前状态 + **scope 校验**（先过滤，再操作）。"""
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, session_id, layer, importance, created_at "
                "FROM memories WHERE id = ?", (mid,)
            ).fetchone()
        except sqlite3.Error:
            return {"reject": RetentionReject.IO_ERROR.value,
                    "message": "记忆表不可读"}
        if row is None:
            return {"reject": RetentionReject.NOT_FOUND.value,
                    "message": "记忆不存在"}
        if str(row[1] or "default") != sid:
            # 不泄漏"这个 id 在别的会话里存在"
            return {"reject": RetentionReject.BAD_SCOPE.value,
                    "message": "目标不在该 session 范围内"}

        state: Dict[str, Any] = {
            "id": int(row[0]),
            "session_id": str(row[1]),
            "layer": str(row[2] or "episodic"),
            "importance": float(row[3] or 0.0),
            "created_at": float(row[4] or 0.0),
        }
        try:
            srow = conn.execute(
                "SELECT stability, last_reinforced_day, salience, lapse_count, "
                "state, pinned FROM memory_strength WHERE memory_id = ?",
                (mid,),
            ).fetchone()
        except sqlite3.Error:
            srow = None
        if srow is None:
            # 老库没有强度行：按层默认 S0 补一条（不臆造置信度）
            policy = policy_of(state["layer"])
            stability = _strength.initial_stability(
                policy.layer, state["importance"]
            )
            state.update({
                "stability": stability,
                "last_reinforced_day": state["created_at"] / 86400.0,
                "salience": 0.0, "lapse_count": 0,
                "state": "active", "pinned": 0,
            })
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO memory_strength("
                    "memory_id, stability, last_reinforced_day, importance, "
                    "salience, lapse_count, state, pinned) "
                    "VALUES(?,?,?,?,0,0,'active',0)",
                    (mid, stability, state["last_reinforced_day"],
                     state["importance"]),
                )
            except sqlite3.Error:
                pass
        else:
            state.update({
                "stability": float(srow[0] or 1.0),
                "last_reinforced_day": float(srow[1] or 0.0),
                "salience": float(srow[2] or 0.0),
                "lapse_count": int(srow[3] or 0),
                "state": str(srow[4] or "active"),
                "pinned": int(srow[5] or 0),
            })
        return state

    # ─────────────────────────────────────────────────────────
    # 三个动作
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _apply_pin(conn, mid, pinned: bool, before) -> Tuple[Dict[str, Any], List[str]]:
        warnings: List[str] = []
        target = 1 if pinned else 0
        if int(before.get("pinned", 0)) == target:
            warnings.append("no_change: 已是目标状态")
            return dict(before), warnings
        after = dict(before)
        after["pinned"] = target
        # pin 后 R 恒为 1（§6.1），state 必须回到 active
        if pinned:
            after["state"] = "active"
        conn.execute(
            "UPDATE memory_strength SET pinned = ?, state = ? WHERE memory_id = ?",
            (target, after["state"], mid),
        )
        return after, warnings

    @staticmethod
    def _apply_revive(conn, mid, before, now_day: float) -> Tuple[Dict[str, Any], List[str]]:
        """把 R 抬到 >= 0.5，不重置时间轴，不谎报成功。"""
        warnings: List[str] = []
        after = dict(before)
        s = float(before.get("stability", MIN_STABILITY))
        last = float(before.get("last_reinforced_day", 0.0))
        delta = max(0.0, now_day - last)
        # R >= 0.5  <=>  S >= Δ/9
        required = delta / RETENTION_NINE
        new_s = min(
            policy_of(before.get("layer")).s_max,
            max(s, required, MIN_STABILITY),
        )
        if int(before.get("pinned", 0)):
            warnings.append("no_change: 已固定，无需唤醒")
            return dict(before), warnings
        if new_s <= s + 1e-9 and str(before.get("state")) == "active":
            warnings.append("no_change: 已是 active 且稳定度满足 R>=0.5")
            return dict(before), warnings
        after["stability"] = new_s
        after["state"] = "active"
        warnings.append(
            "唤醒后的下一次强化须带 awakened=True，增益乘 0.5（§8.2）"
        )
        conn.execute(
            "UPDATE memory_strength SET stability = ?, state = 'active' "
            "WHERE memory_id = ?",
            (new_s, mid),
        )
        return after, warnings

    @staticmethod
    def _apply_retention(conn, mid, before, days: float,
                         layer: str) -> Tuple[Dict[str, Any], List[str]]:
        """只改策略字段，**不动强度时间轴**（§8.1 排序只改权重）。"""
        warnings: List[str] = []
        after = dict(before)
        after["retention_days"] = days
        if layer:
            after["layer"] = layer
        elif days <= 0:
            # 0 = 按层默认策略
            after["retention_days"] = float(
                policy_of(before.get("layer")).retention_days or 0.0
            )
            warnings.append("retention_days=0，已按层默认策略解释")
        # 策略存 metadata JSON，避免为可选字段再加列
        try:
            row = conn.execute(
                "SELECT metadata FROM memories WHERE id = ?", (mid,)
            ).fetchone()
            import json

            meta = {}
            if row and row[0]:
                try:
                    parsed = json.loads(str(row[0]))
                    if isinstance(parsed, dict):
                        meta = parsed
                except (ValueError, TypeError):
                    meta = {}
            old_days = float(meta.get("retention_days", -1.0) or -1.0)
            old_layer = str(before.get("layer", ""))
            if (abs(old_days - float(after["retention_days"])) < 1e-9
                    and old_layer == str(after["layer"])):
                warnings.append("no_change: 策略未变化")
                return after, warnings
            meta["retention_days"] = float(after["retention_days"])
            conn.execute(
                "UPDATE memories SET metadata = ?, layer = ? WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False, sort_keys=True),
                 str(after["layer"]), mid),
            )
        except Exception:  # noqa: BLE001
            warnings.append("策略元数据写入降级，仅更新了 layer")
        return after, warnings

    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _emit_audit(action: str, result: ActionResult, request_id: str) -> None:
        try:
            audit.record(
                audit.Action.MEMORY_RETENTION.value if action == "retention"
                else audit.Action.MEMORY_PIN.value if action == "pin"
                else audit.Action.MEMORY_REVIVE.value,
                request_id=str(request_id or ""),
                session_id=result.session_id,
                decision=audit.Decision.ALLOW.value,
                # dry-run / no_change 也是"按预期执行完毕"，
                # 没写入这件事由 metadata.applied 表达，不谎报 partial
                result=audit.Result.SUCCESS.value,
                reason_code=result.code,
                resource=audit.Resource(
                    type=audit.ResourceType.MEMORY.value,
                    id=str(result.memory_id),
                ),
                metadata={
                    "action": action,
                    "applied": result.applied,
                    "before_state": str(result.before.get("state", "")),
                    "after_state": str(result.after.get("state", "")),
                },
            )
        except Exception:  # noqa: BLE001
            pass
