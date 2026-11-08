PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS `memories` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `session_id` TEXT NOT NULL DEFAULT 'default',
    `role` TEXT NOT NULL DEFAULT 'user',
    `source` TEXT NOT NULL DEFAULT 'text',
    `content` TEXT NOT NULL,
    `importance` REAL NOT NULL DEFAULT 1.0,
    `access_count` INTEGER NOT NULL DEFAULT 0,
    `last_access_time` REAL NOT NULL,
    `created_at` REAL NOT NULL,
    `updated_at` REAL NOT NULL,
    `tokens` INTEGER NOT NULL DEFAULT 0,
    `metadata` TEXT NOT NULL DEFAULT '{}',
    `layer` TEXT NOT NULL DEFAULT 'episodic',
    `kind` TEXT NOT NULL DEFAULT 'fact',
    `confidence` REAL NOT NULL DEFAULT 0.5,
    `valid_from` REAL NOT NULL DEFAULT 0,
    `valid_until` REAL DEFAULT NULL,
    `source_ids` TEXT NOT NULL DEFAULT '[]',
    `embedding_version` TEXT NOT NULL DEFAULT '',
    `supersedes` TEXT NOT NULL DEFAULT '[]',
    `conflict_group` TEXT NOT NULL DEFAULT '',
    `pinned` INTEGER NOT NULL DEFAULT 0,
    `derived_from` TEXT NOT NULL DEFAULT '[]',
    `covered_by_summary` INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS `compressed_memories` (
    `id` TEXT PRIMARY KEY,
    `session_id` TEXT NOT NULL DEFAULT 'default',
    `original_ids` TEXT NOT NULL,
    `compressed_content` TEXT NOT NULL,
    `summary` TEXT NOT NULL,
    `created_at` REAL NOT NULL,
    `range_start` REAL NOT NULL,
    `range_end` REAL NOT NULL,
    `metadata` TEXT NOT NULL DEFAULT '{}'
);

-- 向量索引由 Milvus 服务端管理，以 memory_id 为主键。
-- **没有本地 id 映射表**：metadata.id 与 Milvus.memory_id 是同一个值，
-- 对齐诊断就是两个 id 集合的差集（B1-04）。FAISS 及其映射表已移除。

CREATE INDEX IF NOT EXISTS `idx_memories_session_created` ON memories(`session_id`, created_at DESC);
CREATE INDEX IF NOT EXISTS `idx_memories_last_access` ON memories(`last_access_time` DESC);
CREATE INDEX IF NOT EXISTS `idx_memories_importance` ON memories(`importance` DESC);
CREATE INDEX IF NOT EXISTS `idx_compressed_session_created` ON compressed_memories(`session_id`, created_at DESC);

-- B1-05：删除墓碑。只存 id + 内容摘要 + 时间，**不存正文**。
-- 用途：快照恢复后重放，防止已删记忆复活（SecurityAndAuditDesign §7）。
CREATE TABLE IF NOT EXISTS `memory_tombstones` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `memory_id` INTEGER NOT NULL,
    `session_id` TEXT NOT NULL DEFAULT 'default',
    `digest` TEXT NOT NULL DEFAULT '',
    `deleted_at` REAL NOT NULL,
    `reason` TEXT NOT NULL DEFAULT 'user'
);

CREATE UNIQUE INDEX IF NOT EXISTS `idx_tombstones_memory` ON memory_tombstones(`memory_id`, `digest`);
CREATE INDEX IF NOT EXISTS `idx_tombstones_deleted_at` ON memory_tombstones(`deleted_at` DESC);

-- embedding 指纹。记录当前向量索引由哪套配置产出，
-- 配置变了必须重建，不能混用（B1-06）。
CREATE TABLE IF NOT EXISTS `embedding_meta` (
    `id` INTEGER PRIMARY KEY CHECK (`id` = 1),
    `provider` TEXT NOT NULL DEFAULT '',
    `model` TEXT NOT NULL DEFAULT '',
    `dim` INTEGER NOT NULL DEFAULT 0,
    `version` TEXT NOT NULL DEFAULT '1',
    `digest` TEXT NOT NULL DEFAULT '',
    `updated_at` REAL NOT NULL
);


-- ── 强度、时钟、使用事件、迁移进度 ──
-- 详细语义见 src_py/modules/memory/migrations.py。
CREATE TABLE IF NOT EXISTS `memory_strength` (
    `memory_id` INTEGER PRIMARY KEY,
    `stability` REAL NOT NULL DEFAULT 1.0,
    `last_reinforced_day` REAL NOT NULL DEFAULT 0,
    `importance` REAL NOT NULL DEFAULT 0.4,
    `salience` REAL NOT NULL DEFAULT 0.0,
    `lapse_count` INTEGER NOT NULL DEFAULT 0,
    `state` TEXT NOT NULL DEFAULT 'active',
    `pinned` INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(`memory_id`) REFERENCES memories(`id`) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `memory_usage_event` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `memory_id` INTEGER NOT NULL,
    `session_id` TEXT NOT NULL DEFAULT 'default',
    `usage` TEXT NOT NULL,
    `request_id` TEXT NOT NULL DEFAULT '',
    `ts` REAL NOT NULL,
    `awakened` INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS `idx_usage_session_ts` ON memory_usage_event(`session_id`, `ts` DESC);

CREATE TABLE IF NOT EXISTS `memory_clock_state` (
    `id` INTEGER PRIMARY KEY CHECK (`id` = 1),
    `kind` TEXT NOT NULL DEFAULT 'wall',
    `anchor_epoch` REAL NOT NULL DEFAULT 0,
    `anchor_day` REAL NOT NULL DEFAULT 0,
    `active_seconds` REAL NOT NULL DEFAULT 0,
    `game_day` REAL NOT NULL DEFAULT 0,
    `updated_at` REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS `memory_schema_meta` (
    `key` TEXT PRIMARY KEY,
    `value` TEXT NOT NULL DEFAULT '',
    `updated_at` REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS `idx_memories_layer` ON memories(`layer`);
CREATE INDEX IF NOT EXISTS `idx_memories_valid_until` ON memories(`valid_until`);
