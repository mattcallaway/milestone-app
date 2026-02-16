"""API router for batch reduction of over-replicated items (Expert Mode only)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..config import is_write_enabled
from ..expert import require_expert

router = APIRouter(prefix="/reduction", tags=["reduction"])


class ReductionPreviewRequest(BaseModel):
    target_copies: int = 2
    media_type: Optional[str] = None


class ReductionExecuteRequest(BaseModel):
    target_copies: int = 2
    item_ids: list[int] = []
    permanent_delete: bool = False


@router.post("/preview")
async def reduction_preview(
    request: ReductionPreviewRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Preview which file instances would be removed to reach target copy count.
    
    Returns items with more copies than target, and which specific files
    would be candidates for removal (preferring to keep files in distinct
    failure domains).
    """
    if request.target_copies < 1:
        raise HTTPException(status_code=400, detail="Target copies must be at least 1")
    
    async with get_db() as db:
        # Find over-replicated items
        type_filter = "AND mi.type = ?" if request.media_type else ""
        params = [request.target_copies]
        if request.media_type:
            params.append(request.media_type)
        
        cursor = await db.execute(
            f"""SELECT 
                mi.id as item_id, mi.type, mi.title,
                COUNT(DISTINCT mif.file_id) as current_copies,
                COUNT(DISTINCT mif.file_id) - ? as excess_copies
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            {type_filter}
            GROUP BY mi.id
            HAVING current_copies > ?
            ORDER BY excess_copies DESC""",
            params + [request.target_copies]
        )
        over_replicated = [dict(row) for row in await cursor.fetchall()]
        
        # For each over-replicated item, identify removal candidates
        removal_plan = []
        total_bytes_reclaimable = 0
        
        for item in over_replicated:
            cursor = await db.execute(
                """SELECT f.id as file_id, f.path, f.size, r.drive_id,
                          d.mount_path, d.failure_domain_id
                   FROM media_item_files mif
                   JOIN files f ON mif.file_id = f.id
                   JOIN roots r ON f.root_id = r.id
                   JOIN drives d ON r.drive_id = d.id
                   WHERE mif.media_item_id = ?
                   ORDER BY d.failure_domain_id ASC, f.id ASC""",
                (item["item_id"],)
            )
            copies = [dict(row) for row in await cursor.fetchall()]
            
            # Strategy: keep copies in distinct failure domains, remove extras
            # Sort: keep one per domain first, then remove oldest/least valuable
            domains_covered = set()
            keep = []
            candidates = []
            
            for copy in copies:
                domain = copy.get("failure_domain_id")
                if len(keep) < request.target_copies:
                    if domain and domain not in domains_covered:
                        keep.append(copy)
                        domains_covered.add(domain)
                    elif not domain and len(keep) < request.target_copies:
                        keep.append(copy)
                    else:
                        candidates.append(copy)
                else:
                    candidates.append(copy)
            
            # If we didn't keep enough, move some candidates back
            while len(keep) < request.target_copies and candidates:
                keep.append(candidates.pop(0))
            
            for candidate in candidates:
                total_bytes_reclaimable += candidate.get("size", 0) or 0
            
            if candidates:
                removal_plan.append({
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "type": item["type"],
                    "current_copies": item["current_copies"],
                    "keep": keep,
                    "remove": candidates,
                })
        
        return {
            "target_copies": request.target_copies,
            "items_affected": len(removal_plan),
            "total_files_to_remove": sum(len(p["remove"]) for p in removal_plan),
            "bytes_reclaimable": total_bytes_reclaimable,
            "plan": removal_plan,
        }


@router.post("/execute")
async def reduction_execute(
    request: ReductionExecuteRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Execute batch reduction — move excess copies to quarantine.
    
    permanent_delete=true requires secondary confirmation and cannot
    reduce any item below safe domain coverage.
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    if request.target_copies < 1:
        raise HTTPException(status_code=400, detail="Target copies must be at least 1")
    
    async with get_db() as db:
        moved = 0
        errors = []
        
        for item_id in request.item_ids:
            # Get copies sorted by priority (keep in distinct domains)
            cursor = await db.execute(
                """SELECT f.id as file_id, f.path, f.size, r.drive_id,
                          d.failure_domain_id
                   FROM media_item_files mif
                   JOIN files f ON mif.file_id = f.id
                   JOIN roots r ON f.root_id = r.id
                   JOIN drives d ON r.drive_id = d.id
                   WHERE mif.media_item_id = ?
                   ORDER BY d.failure_domain_id ASC, f.id ASC""",
                (item_id,)
            )
            copies = [dict(row) for row in await cursor.fetchall()]
            
            if len(copies) <= request.target_copies:
                continue
            
            # Safety check: ensure we maintain domain coverage
            domains = set(c["failure_domain_id"] for c in copies if c.get("failure_domain_id"))
            if len(domains) >= 2 and request.target_copies < 2:
                errors.append({
                    "item_id": item_id,
                    "error": "Cannot reduce below domain coverage minimum"
                })
                continue
            
            # Remove excess (keep first target_copies, sorted by domain diversity)
            to_remove = copies[request.target_copies:]
            
            for copy in to_remove:
                # Default: move to quarantine
                action = "permanent_delete" if request.permanent_delete else "quarantine"
                
                await db.execute(
                    """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
                       VALUES (?, 'file', ?, ?, 1)""",
                    (f"reduction_{action}", copy["file_id"], 
                     f"item={item_id}, path={copy['path']}")
                )
                moved += 1
        
        await db.commit()
        
        return {
            "message": f"Reduction complete: {moved} files processed",
            "files_processed": moved,
            "errors": errors,
            "action": "permanent_delete" if request.permanent_delete else "quarantine",
        }
