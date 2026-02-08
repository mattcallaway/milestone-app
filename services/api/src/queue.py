"""Queue engine for processing file operations."""

import asyncio
import threading
from typing import Optional, Callable
from datetime import datetime
from .database import get_db


# Queue state
_queue_state = {
    "running": False,
    "paused": False,
    "concurrency": 2,
    "active_ops": set(),
    "worker_task": None,
}


def get_queue_status() -> dict:
    """Get current queue status."""
    return {
        "running": _queue_state["running"],
        "paused": _queue_state["paused"],
        "concurrency": _queue_state["concurrency"],
        "active_count": len(_queue_state["active_ops"]),
    }


async def get_pending_operations(limit: int = 10) -> list[dict]:
    """Get pending operations from database."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT o.*, f.path as source_path, f.size as file_size, d.mount_path as dest_drive
            FROM operations o
            LEFT JOIN files f ON o.source_file_id = f.id
            LEFT JOIN drives d ON o.dest_drive_id = d.id
            WHERE o.status = 'pending'
            ORDER BY o.created_at ASC
            LIMIT ?
            """,
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_operation_status(
    op_id: int,
    status: str,
    progress: Optional[int] = None,
    error: Optional[str] = None
) -> None:
    """Update operation status in database."""
    async with get_db() as db:
        updates = ["status = ?"]
        params = [status]
        
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        
        if status == "running":
            updates.append("started_at = ?")
            params.append(datetime.now().isoformat())
        elif status in ("completed", "failed", "cancelled"):
            updates.append("completed_at = ?")
            params.append(datetime.now().isoformat())
        
        params.append(op_id)
        await db.execute(
            f"UPDATE operations SET {', '.join(updates)} WHERE id = ?",
            params
        )
        await db.commit()


async def process_operation(op: dict, progress_callback: Optional[Callable] = None) -> bool:
    """Process a single operation. Returns True on success."""
    from .copier import safe_copy
    
    op_id = op["id"]
    _queue_state["active_ops"].add(op_id)
    
    try:
        await update_operation_status(op_id, "running")
        
        if op["type"] == "copy":
            success = await safe_copy(
                source_path=op["source_path"],
                dest_path=op["dest_path"],
                verify_hash=bool(op.get("verify_hash", 0)),
                progress_callback=lambda p: asyncio.create_task(
                    update_operation_status(op_id, "running", progress=p)
                ) if progress_callback is None else progress_callback(p)
            )
            
            if success:
                await update_operation_status(op_id, "completed", progress=op.get("total_size", 0))
                return True
            else:
                await update_operation_status(op_id, "failed", error="Copy failed")
                return False
        else:
            await update_operation_status(op_id, "failed", error=f"Unknown operation type: {op['type']}")
            return False
            
    except Exception as e:
        await update_operation_status(op_id, "failed", error=str(e))
        return False
    finally:
        _queue_state["active_ops"].discard(op_id)


async def queue_worker():
    """Background worker that processes the queue."""
    while _queue_state["running"]:
        if _queue_state["paused"]:
            await asyncio.sleep(1)
            continue
        
        # Check if we have room for more concurrent operations
        active_count = len(_queue_state["active_ops"])
        if active_count >= _queue_state["concurrency"]:
            await asyncio.sleep(0.5)
            continue
        
        # Get pending operations
        pending = await get_pending_operations(limit=_queue_state["concurrency"] - active_count)
        
        if not pending:
            await asyncio.sleep(2)  # Wait before checking again
            continue
        
        # Start operations concurrently
        for op in pending:
            if op["id"] not in _queue_state["active_ops"]:
                asyncio.create_task(process_operation(op))
        
        await asyncio.sleep(0.5)


def start_queue():
    """Start the queue worker."""
    if _queue_state["running"]:
        return
    
    _queue_state["running"] = True
    _queue_state["paused"] = False
    
    # Start worker in background
    loop = asyncio.get_event_loop()
    _queue_state["worker_task"] = loop.create_task(queue_worker())


def stop_queue():
    """Stop the queue worker."""
    _queue_state["running"] = False
    if _queue_state["worker_task"]:
        _queue_state["worker_task"].cancel()
        _queue_state["worker_task"] = None


def pause_queue():
    """Pause queue processing."""
    _queue_state["paused"] = True


def resume_queue():
    """Resume queue processing."""
    _queue_state["paused"] = False


def set_concurrency(limit: int):
    """Set concurrency limit."""
    _queue_state["concurrency"] = max(1, min(limit, 10))


async def pause_operation(op_id: int) -> bool:
    """Pause a specific operation."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM operations WHERE id = ?", (op_id,)
        )
        row = await cursor.fetchone()
        if row and row["status"] in ("pending", "running"):
            await update_operation_status(op_id, "paused")
            return True
    return False


async def resume_operation(op_id: int) -> bool:
    """Resume a paused operation."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM operations WHERE id = ?", (op_id,)
        )
        row = await cursor.fetchone()
        if row and row["status"] == "paused":
            await update_operation_status(op_id, "pending")
            return True
    return False


async def cancel_operation(op_id: int) -> bool:
    """Cancel an operation."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM operations WHERE id = ?", (op_id,)
        )
        row = await cursor.fetchone()
        if row and row["status"] in ("pending", "running", "paused"):
            await update_operation_status(op_id, "cancelled")
            _queue_state["active_ops"].discard(op_id)
            return True
    return False
