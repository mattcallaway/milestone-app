"""v2.0.0 migration — Expert Mode, audit log, and advanced features."""

import logging

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- ============================================
-- v2.0.0 Expert Mode & Advanced Features
-- ============================================

-- audit_log: tracks all significant operations for replay/forensics
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    expert_mode INTEGER DEFAULT 0,
    override_used TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

-- safety_overrides: per-operation override records
CREATE TABLE IF NOT EXISTS safety_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER,
    override_type TEXT NOT NULL,
    reason TEXT,
    auto_reset INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reset_at TIMESTAMP
);

-- item_pins: pin media items to specific drives
CREATE TABLE IF NOT EXISTS item_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_item_id INTEGER NOT NULL,
    drive_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (media_item_id) REFERENCES media_items(id) ON DELETE CASCADE,
    FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE,
    UNIQUE(media_item_id, drive_id)
);

-- drive_capabilities: detected filesystem features per drive
CREATE TABLE IF NOT EXISTS drive_capabilities (
    drive_id INTEGER PRIMARY KEY,
    supports_hardlink INTEGER DEFAULT 0,
    supports_reflink INTEGER DEFAULT 0,
    filesystem_type TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
);
"""


async def run_migration(db) -> None:
    """Apply v2.0.0 schema migration."""
    logger.info("Running v2.0.0 migration...")
    
    # Check if migration already applied
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
    )
    if await cursor.fetchone():
        logger.info("v2.0.0 migration already applied, skipping")
        return
    
    await db.executescript(MIGRATION_SQL)
    await db.commit()
    logger.info("v2.0.0 migration complete")
