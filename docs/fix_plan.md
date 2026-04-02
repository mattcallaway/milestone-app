# v2.6.0 Deep Audit Fix Plan

This document outlines the priority and action items for fixing issues discovered during the Deep Audit (v2.6.0).

## 1. Phase 1: Critical & High Priority (IMMEDIATE)

| Task | Priority | Location | Status |
| :--- | :--- | :--- | :--- |
| **[C-01] Fix Destination Path Flattening** | Critical | `copier.py` | [x] Complete |
| **[H-01] Implement `delete` in Queue worker** | High | `queue.py` | [x] Complete |
| **[H-02] Fix Race Condition in task start** | High | `queue.py` | [x] Complete |

---

## 2. Phase 2: Medium Priority (v2.6.0 Release)

| Task | Priority | Location | Status |
| :--- | :--- | :--- | :--- |
| **[M-02] Path Normalization** | Medium | `scanner.py`, `copier.py` | [x] Complete |
| **[L-02] Operation Enums & Types** | Medium | `models.py`, `queue.py` | [x] Complete |
| **[M-03] Cleanup Dead `signature_stub`** | Low | `schema.sql`, `models.py` | [x] Complete |

---

## 3. Phase 3: Performance & Polishing (Future)

| Task | Priority | Location | Status |
| :--- | :--- | :--- | :--- |
| **[M-01] Optimize Sidecar Reports (Batch SQL)** | High | `routers/sidecars.py` | [x] Complete |
| **[L-01] Refactor UI Colors to Shared Config** | Low | `RiskScreen.tsx` | [x] Complete |

---

## 4. Theory & Model Improvements (Proposed)

| Item | Impact | Complexity |
| :--- | :--- | :--- |
| **Integrity-First Score** | High | Medium |
| **Expert Mode UI Guides** | Medium | Low |
| **Drive Age Factor** | Medium | Low |
