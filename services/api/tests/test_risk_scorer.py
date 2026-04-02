"""
Tests for the Risk Scoring Engine (risk_scorer.py)
====================================================
Pure unit tests — no DB, no async.

Scenarios covered:
  S1: Single copy, no domain → very high risk
  S2: Two copies, same domain (unsafe_single_domain) → high risk
  S3: Two copies, different domains (safe_two_domains) → low risk
  S4: Three copies, two domains (resilient) → minimal risk
  S5: Single copy + degraded drive → critical risk (score boost)
  S6: Verified item → score reduction from verification bonus
  S7: Large file, unsafe → size bonus applied
  S8: Domain mapping incomplete → domain modifier applied
  S9: Old logic (copy-count-only) vs new logic comparison
"""

import pytest
from src.risk_scorer import compute_risk_score, score_label, score_color


def make_item(**kwargs):
    """Build an item dict with safe defaults."""
    return {
        "resilience_state": kwargs.get("resilience_state", "unsafe_no_backup"),
        "domain_mapping_complete": kwargs.get("domain_mapping_complete", True),
        "status": kwargs.get("status", "auto"),
        "total_size_bytes": kwargs.get("total_size_bytes", 0),
        "drive_healths": kwargs.get("drive_healths", ["healthy"]),
        "copy_count": kwargs.get("copy_count", 1),
    }


# ── S1: Single copy, no domain ─────────────────────────────────────────────────

class TestSingleCopyNoBackup:
    def setup_method(self):
        self.item = make_item(
            resilience_state="unsafe_no_backup",
            domain_mapping_complete=False,
            status="auto",
            copy_count=1,
        )
        self.result = compute_risk_score(self.item)

    def test_base_score_is_high(self):
        assert self.result["base_score"] == 75

    def test_domain_modifier_applied(self):
        assert self.result["domain_modifier"] == 5

    def test_verification_modifier_for_auto(self):
        assert self.result["verification_modifier"] == 3

    def test_total_score_above_70(self):
        assert self.result["score"] >= 70

    def test_label_is_critical(self):
        assert score_label(self.result["score"]) in ("Critical", "High")

    def test_recommended_action_mentions_backup(self):
        assert "backup" in self.result["recommended_action"].lower() or \
               "copy" in self.result["recommended_action"].lower()


# ── S2: Two copies, same domain (unsafe_single_domain) ────────────────────────

class TestTwoCopiesSameDomain:
    def setup_method(self):
        self.result = compute_risk_score(make_item(
            resilience_state="unsafe_single_domain",
            domain_mapping_complete=True,
            status="auto",
            copy_count=2,
        ))

    def test_base_score(self):
        assert self.result["base_score"] == 50

    def test_score_in_high_range(self):
        assert 40 <= self.result["score"] <= 65

    def test_label_is_high_or_medium(self):
        assert score_label(self.result["score"]) in ("High", "Medium")

    def test_action_recommends_different_domain(self):
        assert "domain" in self.result["recommended_action"].lower()


# ── S3: Two copies, different domains (safe_two_domains) ──────────────────────

class TestTwoCopiesDifferentDomains:
    def setup_method(self):
        self.result = compute_risk_score(make_item(
            resilience_state="safe_two_domains",
            domain_mapping_complete=True,
            status="auto",
            copy_count=2,
        ))

    def test_base_score_is_low(self):
        assert self.result["base_score"] == 10

    def test_score_below_30(self):
        assert self.result["score"] < 30

    def test_label_is_low_or_minimal(self):
        assert score_label(self.result["score"]) in ("Low", "Minimal")


# ── S4: Three copies, two domains (over_replicated_and_resilient) ─────────────

class TestThreeCopiesResilient:
    def setup_method(self):
        self.result = compute_risk_score(make_item(
            resilience_state="over_replicated_and_resilient",
            domain_mapping_complete=True,
            status="verified",
            copy_count=3,
            drive_healths=["healthy", "healthy", "healthy"],
        ))

    def test_base_score_is_minimal(self):
        assert self.result["base_score"] == 2

    def test_verified_reduces_score(self):
        assert self.result["verification_modifier"] == -5

    def test_final_score_very_low(self):
        # base(2) + verif(-5) + all others 0 = clamped to 0
        assert self.result["score"] == 0

    def test_label_is_minimal(self):
        assert score_label(0) == "Minimal"


# ── S5: Single copy + degraded drive ──────────────────────────────────────────

class TestSingleCopyDegradedDrive:
    def setup_method(self):
        self.result = compute_risk_score(make_item(
            resilience_state="unsafe_no_backup",
            domain_mapping_complete=False,
            status="auto",
            copy_count=1,
            drive_healths=["degraded"],
        ))

    def test_health_modifier_is_20(self):
        assert self.result["health_modifier"] == 20

    def test_score_is_at_or_near_100(self):
        # base(75) + health(20) + verif(3) + domain(5) = 103 → clamped to 100
        assert self.result["score"] == 100

    def test_label_critical(self):
        assert score_label(100) == "Critical"


# ── S6: Verified item reduces score ───────────────────────────────────────────

class TestVerifiedItemScoreReduction:
    def test_verified_reduces_versus_auto(self):
        auto = compute_risk_score(make_item(status="auto"))
        verified = compute_risk_score(make_item(status="verified"))
        assert verified["score"] < auto["score"]

    def test_needs_verification_increases_score(self):
        auto = compute_risk_score(make_item(status="auto"))
        needs = compute_risk_score(make_item(status="needs_verification"))
        assert needs["score"] > auto["score"]

    def test_delta_auto_to_verified_is_8_points(self):
        # auto = +3, verified = -5, delta = 8
        auto = compute_risk_score(make_item(status="auto"))
        verified = compute_risk_score(make_item(status="verified"))
        assert auto["score"] - verified["score"] == 8


# ── S7: Large file size bonus ─────────────────────────────────────────────────

class TestSizeBonusApplied:
    def test_50gb_item_gets_size_bonus(self):
        small = compute_risk_score(make_item(total_size_bytes=0))
        big = compute_risk_score(make_item(total_size_bytes=50 * 1024 ** 3))
        assert big["score"] > small["score"]
        assert big["size_bonus"] == 5

    def test_200gb_item_capped_at_7(self):
        huge = compute_risk_score(make_item(total_size_bytes=200 * 1024 ** 3))
        assert huge["size_bonus"] == 7

    def test_small_file_no_bonus(self):
        small = compute_risk_score(make_item(total_size_bytes=1 * 1024 ** 2))
        assert small["size_bonus"] == 0


# ── S8: Domain mapping incomplete ─────────────────────────────────────────────

class TestDomainMappingIncomplete:
    def test_incomplete_adds_5(self):
        complete = compute_risk_score(make_item(domain_mapping_complete=True))
        incomplete = compute_risk_score(make_item(domain_mapping_complete=False))
        assert incomplete["domain_modifier"] == 5
        assert incomplete["score"] == complete["score"] + 5


# ── S9: Old (copy-count-only) vs new resilience-aware comparison ─────────────

class TestOldVsNewLogicComparison:
    """
    Demonstrates the key insight of the new system:
    Two items with the same copy count can have very different risk scores
    depending on domain distribution.
    """

    def test_2_copies_same_domain_riskier_than_2_copies_different(self):
        single_domain = compute_risk_score(make_item(
            resilience_state="unsafe_single_domain",
            domain_mapping_complete=True,
            copy_count=2,
        ))
        two_domains = compute_risk_score(make_item(
            resilience_state="safe_two_domains",
            domain_mapping_complete=True,
            copy_count=2,
        ))
        # Under the OLD model: both have 2 copies → same priority
        # Under the NEW model: single_domain should score significantly higher
        assert single_domain["score"] > two_domains["score"]
        assert single_domain["score"] - two_domains["score"] >= 30

    def test_3_copies_fragile_riskier_than_2_copies_resilient(self):
        """3 copies in 1 domain should be riskier than 2 copies in 2 domains."""
        three_in_one = compute_risk_score(make_item(
            resilience_state="over_replicated_but_fragile",
            copy_count=3,
        ))
        two_in_two = compute_risk_score(make_item(
            resilience_state="safe_two_domains",
            copy_count=2,
        ))
        # Old model: 3 copies > 2 copies, so 3-copy item looks safer.
        # New model: domain fragility matters.
        assert three_in_one["score"] > two_in_two["score"]

    def test_warning_drive_elevates_score_of_safe_item(self):
        """A 'safe' item on warning drives should score higher than on healthy drives."""
        healthy = compute_risk_score(make_item(
            resilience_state="safe_two_domains",
            drive_healths=["healthy", "healthy"],
        ))
        warning = compute_risk_score(make_item(
            resilience_state="safe_two_domains",
            drive_healths=["warning", "healthy"],
        ))
        assert warning["score"] > healthy["score"]
        assert warning["health_modifier"] == 12


# ── score_label and score_color helpers ───────────────────────────────────────

class TestHelpers:
    def test_score_labels(self):
        assert score_label(0) == "Minimal"
        assert score_label(10) == "Low"
        assert score_label(30) == "Medium"
        assert score_label(50) == "High"
        assert score_label(70) == "Critical"
        assert score_label(100) == "Critical"

    def test_score_colors_are_valid_css(self):
        for score in [0, 10, 30, 50, 70, 100]:
            color = score_color(score)
            assert color.startswith("#")
            assert len(color) == 7
