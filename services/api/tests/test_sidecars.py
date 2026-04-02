"""
Tests for the Sidecar Detection Engine (sidecars.py)
=====================================================
Pure unit tests — no DB, no async.

Covers:
  Section 1: is_sidecar_of() — 10+ representative matching examples
  Section 2: detect_sidecars() — batch detection from a file list
  Section 3: compute_completeness() — cross-drive comparison
  Section 4: build_copy_manifest() — policy-filtered copy list
  Section 5: Copy planning with and without sidecars
  Section 6: Edge cases (empty input, same-extension file, unrelated names)
"""

import pytest
from src.sidecars import (
    is_sidecar_of,
    is_primary,
    get_sidecar_category,
    detect_sidecars,
    compute_completeness,
    build_copy_manifest,
    DEFAULT_COPY_POLICY,
)


# ── Section 1: is_sidecar_of() — 10 representative examples ──────────────────

class TestIsSidecarOf:
    """
    Primary: /movies/The.Matrix.1999.mkv  (stem = "The.Matrix.1999")

    10 test cases — a mix of True and False to prove the matcher is precise.
    """
    PRIMARY = "/movies/The.Matrix.1999.mkv"

    def test_01_english_subtitle(self):
        """Classic .srt subtitle in same directory → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.en.srt", self.PRIMARY) is True

    def test_02_spanish_subtitle(self):
        """Second-language subtitle → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.es.srt", self.PRIMARY) is True

    def test_03_nfo_metadata(self):
        """.nfo metadata file → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.nfo", self.PRIMARY) is True

    def test_04_poster_image(self):
        """Hyphenated poster .jpg → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999-poster.jpg", self.PRIMARY) is True

    def test_05_idx_subtitle(self):
        """.idx format (subtitle index) → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.idx", self.PRIMARY) is True

    def test_06_sub_subtitle(self):
        """.sub format (image-based subtitle) → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.sub", self.PRIMARY) is True

    def test_07_xml_metadata(self):
        """.xml metadata → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.xml", self.PRIMARY) is True

    def test_08_random_image_in_same_dir(self):
        """fanart.jpg with no name relation → NOT a sidecar ❌"""
        assert is_sidecar_of("/movies/fanart.jpg", self.PRIMARY) is False

    def test_09_different_movie_subtitle(self):
        """Inception subtitle in same folder → NOT a sidecar of Matrix ❌"""
        assert is_sidecar_of("/movies/Inception.2010.en.srt", self.PRIMARY) is False

    def test_10_different_directory(self):
        """Same basename but different directory → NOT a sidecar ❌"""
        assert is_sidecar_of("/other/The.Matrix.1999.en.srt", self.PRIMARY) is False

    def test_11_continuation_without_separator(self):
        """'The.Matrix.1999x.jpg' — 'x' is not '.' or '-' → NOT a sidecar ❌"""
        assert is_sidecar_of("/movies/The.Matrix.1999x.jpg", self.PRIMARY) is False

    def test_12_second_video_is_not_sidecar(self):
        """Another .mkv with different name → NOT a sidecar ❌"""
        assert is_sidecar_of("/movies/The.Matrix.1999.extras.mkv", self.PRIMARY) is False

    def test_13_vtt_subtitle(self):
        """.vtt web subtitle format → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999.vtt", self.PRIMARY) is True

    def test_14_webp_artwork(self):
        """.webp thumbnail artwork → sidecar ✅"""
        assert is_sidecar_of("/movies/The.Matrix.1999-thumb.webp", self.PRIMARY) is True

    def test_15_stem_only_nfo(self):
        """Exact stem match (no extra suffix) → sidecar ✅"""
        # File: "The.Matrix.1999.nfo" — stem "The.Matrix.1999" == primary stem
        assert is_sidecar_of("/movies/The.Matrix.1999.nfo", self.PRIMARY) is True

    def test_windows_paths(self):
        """Windows backslash paths should be handled correctly."""
        primary_win = r"D:\movies\The.Matrix.1999.mkv"
        sidecar_win = r"D:\movies\The.Matrix.1999.en.srt"
        assert is_sidecar_of(sidecar_win, primary_win) is True

    def test_windows_different_dir(self):
        primary_win = r"D:\movies\The.Matrix.1999.mkv"
        sidecar_win = r"D:\other\The.Matrix.1999.en.srt"
        assert is_sidecar_of(sidecar_win, primary_win) is False


# ── Section 2: detect_sidecars() ─────────────────────────────────────────────

class TestDetectSidecars:
    """Tests for batch sidecar detection from a list of file paths."""

    FILES = [
        "/movies/The.Matrix.1999.mkv",
        "/movies/The.Matrix.1999.en.srt",
        "/movies/The.Matrix.1999.es.srt",
        "/movies/The.Matrix.1999.nfo",
        "/movies/The.Matrix.1999-poster.jpg",
        "/movies/Inception.2010.mkv",
        "/movies/Inception.2010.en.srt",
        "/movies/fanart.jpg",               # unrelated
        "/movies/readme.txt",               # metadata but no matching primary
    ]

    def test_auto_detects_two_primaries(self):
        results = detect_sidecars(self.FILES)
        primary_paths = {r["primary_path"] for r in results}
        assert "/movies/The.Matrix.1999.mkv" in primary_paths
        assert "/movies/Inception.2010.mkv" in primary_paths

    def test_matrix_has_four_sidecars(self):
        results = detect_sidecars(self.FILES)
        matrix = next(r for r in results if "Matrix" in r["primary_path"])
        sc_paths = {s["path"] for s in matrix["sidecars"]}
        assert "/movies/The.Matrix.1999.en.srt" in sc_paths
        assert "/movies/The.Matrix.1999.es.srt" in sc_paths
        assert "/movies/The.Matrix.1999.nfo" in sc_paths
        assert "/movies/The.Matrix.1999-poster.jpg" in sc_paths

    def test_fanart_not_associated_with_either(self):
        results = detect_sidecars(self.FILES)
        for r in results:
            sc_paths = {s["path"] for s in r["sidecars"]}
            assert "/movies/fanart.jpg" not in sc_paths

    def test_inception_has_one_sidecar(self):
        results = detect_sidecars(self.FILES)
        inception = next(r for r in results if "Inception" in r["primary_path"])
        assert len(inception["sidecars"]) == 1
        assert inception["sidecars"][0]["path"] == "/movies/Inception.2010.en.srt"

    def test_categories_assigned_correctly(self):
        results = detect_sidecars(self.FILES)
        matrix = next(r for r in results if "Matrix" in r["primary_path"])
        by_cat = {s["category"] for s in matrix["sidecars"]}
        assert "subtitle" in by_cat
        assert "metadata" in by_cat
        assert "artwork" in by_cat

    def test_explicit_primary_paths_restricts_results(self):
        """When primary_paths is given, only those primaries are checked."""
        results = detect_sidecars(
            self.FILES,
            primary_paths=["/movies/Inception.2010.mkv"],
        )
        assert len(results) == 1
        assert results[0]["primary_path"] == "/movies/Inception.2010.mkv"

    def test_empty_file_list(self):
        assert detect_sidecars([]) == []

    def test_no_primaries_in_list(self):
        """If no primary video files exist, result is empty."""
        results = detect_sidecars(["/movies/Movie.en.srt", "/movies/Movie.nfo"])
        assert results == []


# ── Section 3: compute_completeness() ─────────────────────────────────────────

class TestComputeCompleteness:
    """Tests for cross-drive sidecar coverage comparison."""

    DRIVE_1_SIDECARS = [
        {"path": "/D1/movies/Movie.en.srt", "category": "subtitle", "ext": ".srt"},
        {"path": "/D1/movies/Movie.nfo",    "category": "metadata", "ext": ".nfo"},
        {"path": "/D1/movies/Movie-poster.jpg", "category": "artwork", "ext": ".jpg"},
    ]

    DRIVE_2_SIDECARS = [
        {"path": "/D2/movies/Movie.en.srt", "category": "subtitle", "ext": ".srt"},
        # missing: Movie.nfo and Movie-poster.jpg
    ]

    def test_complete_when_both_drives_have_all(self):
        result = compute_completeness({1: self.DRIVE_1_SIDECARS, 2: self.DRIVE_1_SIDECARS})
        assert result["completeness"] == "complete"
        assert result["missing_on_any_drive"] is False

    def test_partial_when_d2_missing_metadata(self):
        result = compute_completeness(
            {1: self.DRIVE_1_SIDECARS, 2: self.DRIVE_2_SIDECARS},
            copy_policy={"subtitle": True, "metadata": True, "artwork": False},
        )
        assert result["completeness"] == "partial"
        assert result["missing_on_any_drive"] is True

    def test_d2_missing_list_contains_nfo(self):
        result = compute_completeness(
            {1: self.DRIVE_1_SIDECARS, 2: self.DRIVE_2_SIDECARS},
            copy_policy={"subtitle": True, "metadata": True, "artwork": False},
        )
        # Drive 2 is missing Movie.nfo
        assert any("nfo" in m for m in result["drives"][2]["missing"])

    def test_artwork_excluded_when_policy_false(self):
        """With artwork=False, poster.jpg difference is NOT counted as partial."""
        result = compute_completeness(
            {1: self.DRIVE_1_SIDECARS, 2: self.DRIVE_2_SIDECARS},
            copy_policy={"subtitle": True, "metadata": False, "artwork": False},
        )
        # Only subtitles count; both drives have .srt → complete
        assert result["completeness"] == "complete"

    def test_no_sidecars_when_both_empty(self):
        result = compute_completeness({1: [], 2: []})
        assert result["completeness"] == "no_sidecars"
        assert result["total_unique_sidecars"] == 0

    def test_single_drive_always_complete(self):
        """Single-copy item with sidecars — nothing to compare against → complete."""
        result = compute_completeness({1: self.DRIVE_1_SIDECARS})
        # All sidecars are on drive 1, no other drive to be missing from
        assert result["completeness"] == "complete"

    def test_total_unique_sidecars_counted_correctly(self):
        """Unique count = union of all included sidecar basenames."""
        result = compute_completeness(
            {1: self.DRIVE_1_SIDECARS, 2: self.DRIVE_2_SIDECARS},
            copy_policy={"subtitle": True, "metadata": True, "artwork": False},
        )
        # Movie.en.srt + Movie.nfo = 2 unique
        assert result["total_unique_sidecars"] == 2

    def test_covered_categories_reported(self):
        result = compute_completeness(
            {1: self.DRIVE_1_SIDECARS},
            copy_policy={"subtitle": True, "metadata": True, "artwork": True},
        )
        cats = set(result["all_covered_categories"])
        assert "subtitle" in cats
        assert "metadata" in cats
        assert "artwork" in cats


# ── Section 4: build_copy_manifest() ─────────────────────────────────────────

class TestBuildCopyManifest:
    PRIMARY = "/D1/movies/Movie.mkv"
    SIDECARS = [
        {"path": "/D1/movies/Movie.en.srt", "category": "subtitle", "ext": ".srt"},
        {"path": "/D1/movies/Movie.nfo",    "category": "metadata", "ext": ".nfo"},
        {"path": "/D1/movies/Movie-poster.jpg", "category": "artwork", "ext": ".jpg"},
    ]

    def test_default_policy_includes_subtitles_and_metadata(self):
        manifest = build_copy_manifest(self.PRIMARY, self.SIDECARS)
        roles = {e["role"] for e in manifest}
        assert "primary" in roles
        assert "subtitle" in roles
        assert "metadata" in roles
        assert "artwork" not in roles

    def test_primary_always_first(self):
        manifest = build_copy_manifest(self.PRIMARY, self.SIDECARS)
        assert manifest[0]["path"] == self.PRIMARY
        assert manifest[0]["role"] == "primary"

    def test_artwork_included_when_policy_true(self):
        policy = {"subtitle": True, "metadata": True, "artwork": True}
        manifest = build_copy_manifest(self.PRIMARY, self.SIDECARS, policy)
        roles = {e["role"] for e in manifest}
        assert "artwork" in roles

    def test_subtitles_excluded_when_policy_false(self):
        policy = {"subtitle": False, "metadata": True, "artwork": False}
        manifest = build_copy_manifest(self.PRIMARY, self.SIDECARS, policy)
        roles = [e["role"] for e in manifest]
        assert "subtitle" not in roles

    def test_no_sidecars_manifest_is_just_primary(self):
        manifest = build_copy_manifest(self.PRIMARY, [])
        assert len(manifest) == 1
        assert manifest[0]["role"] == "primary"

    def test_manifest_count(self):
        """Default policy: primary + subtitle + metadata = 3 files."""
        manifest = build_copy_manifest(self.PRIMARY, self.SIDECARS)
        assert len(manifest) == 3


# ── Section 5: Copy planning with and without sidecars ───────────────────────

class TestCopyPlanningScenarios:
    """
    Demonstrates how the sidecar manifest changes the copy operation
    depending on policy choices.
    """

    def setup_method(self):
        self.primary = "/D1/films/Interstellar.2014.mkv"
        self.sidecars = [
            {"path": "/D1/films/Interstellar.2014.en.srt", "category": "subtitle", "ext": ".srt"},
            {"path": "/D1/films/Interstellar.2014.fr.srt", "category": "subtitle", "ext": ".srt"},
            {"path": "/D1/films/Interstellar.2014.nfo",    "category": "metadata", "ext": ".nfo"},
            {"path": "/D1/films/Interstellar.2014-fanart.jpg", "category": "artwork", "ext": ".jpg"},
        ]

    def test_without_sidecars_copies_only_primary(self):
        policy = {"subtitle": False, "metadata": False, "artwork": False}
        manifest = build_copy_manifest(self.primary, self.sidecars, policy)
        assert len(manifest) == 1
        assert manifest[0]["role"] == "primary"

    def test_with_subtitles_only(self):
        policy = {"subtitle": True, "metadata": False, "artwork": False}
        manifest = build_copy_manifest(self.primary, self.sidecars, policy)
        assert len(manifest) == 3   # primary + 2 subtitle files
        roles = [e["role"] for e in manifest]
        assert roles.count("subtitle") == 2

    def test_full_policy_includes_all(self):
        policy = {"subtitle": True, "metadata": True, "artwork": True}
        manifest = build_copy_manifest(self.primary, self.sidecars, policy)
        assert len(manifest) == 5   # primary + 2 sub + 1 meta + 1 art

    def test_completeness_improves_after_copy(self):
        """
        Simulate: D1 has full sidecars, D2 has none after a video-only copy.
        After a full copy (including sidecars), completeness should be 'complete'.
        """
        # Before copy: D2 has no sidecars
        before = compute_completeness(
            {1: self.sidecars, 2: []},
            copy_policy={"subtitle": True, "metadata": True, "artwork": False}
        )
        assert before["completeness"] == "partial"

        # After the copy, D2 now has all the sidecars too
        d2_after = [
            {"path": s["path"].replace("/D1/", "/D2/"), "category": s["category"], "ext": s["ext"]}
            for s in self.sidecars
            if s["category"] in ("subtitle", "metadata")
        ]
        after = compute_completeness(
            {1: self.sidecars, 2: d2_after},
            copy_policy={"subtitle": True, "metadata": True, "artwork": False}
        )
        assert after["completeness"] == "complete"


# ── Section 6: helper function tests ─────────────────────────────────────────

class TestHelpers:
    def test_is_primary_mkv(self):
        assert is_primary("/path/movie.mkv") is True

    def test_is_primary_srt(self):
        assert is_primary("/path/movie.srt") is False

    def test_is_primary_mp4(self):
        assert is_primary("/path/movie.mp4") is True

    def test_get_sidecar_category_subtitle(self):
        assert get_sidecar_category(".srt") == "subtitle"
        assert get_sidecar_category(".vtt") == "subtitle"
        assert get_sidecar_category(".idx") == "subtitle"

    def test_get_sidecar_category_metadata(self):
        assert get_sidecar_category(".nfo") == "metadata"
        assert get_sidecar_category(".xml") == "metadata"

    def test_get_sidecar_category_artwork(self):
        assert get_sidecar_category(".jpg") == "artwork"
        assert get_sidecar_category(".png") == "artwork"

    def test_get_sidecar_category_unknown(self):
        assert get_sidecar_category(".mkv") is None
        assert get_sidecar_category(".zip") is None
        assert get_sidecar_category(".py") is None

    def test_default_copy_policy_values(self):
        assert DEFAULT_COPY_POLICY["subtitle"] is True
        assert DEFAULT_COPY_POLICY["metadata"] is True
        assert DEFAULT_COPY_POLICY["artwork"] is False
