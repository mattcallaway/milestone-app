"""Drives API router."""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..database import get_db
from ..models import Drive, DriveList, DriveRegister

router = APIRouter(prefix="/drives", tags=["drives"])


def get_volume_info(mount_path: str) -> tuple[str | None, str | None]:
    """Get volume serial and label for a drive."""
    try:
        if sys.platform == "win32":
            # Windows: use vol command
            result = subprocess.run(
                ["cmd", "/c", "vol", mount_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            output = result.stdout
            serial = None
            label = None
            for line in output.split("\n"):
                if "Serial Number" in line or "serial number" in line.lower():
                    serial = line.split(":")[-1].strip() if ":" in line else line.split()[-1]
                if "Volume in drive" in line:
                    parts = line.split("is")
                    if len(parts) > 1:
                        label = parts[1].strip()
            return serial, label
        else:
            # Unix: use lsblk or blkid
            return None, None
    except Exception:
        return None, None


def get_disk_space(mount_path: str) -> tuple[int | None, int | None]:
    """Get free and total space for a drive."""
    try:
        usage = shutil.disk_usage(mount_path)
        return usage.free, usage.total
    except Exception:
        return None, None


@router.post("/register", response_model=Drive)
async def register_drive(data: DriveRegister) -> Drive:
    """Register a drive by mount path."""
    mount_path = data.mount_path
    
    # Validate path exists
    if not os.path.exists(mount_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {mount_path}")
    
    # Get volume info
    serial, label = get_volume_info(mount_path)
    free_space, total_space = get_disk_space(mount_path)
    
    async with get_db() as db:
        # Check if already registered
        cursor = await db.execute(
            "SELECT id FROM drives WHERE mount_path = ?",
            (mount_path,)
        )
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Drive already registered")
        
        # Insert new drive
        cursor = await db.execute(
            """INSERT INTO drives (mount_path, volume_serial, volume_label)
               VALUES (?, ?, ?)""",
            (mount_path, serial, label)
        )
        await db.commit()
        drive_id = cursor.lastrowid
        
        return Drive(
            id=drive_id,
            mount_path=mount_path,
            volume_serial=serial,
            volume_label=label,
            created_at=datetime.now(),
            free_space=free_space,
            total_space=total_space
        )


@router.get("", response_model=DriveList)
async def list_drives() -> DriveList:
    """List all registered drives with status."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, mount_path, volume_serial, volume_label, created_at FROM drives"
        )
        rows = await cursor.fetchall()
        
        drives = []
        for row in rows:
            free_space, total_space = get_disk_space(row["mount_path"])
            drives.append(Drive(
                id=row["id"],
                mount_path=row["mount_path"],
                volume_serial=row["volume_serial"],
                volume_label=row["volume_label"],
                created_at=row["created_at"],
                free_space=free_space,
                total_space=total_space
            ))
        
        return DriveList(drives=drives)


@router.delete("/{drive_id}")
async def delete_drive(drive_id: int) -> dict:
    """Delete a registered drive."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM drives WHERE id = ?", (drive_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Drive not found")
        return {"message": "Drive deleted"}
