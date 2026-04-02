"""
Tests for the drive failure simulation engine.
Pure unit tests — no DB, no async.

Seed data design
----------------
We use a fixed library of 8 items across 4 drives in 3 domains:

Drives:
  D1 (id=1, domain_id=1 "NAS")
  D2 (id=2, domain_id=1 "NAS")
  D3 (id=3, domain_id=2 "USB-A")
  D4 (id=4, domain_id=3 "Cloud")  ← different domain
  D5 (id=5, domain_id=None)       ← unassigned

Items:
  I1  1 copy on D1 only                → losing D1: LOST
  I2  2 copies: D1 + D2 (both NAS)    → losing D1: degrades to 1 copy
  I3  2 copies: D1 + D3               → losing D1: still 1 copy on D3 (different domain) → DEGRADED_1_COPY
  I4  2 copies: D1 + D4               → losing D1: 1 copy on D4 (different domain) → DEGRADED_1_COPY
  I5  3 copies: D1 + D2 + D3         → losing D1: 2 copies (D2 NAS + D3 USB-A) → STILL SAFE
  I6  3 copies: D2 + D3 + D4         → NOT on D1 → UNAFFECTED
  I7  2 copies: D3 + D4              → NOT on D1 → UNAFFECTED
  I8  2 copies: D1 + D5 (D5 unassigned) → losing D1: 1 surviving copy (D5, no domain) → DEGRADED_1_COPY
"""

import pytest
from src.simulator import (
    simulate_failure,
    _classify_remaining,
    SEVERITY_LOST,
    SEVERITY_DEGRADED_1_COPY,
    SEVERITY_DEGRADED_DOMAIN,
    SEVERITY_SAFE,
    SEVERITY_UNAFFECTED,
    export_csv,
    export_checklist,
)


# ── Seed data ──────────────────────────────────────────────────────────────────

def make_file(file_id, drive_id, domain_id, path=None, size=1_000_000):
    return {
        "file_id": file_id,
        "drive_id": drive_id,
        "domain_id": domain_id,
        "path": path or f"/media/file_{file_id}.mkv",
        "size": size,
        "root_path": f"/drive_{drive_id}",
    }


def make_item(item_id, files, title=None):
    return {
        "id": item_id,
        "title": title or f"Item {item_id}",
        "type": "movie",
        "status": "auto",
        "files": files,
    }


# Domain assignments
D1_DOMAIN = 1   # NAS
D2_DOMAIN = 1   # NAS (same as D1)
D3_DOMAIN = 2   # USB-A
D4_DOMAIN = 3   # Cloud
D5_DOMAIN = None # unassigned

SEED_ITEMS = [
    make_item(1, [make_file(101, 1, D1_DOMAIN)], "Solo on NAS Drive 1"),
    make_item(2, [make_file(102, 1, D1_DOMAIN), make_file(103, 2, D2_DOMAIN)], "Both on NAS"),
    make_item(3, [make_file(104, 1, D1_DOMAIN), make_file(105, 3, D3_DOMAIN)], "D1+D3 two domains"),
    make_item(4, [make_file(106, 1, D1_DOMAIN), make_file(107, 4, D4_DOMAIN)], "D1+D4 two domains"),
    make_item(5, [make_file(108, 1, D1_DOMAIN), make_file(109, 2, D2_DOMAIN), make_file(110, 3, D3_DOMAIN)], "Triple copy"),
    make_item(6, [make_file(111, 2, D2_DOMAIN), make_file(112, 3, D3_DOMAIN), make_file(113, 4, D4_DOMAIN)], "Not on D1"),
    make_item(7, [make_file(114, 3, D3_DOMAIN), make_file(115, 4, D4_DOMAIN)], "D3+D4 safe"),
    make_item(8, [make_file(116, 1, D1_DOMAIN), make_file(117, 5, D5_DOMAIN)], "D1 + unassigned"),
]


# ── _classify_remaining unit tests ─────────────────────────────────────────────

class TestClassifyRemaining:
    def test_no_survivors(self):
        assert _classify_remaining([]) == SEVERITY_LOST

    def test_one_survivor(self):
        assert _classify_remaining([make_file(1, 2, 1)]) == SEVERITY_DEGRADED_1_COPY

    def test_two_survivors_same_domain(self):
        files = [make_file(1, 2, 1), make_file(2, 3, 1)]
        assert _classify_remaining(files) == SEVERITY_DEGRADED_DOMAIN

    def test_two_survivors_different_domains(self):
        files = [make_file(1, 2, 1), make_file(2, 3, 2)]
        assert _classify_remaining(files) == SEVERITY_SAFE

    def test_two_survivors_no_domains(self):
        # Both unassigned → 0 distinct domains → single-domain risk
        files = [make_file(1, 2, None), make_file(2, 3, None)]
        assert _classify_remaining(files) == SEVERITY_DEGRADED_DOMAIN

    def test_three_survivors_two_domains(self):
        files = [make_file(1, 2, 1), make_file(2, 3, 1), make_file(3, 4, 2)]
        assert _classify_remaining(files) == SEVERITY_SAFE


# ── Scenario 1: Single drive failure — D1 ─────────────────────────────────────

class TestDriveFailureD1:
    """Simulate losing Drive 1 (domain=NAS)."""

    def setup_method(self):
        self.result = simulate_failure(
            failed_drive_ids={1},
            items=SEED_ITEMS,
            scope_label="D1 NAS",
        )
        self.by_id = {i["id"]: i for i in self.result["items"]}

    def test_summary_lost(self):
        # I1: only copy was on D1 → LOST
        assert self.result["summary"]["lost_entirely"] == 1

    def test_summary_degraded_1_copy(self):
        # I2 (D2 NAS survives), I3 (D3 USB-A survives), I4 (D4 Cloud survives), I8 (D5 unassigned)
        # All drop to exactly 1 surviving copy
        assert self.result["summary"]["degraded_to_1_copy"] == 4

    def test_summary_still_safe(self):
        # I5: D2 (NAS) + D3 (USB-A) survive → 2 domains → SAFE
        assert self.result["summary"]["still_safe"] == 1

    def test_summary_unaffected(self):
        # I6, I7 had no files on D1
        assert self.result["summary"]["unaffected"] == 2

    def test_item1_lost(self):
        assert self.by_id[1]["severity"] == SEVERITY_LOST
        assert self.by_id[1]["remaining_copies"] == 0

    def test_item2_degraded(self):
        assert self.by_id[2]["severity"] == SEVERITY_DEGRADED_1_COPY
        assert self.by_id[2]["remaining_copies"] == 1

    def test_item5_safe(self):
        assert self.by_id[5]["severity"] == SEVERITY_SAFE
        assert self.by_id[5]["remaining_copies"] == 2
        assert self.by_id[5]["remaining_distinct_domains"] == 2

    def test_i6_i7_not_in_results(self):
        # Unaffected items appear with severity=unaffected in summary but
        # NOT in result["items"] (only affected items are listed)
        affected_ids = {i["id"] for i in self.result["items"]}
        assert 6 not in affected_ids
        assert 7 not in affected_ids


# ── Scenario 2: Domain failure — NAS (domain_id=1, drives D1+D2) ──────────────

class TestDomainFailureNAS:
    """Simulate losing the entire NAS domain (drives D1 and D2)."""

    def setup_method(self):
        self.result = simulate_failure(
            failed_drive_ids={1, 2},   # D1 and D2 both in domain NAS
            items=SEED_ITEMS,
            scope_label="NAS Domain",
        )
        self.by_id = {i["id"]: i for i in self.result["items"]}

    def test_i1_lost(self):
        # I1 only on D1
        assert self.by_id[1]["severity"] == SEVERITY_LOST

    def test_i2_lost(self):
        # I2 on D1+D2, both fail → LOST
        assert self.by_id[2]["severity"] == SEVERITY_LOST

    def test_i5_degraded_domain(self):
        # I5 on D1+D2+D3 → D3 (USB-A) survives — 1 copy, 1 domain → DEGRADED_1_COPY
        assert self.by_id[5]["severity"] == SEVERITY_DEGRADED_1_COPY
        assert self.by_id[5]["remaining_copies"] == 1

    def test_summary_lost_2(self):
        assert self.result["summary"]["lost_entirely"] == 2


# ── Scenario 3: Losing an unassigned drive (D5) ───────────────────────────────

class TestUnassignedDriveFailure:
    """Simulate losing Drive 5 (no domain assigned). Only I8 is affected."""

    def setup_method(self):
        self.result = simulate_failure(
            failed_drive_ids={5},
            items=SEED_ITEMS,
            scope_label="D5 Unassigned",
        )
        self.by_id = {i["id"]: i for i in self.result["items"]}

    def test_only_i8_affected(self):
        assert self.result["summary"]["total_affected"] == 1

    def test_i8_degraded(self):
        # I8 had D1+D5; losing D5 leaves D1 (1 copy)
        assert self.by_id[8]["severity"] == SEVERITY_DEGRADED_1_COPY
        assert self.by_id[8]["remaining_copies"] == 1

    def test_unaffected_count(self):
        assert self.result["summary"]["unaffected"] == 7


# ── Scenario 4: Empty library ─────────────────────────────────────────────────

class TestEmptyLibrary:
    def test_empty(self):
        result = simulate_failure(failed_drive_ids={1}, items=[], scope_label="D1")
        assert result["summary"]["total_affected"] == 0
        assert result["summary"]["unaffected"] == 0
        assert result["items"] == []
        assert result["recommended_actions"] == []


# ── Scenario 5: Drive with no media on it ─────────────────────────────────────

class TestDriveWithNoMedia:
    def test_no_items_on_drive(self):
        # Drive 99 doesn't exist in any item's files
        result = simulate_failure(failed_drive_ids={99}, items=SEED_ITEMS, scope_label="D99")
        assert result["summary"]["total_affected"] == 0
        assert result["summary"]["unaffected"] == len(SEED_ITEMS)


# ── Export tests ───────────────────────────────────────────────────────────────

class TestExports:
    def setup_method(self):
        self.result = simulate_failure(
            failed_drive_ids={1},
            items=SEED_ITEMS,
            scope_label="D1 NAS",
        )

    def test_csv_has_header(self):
        csv = export_csv(self.result)
        assert csv.startswith("id,title,type,severity")

    def test_csv_row_count(self):
        csv = export_csv(self.result)
        # header + 6 affected items (I1..I5, I8)
        lines = [l for l in csv.strip().splitlines() if l]
        assert len(lines) == 7  # header + 6 items

    def test_checklist_contains_lost_item(self):
        checklist = export_checklist(self.result)
        assert "Solo on NAS Drive 1" in checklist
        assert "NO surviving copy" in checklist

    def test_checklist_has_summary(self):
        checklist = export_checklist(self.result)
        assert "Lost entirely" in checklist
        assert "Required Actions" in checklist


# ── Recommended actions tests ──────────────────────────────────────────────────

class TestRecommendedActions:
    def setup_method(self):
        self.result = simulate_failure(
            failed_drive_ids={1},
            items=SEED_ITEMS,
            scope_label="D1 NAS",
        )
        self.actions_by_item = {a["item_id"]: a for a in self.result["recommended_actions"]}

    def test_lost_item_gets_already_at_risk_action(self):
        # I1 has no survivors at all
        assert 1 in self.actions_by_item
        assert self.actions_by_item[1]["action"] == "already_at_risk"

    def test_degraded_item_gets_backup_action(self):
        # I2 has 1 surviving copy → should recommend backup
        assert 2 in self.actions_by_item
        assert self.actions_by_item[2]["action"] == "backup_before_failure"

    def test_safe_item_has_no_action(self):
        # I5 remains safe → no recommended action
        assert 5 not in self.actions_by_item
