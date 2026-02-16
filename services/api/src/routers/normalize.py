"""API router for library normalization (Expert Mode only)."""

import os
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..config import is_write_enabled
from ..expert import require_expert

router = APIRouter(prefix="/normalize", tags=["normalize"])


# Canonical path patterns
MOVIE_PATTERN = re.compile(
    r"^(.+?)\s*\((\d{4})\)",
    re.IGNORECASE
)
TV_PATTERN = re.compile(
    r"^(.+?)\s*[Ss](\d{1,2})[Ee](\d{1,2})",
    re.IGNORECASE
)


@router.get("/suggestions")
async def get_normalization_suggestions(
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Scan for non-canonical folder structures and suggest reorganization.
    
    Canonical structures:
    - Movies → /Movies/Title (Year)/file.ext
    - TV → /TV/Show/Season XX/file.ext
    """
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT mi.id as item_id, mi.type, mi.title, mi.year,
                      mi.season, mi.episode, f.path, f.id as file_id,
                      r.path as root_path
               FROM media_items mi
               JOIN media_item_files mif ON mi.id = mif.media_item_id
               JOIN files f ON mif.file_id = f.id
               JOIN roots r ON f.root_id = r.id
               LIMIT 200"""
        )
        items = [dict(row) for row in await cursor.fetchall()]
        
        suggestions = []
        
        for item in items:
            file_path = item["path"]
            root_path = item["root_path"]
            filename = os.path.basename(file_path)
            current_dir = os.path.dirname(file_path)
            
            suggested_dir = None
            
            if item["type"] == "movie" and item["title"]:
                year = item["year"] or "Unknown"
                canonical = os.path.join(root_path, "Movies", f"{item['title']} ({year})")
                if not current_dir.endswith(f"{item['title']} ({year})"):
                    suggested_dir = canonical
            
            elif item["type"] == "tv_episode" and item["title"]:
                season_num = item["season"] or 1
                season_dir = f"Season {season_num:02d}"
                canonical = os.path.join(root_path, "TV", item["title"], season_dir)
                if season_dir not in current_dir:
                    suggested_dir = canonical
            
            if suggested_dir and suggested_dir != current_dir:
                suggestions.append({
                    "item_id": item["item_id"],
                    "file_id": item["file_id"],
                    "current_path": file_path,
                    "suggested_path": os.path.join(suggested_dir, filename),
                    "type": item["type"],
                    "title": item["title"],
                })
        
        return {
            "suggestions": suggestions,
            "total": len(suggestions),
        }


class NormalizePreviewRequest(BaseModel):
    item_ids: list[int] = []


@router.post("/preview")
async def preview_normalization(
    request: NormalizePreviewRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """Show planned renames without executing them."""
    suggestions = await get_normalization_suggestions()
    
    if request.item_ids:
        filtered = [s for s in suggestions["suggestions"] if s["item_id"] in request.item_ids]
    else:
        filtered = suggestions["suggestions"]
    
    return {
        "planned_moves": filtered,
        "total": len(filtered),
    }


class NormalizeExecuteRequest(BaseModel):
    item_ids: list[int]


@router.post("/execute")
async def execute_normalization(
    request: NormalizeExecuteRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Queue move operations for normalization.
    
    No automatic execution — creates plan entries that must be confirmed.
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    async with get_db() as db:
        # Create a plan for the moves
        cursor = await db.execute(
            "INSERT INTO plans (name, plan_type, status) VALUES ('Library Normalization', 'move', 'draft')"
        )
        plan_id = cursor.lastrowid
        
        queued = 0
        suggestions = await get_normalization_suggestions()
        
        for s in suggestions["suggestions"]:
            if s["item_id"] in request.item_ids:
                await db.execute(
                    """INSERT INTO plan_items (plan_id, action, source_file_id, dest_path)
                       VALUES (?, 'move', ?, ?)""",
                    (plan_id, s["file_id"], s["suggested_path"])
                )
                queued += 1
        
        await db.execute(
            "UPDATE plans SET item_count = ? WHERE id = ?",
            (queued, plan_id)
        )
        
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('normalize_plan', 'plan', ?, ?, 1)""",
            (plan_id, f"Created normalization plan with {queued} moves")
        )
        await db.commit()
        
        return {
            "message": f"Normalization plan created with {queued} moves",
            "plan_id": plan_id,
            "moves_planned": queued,
        }
