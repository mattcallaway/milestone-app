"""API router for per-operation safety overrides (Expert Mode only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..expert import require_expert

router = APIRouter(prefix="/overrides", tags=["overrides"])


class OverrideCreateRequest(BaseModel):
    override_type: str  # 'skip_verification', 'ignore_domain', 'force_write'
    operation_id: Optional[int] = None
    reason: str


VALID_OVERRIDE_TYPES = {
    "skip_verification": "Skip hash verification after copy",
    "ignore_domain": "Ignore failure-domain requirement for placement",
    "force_write": "Allow write to read-only configured drive",
}


@router.post("/create")
async def create_override(
    request: OverrideCreateRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Create a per-operation safety override.
    
    Each override:
    - Is logged to audit_log
    - Shows prominent warning
    - Auto-resets after operation completes
    """
    if request.override_type not in VALID_OVERRIDE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid override type. Valid types: {list(VALID_OVERRIDE_TYPES.keys())}"
        )
    
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO safety_overrides 
               (operation_id, override_type, reason, auto_reset)
               VALUES (?, ?, ?, 1)""",
            (request.operation_id, request.override_type, request.reason)
        )
        override_id = cursor.lastrowid
        
        # Log to audit
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode, override_used)
               VALUES ('override_create', 'safety_override', ?, ?, 1, ?)""",
            (override_id, 
             f"Type: {request.override_type}, Reason: {request.reason}",
             request.override_type)
        )
        await db.commit()
        
        return {
            "override_id": override_id,
            "override_type": request.override_type,
            "description": VALID_OVERRIDE_TYPES[request.override_type],
            "warning": f"⚠️ Safety override active: {VALID_OVERRIDE_TYPES[request.override_type]}. "
                       "This will auto-reset after the operation completes.",
            "auto_reset": True,
        }


@router.get("/active")
async def list_active_overrides() -> dict:
    """List all currently active (non-reset) safety overrides."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM safety_overrides
               WHERE reset_at IS NULL
               ORDER BY created_at DESC"""
        )
        overrides = [dict(row) for row in await cursor.fetchall()]
        
        # Add descriptions
        for o in overrides:
            o["description"] = VALID_OVERRIDE_TYPES.get(o["override_type"], "Unknown")
        
        return {"overrides": overrides, "total": len(overrides)}


@router.post("/reset/{override_id}")
async def reset_override(
    override_id: int,
    _expert: bool = Depends(require_expert)
) -> dict:
    """Manually reset (deactivate) a safety override."""
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE safety_overrides 
               SET reset_at = CURRENT_TIMESTAMP
               WHERE id = ? AND reset_at IS NULL""",
            (override_id,)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Override not found or already reset")
        
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('override_reset', 'safety_override', ?, 'Manual reset', 1)""",
            (override_id,)
        )
        await db.commit()
        
        return {"message": "Override reset", "override_id": override_id}
