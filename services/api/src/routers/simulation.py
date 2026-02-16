"""API router for drive failure simulation."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..expert import require_expert


router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationRequest(BaseModel):
    drive_ids: list[int]


class DomainFailureRequest(BaseModel):
    domain_id: int


class AddDriveRequest(BaseModel):
    total_space: int
    domain_id: Optional[int] = None


class MultiFailureRequest(BaseModel):
    drive_ids: list[int] = []
    domain_ids: list[int] = []


@router.post("/drive-failure")
async def simulate_drive_failure(request: SimulationRequest) -> dict:
    """
    Simulate what happens if specified drives fail.
    Calculates items that would lose coverage without those drives.
    No writes - purely analytical.
    """
    if not request.drive_ids:
        return {"error": "No drives specified"}
    
    async with get_db() as db:
        # Get affected items - items that would fall below 2 copies
        placeholders = ",".join("?" * len(request.drive_ids))
        
        cursor = await db.execute(
            f"""
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                COUNT(DISTINCT mif.file_id) as current_copies,
                COUNT(DISTINCT CASE 
                    WHEN d.id NOT IN ({placeholders}) THEN mif.file_id 
                    ELSE NULL 
                END) as remaining_copies
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            GROUP BY mi.id
            HAVING remaining_copies < 2 AND current_copies >= 2
            ORDER BY remaining_copies ASC, current_copies DESC
            """,
            request.drive_ids
        )
        at_risk_items = [dict(row) for row in await cursor.fetchall()]
        
        # Items that would lose ALL copies
        cursor = await db.execute(
            f"""
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                COUNT(DISTINCT mif.file_id) as current_copies
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            GROUP BY mi.id
            HAVING COUNT(DISTINCT CASE 
                WHEN d.id NOT IN ({placeholders}) THEN mif.file_id 
                ELSE NULL 
            END) = 0
            ORDER BY current_copies DESC
            """,
            request.drive_ids
        )
        total_loss_items = [dict(row) for row in await cursor.fetchall()]
        
        # Items that would lose failure-domain redundancy
        cursor = await db.execute(
            f"""
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                COUNT(DISTINCT d.failure_domain_id) as current_domains,
                COUNT(DISTINCT CASE 
                    WHEN d.id NOT IN ({placeholders}) THEN d.failure_domain_id 
                    ELSE NULL 
                END) as remaining_domains
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            WHERE d.failure_domain_id IS NOT NULL
            GROUP BY mi.id
            HAVING remaining_domains < 2 AND current_domains >= 2
            ORDER BY remaining_domains ASC
            """,
            request.drive_ids
        )
        domain_risk_items = [dict(row) for row in await cursor.fetchall()]
        
        # Get info about selected drives
        cursor = await db.execute(
            f"""
            SELECT d.id, d.mount_path, d.volume_label, fd.name as domain_name,
                   (SELECT COUNT(*) FROM roots r 
                    JOIN files f ON r.id = f.root_id 
                    WHERE r.drive_id = d.id) as file_count,
                   (SELECT COALESCE(SUM(f.size), 0) FROM roots r 
                    JOIN files f ON r.id = f.root_id 
                    WHERE r.drive_id = d.id) as total_size
            FROM drives d
            LEFT JOIN failure_domains fd ON d.failure_domain_id = fd.id
            WHERE d.id IN ({placeholders})
            """,
            request.drive_ids
        )
        selected_drives = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "simulated_failures": selected_drives,
            "summary": {
                "total_loss_count": len(total_loss_items),
                "at_risk_count": len(at_risk_items),
                "domain_violation_count": len(domain_risk_items)
            },
            "total_loss": total_loss_items,
            "at_risk": at_risk_items,
            "domain_violations": domain_risk_items
        }


@router.post("/domain-failure")
async def simulate_domain_failure(request: DomainFailureRequest) -> dict:
    """
    Simulate loss of an entire failure domain.
    All drives in the domain are considered lost simultaneously.
    """
    async with get_db() as db:
        # Get all drives in this domain
        cursor = await db.execute(
            "SELECT id FROM drives WHERE failure_domain_id = ?",
            (request.domain_id,)
        )
        drive_rows = await cursor.fetchall()
        drive_ids = [row["id"] for row in drive_rows]
        
        if not drive_ids:
            return {"error": "No drives found in this domain"}
        
        # Reuse drive-failure simulation
        sim_request = SimulationRequest(drive_ids=drive_ids)
        result = await simulate_drive_failure(sim_request)
        
        # Get domain info
        cursor = await db.execute(
            "SELECT * FROM failure_domains WHERE id = ?", (request.domain_id,)
        )
        domain = await cursor.fetchone()
        
        result["domain"] = dict(domain) if domain else None
        result["drives_in_domain"] = len(drive_ids)
        
        return result


@router.post("/add-drive")
async def simulate_add_drive(request: AddDriveRequest) -> dict:
    """
    What-if: adding a new drive. Shows items that would benefit
    from additional storage — items currently at-risk or under-replicated.
    """
    async with get_db() as db:
        # Items with fewer than 2 copies
        cursor = await db.execute(
            """SELECT mi.id as item_id, mi.type, mi.title,
                      COUNT(DISTINCT mif.file_id) as copy_count,
                      COUNT(DISTINCT r.drive_id) as drive_count,
                      COALESCE(SUM(f.size), 0) as total_size
               FROM media_items mi
               JOIN media_item_files mif ON mi.id = mif.media_item_id
               JOIN files f ON mif.file_id = f.id
               JOIN roots r ON f.root_id = r.id
               GROUP BY mi.id
               HAVING copy_count < 2
               ORDER BY copy_count ASC"""
        )
        under_replicated = [dict(row) for row in await cursor.fetchall()]
        
        # How much space the new drive could absorb
        total_needed = sum(i["total_size"] for i in under_replicated)
        items_serviceable = 0
        cumulative = 0
        for item in under_replicated:
            cumulative += item["total_size"]
            if cumulative <= request.total_space:
                items_serviceable += 1
            else:
                break
        
        # Domain benefit
        domain_benefit = "none"
        if request.domain_id:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM drives WHERE failure_domain_id = ?",
                (request.domain_id,)
            )
            existing_in_domain = (await cursor.fetchone())["cnt"]
            domain_benefit = "new_domain" if existing_in_domain == 0 else "existing_domain"
        
        return {
            "proposed_drive": {
                "total_space": request.total_space,
                "domain_id": request.domain_id,
                "domain_benefit": domain_benefit,
            },
            "impact": {
                "under_replicated_items": len(under_replicated),
                "items_serviceable": items_serviceable,
                "space_needed_for_all": total_needed,
            },
            "under_replicated": under_replicated[:50],
        }


@router.post("/multi-failure")
async def simulate_multi_failure(
    request: MultiFailureRequest,
    _expert: bool = Depends(require_expert)
) -> dict:
    """
    Expert only: simulate combined drive + domain failures.
    Can model catastrophic scenarios.
    """
    async with get_db() as db:
        # Collect all drive IDs from both direct and domain
        all_drive_ids = list(request.drive_ids)
        
        for domain_id in request.domain_ids:
            cursor = await db.execute(
                "SELECT id FROM drives WHERE failure_domain_id = ?",
                (domain_id,)
            )
            for row in await cursor.fetchall():
                if row["id"] not in all_drive_ids:
                    all_drive_ids.append(row["id"])
        
        if not all_drive_ids:
            return {"error": "No drives or domains specified"}
        
        # Run combined simulation
        sim_request = SimulationRequest(drive_ids=all_drive_ids)
        result = await simulate_drive_failure(sim_request)
        
        result["scenario"] = {
            "direct_drives": request.drive_ids,
            "failed_domains": request.domain_ids,
            "total_drives_affected": len(all_drive_ids),
        }
        
        return result
