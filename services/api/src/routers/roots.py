"""Roots API router."""

import os
from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..database import get_db
from ..models import Root, RootCreate, RootList

router = APIRouter(prefix="/roots", tags=["roots"])


@router.post("", response_model=Root)
async def create_root(data: RootCreate) -> Root:
    """Add a root folder to a drive."""
    path = data.path
    
    # Validate path exists
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
    
    async with get_db() as db:
        # Verify drive exists
        cursor = await db.execute(
            "SELECT id FROM drives WHERE id = ?",
            (data.drive_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Drive not found")
        
        # Check if root already exists
        cursor = await db.execute(
            "SELECT id FROM roots WHERE drive_id = ? AND path = ?",
            (data.drive_id, path)
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Root already exists")
        
        # Insert new root
        cursor = await db.execute(
            """INSERT INTO roots (drive_id, path, excluded)
               VALUES (?, ?, ?)""",
            (data.drive_id, path, 1 if data.excluded else 0)
        )
        await db.commit()
        root_id = cursor.lastrowid
        
        return Root(
            id=root_id,
            drive_id=data.drive_id,
            path=path,
            excluded=data.excluded,
            created_at=datetime.now()
        )


@router.get("", response_model=RootList)
async def list_roots(drive_id: int | None = None) -> RootList:
    """List all roots, optionally filtered by drive."""
    async with get_db() as db:
        if drive_id is not None:
            cursor = await db.execute(
                """SELECT id, drive_id, path, excluded, created_at 
                   FROM roots WHERE drive_id = ?""",
                (drive_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT id, drive_id, path, excluded, created_at FROM roots"
            )
        rows = await cursor.fetchall()
        
        roots = [
            Root(
                id=row["id"],
                drive_id=row["drive_id"],
                path=row["path"],
                excluded=bool(row["excluded"]),
                created_at=row["created_at"]
            )
            for row in rows
        ]
        
        return RootList(roots=roots)


@router.patch("/{root_id}")
async def update_root(root_id: int, excluded: bool) -> Root:
    """Update root exclusion status."""
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE roots SET excluded = ? WHERE id = ?",
            (1 if excluded else 0, root_id)
        )
        await db.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Root not found")
        
        cursor = await db.execute(
            "SELECT id, drive_id, path, excluded, created_at FROM roots WHERE id = ?",
            (root_id,)
        )
        row = await cursor.fetchone()
        
        return Root(
            id=row["id"],
            drive_id=row["drive_id"],
            path=row["path"],
            excluded=bool(row["excluded"]),
            created_at=row["created_at"]
        )


@router.delete("/{root_id}")
async def delete_root(root_id: int) -> dict:
    """Delete a root folder."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM roots WHERE id = ?", (root_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Root not found")
        return {"message": "Root deleted"}
