"""
Sidecar Integrity API Router
==============================
Endpoints:
  GET  /items/{item_id}/sidecars               detect side-car files for an item
  GET  /items/{item_id}/sidecars/completeness  cross-drive completeness summary
  GET  /items/{item_id}/sidecars/manifest      copy manifest with sidecar policy
  GET  /sidecars/report                        library-wide sidecar completeness report
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..sidecars import (
    detect_sidecars,
    compute_completeness,
    build_copy_manifest,
    DEFAULT_COPY_POLICY,
    get_sidecar_category,
    is_primary,
)

router = APIRouter(tags=["sidecars"])


# ── Shared DB loader ──────────────────────────────────────────────────────────

async def _load_item_files(db, item_id: int) -> list[dict]:
    """
    Load primary video files for an item plus all files in the same directory
    on the same drive (potential sidecars).
    """
    cursor = await db.execute("SELECT id FROM media_items WHERE id = ?", (item_id,))
    if not await cursor.fetchone():
        return []

    # Primary files for this item
    cursor = await db.execute("""
        SELECT f.id AS file_id, f.path, f.size, r.id AS root_id,
               d.id AS drive_id, d.mount_path,
               COALESCE(d.health_status, 'healthy') AS health_status,
               d.domain_id
        FROM media_item_files mif
        JOIN files f  ON mif.file_id = f.id
        JOIN roots r  ON f.root_id   = r.id
        JOIN drives d ON r.drive_id  = d.id
        WHERE mif.media_item_id = ?
    """, (item_id,))
    primary_rows = await cursor.fetchall()
    return [dict(r) for r in primary_rows]


async def _load_dir_files(db, root_id: int, directory: str) -> list[dict]:
    """
    Load all files in a directory for a given root
    (used to find sidecar candidates alongside a primary).
    """
    like_pattern = directory.rstrip("/") + "/%"
    cursor = await db.execute("""
        SELECT f.id, f.path, f.size
        FROM files f
        WHERE f.root_id = ?
          AND f.path LIKE ?
          AND f.path NOT LIKE ? || '/%/%'
    """, (root_id, like_pattern, directory.rstrip("/")))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


def _dir_of(path: str) -> str:
    """Return the parent directory of a path (forward-slash normalised)."""
    norm = path.replace("\\", "/")
    parts = norm.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


# ── Endpoint: sidecars for one item ──────────────────────────────────────────

@router.get("/items/{item_id}/sidecars")
async def get_item_sidecars(item_id: int) -> dict:
    """
    Return all detected sidecar files for each copy of an item, grouped by drive.
    """
    async with get_db() as db:
        primary_files = await _load_item_files(db, item_id)
        if not primary_files:
            raise HTTPException(status_code=404, detail="Item not found or has no files")

        results = []
        for pf in primary_files:
            directory = _dir_of(pf["path"])
            dir_files = await _load_dir_files(db, pf["root_id"], directory)
            all_paths = [f["path"] for f in dir_files]
            size_by_path = {f["path"]: f["size"] for f in dir_files}

            detected = detect_sidecars(all_paths, primary_paths=[pf["path"]])
            sidecars = detected[0]["sidecars"] if detected else []

            # Attach size info
            for sc in sidecars:
                sc["size"] = size_by_path.get(sc["path"])

            results.append({
                "file_id": pf["file_id"],
                "primary_path": pf["path"],
                "drive_id": pf["drive_id"],
                "drive_mount": pf["mount_path"],
                "domain_id": pf["domain_id"],
                "sidecars": sidecars,
                "sidecar_count": len(sidecars),
            })

    return {"item_id": item_id, "copies": results}


# ── Endpoint: cross-drive completeness ───────────────────────────────────────

@router.get("/items/{item_id}/sidecars/completeness")
async def get_sidecar_completeness(
    item_id: int,
    include_subtitles: bool = Query(True),
    include_metadata: bool = Query(True),
    include_artwork: bool = Query(False),
) -> dict:
    """
    Return a cross-drive sidecar completeness analysis.

    completeness values:
      complete    — all drives have all included sidecars
      partial     — at least one drive is missing included sidecars
      no_sidecars — no included sidecars detected on any drive
    """
    policy = {
        "subtitle": include_subtitles,
        "metadata": include_metadata,
        "artwork":  include_artwork,
    }

    async with get_db() as db:
        primary_files = await _load_item_files(db, item_id)
        if not primary_files:
            raise HTTPException(status_code=404, detail="Item not found or has no files")

        sidecars_by_drive: dict[int, list[dict]] = {}
        for pf in primary_files:
            directory = _dir_of(pf["path"])
            dir_files = await _load_dir_files(db, pf["root_id"], directory)
            all_paths = [f["path"] for f in dir_files]

            detected = detect_sidecars(all_paths, primary_paths=[pf["path"]])
            sidecars_by_drive[pf["drive_id"]] = detected[0]["sidecars"] if detected else []

    result = compute_completeness(sidecars_by_drive, policy)
    result["item_id"] = item_id
    result["copy_count"] = len(primary_files)
    result["policy"] = policy
    return result


# ── Endpoint: copy manifest ───────────────────────────────────────────────────

@router.get("/items/{item_id}/sidecars/manifest")
async def get_copy_manifest(
    item_id: int,
    source_drive_id: int = Query(..., description="Which drive's copy to use as source"),
    include_subtitles: bool = Query(True),
    include_metadata: bool = Query(True),
    include_artwork: bool = Query(False),
) -> dict:
    """
    Return the ordered list of files (primary + policy-filtered sidecars)
    that should be copied when duplicating this item from a specific drive.
    """
    policy = {
        "subtitle": include_subtitles,
        "metadata": include_metadata,
        "artwork":  include_artwork,
    }

    async with get_db() as db:
        primary_files = await _load_item_files(db, item_id)
        if not primary_files:
            raise HTTPException(status_code=404, detail="Item not found or has no files")

        source = next((pf for pf in primary_files if pf["drive_id"] == source_drive_id), None)
        if not source:
            raise HTTPException(
                status_code=404,
                detail=f"No copy of item {item_id} found on drive {source_drive_id}",
            )

        directory = _dir_of(source["path"])
        dir_files = await _load_dir_files(db, source["root_id"], directory)
        all_paths = [f["path"] for f in dir_files]
        size_by_path = {f["path"]: f["size"] for f in dir_files}

        detected = detect_sidecars(all_paths, primary_paths=[source["path"]])
        sidecars = detected[0]["sidecars"] if detected else []

        # Attach sizes
        for sc in sidecars:
            sc["size"] = size_by_path.get(sc["path"])

    manifest = build_copy_manifest(source["path"], sidecars, policy)
    # Attach sizes to manifest entries
    for entry in manifest:
        entry["size"] = size_by_path.get(entry["path"])

    total_size = sum(e.get("size") or 0 for e in manifest)

    return {
        "item_id": item_id,
        "source_drive_id": source_drive_id,
        "policy": policy,
        "manifest": manifest,
        "file_count": len(manifest),
        "total_size_bytes": total_size,
    }


# ── Library-wide report ───────────────────────────────────────────────────────

@router.get("/sidecars/report")
async def get_sidecar_report(limit: int = Query(50)) -> dict:
    """
    Scan all items and return a completeness report.
    Returns items with complete, partial, and no-sidecar coverage.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, type FROM media_items ORDER BY id LIMIT ?",
            (limit,),
        )
        items = await cursor.fetchall()

        complete_items: list[dict] = []
        partial_items: list[dict] = []
        no_sidecar_items: list[dict] = []

        for row in items:
            item_id = row["id"]
            primary_files = await _load_item_files(db, item_id)
            if not primary_files:
                continue

            sidecars_by_drive: dict[int, list[dict]] = {}
            for pf in primary_files:
                directory = _dir_of(pf["path"])
                dir_files = await _load_dir_files(db, pf["root_id"], directory)
                all_paths = [f["path"] for f in dir_files]
                detected = detect_sidecars(all_paths, primary_paths=[pf["path"]])
                sidecars_by_drive[pf["drive_id"]] = detected[0]["sidecars"] if detected else []

            result = compute_completeness(sidecars_by_drive)
            info = {
                "id": item_id,
                "title": row["title"],
                "type": row["type"],
                "completeness": result["completeness"],
                "total_unique_sidecars": result["total_unique_sidecars"],
                "missing_on_any_drive": result["missing_on_any_drive"],
                "copy_count": len(primary_files),
            }

            if result["completeness"] == "complete":
                complete_items.append(info)
            elif result["completeness"] == "partial":
                partial_items.append(info)
            else:
                no_sidecar_items.append(info)

    return {
        "total_scanned": len(items),
        "complete": complete_items,
        "partial": partial_items,
        "no_sidecars": no_sidecar_items,
        "summary": {
            "complete_count": len(complete_items),
            "partial_count": len(partial_items),
            "no_sidecars_count": len(no_sidecar_items),
        },
    }
