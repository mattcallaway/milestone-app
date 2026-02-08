"""Media items API router."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..database import get_db
from ..matcher import merge_items, split_file, process_all_unlinked_files

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
async def list_items(
    type: Optional[str] = None,
    min_copies: Optional[int] = None,
    max_copies: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """List media items with filters."""
    async with get_db() as db:
        # Build query
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
        
        # Get items with copy count
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
        
        # Apply copy count filters in HAVING
        having_conditions = []
        if min_copies is not None:
            having_conditions.append(f"copy_count >= {min_copies}")
        if max_copies is not None:
            having_conditions.append(f"copy_count <= {max_copies}")
        
        if having_conditions:
            query += " HAVING " + " AND ".join(having_conditions)
        
        query += " ORDER BY mi.title, mi.season, mi.episode"
        
        # Get total count (without pagination)
        count_query = f"SELECT COUNT(*) FROM ({query})"
        cursor = await db.execute(count_query, params)
        total = (await cursor.fetchone())[0]
        
        # Apply pagination
        offset = (page - 1) * page_size
        query += f" LIMIT {page_size} OFFSET {offset}"
        
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        
        items = []
        for row in rows:
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
            })
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }


@router.get("/stats")
async def item_stats() -> dict:
    """Get media item statistics including copy counts."""
    async with get_db() as db:
        # Total items by type
        cursor = await db.execute("""
            SELECT type, COUNT(*) as count FROM media_items GROUP BY type
        """)
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
        
        return {
            "total_items": total_items,
            "by_type": by_type,
            "by_copy_count": by_copies,
            "needs_verification": needs_verification
        }


@router.get("/{item_id}")
async def get_item(item_id: int) -> dict:
    """Get media item detail with all file instances."""
    async with get_db() as db:
        # Get item
        cursor = await db.execute("""
            SELECT id, type, title, year, season, episode, status, created_at
            FROM media_items WHERE id = ?
        """, (item_id,))
        item = await cursor.fetchone()
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Get all files for this item
        cursor = await db.execute("""
            SELECT 
                f.id, f.path, f.size, f.ext, f.quick_sig, f.full_hash, f.hash_status,
                mif.is_primary,
                r.path as root_path,
                d.mount_path as drive_path
            FROM files f
            JOIN media_item_files mif ON f.id = mif.file_id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
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
            })
        
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
            "copy_count": len(file_list)
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
