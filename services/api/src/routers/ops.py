"""API router for operations queue."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from ..database import get_db
from ..queue import (
    get_queue_status, start_queue, stop_queue, pause_queue, resume_queue,
    pause_operation, resume_operation, cancel_operation, set_concurrency
)
from ..copier import create_copy_operation, get_destination_drives


router = APIRouter(prefix="/ops", tags=["operations"])


class CopyRequest(BaseModel):
    source_file_id: int
    dest_drive_id: Optional[int] = None
    dest_path: Optional[str] = None
    verify_hash: bool = True


class BatchCopyRequest(BaseModel):
    media_item_id: int
    verify_hash: bool = True


@router.get("")
async def list_operations(
    status: Optional[str] = None,
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
) -> dict:
    """List operations with filters."""
    async with get_db() as db:
        where_clauses = []
        params = []
        
        if status:
            where_clauses.append("o.status = ?")
            params.append(status)
        
        if type:
            where_clauses.append("o.type = ?")
            params.append(type)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        # Get total count
        cursor = await db.execute(
            f"SELECT COUNT(*) as count FROM operations o {where_sql}",
            params
        )
        total = (await cursor.fetchone())["count"]
        
        # Get paginated results
        offset = (page - 1) * page_size
        cursor = await db.execute(
            f"""
            SELECT o.*, f.path as source_path, d.mount_path as dest_drive_path
            FROM operations o
            LEFT JOIN files f ON o.source_file_id = f.id
            LEFT JOIN drives d ON o.dest_drive_id = d.id
            {where_sql}
            ORDER BY o.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset]
        )
        
        operations = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "operations": operations,
            "total": total,
            "page": page,
            "page_size": page_size
        }


@router.get("/queue/status")
async def queue_status_endpoint() -> dict:
    """Get queue status."""
    status = get_queue_status()
    
    async with get_db() as db:
        # Count pending operations
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM operations WHERE status = 'pending'"
        )
        pending = (await cursor.fetchone())["count"]
        
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM operations WHERE status = 'running'"
        )
        running = (await cursor.fetchone())["count"]
    
    return {
        **status,
        "pending_count": pending,
        "running_count": running
    }


@router.post("/queue/start")
async def start_queue_endpoint() -> dict:
    """Start the queue worker."""
    start_queue()
    return {"message": "Queue started", "status": get_queue_status()}


@router.post("/queue/stop")
async def stop_queue_endpoint() -> dict:
    """Stop the queue worker."""
    stop_queue()
    return {"message": "Queue stopped", "status": get_queue_status()}


@router.post("/queue/pause")
async def pause_queue_endpoint() -> dict:
    """Pause queue processing."""
    pause_queue()
    return {"message": "Queue paused", "status": get_queue_status()}


@router.post("/queue/resume")
async def resume_queue_endpoint() -> dict:
    """Resume queue processing."""
    resume_queue()
    return {"message": "Queue resumed", "status": get_queue_status()}


@router.post("/queue/concurrency")
async def set_concurrency_endpoint(limit: int = Query(2, ge=1, le=10)) -> dict:
    """Set queue concurrency limit."""
    set_concurrency(limit)
    return {"message": f"Concurrency set to {limit}", "status": get_queue_status()}


@router.get("/{op_id}")
async def get_operation(op_id: int) -> dict:
    """Get operation details."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT o.*, f.path as source_path, d.mount_path as dest_drive_path
            FROM operations o
            LEFT JOIN files f ON o.source_file_id = f.id
            LEFT JOIN drives d ON o.dest_drive_id = d.id
            WHERE o.id = ?
            """,
            (op_id,)
        )
        op = await cursor.fetchone()
        
        if not op:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        return dict(op)


@router.post("/copy")
async def create_copy(request: CopyRequest) -> dict:
    """Create a copy operation."""
    try:
        op = await create_copy_operation(
            source_file_id=request.source_file_id,
            dest_drive_id=request.dest_drive_id,
            dest_path=request.dest_path,
            verify_hash=request.verify_hash
        )
        return {"message": "Copy operation created", "operation": op}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/copy/batch")
async def create_batch_copy(request: BatchCopyRequest) -> dict:
    """Create copy operations for all files in a media item (for backup)."""
    async with get_db() as db:
        # Get all files for this media item
        cursor = await db.execute(
            """
            SELECT f.id, f.path, f.size
            FROM media_item_files mif
            JOIN files f ON mif.file_id = f.id
            WHERE mif.media_item_id = ?
            """,
            (request.media_item_id,)
        )
        files = [dict(row) for row in await cursor.fetchall()]
        
        if not files:
            raise HTTPException(status_code=404, detail="No files found for media item")
    
    created = []
    errors = []
    
    for file in files:
        try:
            op = await create_copy_operation(
                source_file_id=file["id"],
                verify_hash=request.verify_hash
            )
            created.append(op)
        except Exception as e:
            errors.append({"file_id": file["id"], "error": str(e)})
    
    return {
        "message": f"Created {len(created)} copy operations",
        "operations": created,
        "errors": errors
    }


@router.get("/destinations/{file_id}")
async def get_destinations(file_id: int) -> dict:
    """Get suitable destination drives for a file."""
    drives = await get_destination_drives(file_id)
    return {"drives": drives}


@router.post("/{op_id}/pause")
async def pause_op(op_id: int) -> dict:
    """Pause an operation."""
    success = await pause_operation(op_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause this operation")
    return {"message": "Operation paused", "id": op_id}


@router.post("/{op_id}/resume")
async def resume_op(op_id: int) -> dict:
    """Resume a paused operation."""
    success = await resume_operation(op_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume this operation")
    return {"message": "Operation resumed", "id": op_id}


@router.post("/{op_id}/cancel")
async def cancel_op(op_id: int) -> dict:
    """Cancel an operation."""
    success = await cancel_operation(op_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this operation")
    return {"message": "Operation cancelled", "id": op_id}


# User rules management

class RuleRequest(BaseModel):
    rule_type: str  # 'denylist', 'prefer_movie', 'prefer_tv', 'prefer_all'
    drive_id: int
    priority: int = 0


@router.get("/rules")
async def list_rules() -> dict:
    """List user rules."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT r.*, d.mount_path, d.volume_label
            FROM user_rules r
            JOIN drives d ON r.drive_id = d.id
            ORDER BY r.rule_type, r.priority DESC
            """
        )
        rules = [dict(row) for row in await cursor.fetchall()]
        return {"rules": rules}


@router.post("/rules")
async def create_rule(request: RuleRequest) -> dict:
    """Create a user rule."""
    valid_types = ["denylist", "prefer_movie", "prefer_tv", "prefer_all"]
    if request.rule_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid rule type. Must be one of: {valid_types}")
    
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO user_rules (rule_type, drive_id, priority) VALUES (?, ?, ?)",
            (request.rule_type, request.drive_id, request.priority)
        )
        await db.commit()
        return {"message": "Rule created", "id": cursor.lastrowid}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int) -> dict:
    """Delete a user rule."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM user_rules WHERE id = ?", (rule_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"message": "Rule deleted", "id": rule_id}
