# Sahaay AI — Phase 7 Blocker Resolution Plan

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  

---

## 1. Governance Principles for Blocker Resolution

To maintain complete transparency and avoid unearned readiness claims, the resolution of institutional, safety, and technical blockers follows these strict guidelines:

1. **Source of Truth:** All blocker tracking originates from [`data/phase7/blocker_register.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase7/blocker_register.csv).
2. **Explicit Human Ownership:** Each blocker is assigned to a specific role. Generic or missing owners are flagged as `HUMAN_TEAM_TO_SUPPLY`.
3. **Decoupled Impact Scope:**
   - **Whole-Pilot Blockers:** Must be 100% resolved before any field team can be dispatched.
   - **Feed-Specific Blockers:** Block only the specific data adapter or external stream; the system gracefully operates in fallback or sandbox mode without blocking the overall pilot.
4. **Documentary Evidence Required:** A blocker cannot transition to `RESOLVED` without an official document reference (MoU ID, inspection log, serial inventory).

---

## 2. Whole-Pilot Mandatory Blockers Matrix

These 4 blockers directly bar field teams from deploying to candidate corridors:

```
+---------------------------------------------------------------------------------------------------------+
|                                    WHOLE-PILOT MANDATORY BLOCKERS                                       |
+---------------------------------------------------------------------------------------------------------+
| Blocker ID | Title                          | Responsible Role     | Evidence Required for Closure      |
+------------+--------------------------------+----------------------+------------------------------------+
| BLK-03     | Site Safety Inspections        | Field Operations Lead| Signed inspection report & photos  |
|            | at 4 Candidate Corridors       |                      | for 4 elevated footbridges         |
+------------+--------------------------------+----------------------+------------------------------------+
| BLK-04     | PPE Procurement & Inspection   | Field Operations Lead| Equipment serial inventory and     |
|            |                                |                      | Class 2 certification sign-off     |
+------------+--------------------------------+----------------------+------------------------------------+
| BLK-05     | DPDP Consent Deployment        | Legal & Compliance   | Staging portal audit report with   |
|            | on Staging Portal              | Lead                 | 3-decimal coarsening verification  |
+------------+--------------------------------+----------------------+------------------------------------+
| BLK-06     | Formal Role Appointment        | Principal            | Executed institutional appointment |
|            | for Field Lead & Safety Officer| Investigator         | letters with emergency contacts    |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Feed-Specific Optional Blockers Matrix

These 3 blockers apply to specific automated data feeds and do not prevent manual vantage field collection:

| Blocker ID | Title | Responsible Role | Current Status | Operational Fallback Behavior |
| :---: | :--- | :--- | :---: | :--- |
| **BLK-01** | TSDPS AWS Agreement | Principal Investigator | `PENDING_APPROVAL` | TSDPS adapter uses historical playback / sandbox fallback. |
| **BLK-02** | GHMC DRF Incident Logs | Legal & Compliance Lead | `NOT_SUBMITTED` | Emergency calls must be entered manually by authorized operator. |
| **BLK-07** | Municipal CCTV & DPIA | Vision Safety Lead | `QUARANTINED_BLOCKED` | CCTV is strictly quarantined under the Vision V4 **NO-GO** gate. |

---

## 4. Closure Procedures & Audit Protocol

When a responsible owner satisfies the requirements for blocker closure:
1. The evidence document is archived in the compliance vault (`data/compliance/`).
2. The owner updates the record in [`data/phase7/blocker_register.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase7/blocker_register.csv) with the document reference.
3. The owner calls `PilotActivationGate.update_prerequisite_evidence()` with their role and user ID.
4. The activation gate re-evaluates the system state. If all 4 mandatory blockers are resolved, the state transitions automatically to `READY_FOR_AUTHORIZED_PILOT_REVIEW`.
