"""API router for drive failure simulation."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..database import get_db


router = APIRouter(prefix="/simulation", tags=["simulation"])


class SimulationRequest(BaseModel):
    drive_ids: list[int]


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
