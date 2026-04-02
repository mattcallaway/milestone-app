"""
Risk / Placement API Router
==============================
Endpoints:
  GET  /risk/item/{item_id}               risk score + explanation for one item
  GET  /risk/summary                      dashboard rollup (top risk, biggest, fragile drives)
  GET  /risk/placement/{item_id}          destination suggestions for this item
  GET  /drives/{drive_id}/health          get health status
  PATCH /drives/{drive_id}/health         update health status
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import get_db
from ..risk_scorer import compute_risk_score, score_label, score_color
from ..placement import suggest_destinations

router = APIRouter(tags=["risk"])


# ── Drive health PATCH ─────────────────────────────────────────────────────────

VALID_HEALTH_STATUSES = {"healthy", "warning", "degraded", "avoid_for_new_copies"}


class HealthUpdate(BaseModel):
    status: str


@router.patch("/drives/{drive_id}/health")
async def set_drive_health(drive_id: int, body: HealthUpdate) -> dict:
    """Update the health status of a drive."""
    if body.status not in VALID_HEALTH_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_HEALTH_STATUSES)}",
        )
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE drives SET health_status = ? WHERE id = ?",
            (body.status, drive_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Drive not found")
    return {"drive_id": drive_id, "health_status": body.status}


# ── Item risk score ─────────────────────────────────────────────────────────────

async def _fetch_item_for_scoring(db, item_id: int) -> dict | None:
    """Load a single item with all data needed for risk scoring."""
    cursor = await db.execute(
        """SELECT mi.id, mi.title, mi.type, mi.status
           FROM media_items mi WHERE mi.id = ?""",
        (item_id,),
    )
    item_row = await cursor.fetchone()
    if not item_row:
        return None

    cursor = await db.execute(
        """SELECT f.size, d.id AS drive_id, d.domain_id, d.health_status
           FROM media_item_files mif
           JOIN files f ON mif.file_id = f.id
           JOIN roots r ON f.root_id = r.id
           JOIN drives d ON r.drive_id = d.id
           WHERE mif.media_item_id = ?""",
        (item_id,),
    )
    file_rows = await cursor.fetchall()

    total_size = sum(fr["size"] or 0 for fr in file_rows)
    drive_ids = [fr["drive_id"] for fr in file_rows]
    domain_ids = [fr["domain_id"] for fr in file_rows]
    drive_healths = [fr["health_status"] or "healthy" for fr in file_rows]

    assigned_domains = {d for d in domain_ids if d is not None}
    distinct_assigned = len(assigned_domains)
    copy_count = len(file_rows)
    domain_complete = (copy_count > 0 and len(assigned_domains) == copy_count
                       and all(d is not None for d in domain_ids))

    from ..resilience import compute_resilience_state
    resilience_state = compute_resilience_state(copy_count, distinct_assigned)

    return {
        "id": item_row["id"],
        "title": item_row["title"],
        "type": item_row["type"],
        "status": item_row["status"],
        "copy_count": copy_count,
        "resilience_state": resilience_state,
        "domain_mapping_complete": domain_complete,
        "total_size_bytes": total_size,
        "drive_healths": drive_healths,
        "drive_ids": drive_ids,
        "domain_ids": domain_ids,
        "distinct_assigned_domains": distinct_assigned,
    }


@router.get("/risk/item/{item_id}")
async def get_item_risk(item_id: int) -> dict:
    """Return the full risk score and explanation for a single item."""
    async with get_db() as db:
        item = await _fetch_item_for_scoring(db, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

    result = compute_risk_score(item)
    return {
        **result,
        "item_id": item_id,
        "title": item["title"],
        "resilience_state": item["resilience_state"],
        "copy_count": item["copy_count"],
        "total_size_bytes": item["total_size_bytes"],
        "label": score_label(result["score"]),
        "color": score_color(result["score"]),
    }


# ── Dashboard risk summary ─────────────────────────────────────────────────────

@router.get("/risk/summary")
async def get_risk_summary(limit: int = 10) -> dict:
    """
    Return:
      - top_risk_items:     highest-scored items
      - biggest_vulnerable: largest (by size) items that are not safe
      - fragile_drives:     drives holding the most at-risk item copies
    """
    async with get_db() as db:
        # Batch: load all items at once
        cursor = await db.execute(
            "SELECT id, title, type, status FROM media_items ORDER BY id"
        )
        all_items = await cursor.fetchall()

        if not all_items:
            return {"top_risk_items": [], "biggest_vulnerable": [], "fragile_drives": []}

        item_ids = [r["id"] for r in all_items]
        placeholders = ",".join("?" * len(item_ids))

        cursor = await db.execute(f"""
            SELECT
                mif.media_item_id,
                f.size,
                d.id  AS drive_id,
                d.mount_path,
                d.volume_label,
                d.domain_id,
                COALESCE(d.health_status, 'healthy') AS health_status
            FROM media_item_files mif
            JOIN files f  ON mif.file_id  = f.id
            JOIN roots r  ON f.root_id    = r.id
            JOIN drives d ON r.drive_id   = d.id
            WHERE mif.media_item_id IN ({placeholders})
        """, item_ids)
        all_files = await cursor.fetchall()

    # Group files by item
    from collections import defaultdict
    files_by_item: dict[int, list[dict]] = defaultdict(list)
    for fr in all_files:
        files_by_item[fr["media_item_id"]].append(dict(fr))

    from ..resilience import compute_resilience_state

    scored: list[dict] = []
    for row in all_items:
        iid = row["id"]
        files = files_by_item.get(iid, [])
        domain_ids = [f["domain_id"] for f in files]
        assigned = {d for d in domain_ids if d is not None}
        copy_count = len(files)
        state = compute_resilience_state(copy_count, len(assigned))
        domain_complete = copy_count > 0 and all(d is not None for d in domain_ids)
        healths = [f["health_status"] for f in files]
        size = sum(f["size"] or 0 for f in files)

        risk = compute_risk_score({
            "resilience_state": state,
            "domain_mapping_complete": domain_complete,
            "status": row["status"],
            "total_size_bytes": size,
            "drive_healths": healths,
            "copy_count": copy_count,
        })
        scored.append({
            "id": iid,
            "title": row["title"],
            "type": row["type"],
            "resilience_state": state,
            "copy_count": copy_count,
            "score": risk["score"],
            "label": score_label(risk["score"]),
            "color": score_color(risk["score"]),
            "recommended_action": risk["recommended_action"],
            "total_size_bytes": size,
            "drive_ids": [f["drive_id"] for f in files],
        })

    # Top risk items
    top_risk = sorted(scored, key=lambda x: x["score"], reverse=True)[:limit]

    # Biggest vulnerable items (unsafe states + large size)
    vulnerable_states = {"unsafe_no_backup", "unsafe_single_domain", "over_replicated_but_fragile"}
    biggest = sorted(
        [s for s in scored if s["resilience_state"] in vulnerable_states],
        key=lambda x: x["total_size_bytes"],
        reverse=True,
    )[:limit]

    # Fragile drives: count at-risk item copies per drive
    from collections import Counter
    drive_at_risk_counts: Counter = Counter()
    drive_info: dict[int, dict] = {}
    for item in scored:
        if item["resilience_state"] in vulnerable_states:
            for fr in files_by_item.get(item["id"], []):
                did = fr["drive_id"]
                drive_at_risk_counts[did] += 1
                if did not in drive_info:
                    drive_info[did] = {
                        "drive_id": did,
                        "mount_path": fr["mount_path"],
                        "volume_label": fr["volume_label"],
                        "health_status": fr["health_status"],
                    }
    fragile_drives = [
        {**drive_info[did], "at_risk_items": count}
        for did, count in drive_at_risk_counts.most_common(limit)
    ]

    return {
        "top_risk_items": top_risk,
        "biggest_vulnerable": biggest,
        "fragile_drives": fragile_drives,
    }


# ── Placement suggestions ──────────────────────────────────────────────────────

@router.get("/risk/placement/{item_id}")
async def get_placement_suggestions(item_id: int) -> dict:
    """Return ordered destination drive recommendations for this item."""
    async with get_db() as db:
        item = await _fetch_item_for_scoring(db, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        cursor = await db.execute("""
            SELECT d.id, d.mount_path, d.volume_label, d.domain_id,
                   COALESCE(d.health_status, 'healthy') AS health_status
            FROM drives d
        """)
        drive_rows = await cursor.fetchall()

    # Get free space for each drive (computed dynamically)
    import shutil
    drives = []
    for dr in drive_rows:
        try:
            usage = shutil.disk_usage(dr["mount_path"])
            free = usage.free
        except Exception:
            free = 0
        drives.append({
            "id": dr["id"],
            "mount_path": dr["mount_path"],
            "volume_label": dr["volume_label"],
            "domain_id": dr["domain_id"],
            "health_status": dr["health_status"],
            "free_space": free,
        })

    placement_input = {
        "resilience_state": item["resilience_state"],
        "domain_mapping_complete": item["domain_mapping_complete"],
        "copy_count": item["copy_count"],
        "current_drive_ids": set(item["drive_ids"]),
        "current_domain_ids": set(item["domain_ids"]),
        "total_size_bytes": item["total_size_bytes"],
    }

    suggestions = suggest_destinations(placement_input, drives)

    return {
        "item_id": item_id,
        "item_title": item["title"],
        "resilience_state": item["resilience_state"],
        "suggestions": suggestions,
    }
