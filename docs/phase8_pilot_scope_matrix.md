# Sahaay AI — Phase 8 Pilot Scope Matrix & Subsystem Decoupling

**Document Version:** 1.0.0  
**Phase:** 8 (Scope Matrix & Operational Decoupling)  
**Date:** 2026-10-25  

---

## 1. Principles of Scope Decoupling

A common architectural trap in multi-modal systems is total deadlock: waiting for every external government agency to execute high-level MoUs before conducting any controlled, non-hazardous physical validation.

Phase 8 introduces **explicit, auditable scope boundaries**:
1. **Physical Vantage Pilot Scope:** Requires only site inspections, PPE procurement, DPDP consent notices, and role appointments. Does **not** require real-time TSDPS AWS streaming or CCTV access.
2. **Fail-Closed Feed Scoping:** If an external feed (TSDPS AWS, GHMC DRF) is not authorized, that specific capability is disabled or placed in fallback. It **never** silently defaults to zero rainfall or claims live connectivity.
3. **Vision V4 Isolation:** CCTV optical inference remains in `QUARANTINED_DISABLED` status under the Vision V4 **NO-GO** gate.

---

## 2. Pilot Scope Subsystem Matrix

```
+---------------------------------------------------------------------------------------------------------+
|                                    PILOT SUBSYSTEM SCOPE MATRIX                                         |
+---------------------------------------------------------------------------------------------------------+
| Capability / Subsystem        | In Scope? | Prerequisite Required     | Fallback Behavior if Unmet      |
+-------------------------------+-----------+---------------------------+---------------------------------+
| Supervised Vantage Observation| **YES**   | BLK-03, 04, 05, 06 (Mand) | Whole pilot BLOCKED             |
| TSDPS Real-Time Telemetry     | **NO**    | BLK-01-TSDPS-AWS (Opt)    | Non-silent INSUFFICIENT_DATA    |
| GHMC DRF Incident Feed        | **NO**    | BLK-02-GHMC-DRF (Opt)     | Manual operator verification    |
| Municipal CCTV Inference      | **NO**    | BLK-07-CCTV (Quarantined) | Optical feed disabled (V4 NO-GO)|
| Citizen Report Processing     | **YES**   | BLK-05-DPDP-CONSENT (Mand)| Staging sandbox mode only       |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Human Scope Approval Procedure

Any alteration to the active pilot scope profile requires formal sign-off recorded in [`reports/phase8/pilot_scope_decision.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase8/pilot_scope_decision.json) by the Project Director or Principal Investigator. Software executes strictly within the boundaries of the approved scope profile.
