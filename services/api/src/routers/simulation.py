"""
Drive Failure Simulation API Router
=====================================
Endpoints:
  GET  /simulation/drives                           list drives available for simulation
  GET  /simulation/domains                          list domains available for simulation
  GET  /simulation/drive/{drive_id}                 run drive-failure simulation
  GET  /simulation/domain/{domain_id}               run domain-failure simulation
  GET  /simulation/drive/{drive_id}/export          export results (csv|json|checklist)
  GET  /simulation/domain/{domain_id}/export        export results (csv|json|checklist)
"""

from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..database import get_db
from ..simulator import simulate_failure, export_csv, export_checklist

router = APIRouter(prefix="/simulation", tags=["simulation"])


# ── Shared data loader ─────────────────────────────────────────────────────────

async def _load_all_items(db) -> list[dict]:
    """
    Fetch all media items with their per-file drive and domain info.
    Returns a list of item dicts ready for the simulator.
    """
    cursor = await db.execute("""
        SELECT mi.id, mi.title, mi.type, mi.status
        FROM media_items mi
        ORDER BY mi.id
    """)
    raw_items = await cursor.fetchall()

    if not raw_items:
        return []

    item_ids = [r["id"] for r in raw_items]
    placeholders = ",".join("?" * len(item_ids))

    cursor = await db.execute(f"""
        SELECT
            mif.media_item_id,
            f.id     AS file_id,
            f.path,
            f.size,
            r.path   AS root_path,
            d.id     AS drive_id,
            d.mount_path,
            d.domain_id
        FROM media_item_files mif
        JOIN files f  ON mif.file_id  = f.id
        JOIN roots r  ON f.root_id    = r.id
        JOIN drives d ON r.drive_id   = d.id
        WHERE mif.media_item_id IN ({placeholders})
    """, item_ids)
    file_rows = await cursor.fetchall()

    # Group files by item_id
    files_by_item: dict[int, list[dict]] = {r["id"]: [] for r in raw_items}
    for fr in file_rows:
        mid = fr["media_item_id"]
        if mid in files_by_item:
            files_by_item[mid].append({
                "file_id": fr["file_id"],
                "path": fr["path"],
                "size": fr["size"],
                "root_path": fr["root_path"],
                "drive_id": fr["drive_id"],
                "mount_path": fr["mount_path"],
                "domain_id": fr["domain_id"],
            })

    items = []
    for r in raw_items:
        items.append({
            "id": r["id"],
            "title": r["title"],
            "type": r["type"],
            "status": r["status"],
            "files": files_by_item.get(r["id"], []),
        })
    return items


# ── Picker endpoints ────────────────────────────────────────────────────────────

@router.get("/drives")
async def list_simulation_drives() -> dict:
    """List all drives with file counts and domain info for the simulation picker."""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT
                d.id, d.mount_path, d.volume_label, d.domain_id,
                fd.name AS domain_name,
                COUNT(DISTINCT f.id) AS file_count,
                COUNT(DISTINCT mif.media_item_id) AS item_count
            FROM drives d
            LEFT JOIN failure_domains fd ON d.domain_id = fd.id
            LEFT JOIN roots r ON r.drive_id = d.id
            LEFT JOIN files f ON f.root_id = r.id
            LEFT JOIN media_item_files mif ON mif.file_id = f.id
            GROUP BY d.id
            ORDER BY d.mount_path
        """)
        rows = await cursor.fetchall()
        return {"drives": [dict(r) for r in rows]}


@router.get("/domains")
async def list_simulation_domains() -> dict:
    """List all failure domains with drive counts for the simulation picker."""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT
                fd.id, fd.name, fd.description,
                COUNT(DISTINCT d.id) AS drive_count,
                COUNT(DISTINCT mif.media_item_id) AS item_count
            FROM failure_domains fd
            LEFT JOIN drives d ON d.domain_id = fd.id
            LEFT JOIN roots r ON r.drive_id = d.id
            LEFT JOIN files f ON f.root_id = r.id
            LEFT JOIN media_item_files mif ON mif.file_id = f.id
            GROUP BY fd.id
            ORDER BY fd.name
        """)
        rows = await cursor.fetchall()
        return {"domains": [dict(r) for r in rows]}


# ── Simulation runner ──────────────────────────────────────────────────────────

@router.get("/drive/{drive_id}")
async def simulate_drive_failure(drive_id: int) -> dict:
    """Simulate losing a single drive and return the impact analysis."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, mount_path, volume_label, domain_id FROM drives WHERE id = ?",
            (drive_id,),
        )
        drive = await cursor.fetchone()
        if not drive:
            raise HTTPException(status_code=404, detail="Drive not found")

        label = drive["volume_label"] or drive["mount_path"]
        items = await _load_all_items(db)

    result = simulate_failure(
        failed_drive_ids={drive_id},
        items=items,
        scope_label=label,
    )
    result["scope"] = "drive"
    result["target_id"] = drive_id
    result["target_label"] = label
    return result


@router.get("/domain/{domain_id}")
async def simulate_domain_failure(domain_id: int) -> dict:
    """Simulate losing all drives in a failure domain and return the impact analysis."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, name FROM failure_domains WHERE id = ?",
            (domain_id,),
        )
        domain = await cursor.fetchone()
        if not domain:
            raise HTTPException(status_code=404, detail="Failure domain not found")

        cursor = await db.execute(
            "SELECT id FROM drives WHERE domain_id = ?",
            (domain_id,),
        )
        drive_rows = await cursor.fetchall()
        if not drive_rows:
            raise HTTPException(
                status_code=400,
                detail="This domain has no drives assigned — simulation is empty",
            )

        failed_drive_ids = {r["id"] for r in drive_rows}
        items = await _load_all_items(db)

    result = simulate_failure(
        failed_drive_ids=failed_drive_ids,
        items=items,
        scope_label=domain["name"],
    )
    result["scope"] = "domain"
    result["target_id"] = domain_id
    result["target_label"] = domain["name"]
    result["failed_drive_count"] = len(failed_drive_ids)
    return result


# ── Export endpoints ───────────────────────────────────────────────────────────

@router.get("/drive/{drive_id}/export")
async def export_drive_simulation(
    drive_id: int,
    format: str = Query("csv", pattern="^(csv|json|checklist)$"),
) -> PlainTextResponse:
    """Export simulation results for a drive failure."""
    result = await simulate_drive_failure(drive_id)
    return _make_export(result, format)


@router.get("/domain/{domain_id}/export")
async def export_domain_simulation(
    domain_id: int,
    format: str = Query("csv", pattern="^(csv|json|checklist)$"),
) -> PlainTextResponse:
    """Export simulation results for a domain failure."""
    result = await simulate_domain_failure(domain_id)
    return _make_export(result, format)


def _make_export(result: dict, format: str) -> PlainTextResponse:
    if format == "csv":
        content = export_csv(result)
        media_type = "text/csv"
        filename = f"simulation_{result['target_id']}.csv"
    elif format == "json":
        content = json.dumps(result, indent=2, default=str)
        media_type = "application/json"
        filename = f"simulation_{result['target_id']}.json"
    else:  # checklist
        content = export_checklist(result)
        media_type = "text/markdown"
        filename = f"simulation_{result['target_id']}_checklist.md"

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
