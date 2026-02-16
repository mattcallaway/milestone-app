"""API router for advanced copy operations (Expert Mode only)."""

import os
import platform
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..config import is_write_enabled
from ..expert import require_expert

router = APIRouter(prefix="/advanced-copy", tags=["advanced-copy"])


class HardlinkRequest(BaseModel):
    source_file_id: int
    dest_path: str


class ConvertRequest(BaseModel):
    file_id: int


@router.get("/filesystem-info/{drive_id}")
async def get_filesystem_info(drive_id: int) -> dict:
    """Detect filesystem capabilities for a drive."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM drives WHERE id = ?", (drive_id,))
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")
        
        mount_path = drive["mount_path"]
        fs_type = "unknown"
        supports_hardlink = False
        supports_reflink = False
        
        if platform.system() == "Windows":
            # Check for NTFS
            try:
                result = subprocess.run(
                    ["fsutil", "fsinfo", "volumeinfo", mount_path],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout
                if "NTFS" in output:
                    fs_type = "NTFS"
                    supports_hardlink = True
                elif "ReFS" in output:
                    fs_type = "ReFS"
                    supports_hardlink = True
                    supports_reflink = True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        else:
            # Linux/macOS
            try:
                result = subprocess.run(
                    ["df", "-T", mount_path],
                    capture_output=True, text=True, timeout=5
                )
                output = result.stdout.lower()
                if "btrfs" in output:
                    fs_type = "btrfs"
                    supports_hardlink = True
                    supports_reflink = True
                elif "xfs" in output:
                    fs_type = "xfs"
                    supports_hardlink = True
                    supports_reflink = True
                elif "ext4" in output or "ext3" in output:
                    fs_type = output.split()[1] if len(output.split()) > 1 else "ext"
                    supports_hardlink = True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        
        # Cache in DB
        await db.execute(
            """INSERT OR REPLACE INTO drive_capabilities 
               (drive_id, supports_hardlink, supports_reflink, filesystem_type, detected_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (drive_id, int(supports_hardlink), int(supports_reflink), fs_type)
        )
        await db.commit()
        
        return {
            "drive_id": drive_id,
            "mount_path": mount_path,
            "filesystem_type": fs_type,
            "supports_hardlink": supports_hardlink,
            "supports_reflink": supports_reflink,
        }


@router.post("/hardlink")
async def create_hardlink(
    request: HardlinkRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Create a hardlink (same filesystem only).
    
    WARNING: Hardlinks share storage. Deleting one may affect the other.
    This does NOT count as a redundant copy for safety purposes.
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT f.path, r.drive_id FROM files f JOIN roots r ON f.root_id = r.id WHERE f.id = ?",
            (request.source_file_id,)
        )
        source = await cursor.fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="Source file not found")
        
        source_path = source["path"]
        
        # Verify same drive
        source_drive = os.path.splitdrive(source_path)[0]
        dest_drive = os.path.splitdrive(request.dest_path)[0]
        if source_drive.lower() != dest_drive.lower():
            raise HTTPException(
                status_code=400,
                detail="Hardlinks only work on the same filesystem/drive"
            )
        
        if not os.path.exists(source_path):
            raise HTTPException(status_code=404, detail="Source file not found on disk")
        
        if os.path.exists(request.dest_path):
            raise HTTPException(status_code=409, detail="Destination already exists")
        
        # Create parent directory
        os.makedirs(os.path.dirname(request.dest_path), exist_ok=True)
        
        try:
            os.link(source_path, request.dest_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to create hardlink: {e}")
        
        # Log to audit
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('hardlink_create', 'file', ?, ?, 1)""",
            (request.source_file_id, f"source={source_path}, dest={request.dest_path}")
        )
        await db.commit()
        
        return {
            "message": "Hardlink created",
            "source": source_path,
            "destination": request.dest_path,
            "warning": "This file shares storage with the source. It does NOT count as a backup copy."
        }


@router.post("/convert-to-full")
async def convert_to_full_copy(
    request: ConvertRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """Convert a hardlinked file to a full independent copy."""
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    
    async with get_db() as db:
        cursor = await db.execute("SELECT path FROM files WHERE id = ?", (request.file_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = row["path"]
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Check if it's actually a hardlink (link count > 1)
        stat = os.stat(file_path)
        if stat.st_nlink <= 1:
            return {"message": "File is already an independent copy", "path": file_path}
        
        # Read, delete, rewrite to break the link
        temp_path = file_path + ".converting"
        try:
            import shutil
            shutil.copy2(file_path, temp_path)
            os.unlink(file_path)
            os.rename(temp_path, file_path)
        except OSError as e:
            # Cleanup
            if os.path.exists(temp_path):
                try: os.unlink(temp_path)
                except OSError: pass
            raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
        
        # Log
        await db.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, details, expert_mode)
               VALUES ('hardlink_convert', 'file', ?, ?, 1)""",
            (request.file_id, f"Converted to full copy: {file_path}")
        )
        await db.commit()
        
        return {"message": "Converted to full independent copy", "path": file_path}
