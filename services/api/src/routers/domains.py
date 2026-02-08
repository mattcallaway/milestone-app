"""API router for failure domains and drive safety controls."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from ..database import get_db


router = APIRouter(prefix="/domains", tags=["domains"])


class FailureDomainCreate(BaseModel):
    name: str
    description: Optional[str] = None
    domain_type: str = "enclosure"  # 'enclosure', 'nas', 'location', 'power'


class FailureDomainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain_type: Optional[str] = None


@router.get("")
async def list_domains() -> dict:
    """List all failure domains with their drives."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT fd.id, fd.name, fd.description, fd.domain_type, fd.created_at,
                   COUNT(d.id) as drive_count
            FROM failure_domains fd
            LEFT JOIN drives d ON d.failure_domain_id = fd.id
            GROUP BY fd.id
            ORDER BY fd.name
            """
        )
        domains = [dict(row) for row in await cursor.fetchall()]
        
        # Get drives for each domain
        for domain in domains:
            cursor = await db.execute(
                """
                SELECT id, mount_path, volume_label, read_only, never_write, preferred
                FROM drives WHERE failure_domain_id = ?
                """,
                (domain["id"],)
            )
            domain["drives"] = [dict(row) for row in await cursor.fetchall()]
        
        return {"domains": domains}


@router.post("")
async def create_domain(domain: FailureDomainCreate) -> dict:
    """Create a new failure domain."""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                """
                INSERT INTO failure_domains (name, description, domain_type)
                VALUES (?, ?, ?)
                """,
                (domain.name, domain.description, domain.domain_type)
            )
            await db.commit()
            return {"id": cursor.lastrowid, "name": domain.name}
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=400, detail="Domain name already exists")
            raise


@router.get("/{domain_id}")
async def get_domain(domain_id: int) -> dict:
    """Get a specific failure domain with its drives."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM failure_domains WHERE id = ?",
            (domain_id,)
        )
        domain = await cursor.fetchone()
        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")
        
        result = dict(domain)
        
        cursor = await db.execute(
            """
            SELECT id, mount_path, volume_label, read_only, never_write, preferred
            FROM drives WHERE failure_domain_id = ?
            """,
            (domain_id,)
        )
        result["drives"] = [dict(row) for row in await cursor.fetchall()]
        
        return result


@router.put("/{domain_id}")
async def update_domain(domain_id: int, update: FailureDomainUpdate) -> dict:
    """Update a failure domain."""
    async with get_db() as db:
        updates = []
        params = []
        
        if update.name is not None:
            updates.append("name = ?")
            params.append(update.name)
        if update.description is not None:
            updates.append("description = ?")
            params.append(update.description)
        if update.domain_type is not None:
            updates.append("domain_type = ?")
            params.append(update.domain_type)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        params.append(domain_id)
        await db.execute(
            f"UPDATE failure_domains SET {', '.join(updates)} WHERE id = ?",
            params
        )
        await db.commit()
        
        return {"id": domain_id, "updated": True}


@router.delete("/{domain_id}")
async def delete_domain(domain_id: int) -> dict:
    """Delete a failure domain. Drives are unassigned, not deleted."""
    async with get_db() as db:
        # Unassign drives first
        await db.execute(
            "UPDATE drives SET failure_domain_id = NULL WHERE failure_domain_id = ?",
            (domain_id,)
        )
        await db.execute("DELETE FROM failure_domains WHERE id = ?", (domain_id,))
        await db.commit()
        return {"id": domain_id, "deleted": True}


@router.put("/drives/{drive_id}/domain")
async def assign_drive_to_domain(
    drive_id: int,
    domain_id: Optional[int] = Query(None, description="Domain ID, or null to unassign")
) -> dict:
    """Assign a drive to a failure domain."""
    async with get_db() as db:
        # Verify drive exists
        cursor = await db.execute("SELECT id FROM drives WHERE id = ?", (drive_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Drive not found")
        
        # Verify domain exists if provided
        if domain_id is not None:
            cursor = await db.execute(
                "SELECT id FROM failure_domains WHERE id = ?",
                (domain_id,)
            )
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Domain not found")
        
        await db.execute(
            "UPDATE drives SET failure_domain_id = ? WHERE id = ?",
            (domain_id, drive_id)
        )
        await db.commit()
        
        return {"drive_id": drive_id, "domain_id": domain_id}


@router.get("/coverage/items")
async def get_domain_coverage_issues(
    min_domains: int = Query(2, ge=1, le=10)
) -> dict:
    """
    Find items that don't have copies in enough distinct failure domains.
    Requires at least min_domains domains for an item to be considered safe.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                COUNT(DISTINCT mif.file_id) as copy_count,
                COUNT(DISTINCT d.failure_domain_id) as domain_count
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            GROUP BY mi.id
            HAVING domain_count < ? AND copy_count >= ?
            ORDER BY domain_count ASC, copy_count DESC
            """,
            (min_domains, min_domains)
        )
        items = [dict(row) for row in await cursor.fetchall()]
        
        # Add file locations for each item
        for item in items:
            cursor = await db.execute(
                """
                SELECT f.id, f.path, d.mount_path, d.failure_domain_id, fd.name as domain_name
                FROM files f
                JOIN media_item_files mif ON f.id = mif.file_id
                JOIN roots r ON f.root_id = r.id
                JOIN drives d ON r.drive_id = d.id
                LEFT JOIN failure_domains fd ON d.failure_domain_id = fd.id
                WHERE mif.media_item_id = ?
                """,
                (item["item_id"],)
            )
            item["files"] = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "insufficient_coverage": items,
            "total_count": len(items),
            "required_domains": min_domains
        }
