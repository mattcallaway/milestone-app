"""Media items API router."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..database import get_db
from ..matcher import merge_items, split_file, process_all_unlinked_files
from ..resilience import compute_item_resilience, ALL_STATES

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
async def list_items(
    type: Optional[str] = None,
    min_copies: Optional[int] = None,
    max_copies: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    resilience_state: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """List media items with filters, including resilience state per item."""
    if resilience_state is not None and resilience_state not in ALL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resilience_state. Must be one of: {', '.join(ALL_STATES)}",
        )

    async with get_db() as db:
        # Build WHERE clause
        conditions = []
        params: list = []

        if type:
            conditions.append("mi.type = ?")
            params.append(type)
        if status:
            conditions.append("mi.status = ?")
            params.append(status)
        if search:
            conditions.append("mi.title LIKE ?")
            params.append(f"%{search}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Base query — copy_count via aggregate
        query = f"""
            SELECT
                mi.id, mi.type, mi.title, mi.year, mi.season, mi.episode,
                mi.status, mi.created_at,
                COUNT(mif.file_id) as copy_count
            FROM media_items mi
            LEFT JOIN media_item_files mif ON mi.id = mif.media_item_id
            WHERE {where_clause}
            GROUP BY mi.id
        """

        # HAVING copy_count filters — parameterized, never interpolated
        having_conditions = []
        having_params: list = []
        if min_copies is not None:
            having_conditions.append("copy_count >= ?")
            having_params.append(min_copies)
        if max_copies is not None:
            having_conditions.append("copy_count <= ?")
            having_params.append(max_copies)

        if having_conditions:
            query += " HAVING " + " AND ".join(having_conditions)

        query += " ORDER BY mi.title, mi.season, mi.episode"

        # Fetch all matching items (before pagination) so we can compute
        # resilience and apply the resilience_state filter in Python.
        # This is acceptable for typical library sizes (10k–100k items).
        all_params = params + having_params
        cursor = await db.execute(query, all_params)
        rows = await cursor.fetchall()

        # For each item, fetch its domains to compute resilience.
        # We batch this: one query to get all domain_ids for all item_ids.
        if rows:
            item_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(item_ids))
            cursor = await db.execute(
                f"""SELECT mif.media_item_id, d.id as drive_id, d.domain_id
                    FROM media_item_files mif
                    JOIN files f ON mif.file_id = f.id
                    JOIN roots r ON f.root_id = r.id
                    JOIN drives d ON r.drive_id = d.id
                    WHERE mif.media_item_id IN ({placeholders})""",
                item_ids,
            )
            domain_rows = await cursor.fetchall()

            # Group info by item_id
            item_domains: dict[int, list[dict]] = {r["id"]: [] for r in rows}
            for dr in domain_rows:
                mid = dr["media_item_id"]
                if mid in item_domains:
                    item_domains[mid].append({
                        "drive_id": dr["drive_id"],
                        "domain_id": dr["domain_id"]
                    })
        else:
            item_domains = {}

        # Build item list with resilience, applying resilience filter
        items = []
        for row in rows:
            file_domains = item_domains.get(row["id"], [])
            resilience = compute_item_resilience(file_domains)
            if resilience_state and resilience["resilience_state"] != resilience_state:
                continue
            items.append({
                "id": row["id"],
                "type": row["type"],
                "title": row["title"],
                "year": row["year"],
                "season": row["season"],
                "episode": row["episode"],
                "status": row["status"],
                "created_at": row["created_at"],
                "copy_count": row["copy_count"],
                "resilience_state": resilience["resilience_state"],
                "domain_mapping_complete": resilience["domain_mapping_complete"],
            })

        total = len(items)

        # Apply pagination
        offset = (page - 1) * page_size
        paged = items[offset: offset + page_size]

        return {
            "items": paged,
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get("/stats")
async def item_stats() -> dict:
    """Get media item statistics including copy counts and resilience breakdown."""
    async with get_db() as db:
        # Total items by type
        cursor = await db.execute(
            "SELECT type, COUNT(*) as count FROM media_items GROUP BY type"
        )
        by_type = {row["type"]: row["count"] for row in await cursor.fetchall()}

        # Items by copy count
        cursor = await db.execute("""
            SELECT copy_count, COUNT(*) as item_count FROM (
                SELECT mi.id, COUNT(mif.file_id) as copy_count
                FROM media_items mi
                LEFT JOIN media_item_files mif ON mi.id = mif.media_item_id
                GROUP BY mi.id
            ) GROUP BY copy_count
        """)
        by_copies = {row["copy_count"]: row["item_count"] for row in await cursor.fetchall()}

        # Total items
        cursor = await db.execute("SELECT COUNT(*) FROM media_items")
        total_items = (await cursor.fetchone())[0]

        # Items needing verification
        cursor = await db.execute(
            "SELECT COUNT(*) FROM media_items WHERE status = 'needs_verification'"
        )
        needs_verification = (await cursor.fetchone())[0]

        # Resilience breakdown — fetch domain_id per file per item
        cursor = await db.execute("""
            SELECT mi.id, COUNT(mif.file_id) as copy_count
            FROM media_items mi
            LEFT JOIN media_item_files mif ON mi.id = mif.media_item_id
            GROUP BY mi.id
        """)
        all_items = await cursor.fetchall()

        by_resilience: dict[str, int] = {s: 0 for s in ALL_STATES}
        incomplete_domain_mapping = 0

        if all_items:
            item_ids = [r["id"] for r in all_items]
            placeholders = ",".join("?" * len(item_ids))
            cursor = await db.execute(
                f"""SELECT mif.media_item_id, d.id as drive_id, d.domain_id
                    FROM media_item_files mif
                    JOIN files f ON mif.file_id = f.id
                    JOIN roots r ON f.root_id = r.id
                    JOIN drives d ON r.drive_id = d.id
                    WHERE mif.media_item_id IN ({placeholders})""",
                item_ids,
            )
            domain_rows = await cursor.fetchall()
            item_domain_map: dict[int, list[dict]] = {r["id"]: [] for r in all_items}
            for dr in domain_rows:
                mid = dr["media_item_id"]
                if mid in item_domain_map:
                    item_domain_map[mid].append({
                        "drive_id": dr["drive_id"],
                        "domain_id": dr["domain_id"]
                    })

            for item_row in all_items:
                file_domains = item_domain_map.get(item_row["id"], [])
                res = compute_item_resilience(file_domains)
                by_resilience[res["resilience_state"]] += 1
                if not res["domain_mapping_complete"]:
                    incomplete_domain_mapping += 1

        return {
            "total_items": total_items,
            "by_type": by_type,
            "by_copy_count": by_copies,
            "needs_verification": needs_verification,
            "by_resilience_state": by_resilience,
            "incomplete_domain_mapping": incomplete_domain_mapping,
        }


@router.get("/{item_id}")
async def get_item(item_id: int) -> dict:
    """Get media item detail with all file instances and resilience state."""
    async with get_db() as db:
        # Get item
        cursor = await db.execute("""
            SELECT id, type, title, year, season, episode, status, created_at
            FROM media_items WHERE id = ?
        """, (item_id,))
        item = await cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Get all files with drive → domain info
        cursor = await db.execute("""
            SELECT
                f.id, f.path, f.size, f.ext, f.quick_sig, f.full_hash, f.hash_status,
                mif.is_primary,
                r.path as root_path,
                d.id as drive_id,
                d.mount_path as drive_path,
                d.domain_id,
                fd.name as domain_name
            FROM files f
            JOIN media_item_files mif ON f.id = mif.file_id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            LEFT JOIN failure_domains fd ON d.domain_id = fd.id
            WHERE mif.media_item_id = ?
        """, (item_id,))
        files = await cursor.fetchall()

        file_list = []
        for f in files:
            file_list.append({
                "id": f["id"],
                "path": f["path"],
                "size": f["size"],
                "ext": f["ext"],
                "quick_sig": f["quick_sig"],
                "full_hash": f["full_hash"],
                "hash_status": f["hash_status"],
                "is_primary": bool(f["is_primary"]),
                "root_path": f["root_path"],
                "drive_path": f["drive_path"],
                "domain_id": f["domain_id"],
                "domain_name": f["domain_name"],
            })

        resilience = compute_item_resilience(file_list)

        return {
            "id": item["id"],
            "type": item["type"],
            "title": item["title"],
            "year": item["year"],
            "season": item["season"],
            "episode": item["episode"],
            "status": item["status"],
            "created_at": item["created_at"],
            "files": file_list,
            "copy_count": len(file_list),
            "resilience_state": resilience["resilience_state"],
            "domain_mapping_complete": resilience["domain_mapping_complete"],
            "distinct_domains": resilience["distinct_domains"],
        }


@router.post("/merge")
async def merge(target_id: int, source_ids: list[int]) -> dict:
    """Merge multiple media items into one."""
    result = await merge_items(target_id, source_ids)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/split")
async def split(file_id: int) -> dict:
    """Split a file out of its media item into a new one."""
    result = await split_file(file_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/process")
async def process_unlinked() -> dict:
    """Process all unlinked files and create/link media items."""
    result = await process_all_unlinked_files()
    return result


@router.patch("/{item_id}")
async def update_item(
    item_id: int,
    title: Optional[str] = None,
    year: Optional[int] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    type: Optional[str] = None,
) -> dict:
    """Update media item metadata."""
    async with get_db() as db:
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if year is not None:
            updates.append("year = ?")
            params.append(year)
        if season is not None:
            updates.append("season = ?")
            params.append(season)
        if episode is not None:
            updates.append("episode = ?")
            params.append(episode)
        if type is not None:
            updates.append("type = ?")
            params.append(type)

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(item_id)
        query = f"UPDATE media_items SET {', '.join(updates)} WHERE id = ?"

        cursor = await db.execute(query, params)
        await db.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")

        return {"message": "Updated", "id": item_id}
