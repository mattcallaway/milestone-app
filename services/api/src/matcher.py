"""Matcher service for grouping files into media items."""

from typing import Optional
from datetime import datetime

from .database import get_db
from .parser import parse_path, is_video_file


async def find_matching_item(quick_sig: Optional[str], full_hash: Optional[str]) -> Optional[int]:
    """
    Find existing media item matching the given signatures.
    Primary: full hash equality
    Fallback: quick signature match (marks as needs_verification)
    """
    if not quick_sig and not full_hash:
        return None
    
    async with get_db() as db:
        # Primary: exact full hash match
        if full_hash:
            cursor = await db.execute("""
                SELECT mi.id 
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                JOIN files f ON mif.file_id = f.id
                WHERE f.full_hash = ?
                LIMIT 1
            """, (full_hash,))
            row = await cursor.fetchone()
            if row:
                return row["id"]
        
        # Fallback: quick signature match
        if quick_sig:
            cursor = await db.execute("""
                SELECT mi.id 
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                JOIN files f ON mif.file_id = f.id
                WHERE f.quick_sig = ?
                LIMIT 1
            """, (quick_sig,))
            row = await cursor.fetchone()
            if row:
                # Mark as needs verification since we're matching on quick sig only
                await db.execute(
                    "UPDATE media_items SET status = 'needs_verification' WHERE id = ?",
                    (row["id"],)
                )
                await db.commit()
                return row["id"]
    
    return None


async def create_media_item_from_file(file_id: int) -> Optional[int]:
    """Create a new media item from a file using parsed metadata."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, path, ext, quick_sig, full_hash FROM files WHERE id = ?",
            (file_id,)
        )
        file_row = await cursor.fetchone()
        if not file_row:
            return None
        
        filepath = file_row["path"]
        
        # Only process video files
        if not is_video_file(filepath):
            return None
        
        # Check if file is already linked to an item
        cursor = await db.execute(
            "SELECT media_item_id FROM media_item_files WHERE file_id = ?",
            (file_id,)
        )
        if await cursor.fetchone():
            return None  # Already linked
        
        # Try to find matching item
        matching_id = await find_matching_item(
            file_row["quick_sig"], 
            file_row["full_hash"]
        )
        
        if matching_id:
            # Add file to existing item
            await db.execute(
                "INSERT OR IGNORE INTO media_item_files (media_item_id, file_id) VALUES (?, ?)",
                (matching_id, file_id)
            )
            await db.commit()
            return matching_id
        
        # Create new item with parsed metadata
        parsed = parse_path(filepath)
        
        cursor = await db.execute("""
            INSERT INTO media_items (type, title, year, season, episode, status)
            VALUES (?, ?, ?, ?, ?, 'auto')
        """, (parsed.type, parsed.title, parsed.year, parsed.season, parsed.episode))
        await db.commit()
        
        item_id = cursor.lastrowid
        
        # Link file to new item
        await db.execute(
            "INSERT INTO media_item_files (media_item_id, file_id, is_primary) VALUES (?, ?, 1)",
            (item_id, file_id)
        )
        await db.commit()
        
        return item_id


async def process_all_unlinked_files() -> dict:
    """Process all files not yet linked to media items."""
    stats = {"processed": 0, "new_items": 0, "linked": 0, "skipped": 0}
    
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT f.id FROM files f
            LEFT JOIN media_item_files mif ON f.id = mif.file_id
            WHERE mif.file_id IS NULL
        """)
        unlinked = await cursor.fetchall()
    
    for row in unlinked:
        file_id = row["id"]
        
        async with get_db() as db:
            cursor = await db.execute("SELECT path FROM files WHERE id = ?", (file_id,))
            file_row = await cursor.fetchone()
            if not file_row or not is_video_file(file_row["path"]):
                stats["skipped"] += 1
                continue
        
        result = await create_media_item_from_file(file_id)
        stats["processed"] += 1
        
        if result:
            # Check if this was a new item or existing
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM media_item_files WHERE media_item_id = ?",
                    (result,)
                )
                count = (await cursor.fetchone())[0]
                if count == 1:
                    stats["new_items"] += 1
                else:
                    stats["linked"] += 1
    
    return stats


async def merge_items(target_id: int, source_ids: list[int]) -> dict:
    """Merge multiple media items into one."""
    async with get_db() as db:
        # Verify target exists
        cursor = await db.execute("SELECT id FROM media_items WHERE id = ?", (target_id,))
        if not await cursor.fetchone():
            return {"error": "Target item not found"}
        
        files_moved = 0
        for source_id in source_ids:
            if source_id == target_id:
                continue
            
            # Move all files from source to target
            cursor = await db.execute(
                "UPDATE media_item_files SET media_item_id = ? WHERE media_item_id = ?",
                (target_id, source_id)
            )
            files_moved += cursor.rowcount
            
            # Delete empty source item
            await db.execute("DELETE FROM media_items WHERE id = ?", (source_id,))
        
        # Mark target as verified (manual merge = verified)
        await db.execute(
            "UPDATE media_items SET status = 'verified' WHERE id = ?",
            (target_id,)
        )
        await db.commit()
        
        return {"target_id": target_id, "files_moved": files_moved, "items_merged": len(source_ids)}


async def split_file(file_id: int) -> dict:
    """Split a file out of its current media item into a new one."""
    async with get_db() as db:
        # Get current link
        cursor = await db.execute(
            "SELECT media_item_id FROM media_item_files WHERE file_id = ?",
            (file_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return {"error": "File not linked to any item"}
        
        old_item_id = row["media_item_id"]
        
        # Check if this is the only file in the item
        cursor = await db.execute(
            "SELECT COUNT(*) FROM media_item_files WHERE media_item_id = ?",
            (old_item_id,)
        )
        count = (await cursor.fetchone())[0]
        if count == 1:
            return {"error": "Cannot split - file is alone in its item"}
        
        # Get file info for new item
        cursor = await db.execute("SELECT path FROM files WHERE id = ?", (file_id,))
        file_row = await cursor.fetchone()
        if not file_row:
            return {"error": "File not found"}
        
        parsed = parse_path(file_row["path"])
        
        # Create new item
        cursor = await db.execute("""
            INSERT INTO media_items (type, title, year, season, episode, status)
            VALUES (?, ?, ?, ?, ?, 'verified')
        """, (parsed.type, parsed.title, parsed.year, parsed.season, parsed.episode))
        new_item_id = cursor.lastrowid
        
        # Move file to new item
        await db.execute(
            "UPDATE media_item_files SET media_item_id = ?, is_primary = 1 WHERE file_id = ?",
            (new_item_id, file_id)
        )
        await db.commit()
        
        return {
            "old_item_id": old_item_id,
            "new_item_id": new_item_id,
            "file_id": file_id
        }
