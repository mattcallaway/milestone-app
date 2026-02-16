"""API router for drive evacuation (Expert Mode only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..config import is_write_enabled
from ..expert import require_expert

router = APIRouter(prefix="/evacuation", tags=["evacuation"])

# Runtime evacuation state
_evacuation_state = {
    "active": False,
    "drive_id": None,
    "progress": None,
}


class EvacuationPlanRequest(BaseModel):
    drive_id: int


class EvacuationExecuteRequest(BaseModel):
    drive_id: int


@router.post("/plan")
async def plan_evacuation(
    request: EvacuationPlanRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Plan migration of all required copies off a selected drive.
    
    Analyzes which items need copies on other drives to maintain
    redundancy after the source drive is removed.
    """
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM drives WHERE id = ?", (request.drive_id,))
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")
        
        # Find items that only exist on this drive
        cursor = await db.execute(
            """SELECT mi.id as item_id, mi.type, mi.title,
                      COUNT(DISTINCT mif.file_id) as total_copies,
                      COUNT(DISTINCT CASE WHEN r.drive_id = ? THEN mif.file_id END) as copies_on_drive,
                      COUNT(DISTINCT CASE WHEN r.drive_id != ? THEN mif.file_id END) as copies_elsewhere
               FROM media_items mi
               JOIN media_item_files mif ON mi.id = mif.media_item_id
               JOIN files f ON mif.file_id = f.id
               JOIN roots r ON f.root_id = r.id
               GROUP BY mi.id
               HAVING copies_on_drive > 0
               ORDER BY copies_elsewhere ASC, total_copies ASC""",
            (request.drive_id, request.drive_id)
        )
        affected_items = [dict(row) for row in await cursor.fetchall()]
        
        # Categorize risk
        unique_to_drive = [i for i in affected_items if i["copies_elsewhere"] == 0]
        needs_copy = [i for i in affected_items if i["copies_elsewhere"] == 1]
        safe = [i for i in affected_items if i["copies_elsewhere"] >= 2]
        
        # Calculate total size
        cursor = await db.execute(
            """SELECT COALESCE(SUM(f.size), 0) as total_size
               FROM files f
               JOIN roots r ON f.root_id = r.id
               WHERE r.drive_id = ?""",
            (request.drive_id,)
        )
        total_size = (await cursor.fetchone())["total_size"]
        
        # Get available destination drives
        cursor = await db.execute(
            """SELECT d.id, d.mount_path, d.volume_label, d.free_space,
                      fd.name as domain_name
               FROM drives d
               LEFT JOIN failure_domains fd ON d.failure_domain_id = fd.id
               WHERE d.id != ?""",
            (request.drive_id,)
        )
        destinations = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "drive": dict(drive),
            "summary": {
                "total_items_on_drive": len(affected_items),
                "unique_to_drive": len(unique_to_drive),
                "needs_additional_copy": len(needs_copy),
                "already_safe": len(safe),
                "total_size": total_size,
            },
            "risk": {
                "critical": unique_to_drive[:20],
                "warning": needs_copy[:20],
            },
            "available_destinations": destinations,
        }


@router.post("/execute")
async def execute_evacuation(
    request: EvacuationExecuteRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Execute drive evacuation — queue copy operations to migrate data.
    
    Prioritizes items unique to the evacuating drive.
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    if _evacuation_state["active"]:
        raise HTTPException(status_code=409, detail="An evacuation is already in progress")
    
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM drives WHERE id = ?", (request.drive_id,))
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")
        
        # Find items needing evacuation
        cursor = await db.execute(
            """SELECT mi.id as item_id, f.id as file_id, f.path, f.size
               FROM media_items mi
               JOIN media_item_files mif ON mi.id = mif.media_item_id
               JOIN files f ON mif.file_id = f.id
               JOIN roots r ON f.root_id = r.id
               WHERE r.drive_id = ?
               AND mi.id IN (
                   SELECT mi2.id
                   FROM media_items mi2
                   JOIN media_item_files mif2 ON mi2.id = mif2.media_item_id
                   JOIN files f2 ON mif2.file_id = f2.id
                   JOIN roots r2 ON f2.root_id = r2.id
                   GROUP BY mi2.id
                   HAVING COUNT(DISTINCT CASE WHEN r2.drive_id != ? THEN mif2.file_id END) < 2
               )
               ORDER BY f.size DESC""",
            (request.drive_id, request.drive_id)
        )
        files_to_evacuate = [dict(row) for row in await cursor.fetchall()]
        
        # Queue copy operations
        queued = 0
        for file_info in files_to_evacuate:
            await db.execute(
                """INSERT INTO operations (type, status, source_file_id, total_size)
                   VALUES ('copy', 'pending', ?, ?)""",
                (file_info["file_id"], file_info["size"])
            )
            queued += 1
        
        # Log evacuation
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('evacuation_start', 'drive', ?, ?, 1)""",
            (request.drive_id, f"Queued {queued} copy operations")
        )
        await db.commit()
        
        _evacuation_state["active"] = True
        _evacuation_state["drive_id"] = request.drive_id
        _evacuation_state["progress"] = {"queued": queued, "completed": 0}
        
        return {
            "message": f"Evacuation started: {queued} operations queued",
            "drive_id": request.drive_id,
            "operations_queued": queued,
        }


@router.get("/status")
async def get_evacuation_status() -> dict:
    """Get current evacuation progress and risk status."""
    return {
        "active": _evacuation_state["active"],
        "drive_id": _evacuation_state["drive_id"],
        "progress": _evacuation_state["progress"],
    }
