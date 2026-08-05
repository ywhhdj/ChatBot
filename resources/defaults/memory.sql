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
    `metadata` TEXT NOT NULL DEFAULT '{}'
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

CREATE TABLE IF NOT EXISTS `faiss_id_map` (
    `faiss_id` INTEGER PRIMARY KEY,
    `memory_id` INTEGER NOT NULL UNIQUE,
    FOREIGN KEY(`memory_id`) REFERENCES memories(`id`) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS `idx_memories_session_created` ON memories(`session_id`, created_at DESC);
CREATE INDEX IF NOT EXISTS `idx_memories_last_access` ON memories(`last_access_time` DESC);
CREATE INDEX IF NOT EXISTS `idx_memories_importance` ON memories(`importance` DESC);
CREATE INDEX IF NOT EXISTS `idx_compressed_session_created` ON compressed_memories(`session_id`, created_at DESC);
