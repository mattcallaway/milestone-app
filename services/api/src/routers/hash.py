"""Hash computation API router."""

from fastapi import APIRouter

from ..hasher import (
    start_hash_computation,
    get_hash_status,
    stop_hashing,
    queue_pending_files,
    hash_file
)

router = APIRouter(prefix="/hash", tags=["hash"])


@router.post("/compute")
async def compute_hashes(file_ids: list[int] | None = None) -> dict:
    """
    Start hash computation for specified files or all pending files.
    """
    if file_ids is None:
        count = await queue_pending_files()
        if count == 0:
            return {"message": "No pending files to hash", "queued": 0}
        file_ids = None  # Will use the queue
    
    success = start_hash_computation(file_ids)
    if not success:
        return {"error": "Hash computation already running"}
    
    status = get_hash_status()
    return {"message": "Hash computation started", "status": status}


@router.get("/status")
async def hash_status() -> dict:
    """Get current hash computation status."""
    return get_hash_status()


@router.post("/stop")
async def stop_hash() -> dict:
    """Stop hash computation."""
    success = stop_hashing()
    return {"stopped": success}


@router.post("/file/{file_id}")
async def hash_single_file(file_id: int) -> dict:
    """Hash a single file immediately."""
    result = await hash_file(file_id)
    return result
