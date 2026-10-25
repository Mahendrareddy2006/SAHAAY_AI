# Sahaay AI — Phase 6 Operational Runbook: Incident Triage & Human Review Workflow

**Document Version:** 1.0.0  
**Status:** Operational Protocol  
**Date:** 2026-10-25  
**Audience:** Municipal Emergency Operators, Dispatch Supervisors, Field Leads  

---

## 1. Principles of Operational Review

The Sahaay AI platform operates on an explicit **Human-in-the-Loop** model. Algorithms, feature pipelines, and vision models assist human situational awareness—they **never** hold authority to:
- Issue autonomous public flood declarations
- Trigger automated municipal road closures
- Dispatch emergency rescue teams without human verification

Every operational alert escalation and verification action must be traceable, attributable to a verified human operator, and cryptographically chained in an audit log.

---

## 2. Review Queue Routing Architecture

The operational review queue is exposed via `GET /api/v1/review/pending` and transitions items through authorized human actions:

```
+--------------------------------------------------------------------------------------------------+
|                                    OPERATIONAL REVIEW ROUTING                                    |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   TRIGGER CONDITION                                                                              |
|   1. Citizen report claiming depth >= 15 cm                                                      |
|   2. Contradictory evidence (e.g. CCTV clear vs citizen report flooded)                          |
|   3. High environmental rainfall risk on critical road without field observation                 |
|   4. Suspected duplicate burst from same geographic cell                                         |
|                                                                                                  |
|   ENQUEUED TO: `ReviewQueueService` -> Status: `PENDING_REVIEW`                                  |
|                                                                                                  |
|   ACTION OPTIONS BY SUPERVISOR:                                                                  |
|   - `DISMISS_FALSE_ALARM`: Unsubstantiated citizen claim or clear camera vantage; reason logged.  |
|   - `ESCALATE_TO_FIELD_TEAM`: Order non-contact vantage inspection by deployed field unit.       |
|   - `ESCALATE_TO_DRF`: Forward verified deep inundation (>= 30cm) to Municipal DRF console.      |
|   - `VERIFIED_CONFIRMED`: Official responder confirms street condition on site.                 |
|                                                                                                  |
|   CRYPTOGRAPHIC AUDIT CHAIN:                                                                     |
|   Action hash = SHA-256(ActionID | Role | UserID | ActionType | Timestamp | Notes | PrevHash)    |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Standard Operating Procedures (SOPs)

### SOP-01: Contradictory Evidence Triage
- **Condition:** Decision Engine flags `INCONCLUSIVE_CONTRADICTORY` with reason code `CONTRADICTORY_OBSERVATIONS_DETECTED`.
- **Operator Action:**
  1. Open camera stream history to inspect if camera orientation (Pan-Tilt-Zoom) was moved away from low-lying curb depressions.
  2. Inspect citizen report photo (if attached) for identifiable local landmarks (metro piers, bus shelters).
  3. If uncertainty remains, dispatch Field Unit to elevated pedestrian footbridge.
  4. Record action via `POST /api/v1/review/action` with justification notes.

### SOP-02: Rapid Duplicate Burst Triage
- **Condition:** Multiple citizen submissions from the same corridor within 30 minutes.
- **Operator Action:**
  1. Automated clustering algorithm suppresses duplicates to a single evidence event with corroboration count.
  2. Reviewer confirms whether reports reflect independent observers or a coordinated spam burst.
  3. If genuine, mark status as `VERIFIED_CONFIRMED` or assign single priority ticket.

### SOP-03: High Environmental Risk under Missing Telemetry
- **Condition:** Rainfall station goes offline during active thunderstorm; engine reports `INSUFFICIENT_OR_STALE_DATA`.
- **Operator Action:**
  1. Cross-reference nearest operational radar or secondary AWS station within 10 km.
  2. Do not mark corridor as CLEAR.
  3. Maintain ADVISORY status until telemetry recovers or manual observation confirms road condition.

---

## 4. End-to-End Review Example

A complete, machine-readable walkthrough of an auditable incident review is documented at [`data/phase6/review_fixtures/incident_review_example.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/phase6/review_fixtures/incident_review_example.json).
