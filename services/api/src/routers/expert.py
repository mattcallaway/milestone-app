"""API router for Expert Mode management."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..expert import (
    activate_expert_mode,
    deactivate_expert_mode,
    get_expert_status,
    CONFIRMATION_PHRASE,
)

router = APIRouter(prefix="/expert", tags=["expert"])


class ActivateRequest(BaseModel):
    phrase: str
    persist: bool = False


@router.post("/activate")
async def activate_endpoint(request: ActivateRequest) -> dict:
    """
    Activate Expert Mode.
    
    Requires typing the exact confirmation phrase:
    "I UNDERSTAND THIS SOFTWARE CAN CAUSE IRREVERSIBLE DATA LOSS"
    
    Set persist=true to keep active across restarts (additional risk).
    """
    try:
        result = activate_expert_mode(request.phrase, request.persist)
        return {"message": "Expert Mode activated", **result}
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/deactivate")
async def deactivate_endpoint() -> dict:
    """Deactivate Expert Mode."""
    result = deactivate_expert_mode()
    return {"message": "Expert Mode deactivated", **result}


@router.get("/status")
async def status_endpoint() -> dict:
    """Get current Expert Mode status."""
    return get_expert_status()
