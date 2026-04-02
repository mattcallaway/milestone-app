"""
Risk Scoring Engine
====================
Pure, database-free module computing a 0–100 risk score for each media item.

Score: 0 = zero risk (perfectly protected), 100 = maximum risk (loss imminent).

Scoring formula (additive, clamped to [0, 100]):

  Base score from resilience state:
    unsafe_no_backup            → 75
    unsafe_single_domain        → 50
    over_replicated_but_fragile → 30
    safe_two_domains            → 10
    over_replicated_and_resilient→  2
    None / unknown              → 85

  Drive-health modifier:
    +20  any copy is on a 'degraded' drive
    +12  any copy is on a 'warning' drive
    + 6  any copy is on an 'avoid_for_new_copies' drive

  Verification modifier:
    +10  status == 'needs_verification'
    + 3  status == 'auto'  (never explicitly verified)
    - 5  status == 'verified'

  Domain-mapping modifier:
    + 5  domain_mapping_complete == False  (resilience cannot be confirmed)

  Sidecar modifier:
    + 3  item has no sidecar coverage on any backup copy
    (proxy: we treat domain_mapping_complete=False as partial indicator)

  Size bonus (0–7):
    round(min(7, total_size_bytes / (10 * 1024**3)))  # +1 per 10 GB, max 7
    — large unprotected files are surfaced higher in priority lists

One-action explanation is also returned: the single change that would most
reduce the risk score.
"""

from __future__ import annotations

from typing import Any

# State → base score
_BASE_SCORES: dict[str | None, int] = {
    "unsafe_no_backup":             75,
    "unsafe_single_domain":         50,
    "over_replicated_but_fragile":  30,
    "safe_two_domains":             10,
    "over_replicated_and_resilient": 2,
    None:                           85,  # unmapped / 0-copy item
}

# Drive health → penalty
_HEALTH_PENALTY: dict[str, int] = {
    "healthy":              0,
    "warning":             12,
    "degraded":            20,
    "avoid_for_new_copies": 6,
}

_HEALTH_LABELS: dict[str, str] = {
    "healthy":              "Healthy",
    "warning":              "Warning",
    "degraded":             "Degraded",
    "avoid_for_new_copies": "Avoid for New Copies",
}


def compute_risk_score(item: dict[str, Any]) -> dict[str, Any]:
    """
    Compute the risk score for a single media item.

    Parameters
    ----------
    item : dict with keys:
        resilience_state        : str | None
        domain_mapping_complete : bool
        status                  : str   ('auto' | 'verified' | 'needs_verification')
        total_size_bytes        : int
        drive_healths           : list[str]   health_status of every drive holding a copy
        copy_count              : int
        sidecar_completeness    : str | None  ('complete'|'partial'|'no_sidecars'|None)
                                  — informational only; does NOT change risk score.
                                    Missing sidecars are tracked as completeness,
                                    not as a safety risk.

    Returns
    -------
    dict with:
        score                 : int (0–100)
        base_score            : int
        health_modifier       : int
        verification_modifier : int
        domain_modifier       : int
        size_bonus            : int
        sidecar_completeness  : str | None
        factors               : list[str]   human-readable factor explanations
        recommended_action    : str
        improvement_if_acted  : int   how much the score would drop
    """
    resilience_state: str | None = item.get("resilience_state")
    domain_complete: bool = item.get("domain_mapping_complete", False)
    status: str = item.get("status", "auto")
    size_bytes: int = item.get("total_size_bytes", 0)
    drive_healths: list[str] = item.get("drive_healths", [])
    sidecar_completeness: str | None = item.get("sidecar_completeness")

    factors: list[str] = []

    # 1. Base from resilience state
    base = _BASE_SCORES.get(resilience_state, 85)
    factors.append(f"Resilience state '{resilience_state}' → base {base}")

    # 2. Drive-health modifier
    health_mod = 0
    worst_health = "healthy"
    for h in drive_healths:
        penalty = _HEALTH_PENALTY.get(h, 0)
        if penalty > health_mod:
            health_mod = penalty
            worst_health = h
    if health_mod > 0:
        factors.append(f"Drive health '{worst_health}' → +{health_mod}")

    # 3. Verification modifier
    verif_mod = {"verified": -5, "auto": 3, "needs_verification": 10}.get(status, 3)
    if verif_mod > 0:
        factors.append(f"Verification status '{status}' → +{verif_mod}")
    elif verif_mod < 0:
        factors.append(f"Verification status '{status}' → {verif_mod}")

    # 4. Domain mapping modifier
    domain_mod = 5 if not domain_complete else 0
    if domain_mod > 0:
        factors.append("Domain mapping incomplete → +5 (resilience unconfirmable)")

    # 5. Size bonus (tiebreaker / priority)
    size_bonus = min(7, round(size_bytes / (10 * 1024 ** 3)))
    if size_bonus > 0:
        gb = size_bytes / (1024 ** 3)
        factors.append(f"Large item ({gb:.0f} GB) → +{size_bonus}")

    raw_score = base + health_mod + verif_mod + domain_mod + size_bonus
    score = max(0, min(100, raw_score))

    # Sidecar completeness note (informational — does NOT change risk score)
    if sidecar_completeness == "partial":
        factors.append("⚠️ Sidecar completeness: partial (some backup copies missing sidecars)")
    elif sidecar_completeness == "complete":
        factors.append("✅ Sidecar completeness: complete")

    # Recommended single action
    action, improvement = _recommend_action(resilience_state, domain_complete, status, worst_health)

    return {
        "score": score,
        "base_score": base,
        "health_modifier": health_mod,
        "verification_modifier": verif_mod,
        "domain_modifier": domain_mod,
        "size_bonus": size_bonus,
        "sidecar_completeness": sidecar_completeness,
        "factors": factors,
        "recommended_action": action,
        "improvement_if_acted": improvement,
    }


def _recommend_action(
    resilience_state: str | None,
    domain_complete: bool,
    status: str,
    worst_health: str,
) -> tuple[str, int]:
    """Return (action_text, score_reduction_if_done)."""
    # Highest-impact actions first
    if resilience_state == "unsafe_no_backup" or resilience_state is None:
        return "Copy to a drive in any failure domain", 65
    if resilience_state == "unsafe_single_domain":
        return "Copy to a drive in a different failure domain", 40
    if worst_health in ("degraded", "avoid_for_new_copies"):
        return f"Migrate copy off the {_HEALTH_LABELS[worst_health]} drive", 20
    if not domain_complete:
        return "Assign all drives to failure domains so resilience can be confirmed", 5
    if status == "needs_verification":
        return "Run file verification to confirm integrity", 10
    if resilience_state == "over_replicated_but_fragile":
        return "Move at least one copy to a drive in a different failure domain", 20
    return "No action needed — item is well-protected", 0


def score_label(score: int) -> str:
    """Return a human-readable risk label for a score."""
    if score >= 70:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 30:
        return "Medium"
    if score >= 10:
        return "Low"
    return "Minimal"


def score_color(score: int) -> str:
    """Return a CSS color string for a score."""
    if score >= 70:
        return "#f44336"
    if score >= 50:
        return "#ff5722"
    if score >= 30:
        return "#ff9800"
    if score >= 10:
        return "#ffc107"
    return "#4caf50"
