# Known Resilience Limitations (v2.5.1)

This document lists the CURRENT technical limitations of the Milestone resilience logic.

## 1. Single-Drive Multiple Partitions
**Current Issue**: If a user creates multiple database "Drives" (e.g., C: and D:) from the same physical disk, the system will incorrectly report 2-copy resilience if files exist on both.
- **Why**: There is no current way to bridge "Drive Serial Number" into a "Physical ID" for automatic grouping.
- **Mitigation**: Users should assign the SAME `failure_domain_id` to all partitions of the same physics disk to correctly trigger `unsafe_single_domain`.

## 2. Incomplete Domain Mapping
**Current Issue**: When any copy of an item is on a drive with NO domain assigned, the resilience state calculation becomes "optimistic".
- **Why**: The logic assumes that if a domain is unknown, it *might* be different from known domains, yet it doesn't count toward `distinct_domains`.
- **Status**: Visualized via the `domain_mapping_complete = False` field in API responses.

## 3. Sidecars vs. Resilience
**Current Issue**: An item can be marked `safe_two_domains` even if 100% of its sidecars (subtitles, metadata) exist on ONLY ONE of those domains.
- **Why**: Resilience states are calculated based on the existence of the primary media files only.
- **Mitigation**: Use the "Sidecar Completeness" field in `ItemDetailScreen` to manually audit backup integrity.

## 4. Degraded Drive Logic
**Current Issue**: An item on 2 healthy drives and 1 degraded drive will be marked `over_replicated_and_resilient`.
- **Why**: The status is "Technically True", even though risk is elevated.
- **Status**: The `Risk Score` correctly penalizes items on degraded drives (+20), even if they are resilient.

## 5. Duplicate Drives in Metadata
**Current Issue**: If `len(files) == 2` but `distinct_drive_ids == 1` (duplicate files on same drive), the system currently reports `unsafe_single_domain`.
- **Status**: **TO BE FIXED** in v2.5.1. (See Verification Plan).
