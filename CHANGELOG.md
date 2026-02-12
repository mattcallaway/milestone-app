# Changelog

## [v1.1.2] - 2026-02-10

### Deep Audit Pass

**Critical Fixes**
- Added write-mode guards to quarantine, restore, and confirm_plan endpoints (`cleanup.py`, `plans.py`)
- Fixed queue status type mismatch — backend now returns `running_count`/`pending_count` matching frontend (`queue.py`, `ops.py`)
- Moved `safe_copy` I/O to thread executor to prevent event loop blocking during multi-GB copies (`copier.py`)

**High Fixes**
- Added path traversal validation to quarantine endpoint (`cleanup.py`)
- Eliminated scanner dual-state desync with `_set_scan_state()` setter (`scanner.py`)
- Wrapped hasher queue in try/finally to prevent permanent stuck state on error (`hasher.py`)
- Added plan status check to `toggle_plan_item` — only draft plans modifiable (`plans.py`)

**Medium Fixes**
- Added `usedforsecurity=False` to `hashlib.md5()` for FIPS compatibility (`hasher.py`)

**Cleanup**
- Removed unused `Any` import (`scanner.py`)
- Removed dead `relative_path` / `source_mount` variables (`copier.py`)
- Simplified `queue_status_endpoint` — removed duplicated DB queries (`ops.py`)

---

## [v1.1.1-audit] - 2026-02-08

### Stability & Audit Pass

**Critical Fixes**
- Fixed SQL string interpolation in `items.py` HAVING clause → parameterized queries
- Fixed scanner error state set to IDLE instead of CANCELLED on exceptions

**Warning Fixes**
- Replaced bare `except:` with `except OSError:` in `copier.py`
- Removed dead `get_db_connection()` function that leaked resources (`database.py`)
- Hoisted redundant internal `HTTPException` imports to module level (`files.py`)
- Replaced `print()` with proper `logging` in migration script (`v110.py`)

**Cleanup**
- Removed unused `threading` import (`queue.py`)
- Removed unused `hashlib` import (`copier.py`)
- Removed unused `get_settings` import (`database.py`)

**Documentation**
- Added `AUDIT_REPORT.md` with full findings, severity, and justifications

---

## [v1.1.0] - 2026-02-08

### Added

**Failure Domains**
- New `failure_domains` table for grouping drives by shared risk
- Drives can be assigned to domains (enclosure, NAS, location, power)
- Copy-health now requires copies in 2+ distinct domains for safety
- DomainsScreen for managing failure domains

**Drive Failure Simulation**  
- Simulation endpoint to analyze impact if drives fail
- Shows items that would lose all copies, fall below 2 copies, or lose domain redundancy
- SimulationScreen with interactive drive selection

**Bulk Planning Workflow**
- Plans/plan_items tables for preview-before-execute operations
- Create copy plans for at-risk items (0-1 copies)
- Create reduction plans for over-replicated items
- Review and toggle individual items before execution
- PlanScreen for managing plans

**Schema Additions**
- `failure_domains` table
- `io_settings` table for throttling configuration  
- `sidecars` table for subtitle/poster tracking
- `plans` and `plan_items` tables
- Drive columns: `failure_domain_id`, `read_only`, `never_write`, `preferred`
- Media item column: `verification_state`
- Join columns: `match_reason`, `confidence`

**Frontend**
- DomainsScreen for failure domain management
- SimulationScreen for drive failure analysis
- PlanScreen for bulk planning workflow
- Navigation updated with Domains, Simulation, Plans

### Changed
- API version bumped to 1.1.0
- Updated API description

---

## [v1.0.0] - 2026-02-08

### Added
- Cleanup recommendations for items with 3+ copies
- Quarantine move operation (reversible deletion)
- CSV exports: at-risk, inventory, duplicates
- Open in Explorer endpoints
- CleanupScreen frontend

---

## [v0.3.0-m3] - 2026-02-07

### Added
- Operations queue with copy/move/delete
- Safe copy with verification
- Operations UI

---

## [v0.2.0-m2] - 2026-02-06

### Added
- Media items and grouping
- File hashing (quick signature, full hash)
- Items screen and filtering

---

## [v0.1.0-m1] - 2026-02-05

### Added
- Drives and roots management
- File scanning
- Basic dashboard
