"""
Health-Aware Placement Advisor
================================
Pure, database-free module that recommends the best destination drives for
a copy operation, maximising the resilience improvement per copy made.

Input: item's current state + list of candidate drives.
Output: ordered list of (drive, placement_score, reason).

Placement scoring:
  Resilience gain (additive)
    +60  would create the item's first backup (no copies → one copy)
    +50  would convert unsafe_single_domain → safe_two_domains
         (drive is in a different domain than all current copies)
    +40  would create a copy on a domain not yet represented
          (e.g. 2 copies on domain A, this adds domain B)
    +20  would add 3rd+ copy across ≥2 existing domains (extra safety)
    + 5  would add a redundant copy within same domain (low value)

  Health modifier
    +10  drive is 'healthy'
    + 3  drive is 'warning' (allowed but sub-optimal)
    -∞   drive is 'degraded' or 'avoid_for_new_copies' → excluded

  Space modifier (0–8)
    proportional to free GB, maxing at +8 for drives with ≥200 GB free

  Skip conditions:
    • drive is 'degraded' or 'avoid_for_new_copies'
    • item already has a file on this drive
    • drive has insufficient free space (< item_size_bytes)
"""

from __future__ import annotations

from typing import Any

EXCLUDED_HEALTH = {"degraded", "avoid_for_new_copies"}


def suggest_destinations(
    item: dict[str, Any],
    candidate_drives: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return a sorted list of destination drive recommendations.

    Parameters
    ----------
    item : dict with keys:
        resilience_state : str | None
        domain_mapping_complete : bool
        copy_count : int
        current_drive_ids : set[int]       drives that already hold a copy
        current_domain_ids : set[int | None] domains of existing copies (None = unassigned)
        total_size_bytes : int

    candidate_drives : list of dicts, each with:
        id : int
        mount_path : str
        volume_label : str | None
        domain_id : int | None
        health_status : str
        free_space : int | None

    Returns
    -------
    list of dicts (ordered best-first):
        drive_id, mount_path, volume_label, domain_id,
        health_status, free_space, placement_score, reason
    """
    resilience_state: str | None = item.get("resilience_state")
    current_drive_ids: set[int] = set(item.get("current_drive_ids", []))
    current_domain_ids: set = set(item.get("current_domain_ids", []))
    size_bytes: int = item.get("total_size_bytes", 0)
    copy_count: int = item.get("copy_count", 0)

    results = []

    for drive in candidate_drives:
        drive_id = drive["id"]
        health = drive.get("health_status", "healthy")
        domain_id = drive.get("domain_id")
        free_space = drive.get("free_space") or 0

        # Hard exclusions
        if health in EXCLUDED_HEALTH:
            continue
        if drive_id in current_drive_ids:
            continue
        if size_bytes > 0 and free_space < size_bytes:
            continue  # not enough space

        # Resilience gain
        gain, reason = _compute_gain(
            resilience_state, copy_count, current_domain_ids, domain_id
        )

        # Health modifier
        health_mod = {"healthy": 10, "warning": 3}.get(health, 0)
        if health_mod < 10:
            reason += f" (⚠️ drive health: {health})"

        # Space modifier
        free_gb = free_space / (1024 ** 3)
        space_mod = min(8, round(free_gb / 25))  # +1 per 25 GB, max 8

        placement_score = gain + health_mod + space_mod

        results.append({
            "drive_id": drive_id,
            "mount_path": drive["mount_path"],
            "volume_label": drive.get("volume_label"),
            "domain_id": domain_id,
            "health_status": health,
            "free_space": free_space,
            "placement_score": placement_score,
            "reason": reason,
        })

    # Sort by score descending; break ties by free space
    results.sort(key=lambda x: (x["placement_score"], x["free_space"]), reverse=True)
    return results


def _compute_gain(
    resilience_state: str | None,
    copy_count: int,
    current_domain_ids: set,
    candidate_domain_id: int | None,
) -> tuple[int, str]:
    """Return (gain_score, plain-text reason)."""
    # First copy: maximum value
    if copy_count == 0:
        return 60, "Creates first backup of a currently lost item"

    # Would convert unsafe_no_backup to having a copy
    if resilience_state == "unsafe_no_backup":
        return 60, "Creates the first backup copy"

    # Would fix unsafe_single_domain by adding a new domain
    if resilience_state == "unsafe_single_domain":
        known_domains = {d for d in current_domain_ids if d is not None}
        if candidate_domain_id is not None and candidate_domain_id not in known_domains:
            return 50, "Adds a new failure domain → converts to safe_two_domains"
        return 5, "Same domain — resilience unchanged (consider a different domain)"

    # Would add a domain not yet represented (for already-safe items)
    if candidate_domain_id is not None:
        known_domains = {d for d in current_domain_ids if d is not None}
        if candidate_domain_id not in known_domains:
            return 40, "Adds an additional failure domain (extra redundancy)"

    # 3rd+ copy on same domain
    if resilience_state in ("safe_two_domains", "over_replicated_and_resilient"):
        return 5, "Additional copy within an existing domain (low resilience gain)"

    # over_replicated_but_fragile — adding any copy helps a little
    if resilience_state == "over_replicated_but_fragile":
        return 20, "Adds another copy (item is fragile — focus on domain diversity)"

    return 5, "Additional redundant copy"
