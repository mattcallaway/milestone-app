"""File scanner service with background task support."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any

from .database import get_db
from .models import ScanState, ThrottleLevel

# Global scan state
_scan_state = ScanState.IDLE
_scan_status = {
    "state": ScanState.IDLE,
    "current_root": None,
    "files_scanned": 0,
    "files_total": None,
    "files_new": 0,
    "files_updated": 0,
    "files_missing": 0,
    "started_at": None,
    "eta_seconds": None,
}
_scan_task: Optional[asyncio.Task] = None
_cancel_requested = False
_pause_requested = False

# Log paths
LOG_DIR = Path(__file__).parent.parent / "data" / "logs"
JSONL_LOG: Optional[Path] = None
TEXT_LOG: Optional[Path] = None


def get_throttle_delay(level: ThrottleLevel) -> float:
    """Get delay in seconds for throttle level."""
    delays = {
        ThrottleLevel.LOW: 0.1,    # 100ms
        ThrottleLevel.NORMAL: 0.01, # 10ms
        ThrottleLevel.FAST: 0.0,    # No delay
    }
    return delays.get(level, 0.01)


def get_scan_status() -> dict:
    """Get current scan status."""
    return {**_scan_status, "state": _scan_state}


def log_event(event_type: str, data: dict) -> None:
    """Log scan event to both JSONL and readable log."""
    timestamp = datetime.now().isoformat()
    
    if JSONL_LOG:
        entry = {"timestamp": timestamp, "type": event_type, **data}
        with open(JSONL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    
    if TEXT_LOG:
        message = f"[{timestamp}] {event_type}: {data}"
        with open(TEXT_LOG, "a", encoding="utf-8") as f:
            f.write(message + "\n")


async def scan_directory(
    root_id: int,
    root_path: str,
    throttle: ThrottleLevel,
    progress_callback: Optional[Callable[[dict], Any]] = None
) -> dict:
    """Scan a directory and update database."""
    global _scan_state, _scan_status, _cancel_requested, _pause_requested
    
    delay = get_throttle_delay(throttle)
    stats = {"new": 0, "updated": 0, "unchanged": 0}
    scan_time = datetime.now().isoformat()
    
    async with get_db() as db:
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Check for cancel/pause
            if _cancel_requested:
                log_event("scan_cancelled", {"root": root_path})
                return stats
            
            while _pause_requested:
                _scan_state = ScanState.PAUSED
                await asyncio.sleep(0.5)
            
            _scan_state = ScanState.RUNNING
            
            for filename in filenames:
                if _cancel_requested:
                    return stats
                
                filepath = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(filepath)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    ext = os.path.splitext(filename)[1].lower().lstrip(".")
                    
                    # Check if file exists in DB
                    cursor = await db.execute(
                        "SELECT id, mtime FROM files WHERE root_id = ? AND path = ?",
                        (root_id, filepath)
                    )
                    existing = await cursor.fetchone()
                    
                    if existing:
                        if existing["mtime"] != mtime:
                            # File was modified
                            await db.execute(
                                """UPDATE files SET size = ?, mtime = ?, ext = ?, last_seen = ?
                                   WHERE id = ?""",
                                (size, mtime, ext, scan_time, existing["id"])
                            )
                            stats["updated"] += 1
                        else:
                            # Just update last_seen
                            await db.execute(
                                "UPDATE files SET last_seen = ? WHERE id = ?",
                                (scan_time, existing["id"])
                            )
                            stats["unchanged"] += 1
                    else:
                        # New file
                        await db.execute(
                            """INSERT INTO files (root_id, path, size, mtime, ext, last_seen)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (root_id, filepath, size, mtime, ext, scan_time)
                        )
                        stats["new"] += 1
                    
                    _scan_status["files_scanned"] += 1
                    _scan_status["files_new"] = stats["new"]
                    _scan_status["files_updated"] = stats["updated"]
                    
                    if delay > 0:
                        await asyncio.sleep(delay)
                        
                except (OSError, PermissionError) as e:
                    log_event("file_error", {"path": filepath, "error": str(e)})
                    continue
            
            # Commit periodically
            await db.commit()
        
        # Mark missing files (files that weren't seen in this scan)
        cursor = await db.execute(
            """UPDATE files SET last_seen = NULL 
               WHERE root_id = ? AND (last_seen IS NULL OR last_seen < ?)""",
            (root_id, scan_time)
        )
        _scan_status["files_missing"] = cursor.rowcount
        await db.commit()
    
    return stats


async def run_scan(drive_id: Optional[int], throttle: ThrottleLevel) -> None:
    """Run scan on specified drive or all drives."""
    global _scan_state, _scan_status, _cancel_requested, _pause_requested
    global JSONL_LOG, TEXT_LOG
    
    _scan_state = ScanState.RUNNING
    _cancel_requested = False
    _pause_requested = False
    _scan_status["started_at"] = datetime.now().isoformat()
    _scan_status["files_scanned"] = 0
    _scan_status["files_new"] = 0
    _scan_status["files_updated"] = 0
    _scan_status["files_missing"] = 0
    
    # Setup logging
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    JSONL_LOG = LOG_DIR / f"scan_{timestamp}.jsonl"
    TEXT_LOG = LOG_DIR / f"scan_{timestamp}.log"
    
    log_event("scan_started", {"drive_id": drive_id, "throttle": throttle.value})
    
    try:
        async with get_db() as db:
            # Get roots to scan
            if drive_id is not None:
                cursor = await db.execute(
                    "SELECT id, path FROM roots WHERE drive_id = ? AND excluded = 0",
                    (drive_id,)
                )
            else:
                cursor = await db.execute(
                    "SELECT id, path FROM roots WHERE excluded = 0"
                )
            roots = await cursor.fetchall()
        
        for root in roots:
            if _cancel_requested:
                break
            
            _scan_status["current_root"] = root["path"]
            log_event("scanning_root", {"root_id": root["id"], "path": root["path"]})
            
            stats = await scan_directory(root["id"], root["path"], throttle)
            log_event("root_complete", {
                "root_id": root["id"],
                "new": stats["new"],
                "updated": stats["updated"]
            })
        
        if _cancel_requested:
            _scan_state = ScanState.CANCELLED
        else:
            _scan_state = ScanState.COMPLETED
        
        log_event("scan_complete", {
            "state": _scan_state.value,
            "files_scanned": _scan_status["files_scanned"],
            "files_new": _scan_status["files_new"],
            "files_updated": _scan_status["files_updated"],
            "files_missing": _scan_status["files_missing"]
        })
        
    except Exception as e:
        _scan_state = ScanState.IDLE
        log_event("scan_error", {"error": str(e)})
        raise


def start_scan(drive_id: Optional[int], throttle: ThrottleLevel) -> bool:
    """Start a background scan task."""
    global _scan_task, _scan_state
    
    if _scan_state == ScanState.RUNNING:
        return False
    
    _scan_task = asyncio.create_task(run_scan(drive_id, throttle))
    return True


def pause_scan() -> bool:
    """Pause the current scan."""
    global _pause_requested
    if _scan_state == ScanState.RUNNING:
        _pause_requested = True
        return True
    return False


def resume_scan() -> bool:
    """Resume a paused scan."""
    global _pause_requested
    if _scan_state == ScanState.PAUSED:
        _pause_requested = False
        return True
    return False


def cancel_scan() -> bool:
    """Cancel the current scan."""
    global _cancel_requested
    if _scan_state in (ScanState.RUNNING, ScanState.PAUSED):
        _cancel_requested = True
        return True
    return False
