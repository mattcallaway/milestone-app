"""Database connection and initialization."""

import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Database file path
DB_PATH = Path(__file__).parent.parent / "data" / "milestone.db"


async def init_db() -> None:
    """Initialize the database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(schema)
        await db.commit()
    
    # Run v1.1.0 migrations for existing DBs
    from .migrations.v110 import migrate_v110
    await migrate_v110(str(DB_PATH))


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get database connection as async context manager."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


