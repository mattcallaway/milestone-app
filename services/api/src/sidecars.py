"""
Sidecar Detection Engine
=========================
Pure, database-free module. Given a list of file paths from a single drive,
detects which files are sidecars of which primary video files.

Terminology
-----------
  primary   — a video file (.mkv, .mp4, etc.)
  sidecar   — a companion file (subtitle, metadata, artwork) whose name
              starts with (or exactly equals) the primary's stem.

Matching rules (all must be True):
  1. Same directory as the primary.
  2. Extension is in a known sidecar category.
  3. Filename (without extension) starts with the primary stem, optionally
     followed by '.' or '-' (e.g. "Movie.en.srt" or "Movie-poster.jpg").

Categories
----------
  subtitle  — .srt .sub .idx .ass .ssa .vtt .sup
  metadata  — .nfo .txt .xml
  artwork   — .jpg .jpeg .png .webp .tbn .gif

"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

# ── Extension tables ─────────────────────────────────────────────────────────

PRIMARY_EXTENSIONS: frozenset[str] = frozenset({
    ".mkv", ".mp4", ".avi", ".m2ts", ".m2t", ".mov", ".wmv",
    ".ts", ".m4v", ".mpg", ".mpeg", ".divx", ".flv", ".webm",
})

SIDECAR_CATEGORIES: dict[str, frozenset[str]] = {
    "subtitle": frozenset({".srt", ".sub", ".idx", ".ass", ".ssa", ".vtt", ".sup"}),
    "metadata": frozenset({".nfo", ".txt", ".xml"}),
    "artwork":  frozenset({".jpg", ".jpeg", ".png", ".webp", ".tbn", ".gif"}),
}

# Flat extension → category lookup
_EXT_TO_CATEGORY: dict[str, str] = {
    ext: cat
    for cat, exts in SIDECAR_CATEGORIES.items()
    for ext in exts
}

# Copy policy defaults (which categories to include when copying)
DEFAULT_COPY_POLICY: dict[str, bool] = {
    "subtitle": True,
    "metadata": True,
    "artwork":  False,   # artwork can be large; opt-in
}


# ── Path helpers ─────────────────────────────────────────────────────────────

def _split_path(path: str) -> tuple[str, str, str]:
    """
    Returns (parent_dir, stem, ext) for a path string,
    handling both POSIX and Windows separators.
    """
    # Normalise separators to forward-slash for consistency
    norm = path.replace("\\", "/")
    p = PurePosixPath(norm)
    return str(p.parent), p.stem, p.suffix.lower()


def get_sidecar_category(ext: str) -> str | None:
    """Return the sidecar category for an extension, or None if not a sidecar."""
    return _EXT_TO_CATEGORY.get(ext.lower())


def is_primary(path: str) -> bool:
    """Return True if the file is a recognised primary video format."""
    _, _, ext = _split_path(path)
    return ext in PRIMARY_EXTENSIONS


def is_sidecar_of(candidate_path: str, primary_path: str) -> bool:
    """
    Return True if candidate_path is a sidecar companion of primary_path.

    Rules:
      • Must be in the same directory.
      • Extension must be a known sidecar type.
      • Name must start with primary_stem + '.' or primary_stem + '-',
        or name (sans extension) must exactly equal the primary stem.

    Examples (primary stem = "Movie.2023"):
      "Movie.2023.en.srt"   → True  (starts with "Movie.2023.")
      "Movie.2023.nfo"      → True  (starts with "Movie.2023.")
      "Movie.2023-poster.jpg"→ True  (starts with "Movie.2023-")
      "Movie.2023"          → True  (stem exactly equals)
      "Movie.2023.mkv"      → False (same primary ext — it IS the primary)
      "random.jpg"          → False (name doesn't start with stem)
      "Movie.2023x.jpg"     → False (continuation char is not '.' or '-')
    """
    c_dir, c_stem, c_ext = _split_path(candidate_path)
    p_dir, p_stem, p_ext = _split_path(primary_path)

    if c_dir != p_dir:
        return False
    if get_sidecar_category(c_ext) is None:
        return False
    if c_ext == p_ext:
        return False  # same extension → probably another primary, not a sidecar

    c_name = c_stem + c_ext      # full filename
    stem = p_stem                # e.g. "Movie.2023"

    return (
        c_name.startswith(stem + ".")
        or c_name.startswith(stem + "-")
        or c_stem == stem
    )


# ── Core detection ────────────────────────────────────────────────────────────

def detect_sidecars(
    all_paths: list[str],
    primary_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Detect sidecar files for each primary video in all_paths.

    Parameters
    ----------
    all_paths     — every file path on a drive (or directory)
    primary_paths — if supplied, restrict primary detection to these paths;
                    otherwise auto-detect primaries from all_paths

    Returns
    -------
    List of dicts, one per primary:
        primary_path : str
        sidecars     : list[dict]  (path, category, ext)
    """
    if primary_paths is not None:
        primaries = list(primary_paths)
    else:
        primaries = [p for p in all_paths if is_primary(p)]

    results = []
    for prim in primaries:
        sidecars = []
        for cand in all_paths:
            if cand == prim:
                continue
            if is_sidecar_of(cand, prim):
                _, _, ext = _split_path(cand)
                sidecars.append({
                    "path": cand,
                    "category": get_sidecar_category(ext),
                    "ext": ext,
                })
        results.append({
            "primary_path": prim,
            "sidecars": sidecars,
        })
    return results


# ── Cross-drive completeness ──────────────────────────────────────────────────

def compute_completeness(
    primary_sidecars_by_drive: dict[int, list[dict]],
    copy_policy: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Compare sidecar coverage across drives.

    Parameters
    ----------
    primary_sidecars_by_drive : {drive_id: [{"path":..., "category":..., "ext":...}]}
        Sidecars present on each drive for the SAME primary file
        (i.e. already filtered to one item's copies).

    copy_policy : which categories to care about (defaults to DEFAULT_COPY_POLICY)

    Returns
    -------
    {
        "completeness": "complete" | "partial" | "no_sidecars",
        "total_unique_sidecars": int,
        "drives": {
            drive_id: {
                "sidecars": [...],
                "missing": [...],   # basenames present on at least one other drive
                "extra":   [],      # basenames only on this drive
            }
        },
        "all_covered_categories": set[str],
        "missing_on_any_drive": bool,
    }
    """
    if copy_policy is None:
        copy_policy = DEFAULT_COPY_POLICY

    # Collect all sidecar basenames (normalised to just filename)
    def basename(path: str) -> str:
        return PurePosixPath(path.replace("\\", "/")).name

    # Per-drive: set of sidecar basenames in "included" categories
    drive_sidecar_names: dict[int, set[str]] = {}
    for drive_id, sidecars in primary_sidecars_by_drive.items():
        names = {
            basename(s["path"])
            for s in sidecars
            if copy_policy.get(s["category"], False)
        }
        drive_sidecar_names[drive_id] = names

    all_names: set[str] = set().union(*drive_sidecar_names.values()) if drive_sidecar_names else set()

    if not all_names:
        return {
            "completeness": "no_sidecars",
            "total_unique_sidecars": 0,
            "drives": {
                did: {"sidecars": [], "missing": [], "extra": []}
                for did in primary_sidecars_by_drive
            },
            "all_covered_categories": set(),
            "missing_on_any_drive": False,
        }

    missing_on_any = False
    per_drive: dict[int, dict] = {}
    for drive_id, names in drive_sidecar_names.items():
        missing = sorted(all_names - names)
        extra = sorted(names - all_names)   # always empty by definition, but kept for API symmetry
        if missing:
            missing_on_any = True
        per_drive[drive_id] = {
            "sidecars": sorted(names),
            "missing":  missing,
            "extra":    extra,
        }

    completeness = "complete" if not missing_on_any else "partial"

    # What categories are covered at all
    covered_cats: set[str] = set()
    for sidecars in primary_sidecars_by_drive.values():
        for s in sidecars:
            if copy_policy.get(s["category"], False):
                covered_cats.add(s["category"])

    return {
        "completeness": completeness,
        "total_unique_sidecars": len(all_names),
        "drives": per_drive,
        "all_covered_categories": sorted(covered_cats),
        "missing_on_any_drive": missing_on_any,
    }


# ── Copy manifest builder ─────────────────────────────────────────────────────

def build_copy_manifest(
    primary_path: str,
    available_sidecars: list[dict],
    policy: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    """
    Return an ordered list of files to copy (primary + policy-filtered sidecars).

    Parameters
    ----------
    primary_path        — the video file to copy
    available_sidecars  — list of {"path":..., "category":..., "ext":...}
    policy              — which categories to include

    Returns
    -------
    [{"path":..., "role": "primary"|category, "size": None|int}]
    """
    if policy is None:
        policy = DEFAULT_COPY_POLICY

    manifest = [{"path": primary_path, "role": "primary"}]
    for sc in available_sidecars:
        if policy.get(sc["category"], False):
            manifest.append({"path": sc["path"], "role": sc["category"]})
    return manifest
