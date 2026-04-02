"""Failure Domains API router."""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..database import get_db

router = APIRouter(prefix="/failure-domains", tags=["failure-domains"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class FailureDomainCreate(BaseModel):
    name: str
    description: Optional[str] = None


class FailureDomainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_domain_or_404(db, domain_id: int) -> dict:
    cursor = await db.execute(
        "SELECT id, name, description, created_at FROM failure_domains WHERE id = ?",
        (domain_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Failure domain not found")
    return dict(row)


async def _domain_with_drives(db, domain_id: int) -> dict:
    """Return a domain dict that includes its assigned drives."""
    domain = await _get_domain_or_404(db, domain_id)
    cursor = await db.execute(
        """SELECT id, mount_path, volume_label FROM drives WHERE domain_id = ?
           ORDER BY mount_path""",
        (domain_id,),
    )
    domain["drives"] = [dict(r) for r in await cursor.fetchall()]
    return domain


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_domains() -> dict:
    """List all failure domains with their assigned drives."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name, description, created_at FROM failure_domains ORDER BY name"
        )
        domains = [dict(r) for r in await cursor.fetchall()]

        # Attach drives to each domain
        for domain in domains:
            cursor = await db.execute(
                """SELECT id, mount_path, volume_label FROM drives
                   WHERE domain_id = ? ORDER BY mount_path""",
                (domain["id"],),
            )
            domain["drives"] = [dict(r) for r in await cursor.fetchall()]

        # Count unassigned drives for dashboard awareness
        cursor = await db.execute(
            "SELECT COUNT(*) FROM drives WHERE domain_id IS NULL"
        )
        unassigned_count = (await cursor.fetchone())[0]

        return {"domains": domains, "unassigned_drives": unassigned_count}


@router.post("", status_code=201)
async def create_domain(data: FailureDomainCreate) -> dict:
    """Create a new failure domain."""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO failure_domains (name, description) VALUES (?, ?)",
                (data.name.strip(), data.description),
            )
            await db.commit()
            domain_id = cursor.lastrowid
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=400,
                    detail=f"A failure domain named '{data.name}' already exists",
                )
            raise

        return await _domain_with_drives(db, domain_id)


@router.get("/{domain_id}")
async def get_domain(domain_id: int) -> dict:
    """Get a single failure domain with its drives."""
    async with get_db() as db:
        return await _domain_with_drives(db, domain_id)


@router.patch("/{domain_id}")
async def update_domain(domain_id: int, data: FailureDomainUpdate) -> dict:
    """Update a failure domain's name or description."""
    async with get_db() as db:
        await _get_domain_or_404(db, domain_id)

        updates = []
        params: list = []
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name.strip())
        if data.description is not None:
            updates.append("description = ?")
            params.append(data.description)

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(domain_id)
        try:
            await db.execute(
                f"UPDATE failure_domains SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(
                    status_code=400, detail="A domain with that name already exists"
                )
            raise

        return await _domain_with_drives(db, domain_id)


@router.delete("/{domain_id}")
async def delete_domain(domain_id: int) -> dict:
    """
    Delete a failure domain.

    Drives assigned to this domain will have their domain_id set to NULL
    (handled automatically by the FK ON DELETE SET NULL constraint).
    """
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM failure_domains WHERE id = ?", (domain_id,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Failure domain not found")
        return {"message": "Domain deleted", "id": domain_id}


@router.post("/{domain_id}/drives/{drive_id}")
async def assign_drive(domain_id: int, drive_id: int) -> dict:
    """Assign a drive to a failure domain."""
    async with get_db() as db:
        # Verify domain exists
        await _get_domain_or_404(db, domain_id)

        # Verify drive exists
        cursor = await db.execute(
            "SELECT id, mount_path FROM drives WHERE id = ?", (drive_id,)
        )
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")

        await db.execute(
            "UPDATE drives SET domain_id = ? WHERE id = ?",
            (domain_id, drive_id),
        )
        await db.commit()

        return {
            "message": "Drive assigned to domain",
            "drive_id": drive_id,
            "drive_path": drive["mount_path"],
            "domain_id": domain_id,
        }


@router.delete("/{domain_id}/drives/{drive_id}")
async def unassign_drive(domain_id: int, drive_id: int) -> dict:
    """Remove a drive from a failure domain (sets domain to unassigned)."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, mount_path, domain_id FROM drives WHERE id = ?", (drive_id,)
        )
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")
        if drive["domain_id"] != domain_id:
            raise HTTPException(
                status_code=400,
                detail="Drive is not assigned to this domain",
            )

        await db.execute(
            "UPDATE drives SET domain_id = NULL WHERE id = ?", (drive_id,)
        )
        await db.commit()

        return {
            "message": "Drive unassigned from domain",
            "drive_id": drive_id,
            "drive_path": drive["mount_path"],
        }
