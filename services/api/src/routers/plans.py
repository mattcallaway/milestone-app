"""API router for bulk planning workflow."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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
