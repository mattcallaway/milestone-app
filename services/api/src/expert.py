"""
Expert Mode runtime state management.

Expert Mode is a safety gate that must be explicitly activated by the user
before dangerous operations are allowed. It requires typing an exact
confirmation phrase and is session-scoped by default (resets on restart).
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# The exact phrase required to activate Expert Mode
CONFIRMATION_PHRASE = "I UNDERSTAND THIS SOFTWARE CAN CAUSE IRREVERSIBLE DATA LOSS"

# Runtime state (session-scoped, resets on process restart)
_expert_state = {
    "active": False,
    "activated_at": None,
    "persistent": False,
}


def activate_expert_mode(confirmation_phrase: str, persist: bool = False) -> dict:
    """
    Activate Expert Mode after validating the confirmation phrase.
    
    Args:
        confirmation_phrase: Must exactly match CONFIRMATION_PHRASE
        persist: If True, expert mode survives app restarts (stored in DB)
        
    Returns:
        Status dict with activation details
        
    Raises:
        ValueError: If confirmation phrase doesn't match
    """
    if confirmation_phrase != CONFIRMATION_PHRASE:
        logger.warning("Expert Mode activation failed: incorrect confirmation phrase")
        raise ValueError(
            "Incorrect confirmation phrase. "
            "Expert Mode requires exact phrase to activate."
        )
    
    _expert_state["active"] = True
    _expert_state["activated_at"] = datetime.now().isoformat()
    _expert_state["persistent"] = persist
    
    logger.warning(
        "EXPERT MODE ACTIVATED (persistent=%s) at %s",
        persist, _expert_state["activated_at"]
    )
    
    return get_expert_status()


def deactivate_expert_mode() -> dict:
    """Deactivate Expert Mode."""
    was_active = _expert_state["active"]
    _expert_state["active"] = False
    _expert_state["activated_at"] = None
    _expert_state["persistent"] = False
    
    if was_active:
        logger.info("Expert Mode deactivated")
    
    return get_expert_status()


def is_expert_enabled() -> bool:
    """Check if Expert Mode is currently active."""
    return _expert_state["active"]


def get_expert_status() -> dict:
    """Get current Expert Mode status."""
    return {
        "active": _expert_state["active"],
        "activated_at": _expert_state["activated_at"],
        "session_only": not _expert_state["persistent"],
    }


def require_expert():
    """
    FastAPI dependency that enforces Expert Mode.
    
    Usage in routers:
        @router.post("/dangerous-action")
        async def dangerous_action(expert = Depends(require_expert)):
            ...
    
    Raises HTTPException 403 if Expert Mode is not active.
    """
    if not is_expert_enabled():
        raise HTTPException(
            status_code=403,
            detail="Expert Mode is required for this operation. "
                   "Enable it in Settings → Expert Mode."
        )
    return True
