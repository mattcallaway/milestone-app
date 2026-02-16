"""API router for placement strategy overrides (Expert Mode only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..expert import require_expert

router = APIRouter(prefix="/placement", tags=["placement"])


class PinRequest(BaseModel):
    media_item_id: int
    drive_id: int


class TargetCopiesRequest(BaseModel):
    target_copies: int = 2


@router.post("/pin")
async def pin_item_to_drive(
    request: PinRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """Pin a media item to a specific drive (Expert Mode only)."""
    async with get_db() as db:
        # Validate item and drive exist
        cursor = await db.execute("SELECT id FROM media_items WHERE id = ?", (request.media_item_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Media item not found")
        
        cursor = await db.execute("SELECT id FROM drives WHERE id = ?", (request.drive_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Drive not found")
        
        try:
            await db.execute(
                "INSERT INTO item_pins (media_item_id, drive_id) VALUES (?, ?)",
                (request.media_item_id, request.drive_id)
            )
            await db.commit()
        except Exception:
            raise HTTPException(status_code=409, detail="Item already pinned to this drive")
        
        # Log
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('pin_create', 'media_item', ?, ?, 1)""",
            (request.media_item_id, f"Pinned to drive {request.drive_id}")
        )
        await db.commit()
        
        return {"message": "Item pinned to drive", **request.model_dump()}


@router.post("/unpin")
async def unpin_item_from_drive(
    request: PinRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """Remove a pin from a media item."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM item_pins WHERE media_item_id = ? AND drive_id = ?",
            (request.media_item_id, request.drive_id)
        )
        await db.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Pin not found")
        
        return {"message": "Pin removed", **request.model_dump()}


@router.get("/pins")
async def list_pins() -> dict:
    """List all item pins."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT ip.*, mi.title, mi.type, d.mount_path, d.volume_label
               FROM item_pins ip
               JOIN media_items mi ON ip.media_item_id = mi.id
               JOIN drives d ON ip.drive_id = d.id
               ORDER BY ip.created_at DESC"""
        )
        pins = [dict(row) for row in await cursor.fetchall()]
        return {"pins": pins, "total": len(pins)}


@router.put("/target-copies")
async def set_target_copies(
    request: TargetCopiesRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Set the target copy count (default 2).
    
    Expert Mode allows setting to 1 (dangerous) or higher than 2.
    Normal mode enforces minimum of 2.
    """
    if request.target_copies < 1:
        raise HTTPException(status_code=400, detail="Target copies must be at least 1")
    
    if request.target_copies == 1:
        # Extra warning for single-copy mode
        pass
    
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('target_copies', ?)",
            (str(request.target_copies),)
        )
        await db.commit()
        
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, details, expert_mode)
               VALUES ('target_copies_change', 'settings', ?, 1)""",
            (f"Target copies set to {request.target_copies}",)
        )
        await db.commit()
    
    warning = None
    if request.target_copies == 1:
        warning = "WARNING: Single-copy mode provides NO redundancy. Data loss is likely on drive failure."
    
    return {
        "message": f"Target copies set to {request.target_copies}",
        "target_copies": request.target_copies,
        "warning": warning,
    }


@router.get("/impact")
async def get_placement_impact() -> dict:
    """Show current placement strategy impact on redundancy and space."""
    async with get_db() as db:
        # Get target copies setting
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'target_copies'")
        row = await cursor.fetchone()
        target = int(row["value"]) if row else 2
        
        # Items below target
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt FROM (
                SELECT mi.id, COUNT(DISTINCT mif.file_id) as copies
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                GROUP BY mi.id
                HAVING copies < ?
            )""",
            (target,)
        )
        below_target = (await cursor.fetchone())["cnt"]
        
        # Items at target
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt FROM (
                SELECT mi.id, COUNT(DISTINCT mif.file_id) as copies
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                GROUP BY mi.id
                HAVING copies = ?
            )""",
            (target,)
        )
        at_target = (await cursor.fetchone())["cnt"]
        
        # Items above target
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt FROM (
                SELECT mi.id, COUNT(DISTINCT mif.file_id) as copies
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                GROUP BY mi.id
                HAVING copies > ?
            )""",
            (target,)
        )
        above_target = (await cursor.fetchone())["cnt"]
        
        # Pinned items count
        cursor = await db.execute("SELECT COUNT(DISTINCT media_item_id) as cnt FROM item_pins")
        pinned = (await cursor.fetchone())["cnt"]
        
        return {
            "target_copies": target,
            "below_target": below_target,
            "at_target": at_target,
            "above_target": above_target,
            "pinned_items": pinned,
        }
