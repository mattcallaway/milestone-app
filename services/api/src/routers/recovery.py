"""API router for recovery and forensics tools."""

import os
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..config import is_write_enabled
from ..expert import require_expert

router = APIRouter(prefix="/recovery", tags=["recovery"])


class RepairRequest(BaseModel):
    action: str  # 'reindex' or 'remove_stale'
    file_ids: list[int] = []
    paths: list[str] = []


@router.get("/orphans")
async def detect_orphans(
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Detect orphaned files:
    - Files on disk not indexed in DB
    - DB entries for files that no longer exist on disk
    """
    async with get_db() as db:
        # Find DB entries pointing to missing files
        cursor = await db.execute(
            """SELECT f.id, f.path, f.size, r.drive_id, d.mount_path
               FROM files f
               JOIN roots r ON f.root_id = r.id
               JOIN drives d ON r.drive_id = d.id
               LIMIT 500"""
        )
        db_files = [dict(row) for row in await cursor.fetchall()]
        
        missing_on_disk = []
        for f in db_files:
            if not os.path.exists(f["path"]):
                missing_on_disk.append({
                    "file_id": f["id"],
                    "path": f["path"],
                    "drive": f["mount_path"],
                    "size": f["size"],
                })
        
        # Find files on disk not in DB (scan root dirs)
        cursor = await db.execute(
            "SELECT r.path as root_path, r.id as root_id FROM roots r WHERE r.excluded = 0"
        )
        roots = [dict(row) for row in await cursor.fetchall()]
        
        unindexed = []
        for root in roots:
            if not os.path.isdir(root["root_path"]):
                continue
            try:
                for entry in os.scandir(root["root_path"]):
                    if entry.is_file():
                        cursor = await db.execute(
                            "SELECT id FROM files WHERE path = ?", (entry.path,)
                        )
                        if not await cursor.fetchone():
                            unindexed.append({
                                "path": entry.path,
                                "size": entry.stat().st_size,
                                "root_id": root["root_id"],
                            })
                            if len(unindexed) >= 100:
                                break
            except (PermissionError, OSError):
                continue
            if len(unindexed) >= 100:
                break
        
        return {
            "missing_on_disk": missing_on_disk,
            "unindexed_on_disk": unindexed,
            "summary": {
                "db_files_checked": len(db_files),
                "missing_count": len(missing_on_disk),
                "unindexed_count": len(unindexed),
            }
        }


@router.post("/repair")
async def repair_orphans(
    request: RepairRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Repair orphan issues:
    - reindex: add unindexed disk files to DB
    - remove_stale: remove DB entries for missing files
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    async with get_db() as db:
        processed = 0
        
        if request.action == "remove_stale":
            for file_id in request.file_ids:
                await db.execute("DELETE FROM media_item_files WHERE file_id = ?", (file_id,))
                await db.execute("DELETE FROM files WHERE id = ?", (file_id,))
                await db.execute(
                    """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
                       VALUES ('orphan_remove', 'file', ?, 'Removed stale DB entry', 1)""",
                    (file_id,)
                )
                processed += 1
        
        elif request.action == "reindex":
            for path in request.paths:
                if not os.path.exists(path):
                    continue
                stat = os.stat(path)
                ext = os.path.splitext(path)[1].lower()
                
                # Find matching root
                cursor = await db.execute(
                    "SELECT id FROM roots WHERE ? LIKE path || '%'", (path,)
                )
                root = await cursor.fetchone()
                if not root:
                    continue
                
                await db.execute(
                    """INSERT OR IGNORE INTO files (root_id, path, size, mtime, ext, last_seen)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (root["id"], path, stat.st_size, stat.st_mtime, ext)
                )
                await db.execute(
                    """INSERT INTO audit_log (action, entity_type, details, expert_mode)
                       VALUES ('orphan_reindex', 'file', ?, 1)""",
                    (f"Reindexed: {path}",)
                )
                processed += 1
        else:
            raise HTTPException(status_code=400, detail="Action must be 'reindex' or 'remove_stale'")
        
        await db.commit()
        
        return {
            "message": f"Repair complete: {processed} items processed",
            "action": request.action,
            "processed": processed,
        }


@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    action: Optional[str] = None
) -> dict:
    """Operation replay log — all recorded actions."""
    async with get_db() as db:
        offset = (page - 1) * page_size
        
        where = ""
        params: list = []
        if action:
            where = "WHERE action LIKE ?"
            params.append(f"%{action}%")
        
        cursor = await db.execute(
            f"SELECT COUNT(*) as total FROM audit_log {where}", params
        )
        total = (await cursor.fetchone())["total"]
        
        cursor = await db.execute(
            f"""SELECT * FROM audit_log {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset]
        )
        entries = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "entries": entries,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
