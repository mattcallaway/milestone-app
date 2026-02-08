"""Scan API router."""

from fastapi import APIRouter, HTTPException

from ..models import ScanRequest, ScanStatus, ScanControl, ScanState
from ..scanner import (
    start_scan as _start_scan,
    pause_scan as _pause_scan,
    resume_scan as _resume_scan,
    cancel_scan as _cancel_scan,
    get_scan_status as _get_status
)

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("/start", response_model=ScanStatus)
async def start_scan(data: ScanRequest) -> ScanStatus:
    """Start a file scan."""
    success = _start_scan(data.drive_id, data.throttle)
    if not success:
        raise HTTPException(status_code=400, detail="Scan already running")
    
    status = _get_status()
    return ScanStatus(**status)


@router.get("/status", response_model=ScanStatus)
async def get_scan_status() -> ScanStatus:
    """Get current scan status."""
    status = _get_status()
    return ScanStatus(**status)


@router.post("/control", response_model=ScanStatus)
async def control_scan(data: ScanControl) -> ScanStatus:
    """Control scan: pause, resume, or cancel."""
    action_handlers = {
        "pause": _pause_scan,
        "resume": _resume_scan,
        "cancel": _cancel_scan,
    }
    
    handler = action_handlers.get(data.action)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown action: {data.action}")
    
    success = handler()
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot {data.action} scan in current state"
        )
    
    status = _get_status()
    return ScanStatus(**status)
