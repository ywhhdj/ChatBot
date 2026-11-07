"""记忆域 Originator

为什么需要它
────────────
引入强度后，存档多了两类必须一致的状态：
`memory_strength`（稳定度与最后强化时间）与 `memory_clock_state`
（"现在过了多少有效天"）。只恢复记忆文本而不恢复这两者，
角色要么"一夜之间忘光"（用现实时间算衰减），要么"记得过分清楚"
（强度被重置）—— 两者都破坏存档的可预期性。

三个 section
────────────
| section | 内容 | 说明 |
|---|---|---|
| `memory-strength` | 强度表行，**不含记忆正文** | 体积小，全量写入 |
| `memory-clock` | 时钟锚点/活跃天/游戏天 | 恢复后以此为时间起点 |
| `forgetting-profile` | 角色遗忘画像参数与版本 | 避免恢复后用不同参数重算 |

**不导出向量索引本体**：SQLite 是权威，Milvus collection 可重建。
只导出 checksum / embedding 版本 / 元数据水位
（放在已有的 `memory-manifest` section，由存档层负责）。

墓碑优先
──────────────────────────
快照之后用户删除的记忆，恢复后**不得复活**。
所以 commit 的最后一步是重放墓碑：用 `integrity.filter_resurrected`
按 `id + 内容摘要` 比对，而不是只按 id（快照恢复重建表后，
新行完全可能拿到和已删记忆相同的 id，按 id 一查就误删新记忆）。

依赖方向
────────
本文件实现 `manager/saves/originators.py` 的契约（结构化匹配）。
`saves` 侧不 import 本文件，因此没有环；组合根负责注册。
"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..logger import logger
from ..manager.saves.originators import (
    PrepareReject,
    PreparedRestore,
    SnapshotContext,
    SnapshotSection,
)

SECTION_STRENGTH = "memory-strength"
SECTION_CLOCK = "memory-clock"
SECTION_PROFILE = "forgetting-profile"

SECTION_NAMES: Tuple[str, ...] = (
    SECTION_STRENGTH, SECTION_CLOCK, SECTION_PROFILE,
)

#: 各 section 的 schema 版本。字段语义变更时 +1，
#: 未知版本在 Prepare 阶段**安全拒绝**，不做"尽力解析"。
STRENGTH_SCHEMA = 1
CLOCK_SCHEMA = 1
PROFILE_SCHEMA = 1

#: 强度 section 的行数上限（§8 防耗尽）
MAX_STRENGTH_ROWS = 200_000


@dataclass(frozen=True)
class ForgettingProfile:
    """角色遗忘画像（MemoryCurveAndForgetting §12）。

    这里只放**会影响排序结果**的参数；常量（BASE_S 等）在领域层
    `domain/layers.py` 与 Rust 内核里，不属于角色画像、不进快照。
    """

    version: int = 1
    #: 是否启用确定性抖动（§6.5）
    jitter: bool = False
    #: faded 门控阈值（§8.2，初值 0.75）
    faded_relevance_threshold: float = 0.75
    #: archived 显式回忆阈值
    archived_relevance_threshold: float = 0.9
    #: 角色级权重覆盖（为空则用领域默认）
    channel_weights: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "version": int(self.version),
            "jitter": bool(self.jitter),
            "faded_relevance_threshold": float(self.faded_relevance_threshold),
            "archived_relevance_threshold": float(self.archived_relevance_threshold),
            "channel_weights": dict(self.channel_weights),
        }

    @staticmethod
    def from_dict(raw: Any) -> Tuple[Optional["ForgettingProfile"], str]:
        if not isinstance(raw, dict):
            return None, "profile 不是对象"
        try:
            version = int(raw.get("version", 1))
        except (TypeError, ValueError):
            return None, "profile.version 不可解析"
        if version > PROFILE_SCHEMA:
            return None, f"profile schema {version} 高于当前 {PROFILE_SCHEMA}"
        try:
            return ForgettingProfile(
                version=version,
                jitter=bool(raw.get("jitter", False)),
                faded_relevance_threshold=float(
                    raw.get("faded_relevance_threshold", 0.75)
                ),
                archived_relevance_threshold=float(
                    raw.get("archived_relevance_threshold", 0.9)
                ),
                channel_weights={
                    str(k): float(v)
                    for k, v in (raw.get("channel_weights") or {}).items()
                },
            ), ""
        except (TypeError, ValueError) as exc:
            return None, f"profile 字段非法: {type(exc).__name__}"


DEFAULT_PROFILE = ForgettingProfile()


@dataclass
class _PreparedState:
    """prepare 阶段的临时对象。**不写运行态**。"""

    strength_rows: List[Dict[str, Any]] = field(default_factory=list)
    clock_state: Dict[str, Any] = field(default_factory=dict)
    profile: ForgettingProfile = DEFAULT_PROFILE
    #: 恢复前的保护状态，供 rollback 独立还原
    before_strength: List[Dict[str, Any]] = field(default_factory=list)
    before_clock: Dict[str, Any] = field(default_factory=dict)
    before_profile: ForgettingProfile = DEFAULT_PROFILE
    #: 当前生效的墓碑（commit 后重放）
    tombstones: List[Dict[str, Any]] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)


class MemoryOriginator:
    """`Originator` 协议的记忆域实现。

    通过注入的 `conn_factory` 拿连接，**不持有全局单例**：
    测试可塞内存库，恢复事务可显式控制事务边界。
    """

    owner = "memory_system"

    def __init__(
        self,
        conn_factory: Callable[[], sqlite3.Connection],
        *,
        profile_provider: Optional[Callable[[], ForgettingProfile]] = None,
        tombstone_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        now_seconds: Optional[Callable[[], float]] = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._profile_provider = profile_provider or (lambda: DEFAULT_PROFILE)
        self._tombstone_provider = tombstone_provider or (lambda: [])
        self._now = now_seconds or time.time
        self._last_committed: Optional[PreparedRestore] = None

    @property
    def section_names(self) -> Tuple[str, ...]:
        return SECTION_NAMES

    # ─────────────────────────────────────────────────────────
    # export
    # ─────────────────────────────────────────────────────────

    def export_snapshot(self, ctx: SnapshotContext) -> List[SnapshotSection]:
        """事务读快照。**不选私有变量、不导出正文**。

        SQLite 用 `BEGIN` 拿一致性读视图；绝不"WAL 活跃时直接拷贝主
        DB 文件"（GameSaveArchitecture §7）。
        """
        warnings: List[str] = []
        conn = self._conn_factory()
        strength_rows: List[Dict[str, Any]] = []
        clock_state: Dict[str, Any] = {}
        watermark = 0.0
        try:
            try:
                conn.execute("BEGIN")
            except sqlite3.Error:
                pass
            strength_rows = self._read_strength(conn)
            clock_state = self._read_clock(conn)
            watermark = self._watermark(conn)
            try:
                conn.execute("ROLLBACK")   # 只读，回滚不丢任何东西
            except sqlite3.Error:
                pass
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            warnings.append(f"强度/时钟读取降级: {type(exc).__name__}")
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

        if len(strength_rows) >= MAX_STRENGTH_ROWS:
            warnings.append("强度表接近体积上限，快照可能不完整")

        profile = self._safe_profile(warnings)
        return [
            SnapshotSection(
                name=SECTION_STRENGTH,
                schema_version=STRENGTH_SCHEMA,
                payload={
                    "schema_version": STRENGTH_SCHEMA,
                    "rows": strength_rows,
                    "row_count": len(strength_rows),
                    "watermark": watermark,
                },
                watermark=watermark,
                warnings=tuple(warnings),
            ),
            SnapshotSection(
                name=SECTION_CLOCK,
                schema_version=CLOCK_SCHEMA,
                payload={
                    "schema_version": CLOCK_SCHEMA,
                    "clock": clock_state,
                    "captured_at": float(ctx.captured_at or self._now()),
                },
                warnings=tuple(warnings),
            ),
            SnapshotSection(
                name=SECTION_PROFILE,
                schema_version=PROFILE_SCHEMA,
                payload={
                    "schema_version": PROFILE_SCHEMA,
                    "profile": profile.as_dict(),
                },
            ),
        ]

    def _safe_profile(self, warnings: List[str]) -> ForgettingProfile:
        try:
            return self._profile_provider() or DEFAULT_PROFILE
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"画像读取失败，用默认值: {type(exc).__name__}")
            return DEFAULT_PROFILE

    @staticmethod
    def _read_strength(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        try:
            rows = conn.execute(
                "SELECT memory_id, stability, last_reinforced_day, importance, "
                "salience, lapse_count, state, pinned FROM memory_strength "
                "ORDER BY memory_id ASC"
            ).fetchall()
        except sqlite3.Error:
            return []   # v1 老库没有该表：缺 section 由 RestorePlan 提示回填
        keys = ("memory_id", "stability", "last_reinforced_day", "importance",
                "salience", "lapse_count", "state", "pinned")
        return [dict(zip(keys, row)) for row in rows]

    @staticmethod
    def _read_clock(conn: sqlite3.Connection) -> Dict[str, Any]:
        try:
            row = conn.execute(
                "SELECT kind, anchor_epoch, anchor_day, active_seconds, game_day "
                "FROM memory_clock_state WHERE id = 1"
            ).fetchone()
        except sqlite3.Error:
            return {"kind": "wall", "anchor_epoch": 0.0, "anchor_day": 0.0,
                    "active_seconds": 0.0, "game_day": 0.0}
        if row is None:
            return {"kind": "wall", "anchor_epoch": 0.0, "anchor_day": 0.0,
                    "active_seconds": 0.0, "game_day": 0.0}
        keys = ("kind", "anchor_epoch", "anchor_day", "active_seconds", "game_day")
        return dict(zip(keys, row))

    @staticmethod
    def _watermark(conn: sqlite3.Connection) -> float:
        try:
            row = conn.execute("SELECT MAX(id) FROM memories").fetchone()
            return float(row[0] or 0) if row else 0.0
        except sqlite3.Error:
            return 0.0

    # ─────────────────────────────────────────────────────────
    # prepare
    # ─────────────────────────────────────────────────────────

    def prepare_restore(self, sections, plan) -> PreparedRestore:
        """把三张表装进**临时对象**，跑完所有业务不变量检查。

        任意一项失败都返回 `ok=False`，**运行态完全不变**（§6）。
        """
        by_name = {s.name: s for s in (sections or [])}
        missing = [n for n in SECTION_NAMES if n not in by_name]
        state = _PreparedState()
        warnings: List[str] = []
        for section in sections or []:
            warnings.extend(section.warnings)

        # ── 1) schema 版本：未知或过高一律拒绝 ──
        for name, expected in (
            (SECTION_STRENGTH, STRENGTH_SCHEMA),
            (SECTION_CLOCK, CLOCK_SCHEMA),
            (SECTION_PROFILE, PROFILE_SCHEMA),
        ):
            section = by_name.get(name)
            if section is None:
                continue
            got = int(section.schema_version or 1)
            if got > expected:
                return self._reject(
                    PrepareReject.UNSUPPORTED_SCHEMA,
                    f"{name} schema {got} 高于当前 {expected}，不能降级",
                    sections, warnings,
                )

        # ── 2) 解析 strength ──
        strength_section = by_name.get(SECTION_STRENGTH)
        if strength_section is not None:
            rows = (strength_section.payload or {}).get("rows") or []
            if not isinstance(rows, list):
                return self._reject(PrepareReject.INVALID_VALUE,
                                    "memory-strength.rows 不是列表", sections, warnings)
            if len(rows) > MAX_STRENGTH_ROWS:
                return self._reject(PrepareReject.INVALID_VALUE,
                                    "强度行数超过上限", sections, warnings)
            parsed, err = self._parse_strength(rows)
            if err:
                return self._reject(PrepareReject.INVALID_VALUE, err, sections, warnings)
            state.strength_rows = parsed
        else:
            warnings.append("旧快照无 memory-strength，恢复后按层默认 S0 回填")

        # ── 3) 解析 clock ──
        clock_section = by_name.get(SECTION_CLOCK)
        if clock_section is not None:
            clock, err = self._parse_clock((clock_section.payload or {}).get("clock"))
            if err:
                return self._reject(PrepareReject.INVALID_VALUE, err, sections, warnings)
            state.clock_state = clock
        else:
            warnings.append("旧快照无 memory-clock，恢复后沿用当前时钟")

        # ── 4) 解析 profile ──
        profile_section = by_name.get(SECTION_PROFILE)
        if profile_section is not None:
            profile, err = ForgettingProfile.from_dict(
                (profile_section.payload or {}).get("profile")
            )
            if err or profile is None:
                return self._reject(PrepareReject.INVALID_VALUE,
                                    err or "画像不可解析", sections, warnings)
            state.profile = profile
        else:
            state.profile = DEFAULT_PROFILE
            warnings.append("旧快照无 forgetting-profile，使用默认画像")

        # ── 5) 时间轴一致性：last_reinforced_day ≤ 时钟当前值 ──
        clock_day = float(
            state.clock_state.get("anchor_day", 0.0)
            or state.clock_state.get("game_day", 0.0) or 0.0
        )
        active_day = float(state.clock_state.get("active_seconds", 0.0)) / 86400.0
        effective_day = max(clock_day, active_day)
        future = [
            int(r["memory_id"]) for r in state.strength_rows
            if float(r["last_reinforced_day"]) > effective_day + 1e-6
        ]
        if future:
            return self._reject(
                PrepareReject.TIME_TRAVEL,
                f"{len(future)} 条强度的时间戳晚于快照时钟（样例 {future[:3]}）",
                sections, warnings,
            )

        # ── 6) 外键：强度行必须指向存在的记忆 ──
        orphan = self._find_orphans(state.strength_rows)
        if orphan:
            return self._reject(
                PrepareReject.FOREIGN_KEY,
                f"{len(orphan)} 条强度行指向不存在的记忆（样例 {orphan[:3]}）",
                sections, warnings,
            )

        # ── 7) 快照后的新记忆（预览必须告知，§4）──
        created_after = self._count_created_after(
            float((strength_section.payload or {}).get("watermark", 0.0) or 0.0)
            if strength_section else 0.0
        )

        # ── 8) 墓碑快照 + 保护状态（rollback 要能独立工作）──
        try:
            state.tombstones = [
                dict(t) for t in (self._tombstone_provider() or [])
            ]
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"墓碑读取失败，重放将跳过: {type(exc).__name__}")
        state.before_strength, state.before_clock = self._snapshot_before()
        try:
            state.before_profile = self._profile_provider() or DEFAULT_PROFILE
        except Exception:  # noqa: BLE001
            state.before_profile = DEFAULT_PROFILE

        state.checks = {
            "strength_rows": len(state.strength_rows),
            "clock_kind": str(state.clock_state.get("kind", "wall")),
            "clock_day": effective_day,
            "profile_version": int(state.profile.version),
            "will_discard_created_after": created_after,
            "tombstones_to_replay": len(state.tombstones),
            "strength_schema": STRENGTH_SCHEMA,
            "missing_sections": missing,
        }
        if missing:
            warnings.append(f"缺失 section: {', '.join(missing)}（将按回填规则处理）")

        return PreparedRestore(
            owner=self.owner, ok=True, code=PrepareReject.OK,
            message="记忆域 Prepare 通过",
            sections=tuple(s.name for s in sections or []),
            state=state, checks=state.checks, warnings=tuple(warnings),
        )

    @staticmethod
    def _reject(code: PrepareReject, message: str, sections, warnings) -> PreparedRestore:
        return PreparedRestore(
            owner="memory_system", ok=False, code=code, message=message,
            sections=tuple(s.name for s in sections or []),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _parse_strength(rows) -> Tuple[List[Dict[str, Any]], str]:
        parsed: List[Dict[str, Any]] = []
        seen = set()
        for raw in rows:
            if not isinstance(raw, dict):
                return [], "强度行不是对象"
            try:
                mid = int(raw.get("memory_id"))
                stability = float(raw.get("stability", 1.0))
                last = float(raw.get("last_reinforced_day", 0.0))
                importance = float(raw.get("importance", 0.4))
                salience = float(raw.get("salience", 0.0))
                lapse = int(raw.get("lapse_count", 0))
            except (TypeError, ValueError):
                return [], "强度行字段不可解析"
            if not math.isfinite(stability) or stability <= 0:
                return [], f"memory_id={mid} 的 stability 必须 > 0"
            if not math.isfinite(last) or last < 0:
                return [], f"memory_id={mid} 的 last_reinforced_day 非法"
            if not math.isfinite(importance) or not 0 <= importance <= 1:
                return [], f"memory_id={mid} 的 importance 越界"
            if mid in seen:
                return [], f"memory_id={mid} 重复"
            seen.add(mid)
            parsed.append({
                "memory_id": mid,
                "stability": stability,
                "last_reinforced_day": last,
                "importance": importance,
                "salience": max(0.0, min(1.0, salience)),
                "lapse_count": max(0, lapse),
                "state": str(raw.get("state", "active") or "active"),
                "pinned": 1 if raw.get("pinned") else 0,
            })
        return parsed, ""

    @staticmethod
    def _parse_clock(raw) -> Tuple[Dict[str, Any], str]:
        if not isinstance(raw, dict):
            return {}, "clock 不是对象"
        kind = str(raw.get("kind", "wall") or "wall")
        if kind not in ("wall", "active", "game", "fake"):
            return {}, f"未知时钟类型: {kind}"
        out: Dict[str, Any] = {"kind": kind}
        for key in ("anchor_epoch", "anchor_day", "active_seconds", "game_day"):
            try:
                value = float(raw.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                return {}, f"clock.{key} 不可解析"
            if not math.isfinite(value) or value < 0:
                return {}, f"clock.{key} 非法"
            out[key] = value
        return out, ""

    def _find_orphans(self, rows) -> List[int]:
        if not rows:
            return []
        conn = self._conn_factory()
        try:
            ids = [int(r["memory_id"]) for r in rows]
            # 分批，避免 SQLite 变量数上限
            existing = set()
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                placeholders = ",".join("?" for _ in chunk)
                try:
                    found = conn.execute(
                        f"SELECT id FROM memories WHERE id IN ({placeholders})",
                        tuple(chunk),
                    ).fetchall()
                except sqlite3.Error:
                    # 表不存在时不能假装"全部有外键"：保守报孤儿
                    return ids
                existing.update(int(r[0]) for r in found)
            return [mid for mid in ids if mid not in existing]
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _count_created_after(self, watermark: float) -> int:
        conn = self._conn_factory()
        try:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE id > ?", (float(watermark),)
                ).fetchone()
                return int(row[0] or 0) if row else 0
            except sqlite3.Error:
                return 0
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _snapshot_before(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        conn = self._conn_factory()
        try:
            return self._read_strength(conn), self._read_clock(conn)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ─────────────────────────────────────────────────────────
    # commit / rollback / verify
    # ─────────────────────────────────────────────────────────

    def commit_restore(self, prepared: PreparedRestore) -> None:
        """在恢复锁内原子替换；最后**重放墓碑**。

        单事务完成 strength + clock 替换，中途失败由 SQLite ROLLBACK
        保证不会留下"强度是新、时钟是旧"的混合状态。
        """
        state: _PreparedState = prepared.state
        conn = self._conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM memory_strength")
            conn.executemany(
                "INSERT INTO memory_strength("
                "memory_id, stability, last_reinforced_day, importance, salience, "
                "lapse_count, state, pinned) VALUES(?,?,?,?,?,?,?,?)",
                [
                    (r["memory_id"], r["stability"], r["last_reinforced_day"],
                     r["importance"], r["salience"], r["lapse_count"],
                     r["state"], r["pinned"])
                    for r in state.strength_rows
                ],
            )
            clock = state.clock_state
            conn.execute(
                "INSERT INTO memory_clock_state("
                "id, kind, anchor_epoch, anchor_day, active_seconds, game_day, updated_at) "
                "VALUES(1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "kind=excluded.kind, anchor_epoch=excluded.anchor_epoch, "
                "anchor_day=excluded.anchor_day, "
                "active_seconds=excluded.active_seconds, "
                "game_day=excluded.game_day, updated_at=excluded.updated_at",
                (
                    str(clock.get("kind", "wall")),
                    float(clock.get("anchor_epoch", 0.0)),
                    float(clock.get("anchor_day", 0.0)),
                    float(clock.get("active_seconds", 0.0)),
                    float(clock.get("game_day", 0.0)),
                    float(self._now()),
                ),
            )
            # 墓碑重放：已删记忆不得因恢复复活
            replayed = self._replay_tombstones(conn, state.tombstones)
            conn.execute("COMMIT")
            state.checks["tombstones_replayed"] = replayed
            self._last_committed = prepared
        except Exception as exc:  # noqa: BLE001
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            logger.warning(f"[MemoryOriginator] commit 失败已回滚: {type(exc).__name__}")
            raise
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _replay_tombstones(conn: sqlite3.Connection, tombstones) -> int:
        """按 `id + 内容摘要` 删除复活行。

        按 id 单独匹配是**错的**：快照恢复重建表后，新插入的行完全
        可能拿到和已删记忆相同的 id（B1-05）。摘要为空时退化为弱匹配
        —— 宁可多挡，也不让内容复活。
        """
        if not tombstones:
            return 0
        from .integrity import content_digest

        removed = 0
        for item in tombstones:
            try:
                mid = int(item.get("memory_id"))
            except (TypeError, ValueError):
                continue
            digest = str(item.get("digest", "") or "")
            try:
                row = conn.execute(
                    "SELECT content FROM memories WHERE id = ?", (mid,)
                ).fetchone()
                if row is None:
                    continue
                if digest and content_digest(str(row[0])) != digest:
                    continue  # id 复用但内容不同 → 这是一条新记忆
                conn.execute("DELETE FROM memories WHERE id = ?", (mid,))
                conn.execute("DELETE FROM memory_strength WHERE memory_id = ?", (mid,))
                removed += 1
            except sqlite3.Error:
                continue
        return removed

    def rollback_restore(self, prepared: PreparedRestore) -> None:
        """用恢复前保护状态还原。**独立工作**，不依赖别的域。"""
        state: _PreparedState = prepared.state
        conn = self._conn_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM memory_strength")
            conn.executemany(
                "INSERT INTO memory_strength("
                "memory_id, stability, last_reinforced_day, importance, salience, "
                "lapse_count, state, pinned) VALUES(?,?,?,?,?,?,?,?)",
                [
                    (int(r.get("memory_id", 0)), float(r.get("stability", 1.0)),
                     float(r.get("last_reinforced_day", 0.0)),
                     float(r.get("importance", 0.4)), float(r.get("salience", 0.0)),
                     int(r.get("lapse_count", 0)), str(r.get("state", "active")),
                     1 if r.get("pinned") else 0)
                    for r in state.before_strength
                ],
            )
            before = state.before_clock
            conn.execute(
                "INSERT INTO memory_clock_state("
                "id, kind, anchor_epoch, anchor_day, active_seconds, game_day, updated_at) "
                "VALUES(1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "kind=excluded.kind, anchor_epoch=excluded.anchor_epoch, "
                "anchor_day=excluded.anchor_day, "
                "active_seconds=excluded.active_seconds, "
                "game_day=excluded.game_day, updated_at=excluded.updated_at",
                (
                    str(before.get("kind", "wall")),
                    float(before.get("anchor_epoch", 0.0)),
                    float(before.get("anchor_day", 0.0)),
                    float(before.get("active_seconds", 0.0)),
                    float(before.get("game_day", 0.0)),
                    float(self._now()),
                ),
            )
            conn.execute("COMMIT")
        except Exception:  # noqa: BLE001
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def verify_restore(self, prepared: PreparedRestore) -> Tuple[bool, str]:
        """重读关键状态：行数、时钟、孤儿、墓碑。"""
        state: _PreparedState = prepared.state
        conn = self._conn_factory()
        try:
            try:
                count = int(conn.execute(
                    "SELECT COUNT(*) FROM memory_strength"
                ).fetchone()[0])
            except sqlite3.Error as exc:
                return False, f"强度表不可读: {type(exc).__name__}"
            if count != len(state.strength_rows):
                return False, (
                    f"强度行数不符: 期望 {len(state.strength_rows)}, 实际 {count}"
                )
            try:
                row = conn.execute(
                    "SELECT kind, anchor_day, active_seconds FROM "
                    "memory_clock_state WHERE id = 1"
                ).fetchone()
            except sqlite3.Error as exc:
                return False, f"时钟不可读: {type(exc).__name__}"
            if row is None:
                return False, "时钟行缺失"
            expected_kind = str(state.clock_state.get("kind", "wall"))
            if str(row[0]) != expected_kind:
                return False, f"时钟类型不符: {row[0]} != {expected_kind}"
            orphan = self._find_orphans(state.strength_rows)
            if orphan:
                return False, f"恢复后出现 {len(orphan)} 条孤儿强度行"
            return True, ""
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
