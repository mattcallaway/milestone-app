# Resilience Assumptions (v2.5.1)

This document lists the assumptions made by the Milestone resilience engine.

## 1. Physical Assumptions
- **The "Drive ID is a Physical Unit"**: The engine assumes that a unique `drive_id` in the database corresponds to a single PHYSICAL piece of hardware. If a user maps multiple partitions from the same physical disk as separate drives, the resilience engine will over-report safety (counting separate partitions as separate backups).
- **Domain Reliability**: The assumption is that once a Drive is assigned a `domain_id`, it is part of that failure domain. The system does not currently auto-detect domain groups (e.g., via hardware enclosure IDs).

## 2. Integrity Assumptions
- **The "Verified-One-is-Verified-All" Fallacy**: The engine assumes that if one copy of an item is `verified` (hash matches), the content is safe. If another copy on a different drive is `needs_verification` or `auto`, the engine does NOT yet subtract these from the resilience count. It treats the *item* aggregate as "verified".
- **Silent Rot Assumption**: The system assumes no bit rot occurs between periodic scans. If a file rots on an unverified copy, the system will only detect it during an explicit "Check Integrity" task.

## 3. Planning Assumptions
- **Copy over Move**: The Protection Plan assumes that adding a copy is always better than moving one.
- **Drive Health Honesty**: The engine assumes total trust in the `health_status` field (e.g., provided by SMART or manual flag). It does not perform active disk stress tests.

## 4. Sidecar Integrity
- **Proxy of Protection**: The engine assumes that if a primary video is protected across domains, its sidecars (SRT, NFO) *should* be as well. However, current resilience states (`safe_two_domains`) are based ONLY on the primary media files. Sidecar presence is tracked as `completeness` but does not influence the "Safe" vs. "Unsafe" boolean logic.
