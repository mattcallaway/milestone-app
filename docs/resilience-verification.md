# Resilience Verification Review (v2.5.1)

This document performs a deep dive into the correctness of the Milestone resilience engine.

## Core Definition of "Safe"
The product goal is for a "Safe" item to **survive at least one physical drive failure**.
A "Fully Resilient" item should also survive a **domain failure** (e.g., a whole NAS or enclosure going offline).

### Current Implementation State:
| Category | Survivor Condition | Survivor Count | Current Logic Code |
| :--- | :--- | :--- | :--- |
| **`safe_two_domains`** | Survives 1 drive failure AND 1 domain failure | 2+ drives, 2+ domains | Correct |
| **`unsafe_single_domain`** | Survives 1 drive failure BUT NOT 1 domain failure | 2+ drives, 1 domain | **POTENTIAL BUG** |
| **`unsafe_no_backup`** | No backup | 0–1 copies | Correct |

---

## 1. Cross-Check Analysis

### Q: Does "Safe" match the goal of surviving a single-drive failure?
**YES**, for `safe_two_domains`.
**PARTIAL**, for `unsafe_single_domain`.
- **Bug Discovery**: The current backend code calculates `copy_count = len(files)`. If a user creates a second copy on the **same drive** (e.g., in a different folder), the system incorrectly reports it as `unsafe_single_domain` (implying a backup exists). Since a drive failure would lose both copies, this is not a true backup.
- **Fix Needed**: `resilience.py` must track `distinct_drives` and treat same-drive copies as `unsafe_no_backup` for state calculation.

### Q: Are there edge cases where the UI says "Safe" but single drive loss still destroys the only verified copy?
**YES**.
- **The "Verification-Mix" Edge Case**: If a user has a "Verified" copy on Drive A and an "Unverified" copy on Drive B, the system currently treats the item's overall status as part of the risk score. However, if Drive A fails, you are left with ONLY an unverified (potentially corrupt) copy.
- **The "Stale Index" Edge Case**: If a drive is scanned, then files are modified/deleted externally, the Milestone DB remains "Safe" until the next scan.
- **Action**: Planning should prioritize placing *new* copies based on existing *verified* copies, and users should be encouraged to rescan before executing large plans.

### Q: Are failure domains influencing planning everywhere?
- **Planning Logic**: `planning.py` correctly uses `suggest_destinations()`, which prioritizes cross-domain placement.
- **Improved**: Retirement planning now simulates drive loss to ensure domain diversity is maintained for all items.

---

## 2. Consistency Mapping (Audit)

| Field / Feature | Value | Consistency Status |
| :--- | :--- | :--- |
| **DB Schema** | `mif.is_primary` vs `items.status` | **CONSISTENT**. Status applies to the item aggregate. |
| **Backend Models** | `PlanItem` types | **CONSISTENT**. Supports Protection/Reduction/Retirement. |
| **API Responses** | `resilience_state` strings | **CONSISTENT**. Matches canonical constants in `resilience.py`. |
| **Frontend Labels** | Dashboard badges | **CONSISTENT**. Mapped in `Screens.css` and `RiskScreen.tsx`. |

## 3. Discrepancy Fix List
- [x] **Fix**: Update `resilience.py` to count `distinct_drives` for copy-count baseline. (Done in v2.5.1)
- [x] **Fix**: Update `planning.py` to block suggesting "degraded" drives as copy targets. (Done in v2.5.1)
- [x] **Fix**: Update `RetirementPlan` to simulate drive loss before destination selection. (Done in v2.5.1)
