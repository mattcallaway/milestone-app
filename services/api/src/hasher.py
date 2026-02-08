"""File hashing service with quick signatures and full SHA-256."""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from .database import get_db

# Hash computation settings
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for reading
QUICK_SIG_SIZE = 1024 * 1024  # 1MB from start and end for quick signature

# Global hash queue state
_hash_queue: list[int] = []
_hash_running = False
_hash_status = {
    "state": "idle",
    "files_total": 0,
    "files_processed": 0,
    "current_file": None,
}


def compute_quick_signature(filepath: str) -> Optional[str]:
    """
    Compute quick signature: size + MD5 of first and last 1MB.
    Format: "size:first_hash:last_hash"
    """
    try:
        size = os.path.getsize(filepath)
        
        with open(filepath, 'rb') as f:
            # Read first chunk
            first_chunk = f.read(QUICK_SIG_SIZE)
            first_hash = hashlib.md5(first_chunk).hexdigest()[:16]
            
            # Read last chunk (may overlap with first for small files)
            if size > QUICK_SIG_SIZE:
                f.seek(-QUICK_SIG_SIZE, 2)  # Seek from end
                last_chunk = f.read(QUICK_SIG_SIZE)
            else:
                last_chunk = first_chunk
            last_hash = hashlib.md5(last_chunk).hexdigest()[:16]
        
        return f"{size}:{first_hash}:{last_hash}"
    except (OSError, PermissionError):
        return None


def compute_full_hash(filepath: str) -> Optional[str]:
    """Compute full SHA-256 hash of file."""
    try:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, PermissionError):
        return None


async def hash_file(file_id: int) -> dict:
    """Hash a single file and update database."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT f.path FROM files f WHERE f.id = ?",
            (file_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return {"error": "File not found"}
        
        filepath = row["path"]
        
        # Update status to computing
        await db.execute(
            "UPDATE files SET hash_status = 'computing' WHERE id = ?",
            (file_id,)
        )
        await db.commit()
        
        # Compute hashes (run in executor to not block)
        loop = asyncio.get_event_loop()
        quick_sig = await loop.run_in_executor(None, compute_quick_signature, filepath)
        full_hash = await loop.run_in_executor(None, compute_full_hash, filepath)
        
        if quick_sig and full_hash:
            await db.execute(
                """UPDATE files SET quick_sig = ?, full_hash = ?, hash_status = 'complete'
                   WHERE id = ?""",
                (quick_sig, full_hash, file_id)
            )
            status = "complete"
        else:
            await db.execute(
                "UPDATE files SET hash_status = 'error' WHERE id = ?",
                (file_id,)
            )
            status = "error"
        
        await db.commit()
        
        return {
            "file_id": file_id,
            "quick_sig": quick_sig,
            "full_hash": full_hash,
            "status": status
        }


async def run_hash_queue() -> None:
    """Process the hash queue in background."""
    global _hash_running, _hash_status, _hash_queue
    
    _hash_running = True
    _hash_status["state"] = "running"
    _hash_status["files_total"] = len(_hash_queue)
    _hash_status["files_processed"] = 0
    
    while _hash_queue and _hash_running:
        file_id = _hash_queue.pop(0)
        
        async with get_db() as db:
            cursor = await db.execute("SELECT path FROM files WHERE id = ?", (file_id,))
            row = await cursor.fetchone()
            if row:
                _hash_status["current_file"] = row["path"]
        
        await hash_file(file_id)
        _hash_status["files_processed"] += 1
    
    _hash_running = False
    _hash_status["state"] = "complete" if not _hash_queue else "stopped"
    _hash_status["current_file"] = None


def start_hash_computation(file_ids: Optional[list[int]] = None) -> bool:
    """Start hashing files. If no file_ids provided, hash all pending files."""
    global _hash_queue, _hash_running
    
    if _hash_running:
        return False
    
    if file_ids:
        _hash_queue = file_ids.copy()
    
    asyncio.create_task(run_hash_queue())
    return True


async def queue_pending_files() -> int:
    """Add all files with pending hash status to queue."""
    global _hash_queue
    
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM files WHERE hash_status = 'pending' OR hash_status IS NULL"
        )
        rows = await cursor.fetchall()
        _hash_queue = [row["id"] for row in rows]
        return len(_hash_queue)


def get_hash_status() -> dict:
    """Get current hash queue status."""
    return {**_hash_status, "queue_size": len(_hash_queue)}


def stop_hashing() -> bool:
    """Stop hash processing."""
    global _hash_running
    if _hash_running:
        _hash_running = False
        return True
    return False
