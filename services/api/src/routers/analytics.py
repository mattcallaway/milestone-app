"""API router for analytics, heatmaps, and risk scoring."""

from fastapi import APIRouter, Query
from typing import Optional

from ..database import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/heatmap")
async def get_redundancy_heatmap() -> dict:
    """
    Redundancy heatmap: drives × item count, domain coverage, utilization.
    """
    async with get_db() as db:
        # Per-drive stats
        cursor = await db.execute(
            """SELECT 
                d.id as drive_id,
                d.mount_path,
                d.volume_label,
                d.free_space,
                d.total_space,
                fd.name as domain_name,
                COUNT(DISTINCT f.id) as file_count,
                COUNT(DISTINCT mif.media_item_id) as item_count,
                COALESCE(SUM(f.size), 0) as used_bytes
            FROM drives d
            LEFT JOIN failure_domains fd ON d.failure_domain_id = fd.id
            LEFT JOIN roots r ON r.drive_id = d.id
            LEFT JOIN files f ON f.root_id = r.id
            LEFT JOIN media_item_files mif ON mif.file_id = f.id
            GROUP BY d.id
            ORDER BY d.mount_path"""
        )
        drives = [dict(row) for row in await cursor.fetchall()]
        
        # Calculate utilization percentages
        for drive in drives:
            total = drive.get("total_space") or 0
            free = drive.get("free_space") or 0
            if total > 0:
                drive["utilization_pct"] = round((total - free) / total * 100, 1)
            else:
                drive["utilization_pct"] = 0
        
        # Domain coverage summary
        cursor = await db.execute(
            """SELECT 
                fd.id as domain_id,
                fd.name as domain_name,
                fd.domain_type,
                COUNT(DISTINCT d.id) as drive_count,
                COUNT(DISTINCT mif.media_item_id) as item_count
            FROM failure_domains fd
            LEFT JOIN drives d ON d.failure_domain_id = fd.id
            LEFT JOIN roots r ON r.drive_id = d.id
            LEFT JOIN files f ON f.root_id = r.id
            LEFT JOIN media_item_files mif ON mif.file_id = f.id
            GROUP BY fd.id"""
        )
        domains = [dict(row) for row in await cursor.fetchall()]
        
        # Hot spots: items with single-drive coverage
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt FROM (
                SELECT mi.id
                FROM media_items mi
                JOIN media_item_files mif ON mi.id = mif.media_item_id
                JOIN files f ON mif.file_id = f.id
                JOIN roots r ON f.root_id = r.id
                GROUP BY mi.id
                HAVING COUNT(DISTINCT r.drive_id) = 1
            )"""
        )
        single_drive_items = (await cursor.fetchone())["cnt"]
        
        return {
            "drives": drives,
            "domains": domains,
            "hot_spots": {
                "single_drive_items": single_drive_items,
            }
        }


@router.get("/risk-scores")
async def get_risk_scores(
    sort: str = Query("score", pattern="^(score|title|copies)$"),
    limit: int = Query(50, ge=1, le=500),
    min_risk: int = Query(0, ge=0, le=100)
) -> dict:
    """
    Per-item risk score based on:
    - Copy count (fewer = higher risk)
    - Failure-domain diversity (single domain = high risk)
    - Verification state (unverified = moderate risk)
    """
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT 
                mi.id as item_id,
                mi.type,
                mi.title,
                mi.status as verification_status,
                COUNT(DISTINCT mif.file_id) as copy_count,
                COUNT(DISTINCT r.drive_id) as drive_count,
                COUNT(DISTINCT d.failure_domain_id) as domain_count,
                COUNT(DISTINCT CASE WHEN f.full_hash IS NOT NULL THEN f.id END) as verified_copies
            FROM media_items mi
            JOIN media_item_files mif ON mi.id = mif.media_item_id
            JOIN files f ON mif.file_id = f.id
            JOIN roots r ON f.root_id = r.id
            JOIN drives d ON r.drive_id = d.id
            GROUP BY mi.id"""
        )
        items = [dict(row) for row in await cursor.fetchall()]
        
        # Calculate risk score (0-100, higher = more at risk)
        for item in items:
            score = 0
            
            # Copy count risk (0-40 points)
            copies = item["copy_count"]
            if copies == 0:
                score += 40
            elif copies == 1:
                score += 30
            elif copies == 2:
                score += 10
            # 3+ copies: 0 points
            
            # Domain diversity risk (0-30 points)
            domains = item["domain_count"]
            if domains == 0:
                score += 15  # No domains assigned
            elif domains == 1:
                score += 30  # Single domain = correlated failure risk
            # 2+ domains: 0 points
            
            # Verification risk (0-20 points)
            verified = item["verified_copies"]
            if verified == 0:
                score += 20
            elif verified < copies:
                score += 10
            
            # Drive diversity (0-10 points)
            if item["drive_count"] == 1:
                score += 10
            
            item["risk_score"] = min(score, 100)
            
            # Risk level label
            if score >= 70:
                item["risk_level"] = "critical"
            elif score >= 40:
                item["risk_level"] = "high"
            elif score >= 20:
                item["risk_level"] = "medium"
            else:
                item["risk_level"] = "low"
        
        # Filter and sort
        items = [i for i in items if i["risk_score"] >= min_risk]
        
        if sort == "score":
            items.sort(key=lambda x: x["risk_score"], reverse=True)
        elif sort == "title":
            items.sort(key=lambda x: x["title"] or "")
        elif sort == "copies":
            items.sort(key=lambda x: x["copy_count"])
        
        items = items[:limit]
        
        # Summary stats
        risk_distribution = {
            "critical": sum(1 for i in items if i["risk_level"] == "critical"),
            "high": sum(1 for i in items if i["risk_level"] == "high"),
            "medium": sum(1 for i in items if i["risk_level"] == "medium"),
            "low": sum(1 for i in items if i["risk_level"] == "low"),
        }
        
        return {
            "items": items,
            "total_scored": len(items),
            "risk_distribution": risk_distribution,
        }


@router.get("/at-risk")
async def get_at_risk_items(
    limit: int = Query(50, ge=1, le=200)
) -> dict:
    """Shortcut: most at-risk items, sorted by risk score descending."""
    return await get_risk_scores(sort="score", limit=limit, min_risk=30)
