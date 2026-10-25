# Sahaay AI — Phase 8 Human-Verified Evidence Intake Workflow

**Document Version:** 1.0.0  
**Phase:** 8 (Evidence Intake & Documentary Validation)  
**Date:** 2026-10-25  

---

## 1. Principles of Evidence Intake

To prevent fraudulent or premature closure of safety and legal prerequisites, Sahaay AI enforces a structured **Evidence Intake Workflow**:

1. **Documentary Metadata Schema:** Real evidence must be registered with complete provenance (document hash, issuing agency, execution date, expiration date, and permitted scope).
2. **Rejection of Synthetic Evidence:** Synthetic fixture IDs (`SIM-`, `FIXTURE-`, `MOCK-`) are programmatically barred from registration as real evidence.
3. **Independent Human Review:** Submitting a document does not make it verified. An independent reviewer (e.g. Legal Counsel, Safety Specialist, Data Protection Officer) must review the document and record an attributable verdict (`VERIFIED_VALID` or `REJECTED_DEFICIENT`).
4. **Scope-Bound Enforcement:** An agreement authorizing telemetry access in Corridor 1 cannot satisfy prerequisites for Corridor 2 unless explicitly scoped for metropolitan-wide operations (`ALL_PILOT_OPERATIONS`).

---

## 2. Evidence Intake Lifecycle

```
+--------------------------------------------------------------------------------------------------+
|                                    EVIDENCE INTAKE LIFECYCLE                                     |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|   1. REGISTRATION (`SUBMITTED`)                                                                  |
|      - Responsible owner uploads document to secure compliance vault.                            |
|      - Intake service logs document hash, execution date, expiry, and permitted scope.           |
|                                                                                                  |
|   2. INDEPENDENT AUDIT & VERIFICATION                                                           |
|      - Independent reviewer inspects legal text, signatures, and safety clauses.                 |
|      - If compliant -> Status: `VERIFIED_VALID` (records reviewer role, ID, timestamp).          |
|      - If deficient/incomplete -> Status: `REJECTED_DEFICIENT` (records reason for rejection).   |
|                                                                                                  |
|   3. PREREQUISITE & BLOCKER LINKING                                                              |
|      - Valid evidence reference is linked to corresponding `PrerequisiteRecord` in               |
|        `PilotActivationGate` and `BlockerRecord` in `BlockerRegistry`.                           |
|                                                                                                  |
|   4. AUTOMATIC EXPIRATION WATCHDOG                                                               |
|      - If `as_of > expiration_date`, evidence automatically evaluates to False.                 |
|      - Re-verification required prior to subsequent field shifts.                                |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## 3. Required Evidence Categories & Reviewing Roles

| Category | Example Document Type | Responsible Submitter | Mandatory Independent Reviewer |
| :---: | :--- | :--- | :--- |
| `INSTITUTIONAL_MOU` | Inter-Agency Data-Sharing MoU | Project PI | Institutional Legal Counsel |
| `SITE_SAFETY_INSPECTION` | Daytime Footbridge Hazard Survey | Field Operations Lead | Designated Safety Officer |
| `PPE_EQUIPMENT_AUDIT` | Equipment Serial & Testing Log | Field Operations Lead | Systems Integration Lead |
| `ROLE_DESIGNATION_LETTER` | Official Designation Letter | Project PI | Project Steering Committee |
| `DPDP_PRIVACY_AUDIT` | Staging Coarsening Audit | Legal Lead | Data Protection Officer (DPO) |
| `SOURCE_TELEMETRY_LICENSE` | Telemetry API Key & Terms | Hydrology Lead | Compliance Lead |
