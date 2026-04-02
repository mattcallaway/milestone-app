# Deep Theory Audit Report (v2.6.0)

This document challenges the underlying resilience model of Milestone and identifies gaps between the user's intent and the software's logic.

## 1. Challenge: Is "2 Copies" Always Sufficient?
- **Theory**: 2 copies on 2 domains = "Safe".
- **Critique**: Digital storage is subject to **Silent Bit Rot**. If 1 copy is corrupted (bit rot) and 1 copy survives, we cannot mathematically determine which is the original without a hash.
- **Auditor Verdict**: "Safe" (2 copies) is actually only **"Minimally Resilient"**.
- **Requirement**: "Resilience" should be a score, not a binary "Safe" state. The software should encourage **3-2-1** (3 copies, 2 media, 1 offsite) for true "Safe" status.

## 2. Challenge: Drive Trustworthiness
- **Theory**: Drives are "Healthy" until reported "Warning" or "Degraded" by SMART or a manual flag.
- **Critique**: Budget consumer drives often fail without any SMART warnings (e.g. PCB failure or firmware lock).
- **Auditor Verdict**: The system over-relies on drive state.
- **Requirement**: The Risk Scorer should penalize drive "Age" (calculated from registration date) even if health is "Healthy".

## 3. Challenge: Certainty in Filename Grouping
- **Theory**: Files are grouped into items based on `full_hash` or `quick_sig`.
- **Critique**: Reliance on `quick_sig` (partial hash) for grouping is a "Certainty Overstatement".
- **Auditor Verdict**: Items matched ONLY by `quick_sig` should never be marked "Safe" in the UI; they should be marked "Proposed Group" or "Pending Verification".
- **Status Check**: Milestone currently marks these as `needs_verification` (+10 risk), which is theoretically sound but needs stronger UI visualization.

## 4. Challenge: Failure Domain Ambiguity
- **Theory**: Users manually assign failure domains (NAS 1, PC 1, etc.).
- **Critique**: Users often share a single failure point (e.g. the same power circuit or network switch) across multiple "domains".
- **Auditor Verdict**: The word "Domain" is too technical.
- **Requirement**: The UI should use "Infrastructure Groups" or "Risk Isolation Units" to better explain the concept.

## 5. Summary of Theory Refinements
- [ ] **Shift from Binary to Gradient**: Replace "Safe" with "Resilience Level" (0-100%).
- [ ] **Hash-First Strategy**: Prioritize hashing over just "copying". Resilience without integrity (hashes) is "Blind Redundancy".
- [ ] **Verify-on-Copy**: Every copy operation should MANDATE a verification hash to "reset" the integrity clock.
