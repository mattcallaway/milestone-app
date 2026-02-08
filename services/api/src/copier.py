"""Safe file copy operations with verification."""

import os
import shutil
import hashlib
import asyncio
from typing import Optional, Callable
from pathlib import Path

from .database import get_db
from .hasher import compute_full_hash


CHUNK_SIZE = 1024 * 1024  # 1MB chunks for progress reporting


async def safe_copy(
    source_path: str,
    dest_path: str,
    verify_hash: bool = False,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[int], None]] = None
) -> bool:
    """
    Safely copy a file with verification.
    
    1. Check destination doesn't exist (unless overwrite=True)
    2. Copy to temp file
    3. Verify size matches
    4. Optionally verify hash
    5. Atomic rename to final destination
    
    Returns True on success, False on failure.
    """
    source = Path(source_path)
    dest = Path(dest_path)
    temp_dest = dest.with_suffix(dest.suffix + ".tmp")
    
    # Validate source
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    
    if not source.is_file():
        raise ValueError(f"Source is not a file: {source_path}")
    
    # Check destination
    if dest.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {dest_path}")
    
    # Ensure destination directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    source_size = source.stat().st_size
    bytes_copied = 0
    
    try:
        # Copy to temp file with progress
        with open(source, "rb") as src_file:
            with open(temp_dest, "wb") as dst_file:
                while True:
                    chunk = src_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    dst_file.write(chunk)
                    bytes_copied += len(chunk)
                    
                    if progress_callback:
                        progress_callback(bytes_copied)
        
        # Verify size
        temp_size = temp_dest.stat().st_size
        if temp_size != source_size:
            raise ValueError(f"Size mismatch: source={source_size}, copied={temp_size}")
        
        # Optionally verify hash
        if verify_hash:
            source_hash = compute_full_hash(str(source))
            dest_hash = compute_full_hash(str(temp_dest))
            
            if source_hash != dest_hash:
                raise ValueError(f"Hash mismatch after copy")
        
        # Atomic rename (remove existing if overwrite)
        if dest.exists():
            dest.unlink()
        
        temp_dest.rename(dest)
        return True
        
    except Exception as e:
        # Clean up temp file on failure
        if temp_dest.exists():
            try:
                temp_dest.unlink()
            except:
                pass
        raise


async def get_destination_drives(
    source_file_id: int,
    media_type: Optional[str] = None
) -> list[dict]:
    """
    Get suitable destination drives for a copy operation.
    
    Filters:
    1. Exclude source drive
    2. Exclude denylisted drives
    3. Apply type preferences (prefer_movie, prefer_tv)
    4. Check free space threshold
    
    Returns drives sorted by preference and free space.
    """
    async with get_db() as db:
        # Get source file info
        cursor = await db.execute(
            """
            SELECT f.*, r.drive_id, d.mount_path as source_mount
            FROM files f
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            WHERE f.id = ?
            """,
            (source_file_id,)
        )
        source_file = await cursor.fetchone()
        
        if not source_file:
            return []
        
        source_drive_id = source_file["drive_id"]
        file_size = source_file["size"] or 0
        
        # Get all drives
        cursor = await db.execute("SELECT * FROM drives")
        all_drives = [dict(row) for row in await cursor.fetchall()]
        
        # Get user rules
        cursor = await db.execute("SELECT * FROM user_rules ORDER BY priority DESC")
        rules = [dict(row) for row in await cursor.fetchall()]
        
        # Build denylist
        denylist = set()
        preferred = []
        
        for rule in rules:
            if rule["rule_type"] == "denylist":
                denylist.add(rule["drive_id"])
            elif rule["rule_type"] == f"prefer_{media_type}":
                preferred.append(rule["drive_id"])
            elif rule["rule_type"] == "prefer_all":
                preferred.append(rule["drive_id"])
        
        # Filter and score drives
        candidates = []
        for drive in all_drives:
            drive_id = drive["id"]
            
            # Skip source drive
            if drive_id == source_drive_id:
                continue
            
            # Skip denylisted
            if drive_id in denylist:
                continue
            
            # Check free space (need at least file_size + 10GB buffer or 10% extra)
            mount_path = drive["mount_path"]
            try:
                stat = shutil.disk_usage(mount_path)
                free_space = stat.free
                min_required = file_size + max(10 * 1024**3, file_size * 0.1)
                
                if free_space < min_required:
                    continue
                
                drive["free_space"] = free_space
                drive["total_space"] = stat.total
            except:
                continue  # Skip drives we can't access
            
            # Score: preferred drives get boost
            score = free_space
            if drive_id in preferred:
                score += 10 * 1024**5  # Huge boost for preferred
            
            drive["score"] = score
            candidates.append(drive)
        
        # Sort by score descending
        candidates.sort(key=lambda d: d["score"], reverse=True)
        return candidates


async def create_copy_operation(
    source_file_id: int,
    dest_drive_id: Optional[int] = None,
    dest_path: Optional[str] = None,
    verify_hash: bool = True
) -> dict:
    """
    Create a copy operation in the queue.
    
    If dest_drive_id/dest_path not specified, auto-select best destination.
    """
    async with get_db() as db:
        # Get source file info
        cursor = await db.execute(
            """
            SELECT f.*, r.path as root_path, d.mount_path as source_mount, mi.type as media_type
            FROM files f
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            LEFT JOIN media_item_files mif ON f.id = mif.file_id
            LEFT JOIN media_items mi ON mif.media_item_id = mi.id
            WHERE f.id = ?
            """,
            (source_file_id,)
        )
        source_file = await cursor.fetchone()
        
        if not source_file:
            raise ValueError(f"Source file not found: {source_file_id}")
        
        # Auto-select destination if not specified
        if dest_drive_id is None:
            candidates = await get_destination_drives(
                source_file_id,
                media_type=source_file.get("media_type")
            )
            
            if not candidates:
                raise ValueError("No suitable destination drives available")
            
            dest_drive = candidates[0]
            dest_drive_id = dest_drive["id"]
        else:
            cursor = await db.execute("SELECT * FROM drives WHERE id = ?", (dest_drive_id,))
            dest_drive = await cursor.fetchone()
            if not dest_drive:
                raise ValueError(f"Destination drive not found: {dest_drive_id}")
        
        # Build destination path (mirror structure from source)
        source_full = source_file["path"]
        source_mount = source_file["source_mount"]
        relative_path = source_full
        
        if dest_path is None:
            dest_path = os.path.join(dest_drive["mount_path"], os.path.basename(source_full))
        
        # Check destination doesn't already exist
        if os.path.exists(dest_path):
            raise FileExistsError(f"Destination already exists: {dest_path}")
        
        # Create operation
        cursor = await db.execute(
            """
            INSERT INTO operations (type, source_file_id, dest_drive_id, dest_path, total_size, verify_hash)
            VALUES ('copy', ?, ?, ?, ?, ?)
            """,
            (source_file_id, dest_drive_id, dest_path, source_file["size"], 1 if verify_hash else 0)
        )
        await db.commit()
        op_id = cursor.lastrowid
        
        return {
            "id": op_id,
            "type": "copy",
            "status": "pending",
            "source_file_id": source_file_id,
            "source_path": source_full,
            "dest_drive_id": dest_drive_id,
            "dest_path": dest_path,
            "total_size": source_file["size"],
            "verify_hash": verify_hash
        }
