"""Files API router."""

from fastapi import APIRouter, Query

from ..database import get_db
from ..models import FileItem, FileList

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=FileList)
async def list_files(
    root_id: int | None = None,
    ext: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    path_contains: str | None = None,
    missing: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> FileList:
    """List files with optional filters."""
    async with get_db() as db:
        # Build query with filters
        conditions = []
        params: list = []
        
        if root_id is not None:
            conditions.append("root_id = ?")
            params.append(root_id)
        
        if ext is not None:
            conditions.append("ext = ?")
            params.append(ext.lower().lstrip("."))
        
        if min_size is not None:
            conditions.append("size >= ?")
            params.append(min_size)
        
        if max_size is not None:
            conditions.append("size <= ?")
            params.append(max_size)
        
        if path_contains is not None:
            conditions.append("path LIKE ?")
            params.append(f"%{path_contains}%")
        
        if missing is not None:
            if missing:
                conditions.append("last_seen < datetime('now', '-1 day')")
            else:
                conditions.append("last_seen >= datetime('now', '-1 day')")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM files WHERE {where_clause}"
        cursor = await db.execute(count_query, params)
        total = (await cursor.fetchone())[0]
        
        # Get paginated results
        offset = (page - 1) * page_size
        query = f"""
            SELECT id, root_id, path, size, mtime, ext, last_seen, signature_stub
            FROM files
            WHERE {where_clause}
            ORDER BY path
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query, params + [page_size, offset])
        rows = await cursor.fetchall()
        
        files = [
            FileItem(
                id=row["id"],
                root_id=row["root_id"],
                path=row["path"],
                size=row["size"],
                mtime=row["mtime"],
                ext=row["ext"],
                last_seen=row["last_seen"],
                signature_stub=row["signature_stub"]
            )
            for row in rows
        ]
        
        return FileList(
            files=files,
            total=total,
            page=page,
            page_size=page_size
        )


@router.get("/stats")
async def file_stats() -> dict:
    """Get file statistics."""
    async with get_db() as db:
        # Total files
        cursor = await db.execute("SELECT COUNT(*) FROM files")
        total_files = (await cursor.fetchone())[0]
        
        # Total size
        cursor = await db.execute("SELECT COALESCE(SUM(size), 0) FROM files")
        total_size = (await cursor.fetchone())[0]
        
        # Files by extension
        cursor = await db.execute("""
            SELECT ext, COUNT(*) as count, COALESCE(SUM(size), 0) as size
            FROM files
            WHERE ext IS NOT NULL
            GROUP BY ext
            ORDER BY count DESC
            LIMIT 20
        """)
        ext_stats = [
            {"ext": row["ext"], "count": row["count"], "size": row["size"]}
            for row in await cursor.fetchall()
        ]
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "by_extension": ext_stats
        }
