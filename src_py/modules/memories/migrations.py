"""记忆 schema 版本化迁移与回填（M1-02 / MemoryDesign §3）。

验收项（OptimizationPlan M1-02）
──────────────────────────────
* 版本化迁移；
* 分批回填、进度记录；
* **可中断重入**（跑到一半崩了，重启接着跑，不重复、不丢）；
* 旧行为不变（新增列/表，不删不改已有列）。

为什么不"静默改用户数据库"
──────────────────────────
`MemoryDesign.md` §3 明确要求 schema version/migration。
本模块的 `migrate()` **必须由组合根显式调用**，不在 import 时执行；
每一步都写 `memory_schema_meta` 进度，调用方能查、能停、能重跑。

新增内容
────────
* `memories` 追加 `layer / kind / confidence / valid_from / valid_until /
  source_ids / embedding_version / supersedes / conflict_group /
  pinned / derived_from / covered_by_summary` 列；
* `memory_strength`：S、上次强化日、重要度、显著度、lapse_count、state；
* `memory_usage_event`：使用事件（M1-04）；
* `memory_clock_state`：时钟锚点（M1-01 / S2-01）；
* `memory_schema_meta`：迁移进度。

回填策略
────────
旧数据没有 layer → 按 `normalize_layer()` 的规则映射（短/长/明细/压缩），
`importance` 取原列，`stability = initial_stability(layer, importance)`，
`last_reinforced_day` 取 `created_at / 86400`。
**不臆造 confidence / source_ids**：留空由后续写入补齐。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .domain.layers import normalize_layer
from .domain.strength import initial_stability

SCHEMA_VERSION = 2
SECONDS_PER_DAY = 86400.0

#: (列名, 类型, 默认值)。全部 **ADD COLUMN**，不修改既有列。
NEW_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("layer", "TEXT", "'episodic'"),
    ("kind", "TEXT", "'fact'"),
    ("confidence", "REAL", "0.5"),
    ("valid_from", "REAL", "0"),
    ("valid_until", "REAL", "NULL"),
    ("source_ids", "TEXT", "'[]'"),
    ("embedding_version", "TEXT", "''"),
    ("supersedes", "TEXT", "'[]'"),
    ("conflict_group", "TEXT", "''"),
    ("pinned", "INTEGER", "0"),
    ("derived_from", "TEXT", "'[]'"),
    ("covered_by_summary", "INTEGER", "0"),
)

DDL_STATEMENTS: Tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS `memory_strength` (
        `memory_id` INTEGER PRIMARY KEY,
        `stability` REAL NOT NULL DEFAULT 1.0,
        `last_reinforced_day` REAL NOT NULL DEFAULT 0,
        `importance` REAL NOT NULL DEFAULT 0.4,
        `salience` REAL NOT NULL DEFAULT 0.0,
        `lapse_count` INTEGER NOT NULL DEFAULT 0,
        `state` TEXT NOT NULL DEFAULT 'active',
        `pinned` INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(`memory_id`) REFERENCES memories(`id`) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS `memory_usage_event` (
        `id` INTEGER PRIMARY KEY AUTOINCREMENT,
        `memory_id` INTEGER NOT NULL,
        `session_id` TEXT NOT NULL DEFAULT 'default',
        `usage` TEXT NOT NULL,
        `request_id` TEXT NOT NULL DEFAULT '',
        `ts` REAL NOT NULL,
        `awakened` INTEGER NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS `idx_usage_session_ts` "
    "ON memory_usage_event(`session_id`, `ts` DESC)",
    """CREATE TABLE IF NOT EXISTS `memory_clock_state` (
        `id` INTEGER PRIMARY KEY CHECK (`id` = 1),
        `kind` TEXT NOT NULL DEFAULT 'wall',
        `anchor_epoch` REAL NOT NULL DEFAULT 0,
        `anchor_day` REAL NOT NULL DEFAULT 0,
        `active_seconds` REAL NOT NULL DEFAULT 0,
        `game_day` REAL NOT NULL DEFAULT 0,
        `updated_at` REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS `memory_schema_meta` (
        `key` TEXT PRIMARY KEY,
        `value` TEXT NOT NULL DEFAULT '',
        `updated_at` REAL NOT NULL
    )""",
)


@dataclass
class MigrationReport:
    started_at: float = 0.0
    version_before: int = 0
    version_after: int = 0
    columns_added: List[str] = field(default_factory=list)
    tables_created: int = 0
    backfilled: int = 0
    batches: int = 0
    warnings: List[str] = field(default_factory=list)
    interrupted_resume: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "version_before": self.version_before,
            "version_after": self.version_after,
            "columns_added": list(self.columns_added),
            "tables_created": self.tables_created,
            "backfilled": self.backfilled,
            "batches": self.batches,
            "warnings": list(self.warnings),
            "interrupted_resume": self.interrupted_resume,
        }


class MemoryMigrator:
    """显式调用、可中断重入的迁移器。"""

    def __init__(self, conn: sqlite3.Connection, *, batch_size: int = 500) -> None:
        self.conn = conn
        self.batch_size = max(1, int(batch_size))

    # ---------- 元数据 ----------

    def _meta(self, key: str) -> str:
        try:
            row = self.conn.execute(
                "SELECT value FROM memory_schema_meta WHERE key = ?", (key,)
            ).fetchone()
            return str(row[0]) if row else ""
        except sqlite3.Error:
            return ""

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO memory_schema_meta(key, value, updated_at) "
            "VALUES(?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
            "value = excluded.value, updated_at = excluded.updated_at",
            (key, str(value), time.time()),
        )
        self.conn.commit()

    def version(self) -> int:
        raw = self._meta("schema_version")
        try:
            return int(raw or 1)
        except ValueError:
            return 1

    # ---------- 结构 ----------

    def _existing_columns(self, table: str) -> set:
        try:
            rows = self.conn.execute(f"PRAGMA table_info(`{table}`)").fetchall()
        except sqlite3.Error:
            return set()
        return {str(row[1]) for row in rows}

    def _ensure_tables(self, report: MigrationReport) -> None:
        for ddl in DDL_STATEMENTS:
            try:
                self.conn.execute(ddl)
                report.tables_created += 1
            except sqlite3.Error as exc:
                report.warnings.append(f"DDL 失败: {type(exc).__name__}")
        self.conn.commit()

    def _ensure_columns(self, report: MigrationReport) -> None:
        existing = self._existing_columns("memories")
        if not existing:
            report.warnings.append("memories 表不存在，跳过列迁移")
            return
        for name, typ, default in NEW_COLUMNS:
            if name in existing:
                continue
            try:
                self.conn.execute(
                    f"ALTER TABLE `memories` ADD COLUMN `{name}` {typ} DEFAULT {default}"
                )
                report.columns_added.append(name)
            except sqlite3.Error as exc:
                report.warnings.append(f"ADD COLUMN {name} 失败: {type(exc).__name__}")
        self.conn.commit()

    # ---------- 回填 ----------

    def _backfill(self, report: MigrationReport) -> None:
        """分批回填 layer + strength。**可中断重入**。

        进度用 `backfill_cursor`（已处理的最大 memory_id）持久化；
        每次批结束就 commit，崩溃后从游标继续，不重复处理。
        """
        cursor_raw = self._meta("backfill_cursor")
        try:
            cursor = int(cursor_raw or 0)
        except ValueError:
            cursor = 0
        report.interrupted_resume = cursor > 0

        while True:
            try:
                rows = self.conn.execute(
                    "SELECT id, session_id, content, importance, created_at, layer "
                    "FROM memories WHERE id > ? ORDER BY id ASC LIMIT ?",
                    (cursor, self.batch_size),
                ).fetchall()
            except sqlite3.Error as exc:
                report.warnings.append(f"回填查询失败: {type(exc).__name__}")
                return
            if not rows:
                break

            for row in rows:
                mid = int(row[0])
                cursor = max(cursor, mid)
                old_layer = str(row[5] or "")
                layer = normalize_layer(old_layer or "detailed")
                importance = float(row[3] if row[3] is not None else 0.4)
                created = float(row[4] if row[4] is not None else 0.0)
                day = created / SECONDS_PER_DAY
                stability = initial_stability(layer, importance)
                try:
                    self.conn.execute(
                        "UPDATE memories SET layer = ? WHERE id = ? AND (layer IS NULL OR layer = '')",
                        (layer.value, mid),
                    )
                    self.conn.execute(
                        "INSERT OR IGNORE INTO memory_strength("
                        "memory_id, stability, last_reinforced_day, importance, salience, "
                        "lapse_count, state, pinned) VALUES(?, ?, ?, ?, 0, 0, 'active', 0)",
                        (mid, stability, day, importance),
                    )
                    report.backfilled += 1
                except sqlite3.Error as exc:
                    report.warnings.append(f"回填 {mid} 失败: {type(exc).__name__}")
            self.conn.commit()
            self._set_meta("backfill_cursor", str(cursor))
            report.batches += 1

    # ---------- 入口 ----------

    def migrate(self) -> MigrationReport:
        report = MigrationReport(started_at=time.time())
        self._ensure_tables(report)   # 先建 meta 表，否则 _meta 会失败
        report.version_before = self.version()
        self._ensure_columns(report)
        self._backfill(report)
        self._set_meta("schema_version", str(SCHEMA_VERSION))
        report.version_after = self.version()
        return report

    def progress(self) -> Dict[str, Any]:
        return {
            "schema_version": self.version(),
            "backfill_cursor": self._meta("backfill_cursor"),
            "target_version": SCHEMA_VERSION,
        }
