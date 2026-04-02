"""Database connection and initialization."""

import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from .config import get_settings

# Database file path
DB_PATH = Path(__file__).parent.parent / "data" / "milestone.db"


async def init_db() -> None:
    """Initialize the database with schema and run pending migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(schema)
        await db.commit()

        # Migration: add original_path column if it doesn't exist yet.
        # ALTER TABLE ADD COLUMN is idempotent-safe — we just ignore the
        # "duplicate column" error for databases that already have it.
        try:
            await db.execute(
                "ALTER TABLE files ADD COLUMN original_path TEXT"
            )
            await db.commit()
        except Exception:
            pass  # column already exists — nothing to do

        # Migration v2.1: add failure_domains table.
        # schema.sql already has CREATE TABLE IF NOT EXISTS, so this is a
        # no-op for fresh installs. For existing DBs that ran an older schema,
        # executescript above will have already created it. Belt-and-suspenders.
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS failure_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
        except Exception:
            pass

        # Migration v2.1: add domain_id column to existing drives tables.
        try:
            await db.execute(
                "ALTER TABLE drives ADD COLUMN domain_id INTEGER"
                " REFERENCES failure_domains(id) ON DELETE SET NULL"
            )
            await db.commit()
        except Exception:
            pass  # column already exists


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection as async context manager."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    # Enforce FK constraints (OFF by default in SQLite) and use WAL for
    # concurrent read access during background scans/writes.
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")
    try:
        yield db
    finally:
        await db.close()
