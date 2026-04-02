"""
Drive Failure Simulation Engine
================================
Pure, database-free module that computes the consequences of losing a set
of drives (a single drive or an entire failure domain).

All functions accept plain Python dicts so they can be:
  - called from FastAPI routers after a single DB query
  - unit-tested without any async machinery or DB fixtures

Terminology
-----------
failed_drive_ids : set[int]
    IDs of drives that are being "removed" from the simulation.
items : list[dict]
    Each item has shape:
        {
            "id": int,
            "title": str,
            "type": str,
            "status": str,
            "files": [
                {
                    "file_id": int,
                    "drive_id": int,
                    "domain_id": int | None,
                    "size": int | None,
                    "path": str,
                    "root_path": str,    # drive mount path
                }
            ]
        }
"""

from __future__ import annotations

from typing import Any

# Severity levels (also used for sort order, lower = worse)
SEVERITY_LOST = "lost"                      # 0 copies remain
SEVERITY_DEGRADED_1_COPY = "degraded_1_copy"    # drops to 1 copy
SEVERITY_DEGRADED_DOMAIN = "degraded_domain"    # ≥2 copies, all 1 domain
SEVERITY_SAFE = "still_safe"               # remains ≥2 copies on ≥2 domains
SEVERITY_UNAFFECTED = "unaffected"          # had no files on failed drives

SEVERITY_ORDER = {
    SEVERITY_LOST: 0,
    SEVERITY_DEGRADED_1_COPY: 1,
    SEVERITY_DEGRADED_DOMAIN: 2,
    SEVERITY_SAFE: 3,
    SEVERITY_UNAFFECTED: 4,
}


def _classify_remaining(remaining_files: list[dict]) -> str:
    """Classify an item's state given its surviving files after a failure."""
    copy_count = len(remaining_files)
    if copy_count == 0:
        return SEVERITY_LOST
    if copy_count == 1:
        return SEVERITY_DEGRADED_1_COPY
    # ≥ 2 copies — check domain diversity
    distinct_domains = {f["domain_id"] for f in remaining_files if f["domain_id"] is not None}
    if len(distinct_domains) >= 2:
        return SEVERITY_SAFE
    return SEVERITY_DEGRADED_DOMAIN


def simulate_failure(
    failed_drive_ids: set[int],
    items: list[dict],
    scope_label: str,
) -> dict[str, Any]:
    """
    Core simulation function. Returns a full result dict.

    Parameters
    ----------
    failed_drive_ids : set[int]
        The drives that are assumed to have failed.
    items : list[dict]
        All library items with their file lists (see module docstring).
    scope_label : str
        Human-readable name for the failed scope, e.g. "D:\\ Media" or
        "USB Enclosure A".

    Returns
    -------
    dict with keys: summary, items, recommended_actions
    """
    result_items: list[dict] = []
    summary = {
        "lost_entirely": 0,
        "degraded_to_1_copy": 0,
        "degraded_to_single_domain": 0,
        "still_safe": 0,
        "unaffected": 0,
        "total_affected": 0,
    }

    recommended_actions: list[dict] = []

    for item in items:
        files = item.get("files", [])
        affected_files = [f for f in files if f["drive_id"] in failed_drive_ids]
        surviving_files = [f for f in files if f["drive_id"] not in failed_drive_ids]

        if not affected_files:
            summary["unaffected"] += 1
            continue

        severity = _classify_remaining(surviving_files)

        # Compute current state before failure
        all_domains = {f["domain_id"] for f in files if f["domain_id"] is not None}
        current_copy_count = len(files)
        current_distinct_domains = len(all_domains)

        # Size of affected files (sum, for export/planning)
        item_size = sum(f.get("size") or 0 for f in affected_files)

        result_items.append({
            "id": item["id"],
            "title": item["title"],
            "type": item["type"],
            "status": item.get("status"),
            "severity": severity,
            "current_copies": current_copy_count,
            "remaining_copies": len(surviving_files),
            "current_distinct_domains": current_distinct_domains,
            "remaining_distinct_domains": len(
                {f["domain_id"] for f in surviving_files if f["domain_id"] is not None}
            ),
            "affected_files": [
                {"file_id": f["file_id"], "path": f["path"], "size": f.get("size")}
                for f in affected_files
            ],
            "surviving_files": [
                {
                    "file_id": f["file_id"],
                    "path": f["path"],
                    "drive_id": f["drive_id"],
                    "domain_id": f["domain_id"],
                }
                for f in surviving_files
            ],
            "size_bytes": item_size,
        })

        # Tally summary
        if severity == SEVERITY_LOST:
            summary["lost_entirely"] += 1
        elif severity == SEVERITY_DEGRADED_1_COPY:
            summary["degraded_to_1_copy"] += 1
        elif severity == SEVERITY_DEGRADED_DOMAIN:
            summary["degraded_to_single_domain"] += 1
        elif severity == SEVERITY_SAFE:
            summary["still_safe"] += 1

        # Recommend action for lost and degraded items
        if severity in (SEVERITY_LOST, SEVERITY_DEGRADED_1_COPY):
            if surviving_files:
                recommended_actions.append({
                    "item_id": item["id"],
                    "item_title": item["title"],
                    "action": "backup_before_failure",
                    "reason": "Will be lost entirely" if severity == SEVERITY_LOST
                              else "Will drop to single copy",
                    "source_file": surviving_files[0]["path"],
                    "source_drive_id": surviving_files[0]["drive_id"],
                })
            else:
                # item is already lost — no surviving copy exists
                recommended_actions.append({
                    "item_id": item["id"],
                    "item_title": item["title"],
                    "action": "already_at_risk",
                    "reason": "No surviving copies — this item is already lost if drive fails",
                    "source_file": None,
                    "source_drive_id": None,
                })
        elif severity == SEVERITY_DEGRADED_DOMAIN:
            recommended_actions.append({
                "item_id": item["id"],
                "item_title": item["title"],
                "action": "copy_to_different_domain",
                "reason": "All remaining copies are in the same failure domain",
                "source_file": surviving_files[0]["path"],
                "source_drive_id": surviving_files[0]["drive_id"],
            })

    summary["total_affected"] = (
        summary["lost_entirely"]
        + summary["degraded_to_1_copy"]
        + summary["degraded_to_single_domain"]
        + summary["still_safe"]
    )

    return {
        "scope_label": scope_label,
        "summary": summary,
        "items": result_items,
        "recommended_actions": recommended_actions,
    }


# ── Export helpers ─────────────────────────────────────────────────────────────

def export_csv(result: dict) -> str:
    """Render simulation result as a CSV string."""
    import io
    import csv

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "title", "type", "severity",
        "current_copies", "remaining_copies",
        "current_domains", "remaining_domains",
        "size_bytes", "action",
    ])

    # Build action lookup
    action_map = {a["item_id"]: a["action"] for a in result.get("recommended_actions", [])}

    for item in sorted(result["items"], key=lambda x: SEVERITY_ORDER.get(x["severity"], 99)):
        writer.writerow([
            item["id"],
            item["title"],
            item["type"],
            item["severity"],
            item["current_copies"],
            item["remaining_copies"],
            item["current_distinct_domains"],
            item["remaining_distinct_domains"],
            item["size_bytes"],
            action_map.get(item["id"], "none"),
        ])

    return buf.getvalue()


def export_checklist(result: dict) -> str:
    """Render a 'drive retirement' checklist in plain Markdown."""
    lines = [
        f"# Drive Retirement / Failure Checklist",
        f"**Simulated failure:** {result['scope_label']}",
        "",
        "## Summary",
        f"- 🔴 Lost entirely: **{result['summary']['lost_entirely']}** items",
        f"- 🟠 Drops to 1 copy: **{result['summary']['degraded_to_1_copy']}** items",
        f"- 🟡 Single-domain risk: **{result['summary']['degraded_to_single_domain']}** items",
        f"- 🟢 Still safe: **{result['summary']['still_safe']}** items",
        "",
        "## Required Actions (Total-Loss Items)",
    ]

    lost = [i for i in result["items"] if i["severity"] == SEVERITY_LOST]
    if lost:
        for item in lost:
            lines.append(f"- [ ] **{item['title']}** (ID {item['id']}) — NO surviving copy. Must re-acquire.")
    else:
        lines.append("_None — no items will be completely lost._")

    lines += ["", "## Recommended Copies Before Failure"]
    copy_needed = [
        a for a in result["recommended_actions"]
        if a["action"] in ("backup_before_failure", "copy_to_different_domain")
        and a.get("source_file")
    ]
    if copy_needed:
        for action in copy_needed:
            lines.append(
                f"- [ ] **{action['item_title']}** — {action['reason']}\n"
                f"      Source: `{action['source_file']}`"
            )
    else:
        lines.append("_No copy actions needed._")

    lines += ["", "---", "_Generated by Milestone Drive Failure Simulation Engine_"]
    return "\n".join(lines)
