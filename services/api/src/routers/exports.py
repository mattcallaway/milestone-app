"""API router for CSV exports."""

import csv
import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..database import get_db


router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/at-risk")
async def export_at_risk_csv():
    """
    Export CSV of at-risk items (0-1 copies).
    Includes item details and file locations.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                mi.year,
                mi.season,
                mi.episode,
                mi.status,
                COUNT(mif.file_id) as copy_count,
                GROUP_CONCAT(f.path, '|') as file_paths,
                SUM(f.size) as total_size
            FROM media_items mi
            LEFT JOIN media_item_files mif ON mi.id = mif.media_item_id
            LEFT JOIN files f ON mif.file_id = f.id
            GROUP BY mi.id
            HAVING copy_count <= 1
            ORDER BY copy_count ASC, mi.title
            """
        )
        rows = await cursor.fetchall()
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Item ID", "Type", "Title", "Year", "Season", "Episode",
        "Status", "Copy Count", "File Paths", "Total Size (bytes)"
    ])
    
    # Data rows
    for row in rows:
        writer.writerow([
            row["item_id"],
            row["type"],
            row["title"] or "",
            row["year"] or "",
            row["season"] or "",
            row["episode"] or "",
            row["status"],
            row["copy_count"],
            row["file_paths"] or "",
            row["total_size"] or 0
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=at_risk_report.csv"}
    )


@router.get("/inventory")
async def export_full_inventory_csv():
    """
    Export full inventory CSV with all items and files.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                mi.year,
                mi.season,
                mi.episode,
                mi.status,
                f.id as file_id,
                f.path,
                f.size,
                f.ext,
                f.quick_sig,
                f.full_hash,
                f.hash_status,
                d.mount_path as drive,
                d.volume_label,
                mif.is_primary
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            ORDER BY mi.title, mi.season, mi.episode, f.path
            """
        )
        rows = await cursor.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Item ID", "Type", "Title", "Year", "Season", "Episode", "Status",
        "File ID", "Path", "Size (bytes)", "Extension", 
        "Quick Signature", "Full Hash", "Hash Status",
        "Drive", "Volume Label", "Is Primary"
    ])
    
    for row in rows:
        writer.writerow([
            row["item_id"],
            row["type"],
            row["title"] or "",
            row["year"] or "",
            row["season"] or "",
            row["episode"] or "",
            row["status"],
            row["file_id"],
            row["path"],
            row["size"] or 0,
            row["ext"] or "",
            row["quick_sig"] or "",
            row["full_hash"] or "",
            row["hash_status"],
            row["drive"],
            row["volume_label"] or "",
            "Yes" if row["is_primary"] else "No"
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=full_inventory.csv"}
    )


@router.get("/duplicates")
async def export_duplicates_csv():
    """
    Export CSV of items with 3+ copies (potential duplicates to clean up).
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                mi.year,
                COUNT(mif.file_id) as copy_count,
                SUM(f.size) as total_size,
                GROUP_CONCAT(d.mount_path || ':' || f.path, '|') as locations
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            GROUP BY mi.id
            HAVING copy_count >= 3
            ORDER BY copy_count DESC, total_size DESC
            """
        )
        rows = await cursor.fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Item ID", "Type", "Title", "Year", "Copy Count",
        "Total Size (bytes)", "Locations"
    ])
    
    for row in rows:
        writer.writerow([
            row["item_id"],
            row["type"],
            row["title"] or "",
            row["year"] or "",
            row["copy_count"],
            row["total_size"] or 0,
            row["locations"] or ""
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=duplicates_report.csv"}
    )
