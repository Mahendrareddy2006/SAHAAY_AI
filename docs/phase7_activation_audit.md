# Sahaay AI — Phase 7 Baseline & Activation Audit

**Document Version:** 1.0.0  
**Audit Target:** Commit `0393286` (Phase 6 completion on branch `master`)  
**Audit Date:** 2026-10-25  
**Auditor:** Sahaay AI Research & Systems Integration Team  

---

## 1. Executive Summary

This audit establishes the empirical baseline for **Phase 7: Pilot Activation Gate, First Field Evidence & Operational Validation**.

The repository at commit `0393286` was inspected and verified. All automated software suites, schemas, ingestion pipelines, and decision rules are implemented and passing (**111/111 tests passing in 8.22 seconds**). 

However, the operational readiness status remains strictly:
> **`BLOCKED_NOT_READY_FOR_LIVE_PILOT`**

This status reflects factual real-world conditions, not incomplete code:
1. **Zero institutional data-sharing agreements** have been executed with TSDPS, GHMC, or HTP.
2. **Zero physical site inspections** have been documented across the 4 candidate corridors.
3. **PPE equipment procurement** has not yet been physically verified.
4. **Zero real ground-truth field observations** exist in the repository store.
5. **Vision V4 readiness gate** remains strictly `NO-GO`.

Phase 7 must enforce an evidence-based pilot activation gate that fails closed and prohibits any field session from beginning until authorized human sign-offs are cryptographically and administratively verified.

---

## 2. Test Execution Verification

```bash
.\.venv\Scripts\python.exe -m pytest -v
```

**Results:**
- **Total Tests:** 111
- **Passed:** 111 ($100.0\%$)
- **Failed:** 0
- **Skipped:** 0
- **Duration:** 8.22 seconds
- **Warnings:** 15 (Starlette test client deprecation, Python `datetime.utcnow()` deprecation in feature engines)

### Subsystem Verification Matrix:
- `tests/test_phase6_pilot_readiness.py` (13 passed): Zero real observations assertion, permission register check, bounding box validation, coordinate coarsening, near-duplicate detection, cryptographic review hash chaining, CCTV quarantine check, non-silent missing telemetry enforcement.
- `tests/test_phase5_integration.py` (16 passed): Citizen report PII anonymization, near-duplicate clustering, responder verification, adapter registry live readiness, non-silent missing rainfall, contradictory observation handling, dashboard static assets.
- `tests/test_vision_v4_phase3.py` & `test_vision_v4_collection.py` & `test_vision_v4.py` (31 passed): Master permission register structure, pilot candidate site definitions, duplicate clustering, privacy redactions, metadata leak prevention, Vision V4 readiness gate NO-GO preservation.
- `tests/test_hyderabad_risk_pipeline.py` (16 passed): Rainfall feature scoring, road vulnerability spatial decay, API routes.
- `tests/test_image_quality_gate.py` & `test_transforms.py` & `test_vision_v3.py` & `test_split_integrity.py` & `test_inference.py` & `test_model.py` & `test_api.py` (35 passed): Core model inference, tensor transformations, quality gates, split disjointness, and FastAPI endpoints.

---

## 3. Ground-Truth Data & Field Readiness Gap

The ground-truth inventory at the start of Phase 7 is:
- **Real-World Field Ground-Truth Observations:** **0**
- **Calibrated Staff Gauge Depth Measurements:** **0**
- **Verified Flood Inundation Episodes ($d \ge 5\text{ cm}$):** **0**
- **Verified Non-Flooded Rainy Road Episodes ($d < 5\text{ cm}$):** **0**
- **Pre-Registered Evaluation Sample Size Requirement:** 50 flood episodes, 100 non-flood episodes across $\ge 4$ storm dates and 3 independent corridors.

Any attempt to evaluate flood prediction accuracy or train machine learning classifiers prior to acquiring this ground truth remains scientifically invalid and strictly blocked.

---

## 4. Institutional Permissions Gap

| Data Feed | Agency | Status | Actual Authorization | Production Use |
| :--- | :--- | :---: | :---: | :---: |
| **TSDPS AWS Rainfall** | TSDPS | `PENDING_INSTITUTIONAL_APPROVAL` | None (`NONE_GRANTED`) | Prohibited (Fallback Active) |
| **GHMC DRF Dispatch Logs** | GHMC | `REQUEST_NOT_SUBMITTED` | None (`NONE_GRANTED`) | Prohibited (Operator Manual Only) |
| **Municipal CCTV Video** | HTP / GHMC | `PENDING_INSTITUTIONAL_APPROVAL` | None (`NONE_GRANTED`) | **QUARANTINED_DISABLED (V4 NO-GO)** |
| **Citizen Reports** | Public Users | `INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE` | None (`NONE_GRANTED`) | Staging Sandbox Only |
| **Supervised Field Obs.** | Sahaay Team | `INTERNAL_PROTOCOL_PENDING_SAFETY_CLEARANCE` | None (`NONE_GRANTED`) | **BLOCKED (Safety Gate 01 & 02)** |
| **Water-Depth Telemetry** | Irrigation | `REQUEST_NOT_SUBMITTED` | None (`NONE_GRANTED`) | Prohibited |
| **DEM & Drainage GIS** | TRAC | `NO_COMMERCIAL_LICENSE_IDENTIFIED` | None (`NONE_GRANTED`) | Static Baseline Only |

---

## 5. Non-Negotiable Phase 7 Audit Boundaries

1. **Fail-Closed Principle:** In the absence of an executed agreement, verified site safety inspection, or verified PPE check, the system must evaluate to `BLOCKED_NOT_READY_FOR_LIVE_PILOT`.
2. **Anti-Manufacture Directive:** A unit test or mock fixture must **never** satisfy a real-world legal approval requirement.
3. **Preservation of Safety Gates:** Vision V4 remains strictly `NO-GO`.
