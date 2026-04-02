"""
Resilience state computation for Milestone media items.

This module contains pure, sync functions with zero database dependency.
All logic is designed to be trivially testable in isolation.

Resilience States
-----------------
unsafe_no_backup
    0 or 1 physical copies.  Drive failure = total loss.

unsafe_single_domain
    2+ copies exist, but every copy whose drive has a known domain shares
    the same domain — OR no drives have been assigned a domain at all.
    A single enclosure/NAS/location failure could wipe everything.

safe_two_domains
    Exactly 2 copies AND they are on at least 2 distinct assigned domains.
    Minimal acceptable resilience.

over_replicated_but_fragile
    3+ copies but all on the same domain (or no domains assigned).
    Quantity without diversity — still fragile.

over_replicated_and_resilient
    3+ copies spanning 2+ distinct assigned domains.

Domain-mapping completeness
---------------------------
`domain_mapping_complete` is True when every drive holding a copy of an item
has a domain assigned.  When False, the resilience state may be *optimistic*
because we cannot distinguish "same domain as another drive" from "different
domain" for unassigned drives.  The UI should visually flag this.
"""

from typing import Optional


# Canonical string literals — import these in tests and routers so the
# strings stay in one place.
UNSAFE_NO_BACKUP = "unsafe_no_backup"
UNSAFE_SINGLE_DOMAIN = "unsafe_single_domain"
SAFE_TWO_DOMAINS = "safe_two_domains"
OVER_REPLICATED_FRAGILE = "over_replicated_but_fragile"
OVER_REPLICATED_RESILIENT = "over_replicated_and_resilient"

ALL_STATES = (
    UNSAFE_NO_BACKUP,
    UNSAFE_SINGLE_DOMAIN,
    SAFE_TWO_DOMAINS,
    OVER_REPLICATED_FRAGILE,
    OVER_REPLICATED_RESILIENT,
)


def compute_resilience_state(
    copy_count: int,
    distinct_assigned_domains: int,
) -> str:
    """
    Derive the resilience state from copy count and distinct domain count.

    Parameters
    ----------
    copy_count:
        Total number of physical file copies (len of media_item_files rows).
    distinct_assigned_domains:
        Number of *unique non-NULL* domain IDs across all drives holding a copy.
        Drives without a domain assignment do NOT contribute to this count.

    Returns
    -------
    One of the five resilience state string constants.
    """
    if copy_count <= 1:
        return UNSAFE_NO_BACKUP

    if copy_count >= 3:
        if distinct_assigned_domains >= 2:
            return OVER_REPLICATED_RESILIENT
        return OVER_REPLICATED_FRAGILE

    # copy_count == 2
    if distinct_assigned_domains >= 2:
        return SAFE_TWO_DOMAINS
    return UNSAFE_SINGLE_DOMAIN


def compute_item_resilience(files: list[dict]) -> dict:
    """
    Compute the full resilience summary for a media item given its file list.

    Each dict in `files` must have at least:
        - 'domain_id':  Optional[int]  — the failure-domain ID of the drive,
                        or None if the drive has no domain assigned.

    Returns a dict with:
        resilience_state          str
        copy_count                int
        distinct_domains          int   — distinct non-None domain IDs
        domain_mapping_complete   bool  — True when every file's drive has a domain
    """
    copy_count = len(files)
    domain_ids: set[int] = set()
    mapping_complete = True

    for f in files:
        did: Optional[int] = f.get("domain_id")
        if did is None:
            mapping_complete = False
        else:
            domain_ids.add(did)

    distinct = len(domain_ids)
    state = compute_resilience_state(copy_count, distinct)

    return {
        "resilience_state": state,
        "copy_count": copy_count,
        "distinct_domains": distinct,
        "domain_mapping_complete": mapping_complete,
    }
