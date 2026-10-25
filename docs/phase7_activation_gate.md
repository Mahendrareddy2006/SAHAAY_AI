# Sahaay AI — Phase 7 Evidence-Based Pilot Activation Gate

**Document Version:** 1.0.0  
**Phase:** 7 (Pilot Activation Gate & Operational Validation)  
**Date:** 2026-10-25  
**Governing Standard:** ISO/IEC 25010 / DPDP Act 2023 / Municipal Safety Directives  

---

## 1. Overview and Core Invariants

The **Pilot Activation Gate** is the authoritative, centralized software boundary governing whether any real-world human-supervised field collection session or live data pipeline activation may occur.

### Non-Negotiable Operational Invariants:
1. **Fail-Closed Default:** If any mandatory prerequisite is missing, expired, unverifiable, or rejected, the system status is locked to `BLOCKED_NOT_READY_FOR_LIVE_PILOT`.
2. **Anti-Manufacture Directive:** A synthetic test fixture, mock adapter, or simulation ID (`SIM-`, `FIXTURE-`, `MOCK-`) **cannot** satisfy a real-world legal, safety, or institutional prerequisite.
3. **Strict Separation of Software from Authority:** Software can verify that valid documentary references exist; however, **only an authorized human role** (`PRINCIPAL_INVESTIGATOR` or `PROJECT_DIRECTOR`) can legally execute the transition to `PILOT_AUTHORIZED`.
4. **Purpose-Bound Authorizations:** Approval of an academic data requisition or research agreement for offline analysis does not grant blanket authority for real-time operations or field photography.
5. **Cryptographic Transition Ledger:** Every state change records an attributable, cryptographically hashed audit action (SHA-256).

---

## 2. Activation Gate State Machine

```
+----------------------------------------------------------------------------------------------------+
|                                  PILOT ACTIVATION STATE MACHINE                                    |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|    +-----------------------------------------+                                                     |
|    |    BLOCKED_NOT_READY_FOR_LIVE_PILOT     |<----------------------------------+                 |
|    +-----------------------------------------+                                   |                 |
|                         |                                                        |                 |
|                         | [All Mandatory Prerequisites Satisfied]                |                 |
|                         v                                                        |                 |
|    +-----------------------------------------+                                   |                 |
|    |   READY_FOR_AUTHORIZED_PILOT_REVIEW     |                                   |                 |
|    +-----------------------------------------+                                   |                 |
|                         |                                                        |                 |
|                         | [Human PI / Project Director Signs Transition]         |                 |
|                         v                                                        |                 |
|    +-----------------------------------------+                                   |                 |
|    |             PILOT_AUTHORIZED            |--------+                          |                 |
|    +-----------------------------------------+        |                          |                 |
|                         |                             |                          |                 |
|       [Abort Trigger /  |                             | [All Scheduled Shifts    | [Prereq Expiry/ |
|        Safety Hazard /  |                             |  Completed Successfully] |  Breach]        |
|        Auth Breach]     v                             v                          |                 |
|    +-----------------------------------------+   +---------------------------+   |                 |
|    |             PILOT_SUSPENDED             |   |      PILOT_COMPLETED      |   |                 |
|    +-----------------------------------------+   +---------------------------+   |                 |
|                         |                                                        |                 |
|                         +--------------------------------------------------------+                 |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. The 8 Pilot Prerequisites Specification

| Prerequisite ID | Description | Mandatory? | Required Evidence Reference | Current Verification Status |
| :---: | :--- | :---: | :--- | :---: |
| **PREREQ_01** | Executed Institutional MoU with GHMC / HTP | **YES** | Signed inter-departmental MoU or Govt Order | `UNVERIFIED_PENDING` |
| **PREREQ_02** | Responsible Human Owner & Field Lead Recorded | **YES** | Formal designation letter & safety officer appointment | `UNVERIFIED_PENDING` |
| **PREREQ_03** | Physical Site Hazard Inspection Completed | **YES** | Signed physical survey report for 4 vantage points | `UNVERIFIED_PENDING` |
| **PREREQ_04** | Certified High-Visibility PPE & Gauges Checked | **YES** | Equipment procurement and inspection sign-off | `UNVERIFIED_PENDING` |
| **PREREQ_05** | DPDP Consent & Coordinate Coarsening Deployed | **YES** | Legal staging verification of privacy notice | `UNVERIFIED_PENDING` |
| **PREREQ_06** | Data Tiering & Right-to-Erasure Operational | **YES** | `DOC-PHASE6-DATA-GOVERNANCE-v1.0` | `VERIFIED_EVIDENCE_ATTACHED` |
| **PREREQ_07** | Observation Schema & Ingestion Verified | **YES** | `SUITE-PHASE6-REGRESSION-111-PASSING` | `VERIFIED_EVIDENCE_ATTACHED` |
| **PREREQ_08** | External Telemetry Authorization (Optional) | **NO** | TSDPS API Bearer token / NWIC data license | `UNVERIFIED_PENDING` |

---

## 4. Transition Rules & Human Authority Matrix

1. **Rule 1 (`BLOCKED` $\rightarrow$ `READY`):**
   - Evaluated autonomously by `PilotActivationGate._evaluate_readiness_state()`.
   - Fires *only* when `is_currently_valid() == True` for all 7 mandatory prerequisites.
2. **Rule 2 (`READY` $\rightarrow$ `AUTHORIZED`):**
   - **Requires Human Authority:** Software cannot autonomously grant authorization.
   - Authorized roles: `PRINCIPAL_INVESTIGATOR`, `PROJECT_DIRECTOR`, or `MUNICIPAL_COMMISSIONER`.
   - Requires documented `justification_notes` ($\ge 10\text{ characters}$) and records user ID.
3. **Rule 3 (`AUTHORIZED` $\rightarrow$ `SUSPENDED`):**
   - Immediate safety override. Can be invoked by `FIELD_SAFETY_LEAD`, `SUPERVISOR_DISPATCHER`, or `SYSTEM_ADMINISTRATOR` upon weather abort, lightning proximity, traffic diversion, or lost authorization.
4. **Rule 4 (`SUSPENDED` $\rightarrow$ `AUTHORIZED`):**
   - Requires supervisor sign-off and automatic re-verification that all mandatory prerequisites remain valid.
5. **Rule 5 (`AUTHORIZED` $\rightarrow$ `COMPLETED`):**
   - Executed upon formal completion of the pilot observation schedule.
