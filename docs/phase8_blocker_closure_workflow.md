# Sahaay AI — Phase 8 Verified Blocker-Closure Workflow

**Document Version:** 1.0.0  
**Phase:** 8 (Blocker Closure & Verification)  
**Date:** 2026-10-25  

---

## 1. Governance Principles for Blocker Closure

Resolving blockers in Sahaay AI is governed by strict evidential standards:
1. **Source of Truth:** Master blocker state is recorded in [`data/phase8/blocker_register.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase8/blocker_register.csv) and evaluated via [`src/sahaay/pilot/blockers.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/pilot/blockers.py).
2. **Four-Eye Review Principle:** The role responsible for closing a blocker cannot verify its own closure. An independent reviewer must inspect the documentary evidence before transitioning to `VERIFIED_CLOSED`.
3. **Explicit Five-State Lifecycle:**
   - `NOT_STARTED`: Action pending initial drafting or request.
   - `REQUESTED`: Formal external submission filed with responsible agency.
   - `PENDING_REVIEW`: Documentary evidence submitted to compliance vault; awaiting independent audit.
   - `VERIFIED_CLOSED`: Evidence reviewed, authenticated, and signed off.
   - `REJECTED`: Evidence insufficient, expired, synthetic, or out of scope.
4. **Rejection of Synthetic References:** Any attempt to use `SIM-`, `FIXTURE-`, or `MOCK-` references automatically fails verification.

---

## 2. Master Blocker Matrix & Closure Criteria

```
+---------------------------------------------------------------------------------------------------------+
|                                    BLOCKER CLOSURE LIFECYCLE MATRIX                                     |
+---------------------------------------------------------------------------------------------------------+
| Blocker ID   | Scope             | Responsible Role     | Independent Reviewer | Closure Evidence       |
+--------------+-------------------+----------------------+----------------------+------------------------+
| BLK-01-TSDPS | Optional Feed     | Project PI           | Legal Counsel        | Executed MoU + API Key |
| BLK-02-DRF   | Optional Feed     | Legal Lead           | Dispatch Supervisor  | Data-Sharing Agreement |
| BLK-03-SITE  | Whole-Pilot (Mand)| Field Operations Lead| Safety Specialist    | Signed Survey + Photos |
| BLK-04-PPE   | Whole-Pilot (Mand)| Field Operations Lead| Systems Lead         | Serial Register + Cert |
| BLK-05-DPDP  | Whole-Pilot (Mand)| Legal Lead           | Data Protection Off. | Staging Audit Report   |
| BLK-06-ROLES | Whole-Pilot (Mand)| Project PI           | Steering Committee   | Signed Role Letters    |
| BLK-07-CCTV  | Optional Feed     | Vision Safety Lead   | Ethics Board         | DPIA Sign-Off (V4 Gate)|
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Scope Scoping & Fail-Closed Impact

- **Whole-Pilot Blockers (BLK-03, 04, 05, 06):**
  If any of these 4 remains unverified, the entire pilot is locked in `BLOCKED_NOT_READY_FOR_LIVE_PILOT`. Zero field observation sessions may begin.
- **Feed-Specific Blockers (BLK-01, 02, 07):**
  If unverified, only the automated feed adapter is disabled or placed in fallback. They do **not** block a human vantage point observation session if the pilot scope is explicitly restricted.
