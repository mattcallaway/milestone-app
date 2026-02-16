"""API router for bulk planning workflow."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import shutil

from ..database import get_db
from ..config import is_write_enabled


router = APIRouter(prefix="/plans", tags=["plans"])


class PlanCreate(BaseModel):
    name: Optional[str] = None


@router.get("")
async def list_plans() -> dict:
    """List all plans."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT p.*, 
                   COUNT(pi.id) as total_items,
                   SUM(CASE WHEN pi.included = 1 THEN 1 ELSE 0 END) as included_items
            FROM plans p
            LEFT JOIN plan_items pi ON p.id = pi.plan_id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """
        )
        plans = [dict(row) for row in await cursor.fetchall()]
        return {"plans": plans}


@router.get("/{plan_id}")
async def get_plan(plan_id: int) -> dict:
    """Get a plan with its items."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        plan = await cursor.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        result = dict(plan)
        
        cursor = await db.execute(
            """
            SELECT pi.*, f.path as source_path, f.size, d.mount_path as dest_drive
            FROM plan_items pi
            LEFT JOIN files f ON pi.source_file_id = f.id
            LEFT JOIN drives d ON pi.dest_drive_id = d.id
            WHERE pi.plan_id = ?
            ORDER BY pi.id
            """,
            (plan_id,)
        )
        result["items"] = [dict(row) for row in await cursor.fetchall()]
        
        return result


@router.post("/copy-at-risk")
async def create_copy_plan(data: PlanCreate) -> dict:
    """
    Create a plan to make 2nd copies of all at-risk items (0-1 copies).
    Does not execute - preview only.
    """
    async with get_db() as db:
        # Find items with only 1 copy
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.title,
                mif.file_id,
                f.path,
                f.size,
                d.id as source_drive_id
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            WHERE mif.is_primary = 1
            GROUP BY mi.id
            HAVING COUNT(mi.id) = 1
            """
        )
        at_risk = await cursor.fetchall()
        
        if not at_risk:
            return {"message": "No at-risk items found", "plan_id": None}
        
        # Get available destination drives
        cursor = await db.execute(
            """
            SELECT id, mount_path 
            FROM drives 
            WHERE never_write = 0 AND read_only = 0
            ORDER BY preferred DESC
            """
        )
        dest_drives = await cursor.fetchall()
        
        if not dest_drives:
            raise HTTPException(status_code=400, detail="No writable drives available")
        
        # Calculate total size
        total_size = sum(row["size"] or 0 for row in at_risk)
        
        # Create the plan
        cursor = await db.execute(
            """
            INSERT INTO plans (name, plan_type, total_bytes, item_count)
            VALUES (?, 'copy', ?, ?)
            """,
            (data.name or "Copy At-Risk Items", total_size, len(at_risk))
        )
        plan_id = cursor.lastrowid
        
        # Create plan items - assign to different drives than source
        for item in at_risk:
            # Find a destination drive different from source
            dest_drive = None
            for d in dest_drives:
                if d["id"] != item["source_drive_id"]:
                    dest_drive = d
                    break
            
            if dest_drive:
                await db.execute(
                    """
                    INSERT INTO plan_items (plan_id, action, source_file_id, dest_drive_id)
                    VALUES (?, 'copy', ?, ?)
                    """,
                    (plan_id, item["file_id"], dest_drive["id"])
                )
        
        await db.commit()
        
        return {
            "plan_id": plan_id,
            "item_count": len(at_risk),
            "total_bytes": total_size,
            "status": "draft"
        }


@router.post("/reduce")
async def create_reduction_plan(data: PlanCreate, min_copies: int = 2) -> dict:
    """
    Create a plan to reduce over-replicated items to min_copies.
    Does not execute - preview only.
    """
    async with get_db() as db:
        # Find items with excess copies
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.title,
                COUNT(mif.file_id) as copy_count
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            GROUP BY mi.id
            HAVING copy_count > ?
            """,
            (min_copies,)
        )
        over_replicated = [dict(row) for row in await cursor.fetchall()]
        
        if not over_replicated:
            return {"message": "No over-replicated items found", "plan_id": None}
        
        # Create the plan
        cursor = await db.execute(
            """
            INSERT INTO plans (name, plan_type, item_count)
            VALUES (?, 'reduction', ?)
            """,
            (data.name or f"Reduce to {min_copies} Copies", len(over_replicated))
        )
        plan_id = cursor.lastrowid
        
        total_savings = 0
        
        for item in over_replicated:
            # Get files for this item
            cursor = await db.execute(
                """
                SELECT f.id, f.size, mif.is_primary, d.preferred
                FROM files f
                JOIN media_item_files mif ON f.id = mif.file_id
                JOIN roots r ON f.root_id = r.id
                JOIN drives d ON r.drive_id = d.id
                WHERE mif.media_item_id = ?
                ORDER BY mif.is_primary DESC, d.preferred DESC, f.size DESC
                """,
                (item["item_id"],)
            )
            files = await cursor.fetchall()
            
            # Keep first min_copies, mark rest for deletion
            for i, f in enumerate(files):
                if i >= min_copies:
                    await db.execute(
                        """
                        INSERT INTO plan_items (plan_id, action, source_file_id)
                        VALUES (?, 'delete', ?)
                        """,
                        (plan_id, f["id"])
                    )
                    total_savings += f["size"] or 0
        
        await db.execute(
            "UPDATE plans SET total_bytes = ? WHERE id = ?",
            (total_savings, plan_id)
        )
        await db.commit()
        
        return {
            "plan_id": plan_id,
            "item_count": len(over_replicated),
            "total_savings_bytes": total_savings,
            "status": "draft"
        }


@router.put("/{plan_id}/items/{item_id}")
async def toggle_plan_item(plan_id: int, item_id: int, included: bool) -> dict:
    """Toggle whether a plan item is included."""
    async with get_db() as db:
        cursor = await db.execute("SELECT status FROM plans WHERE id = ?", (plan_id,))
        plan = await cursor.fetchone()
        if not plan or plan["status"] != "draft":
            raise HTTPException(status_code=400, detail="Can only modify draft plans")
        await db.execute(
            "UPDATE plan_items SET included = ? WHERE id = ? AND plan_id = ?",
            (1 if included else 0, item_id, plan_id)
        )
        await db.commit()
        return {"item_id": item_id, "included": included}


@router.post("/{plan_id}/confirm")
async def confirm_plan(plan_id: int) -> dict:
    """
    Confirm a plan and convert to queued operations.
    Only included items are converted.
    """
    if not is_write_enabled():
        raise HTTPException(status_code=403, detail="Write mode is not enabled")
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM plans WHERE id = ? AND status = 'draft'",
            (plan_id,)
        )
        plan = await cursor.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found or not in draft status")
        
        # Get included items
        cursor = await db.execute(
            """
            SELECT * FROM plan_items 
            WHERE plan_id = ? AND included = 1
            """,
            (plan_id,)
        )
        items = await cursor.fetchall()
        
        # Create operations from plan items
        created_ops = 0
        for item in items:
            await db.execute(
                """
                INSERT INTO operations (type, source_file_id, dest_drive_id, dest_path, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (item["action"], item["source_file_id"], item["dest_drive_id"], item["dest_path"])
            )
            created_ops += 1
        
        # Mark plan as executed
        await db.execute(
            """
            UPDATE plans SET status = 'executed', confirmed_at = CURRENT_TIMESTAMP, 
                             executed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (plan_id,)
        )
        await db.commit()
        
        return {
            "plan_id": plan_id,
            "operations_created": created_ops,
            "status": "executed"
        }


@router.get("/{plan_id}/drive-impact")
async def get_drive_impact(plan_id: int) -> dict:
    """Calculate per-drive space impact of executing this plan.
    
    Returns current disk stats + projected changes for each affected drive.
    """
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        plan = await cursor.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Get all included plan items with file sizes and drive info
        cursor = await db.execute("""
            SELECT 
                pi.action,
                pi.source_file_id,
                pi.dest_drive_id,
                f.size,
                f.root_id,
                r.drive_id as source_drive_id
            FROM plan_items pi
            LEFT JOIN files f ON pi.source_file_id = f.id
            LEFT JOIN roots r ON f.root_id = r.id
            WHERE pi.plan_id = ? AND pi.included = 1
        """, (plan_id,))
        items = await cursor.fetchall()
        
        # Accumulate bytes per drive
        # drive_id -> {"incoming": bytes, "outgoing": bytes}
        drive_changes: dict[int, dict] = {}
        
        for item in items:
            size = item["size"] or 0
            
            if item["action"] == "copy" and item["dest_drive_id"]:
                dest_id = item["dest_drive_id"]
                if dest_id not in drive_changes:
                    drive_changes[dest_id] = {"incoming": 0, "outgoing": 0}
                drive_changes[dest_id]["incoming"] += size
            
            if item["action"] == "delete" and item["source_drive_id"]:
                src_id = item["source_drive_id"]
                if src_id not in drive_changes:
                    drive_changes[src_id] = {"incoming": 0, "outgoing": 0}
                drive_changes[src_id]["outgoing"] += size
        
        # Get all drives info
        cursor = await db.execute(
            "SELECT id, mount_path, volume_label, preferred FROM drives"
        )
        all_drives = {row["id"]: dict(row) for row in await cursor.fetchall()}
        
        # Build impact summary for each affected drive
        impacts = []
        for drive_id, changes in drive_changes.items():
            drive = all_drives.get(drive_id)
            if not drive:
                continue
            
            # Get live disk space
            try:
                usage = shutil.disk_usage(drive["mount_path"])
                total = usage.total
                used = usage.used
                free = usage.free
            except Exception:
                total = used = free = 0
            
            net_change = changes["incoming"] - changes["outgoing"]
            projected_free = free - net_change
            projected_used = used + net_change
            
            impacts.append({
                "drive_id": drive_id,
                "mount_path": drive["mount_path"],
                "label": drive["volume_label"] or drive["mount_path"],
                "preferred": drive["preferred"],
                "total": total,
                "used": used,
                "free": free,
                "incoming": changes["incoming"],
                "outgoing": changes["outgoing"],
                "net_change": net_change,
                "projected_free": max(0, projected_free),
                "projected_used": min(total, projected_used) if total else projected_used,
                "utilization_pct": round(used / total * 100, 1) if total else 0,
                "projected_utilization_pct": round(min(total, projected_used) / total * 100, 1) if total else 0,
            })
        
        # Sort: drives receiving data first, then by mount path
        impacts.sort(key=lambda d: (-d["incoming"], d["mount_path"]))
        
        return {
            "plan_id": plan_id,
            "drives": impacts,
            "total_incoming": sum(d["incoming"] for d in impacts),
            "total_outgoing": sum(d["outgoing"] for d in impacts),
        }

@router.delete("/{plan_id}")
async def cancel_plan(plan_id: int) -> dict:
    """Cancel and delete a draft plan."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT status FROM plans WHERE id = ?",
            (plan_id,)
        )
        plan = await cursor.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        if plan["status"] != "draft":
            raise HTTPException(status_code=400, detail="Can only cancel draft plans")
        
        await db.execute("DELETE FROM plan_items WHERE plan_id = ?", (plan_id,))
        await db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        await db.commit()
        
        return {"plan_id": plan_id, "deleted": True}
