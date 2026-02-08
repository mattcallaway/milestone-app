# Changelog

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
