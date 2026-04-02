# Safety Model Review (v2.6.0)

This document verifies the "No Automatic Data Loss" guarantee and safety guards of the Milestone system.

## 1. Automated Deletions & Quarantines
- **Audit Requirement**: No automated file removal.
- **Verification**:
    - `matcher.py`: Links files to items; does not delete originals.
    - `scanner.py`: Updates metadata; does not delete.
    - `copier.py`: Safe copy with `.tmp` and atomic replace.
- **Safety Verdict**: **PASSED**. No logic currently deletes files automatically.

## 2. Planning & Execution Lifecycle
- **Audit Requirement**: No plan execution without explicit human confirmation.
- **Verification**:
    - `planning.py`: All plans created as `PlanStatus.DRAFT`.
    - `routers/planning.py`: Requires a `POST /plans/{id}/execute` to start.
- **Safety Verdict**: **PASSED**.

## 3. Placement to Degraded Drives
- **Audit Requirement**: No placement to degraded drives by default.
- **Verification**:
    - `placement.py`: Skips drives with `health_status` in `EXCLUDED_HEALTH` (degraded/avoid).
    - `planning.py`: Filters drives by health before suggesting.
- **Safety Verdict**: **PASSED**.

## 4. Reduction/Quarantine Risks
- **Audit Requirement**: No quarantine or reduction path can silently strand the only remaining copy.
- **Verification**:
    - `planning.py`: `_populate_reduction_plan` only suggests the last copy *NOT* marked as primary.
    - **Gap Discovery (Minor)**: `mif.is_primary` can be 0 for all copies if an item is newly matched and no primary has been manually selected.
- **Safety Recommendation**: If no primary exists, the reduction planner should NEVER suggest deleting the last remaining copy. (Currently implemented via `if data['copy_count'] <= min_copies: continue`).
- **Safety Verdict**: **PASSED**.

## 5. Security - Expert Mode
- **Audit Requirement**: No silent "expert mode" activation.
- **Verification**:
    - All advanced actions (Merge, Split, Drive Retirement) are separate UI screens or explicit buttons.
- **Safety Verdict**: **PASSED**.
