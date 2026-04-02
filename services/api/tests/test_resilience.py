"""
Tests for resilience state computation.

These are pure unit tests — no database, no async.
Every scenario uses seed data that mirrors real-world situations.
"""

import pytest
from src.resilience import (
    compute_resilience_state,
    compute_item_resilience,
    UNSAFE_NO_BACKUP,
    UNSAFE_SINGLE_DOMAIN,
    SAFE_TWO_DOMAINS,
    OVER_REPLICATED_FRAGILE,
    OVER_REPLICATED_RESILIENT,
)


# ── compute_resilience_state: pure logic ───────────────────────────────────────

class TestComputeResilienceState:
    """Unit tests for the core pure function."""

    def test_zero_copies(self):
        assert compute_resilience_state(0, 0) == UNSAFE_NO_BACKUP

    def test_one_copy_no_domain(self):
        assert compute_resilience_state(1, 0) == UNSAFE_NO_BACKUP

    def test_one_copy_with_domain(self):
        # Domain assignment doesn't matter — one copy is always unsafe
        assert compute_resilience_state(1, 1) == UNSAFE_NO_BACKUP

    def test_two_copies_no_domains_assigned(self):
        # Quantity without domain knowledge → unsafe
        assert compute_resilience_state(2, 0) == UNSAFE_SINGLE_DOMAIN

    def test_two_copies_same_domain(self):
        assert compute_resilience_state(2, 1) == UNSAFE_SINGLE_DOMAIN

    def test_two_copies_different_domains(self):
        assert compute_resilience_state(2, 2) == SAFE_TWO_DOMAINS

    def test_three_copies_no_domains(self):
        assert compute_resilience_state(3, 0) == OVER_REPLICATED_FRAGILE

    def test_three_copies_same_domain(self):
        assert compute_resilience_state(3, 1) == OVER_REPLICATED_FRAGILE

    def test_three_copies_two_domains(self):
        assert compute_resilience_state(3, 2) == OVER_REPLICATED_RESILIENT

    def test_three_copies_three_domains(self):
        assert compute_resilience_state(3, 3) == OVER_REPLICATED_RESILIENT

    def test_five_copies_two_domains(self):
        assert compute_resilience_state(5, 2) == OVER_REPLICATED_RESILIENT


# ── compute_item_resilience: 7 seed scenarios ──────────────────────────────────

class TestComputeItemResilience:
    """
    Seed scenarios matching the spec.  Each scenario documents the expected
    state in a comment so the verification report is easy to produce.
    """

    # Scenario 1: 1 file, 1 drive, no domain
    # → unsafe_no_backup  (single copy regardless of domain)
    def test_scenario_1_single_copy_no_domain(self):
        files = [{"domain_id": None}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == UNSAFE_NO_BACKUP
        assert result["copy_count"] == 1
        assert result["distinct_domains"] == 0
        assert result["domain_mapping_complete"] is False

    # Scenario 2: 2 files, 2 drives, same domain (domain_id=1 on both)
    # → unsafe_single_domain
    def test_scenario_2_two_copies_same_domain(self):
        files = [{"domain_id": 1}, {"domain_id": 1}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == UNSAFE_SINGLE_DOMAIN
        assert result["copy_count"] == 2
        assert result["distinct_domains"] == 1
        assert result["domain_mapping_complete"] is True

    # Scenario 3: 2 files, 2 drives, different domains (1 and 2)
    # → safe_two_domains
    def test_scenario_3_two_copies_different_domains(self):
        files = [{"domain_id": 1}, {"domain_id": 2}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == SAFE_TWO_DOMAINS
        assert result["copy_count"] == 2
        assert result["distinct_domains"] == 2
        assert result["domain_mapping_complete"] is True

    # Scenario 4: 2 files, 2 drives, neither has a domain assigned
    # → unsafe_single_domain  (0 distinct assigned domains → can't verify resilience)
    def test_scenario_4_two_copies_no_domains_assigned(self):
        files = [{"domain_id": None}, {"domain_id": None}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == UNSAFE_SINGLE_DOMAIN
        assert result["copy_count"] == 2
        assert result["distinct_domains"] == 0
        assert result["domain_mapping_complete"] is False

    # Scenario 5: 3 files, 3 drives, all in the same domain (domain_id=1)
    # → over_replicated_but_fragile
    def test_scenario_5_three_copies_same_domain(self):
        files = [{"domain_id": 1}, {"domain_id": 1}, {"domain_id": 1}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == OVER_REPLICATED_FRAGILE
        assert result["copy_count"] == 3
        assert result["distinct_domains"] == 1
        assert result["domain_mapping_complete"] is True

    # Scenario 6: 3 files across 3 drives on 2 domains (domains 1, 1, 2)
    # → over_replicated_and_resilient
    def test_scenario_6_three_copies_two_domains(self):
        files = [{"domain_id": 1}, {"domain_id": 1}, {"domain_id": 2}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == OVER_REPLICATED_RESILIENT
        assert result["copy_count"] == 3
        assert result["distinct_domains"] == 2
        assert result["domain_mapping_complete"] is True

    # Scenario 7: 3 files — 2 assigned to same domain, 1 unassigned
    # → over_replicated_but_fragile (unassigned drive does NOT count toward
    #   distinct_domains; 1 distinct domain found → fragile)
    # domain_mapping_complete = False (one drive unassigned)
    def test_scenario_7_three_copies_mixed_assignment(self):
        files = [{"domain_id": 1}, {"domain_id": 1}, {"domain_id": None}]
        result = compute_item_resilience(files)
        assert result["resilience_state"] == OVER_REPLICATED_FRAGILE
        assert result["copy_count"] == 3
        assert result["distinct_domains"] == 1
        assert result["domain_mapping_complete"] is False

    # Edge: empty item (no files)
    def test_empty_item(self):
        result = compute_item_resilience([])
        assert result["resilience_state"] == UNSAFE_NO_BACKUP
        assert result["copy_count"] == 0
        assert result["domain_mapping_complete"] is True  # vacuously complete
