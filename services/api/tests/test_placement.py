"""
Tests for the Placement Advisor (placement.py)
================================================
Fixture-based unit tests — no DB, no async.

Tests validate:
  - exclusion of degraded/avoid_for_new_copies drives
  - domain-diversity preference: different domain scores higher
  - free space filter: under-capacity drives excluded
  - ordering: highest placement_score first
  - existing-drive filter: drives with current copies excluded
"""

import pytest
from src.placement import suggest_destinations


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_drive(id_, domain_id, health="healthy", free_gb=500, mount=None):
    return {
        "id": id_,
        "mount_path": mount or f"/drives/d{id_}",
        "volume_label": f"Drive{id_}",
        "domain_id": domain_id,
        "health_status": health,
        "free_space": int(free_gb * 1024 ** 3),
    }


def make_item(**kwargs):
    return {
        "resilience_state": kwargs.get("resilience_state", "unsafe_no_backup"),
        "domain_mapping_complete": kwargs.get("domain_mapping_complete", True),
        "copy_count": kwargs.get("copy_count", 1),
        "current_drive_ids": kwargs.get("current_drive_ids", set()),
        "current_domain_ids": kwargs.get("current_domain_ids", set()),
        "total_size_bytes": kwargs.get("total_size_bytes", 1_000_000),
    }


# ── Fixture library ─────────────────────────────────────────────────────────────
# Drives:  D1(NAS=1), D2(NAS=1), D3(USB-A=2), D4(Cloud=3), D5(degraded), D6(avoid)
D1 = make_drive(1, domain_id=1)                              # NAS
D2 = make_drive(2, domain_id=1)                              # NAS (same domain)
D3 = make_drive(3, domain_id=2)                              # USB-A
D4 = make_drive(4, domain_id=3)                              # Cloud
D5 = make_drive(5, domain_id=2, health="degraded")          # Degraded USB
D6 = make_drive(6, domain_id=3, health="avoid_for_new_copies")  # Avoid cloud
D7 = make_drive(7, domain_id=None)                           # Unassigned

ALL_DRIVES = [D1, D2, D3, D4, D5, D6, D7]


# ── Exclusion tests ─────────────────────────────────────────────────────────────

class TestExclusions:
    def test_degraded_drive_excluded(self):
        item = make_item(resilience_state="unsafe_no_backup", copy_count=0)
        results = suggest_destinations(item, [D5])
        assert len(results) == 0

    def test_avoid_drive_excluded(self):
        item = make_item(resilience_state="unsafe_no_backup", copy_count=0)
        results = suggest_destinations(item, [D6])
        assert len(results) == 0

    def test_existing_copy_drive_excluded(self):
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},  # D1 already has a copy
            current_domain_ids={1},
        )
        results = suggest_destinations(item, [D1, D3])
        drive_ids = [r["drive_id"] for r in results]
        assert 1 not in drive_ids  # D1 excluded
        assert 3 in drive_ids      # D3 allowed

    def test_insufficient_space_excluded(self):
        # Drive with only 10 MB available, item is 1 GB
        tiny = make_drive(99, domain_id=1, free_gb=0)
        tiny["free_space"] = 10 * 1024 * 1024  # 10 MB
        item = make_item(total_size_bytes=1 * 1024 ** 3)  # 1 GB
        results = suggest_destinations(item, [tiny])
        assert len(results) == 0


# ── Domain preference tests ─────────────────────────────────────────────────────

class TestDomainPreference:
    def test_different_domain_scores_higher_for_unsafe_single_domain(self):
        """For an item with copies only in domain 1, a domain-2 drive should score higher than domain-1."""
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},
            current_domain_ids={1},
        )
        results = suggest_destinations(item, [D2, D3])
        # D2 is domain 1 (same), D3 is domain 2 (different)
        scores = {r["drive_id"]: r["placement_score"] for r in results}
        assert scores[3] > scores[2], "Domain-2 drive should score higher"

    def test_first_backup_gets_highest_gain(self):
        """An item with 0 copies should get max gain on any eligible drive."""
        item = make_item(
            resilience_state="unsafe_no_backup",
            copy_count=0,
            current_drive_ids=set(),
            current_domain_ids=set(),
        )
        results = suggest_destinations(item, [D1, D3])
        for r in results:
            # First backup = +60 gain
            assert r["placement_score"] >= 60

    def test_new_domain_preferred_for_fragile_item(self):
        """over_replicated_but_fragile: drive in a new domain should score higher."""
        item = make_item(
            resilience_state="over_replicated_but_fragile",
            copy_count=3,
            current_drive_ids={1, 2},
            current_domain_ids={1},  # all copies in domain 1
        )
        # D3 (domain 2) vs D1/D2 already have copies — only D3 and D4 eligible
        results = suggest_destinations(item, [D3, D4])
        # Both add new domains, should have high gain
        assert all(r["placement_score"] >= 40 for r in results)

    def test_within_existing_domain_gets_low_gain(self):
        """Adding a copy within the same domain should get only low gain."""
        item = make_item(
            resilience_state="safe_two_domains",
            copy_count=2,
            current_drive_ids={1},
            current_domain_ids={1, 2},  # already has domains 1 and 2
        )
        results = suggest_destinations(item, [D2])  # D2 is domain 1 (already covered)
        assert len(results) == 1
        assert results[0]["placement_score"] < 20  # low resilience gain


# ── Ordering tests ─────────────────────────────────────────────────────────────

class TestOrdering:
    def test_results_sorted_by_score_descending(self):
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},
            current_domain_ids={1},
        )
        # D3 (domain 2) gives higher gain than D2 (domain 1 same)
        results = suggest_destinations(item, [D2, D3, D4])
        scores = [r["placement_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_warning_drive_comes_after_healthy_with_same_gain(self):
        healthy = make_drive(10, domain_id=2, health="healthy")
        warning = make_drive(11, domain_id=2, health="warning")
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},
            current_domain_ids={1},
        )
        results = suggest_destinations(item, [warning, healthy])
        ids = [r["drive_id"] for r in results]
        assert ids[0] == 10  # healthy first

    def test_empty_candidates_returns_empty(self):
        item = make_item()
        assert suggest_destinations(item, []) == []

    def test_only_excluded_drives_returns_empty(self):
        item = make_item()
        assert suggest_destinations(item, [D5, D6]) == []


# ── Reason text tests ──────────────────────────────────────────────────────────

class TestReasonText:
    def test_first_backup_reason(self):
        item = make_item(resilience_state="unsafe_no_backup", copy_count=0)
        results = suggest_destinations(item, [D1])
        assert "backup" in results[0]["reason"].lower() or "first" in results[0]["reason"].lower()

    def test_new_domain_reason(self):
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},
            current_domain_ids={1},
        )
        results = suggest_destinations(item, [D3])
        assert "domain" in results[0]["reason"].lower()

    def test_same_domain_reason_for_low_gain(self):
        item = make_item(
            resilience_state="unsafe_single_domain",
            copy_count=1,
            current_drive_ids={1},
            current_domain_ids={1},
        )
        results = suggest_destinations(item, [D2])  # D2 is same domain
        assert "same domain" in results[0]["reason"].lower() or "unchanged" in results[0]["reason"].lower()
