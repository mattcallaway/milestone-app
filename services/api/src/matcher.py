"""Matcher service for grouping files into media items."""

from typing import Optional
from datetime import datetime

from .database import get_db
from .parser import parse_path, is_media_file


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
        if not is_media_file(filepath):
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
    """Process all files not yet linked to media items.
    
    Matching priority:
    1. Full hash match (exact duplicate)
    2. Quick signature match (likely duplicate, marked for verification)
    3. Title-based match (same title+type+year for movies, +season+episode for TV)
    4. No match → create new media item
    
    Optimized: single DB connection, batch commits, in-memory title index.
    """
    stats = {"processed": 0, "new_items": 0, "linked": 0, "linked_by_title": 0, "skipped": 0}
    BATCH_SIZE = 500
    
    async with get_db() as db:
        # Build in-memory title index for fast title-based matching
        # Key: (type, title_lower, year, season, episode) -> media_item_id
        cursor = await db.execute("""
            SELECT id, type, title, year, season, episode FROM media_items
            WHERE title IS NOT NULL
        """)
        existing_items = await cursor.fetchall()
        title_index = {}
        for item in existing_items:
            key = (
                item["type"],
                (item["title"] or "").lower(),
                item["year"],
                item["season"],
                item["episode"]
            )
            # Keep the first (lowest id) item for each title group
            if key not in title_index:
                title_index[key] = item["id"]
        
        # Fetch all unlinked files with their paths in one query
        cursor = await db.execute("""
            SELECT f.id, f.path, f.quick_sig, f.full_hash
            FROM files f
            LEFT JOIN media_item_files mif ON f.id = mif.file_id
            WHERE mif.file_id IS NULL
        """)
        unlinked = await cursor.fetchall()
        
        pending_commits = 0
        
        for row in unlinked:
            file_id = row["id"]
            filepath = row["path"]
            
            # Skip non-media files
            if not is_media_file(filepath):
                stats["skipped"] += 1
                continue
            
            # --- Priority 1 & 2: Hash-based matching ---
            matching_id = None
            if row["full_hash"]:
                cursor = await db.execute(
                    """SELECT mif.media_item_id FROM media_item_files mif
                       JOIN files f ON mif.file_id = f.id
                       WHERE f.full_hash = ? LIMIT 1""",
                    (row["full_hash"],)
                )
                match = await cursor.fetchone()
                if match:
                    matching_id = match[0]
            
            if not matching_id and row["quick_sig"]:
                cursor = await db.execute(
                    """SELECT mif.media_item_id FROM media_item_files mif
                       JOIN files f ON mif.file_id = f.id
                       WHERE f.quick_sig = ? LIMIT 1""",
                    (row["quick_sig"],)
                )
                match = await cursor.fetchone()
                if match:
                    matching_id = match[0]
            
            # --- Priority 3: Title-based matching ---
            parsed = parse_path(filepath)
            
            if not matching_id and parsed.title:
                title_key = (
                    parsed.type,
                    parsed.title.lower(),
                    parsed.year,
                    parsed.season,
                    parsed.episode
                )
                matching_id = title_index.get(title_key)
                if matching_id:
                    stats["linked_by_title"] += 1
            
            if matching_id:
                # Link to existing item (copy found!)
                await db.execute(
                    "INSERT OR IGNORE INTO media_item_files (media_item_id, file_id) VALUES (?, ?)",
                    (matching_id, file_id)
                )
                stats["linked"] += 1
            else:
                # No match anywhere — create new media item
                cursor = await db.execute(
                    """INSERT INTO media_items (type, title, year, season, episode, status)
                       VALUES (?, ?, ?, ?, ?, 'auto')""",
                    (parsed.type, parsed.title, parsed.year, parsed.season, parsed.episode)
                )
                item_id = cursor.lastrowid
                await db.execute(
                    "INSERT INTO media_item_files (media_item_id, file_id, is_primary) VALUES (?, ?, 1)",
                    (item_id, file_id)
                )
                stats["new_items"] += 1
                
                # Add new item to title index so subsequent files match it
                if parsed.title:
                    new_key = (
                        parsed.type,
                        parsed.title.lower(),
                        parsed.year,
                        parsed.season,
                        parsed.episode
                    )
                    if new_key not in title_index:
                        title_index[new_key] = item_id
            
            stats["processed"] += 1
            pending_commits += 1
            
            # Batch commit every BATCH_SIZE files
            if pending_commits >= BATCH_SIZE:
                await db.commit()
                pending_commits = 0
        
        # Final commit for remaining items
        if pending_commits > 0:
            await db.commit()
    
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


async def dedup_merge_all() -> dict:
    """Merge all media items that share the same title+type+year+season+episode.
    
    For each group of duplicates, the lowest-ID item becomes the target
    and all file links from other items are moved into it. Empty items
    are deleted.
    
    This is a one-time remediation for items created before title-based
    matching was implemented.
    """
    stats = {"groups_merged": 0, "items_removed": 0, "files_relinked": 0}
    BATCH_SIZE = 500
    
    async with get_db() as db:
        # Find all duplicate title groups
        cursor = await db.execute("""
            SELECT type, title, year, season, episode, 
                   MIN(id) as target_id, COUNT(*) as cnt
            FROM media_items
            WHERE title IS NOT NULL
            GROUP BY type, title, year, season, episode
            HAVING cnt > 1
        """)
        groups = await cursor.fetchall()
        
        pending = 0
        
        for group in groups:
            target_id = group["target_id"]
            
            # Get all item IDs in this group (except target)
            cursor = await db.execute("""
                SELECT id FROM media_items
                WHERE type = ? AND title = ? AND year IS ? AND season IS ? AND episode IS ?
                  AND id != ?
            """, (group["type"], group["title"], group["year"],
                  group["season"], group["episode"], target_id))
            source_rows = await cursor.fetchall()
            
            for source in source_rows:
                source_id = source["id"]
                
                # Move file links — use INSERT OR IGNORE to handle
                # cases where the file is already linked to the target
                cursor = await db.execute("""
                    INSERT OR IGNORE INTO media_item_files (media_item_id, file_id, is_primary)
                    SELECT ?, file_id, 0 FROM media_item_files WHERE media_item_id = ?
                """, (target_id, source_id))
                stats["files_relinked"] += cursor.rowcount
                
                # Remove old links
                await db.execute(
                    "DELETE FROM media_item_files WHERE media_item_id = ?",
                    (source_id,)
                )
                
                # Delete the now-empty item
                await db.execute("DELETE FROM media_items WHERE id = ?", (source_id,))
                stats["items_removed"] += 1
            
            stats["groups_merged"] += 1
            pending += 1
            
            if pending >= BATCH_SIZE:
                await db.commit()
                pending = 0
        
        if pending > 0:
            await db.commit()
    
    return stats

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
