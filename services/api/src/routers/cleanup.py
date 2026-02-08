"""API router for cleanup recommendations and quarantine."""

import os
import shutil
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from ..database import get_db


router = APIRouter(prefix="/cleanup", tags=["cleanup"])


class QuarantineRequest(BaseModel):
    file_ids: list[int]
    quarantine_path: Optional[str] = None  # Default: {drive}/.quarantine/


@router.get("/recommendations")
async def get_deletion_recommendations(
    min_copies: int = Query(3, ge=3),
    limit: int = Query(100, ge=1, le=500)
) -> dict:
    """
    Get deletion recommendations for items with 3+ copies.
    Never auto-deletes - only recommends files to quarantine.
    
    Selection logic:
    - Keep files on preferred drives
    - Recommend deleting duplicates on non-preferred drives
    - If no preference, keep largest/oldest file
    """
    async with get_db() as db:
        # Get items with 3+ copies
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.title,
                mi.type,
                COUNT(mif.file_id) as copy_count
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            GROUP BY mi.id
            HAVING copy_count >= ?
            ORDER BY copy_count DESC
            LIMIT ?
            """,
            (min_copies, limit)
        )
        items = [dict(row) for row in await cursor.fetchall()]
        
        recommendations = []
        
        for item in items:
            # Get all files for this item
            cursor = await db.execute(
                """
                SELECT f.id, f.path, f.size, f.mtime, r.drive_id, d.mount_path,
                       mif.is_primary
                FROM files f
                JOIN media_item_files mif ON f.id = mif.file_id
                JOIN roots r ON f.root_id = r.id
                JOIN drives d ON r.drive_id = d.id
                WHERE mif.media_item_id = ?
                ORDER BY mif.is_primary DESC, f.size DESC
                """,
                (item["item_id"],)
            )
            files = [dict(row) for row in await cursor.fetchall()]
            
            # Get preferred drives
            cursor = await db.execute(
                """
                SELECT drive_id FROM user_rules 
                WHERE rule_type IN ('prefer_all', 'prefer_movie', 'prefer_tv')
                """
            )
            preferred_drives = {row["drive_id"] for row in await cursor.fetchall()}
            
            # Determine which to keep vs delete
            keep = []
            delete = []
            
            for f in files:
                if f["is_primary"]:
                    keep.append(f)
                elif f["drive_id"] in preferred_drives:
                    keep.append(f)
                else:
                    delete.append(f)
            
            # Ensure we keep at least 2 copies
            while len(keep) < 2 and delete:
                keep.append(delete.pop(0))
            
            if delete:
                total_savings = sum(f["size"] or 0 for f in delete)
                recommendations.append({
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "type": item["type"],
                    "total_copies": item["copy_count"],
                    "keep_count": len(keep),
                    "delete_count": len(delete),
                    "savings_bytes": total_savings,
                    "files_to_delete": [
                        {
                            "id": f["id"],
                            "path": f["path"],
                            "size": f["size"],
                            "drive": f["mount_path"]
                        }
                        for f in delete
                    ],
                    "files_to_keep": [
                        {
                            "id": f["id"],
                            "path": f["path"],
                            "drive": f["mount_path"]
                        }
                        for f in keep
                    ]
                })
        
        total_savings = sum(r["savings_bytes"] for r in recommendations)
        
        return {
            "recommendations": recommendations,
            "total_items": len(recommendations),
            "total_files_to_delete": sum(r["delete_count"] for r in recommendations),
            "total_savings_bytes": total_savings,
            "total_savings_gb": round(total_savings / (1024**3), 2)
        }


@router.post("/quarantine")
async def quarantine_files(request: QuarantineRequest) -> dict:
    """
    Move files to quarantine folder (reversible delete).
    Files are moved to {drive}/.quarantine/{date}/{original_path}
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    
    async with get_db() as db:
        moved = []
        errors = []
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        for file_id in request.file_ids:
            cursor = await db.execute(
                """
                SELECT f.id, f.path, r.drive_id, d.mount_path
                FROM files f
                JOIN roots r ON f.root_id = r.id
                JOIN drives d ON r.drive_id = d.id
                WHERE f.id = ?
                """,
                (file_id,)
            )
            file_info = await cursor.fetchone()
            
            if not file_info:
                errors.append({"file_id": file_id, "error": "File not found"})
                continue
            
            source_path = file_info["path"]
            drive_mount = file_info["mount_path"]
            
            if not os.path.exists(source_path):
                errors.append({"file_id": file_id, "error": "File does not exist on disk"})
                continue
            
            # Build quarantine path
            if request.quarantine_path:
                quarantine_base = request.quarantine_path
            else:
                quarantine_base = os.path.join(drive_mount, ".quarantine", date_str)
            
            # Preserve relative path structure
            rel_path = os.path.relpath(source_path, drive_mount)
            quarantine_dest = os.path.join(quarantine_base, rel_path)
            
            try:
                os.makedirs(os.path.dirname(quarantine_dest), exist_ok=True)
                shutil.move(source_path, quarantine_dest)
                
                # Update database - mark file as quarantined
                await db.execute(
                    "UPDATE files SET path = ?, hash_status = 'quarantined' WHERE id = ?",
                    (quarantine_dest, file_id)
                )
                
                moved.append({
                    "file_id": file_id,
                    "original_path": source_path,
                    "quarantine_path": quarantine_dest
                })
            except Exception as e:
                errors.append({"file_id": file_id, "error": str(e)})
        
        await db.commit()
        
        return {
            "moved": len(moved),
            "errors": len(errors),
            "files": moved,
            "error_details": errors
        }


@router.post("/restore")
async def restore_from_quarantine(file_ids: list[int]) -> dict:
    """Restore quarantined files to their original locations."""
    async with get_db() as db:
        restored = []
        errors = []
        
        for file_id in file_ids:
            cursor = await db.execute(
                "SELECT id, path FROM files WHERE id = ? AND hash_status = 'quarantined'",
                (file_id,)
            )
            file_info = await cursor.fetchone()
            
            if not file_info:
                errors.append({"file_id": file_id, "error": "File not found or not quarantined"})
                continue
            
            quarantine_path = file_info["path"]
            
            # Extract original path from quarantine structure
            # Path format: {drive}/.quarantine/{date}/{relative_path}
            parts = quarantine_path.split(".quarantine")
            if len(parts) == 2:
                drive = parts[0].rstrip(os.sep)
                # Skip date folder
                rel_parts = parts[1].split(os.sep)[2:]  # Skip empty + date
                original_path = os.path.join(drive, *rel_parts)
            else:
                errors.append({"file_id": file_id, "error": "Cannot determine original path"})
                continue
            
            try:
                os.makedirs(os.path.dirname(original_path), exist_ok=True)
                shutil.move(quarantine_path, original_path)
                
                await db.execute(
                    "UPDATE files SET path = ?, hash_status = 'pending' WHERE id = ?",
                    (original_path, file_id)
                )
                
                restored.append({
                    "file_id": file_id,
                    "restored_path": original_path
                })
            except Exception as e:
                errors.append({"file_id": file_id, "error": str(e)})
        
        await db.commit()
        
        return {
            "restored": len(restored),
            "errors": len(errors),
            "files": restored,
            "error_details": errors
        }
