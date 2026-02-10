"""Database migration for v1.1.0 schema additions."""

import logging

import aiosqlite

logger = logging.getLogger(__name__)


async def migrate_v110(db_path: str):
    """
    Add v1.1.0 columns to existing tables.
    Safe to run multiple times - uses IF NOT EXISTS or error handling.
    """
    async with aiosqlite.connect(db_path) as db:
        # Add failure_domain_id to drives
        try:
            await db.execute(
                "ALTER TABLE drives ADD COLUMN failure_domain_id INTEGER REFERENCES failure_domains(id)"
            )
        except Exception:
            pass  # Column already exists
        
        # Add drive safety flags
        for column in ["read_only", "never_write", "preferred"]:
            try:
                await db.execute(
                    f"ALTER TABLE drives ADD COLUMN {column} INTEGER DEFAULT 0"
                )
            except Exception:
                pass
        
        # Add verification_state to media_items
        try:
            await db.execute(
                "ALTER TABLE media_items ADD COLUMN verification_state TEXT DEFAULT 'unverified'"
            )
        except Exception:
            pass
        
        # Add match_reason and confidence to media_item_files
        try:
            await db.execute(
                "ALTER TABLE media_item_files ADD COLUMN match_reason TEXT"
            )
        except Exception:
            pass
        
        try:
            await db.execute(
                "ALTER TABLE media_item_files ADD COLUMN confidence REAL DEFAULT 0.0"
            )
        except Exception:
            pass
        
        # Add excluded flag to media_items
        try:
            await db.execute(
                "ALTER TABLE media_items ADD COLUMN excluded INTEGER DEFAULT 0"
            )
        except Exception:
            pass
        
        await db.commit()
        logger.info("v1.1.0 migration complete")


if __name__ == "__main__":
    import asyncio
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "./milestone.db"
    asyncio.run(migrate_v110(db_path))
