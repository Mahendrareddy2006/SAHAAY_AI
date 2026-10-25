# Sahaay AI — Phase 6 Baseline & Repository Audit

**Document Version:** 1.0.0  
**Audit Target:** Commit `ce26c31` (Phase 5 completion on branch `master`)  
**Audit Date:** 2026-10-25  
**Auditor:** Sahaay AI Research & Systems Integration Team  

---

## 1. Executive Summary

This audit establishes the baseline technical and operational state of Sahaay AI prior to beginning **Phase 6: Hyderabad Field-Pilot Readiness, Ground-Truth Collection & Operational Validation**.

Phase 5 successfully unified citizen reports, rainfall and vulnerability feature pipelines, and live-data adapters into a hardened, explainable Decision Engine and an interactive dashboard. However, as documented in [`reports/phase5/phase5_completion_report.md`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase5/phase5_completion_report.md):
- **Zero live feeds are connected to unauthenticated external streams.** All live adapters operate in sandbox, historical playback, or quarantined states.
- **Zero field observations have been gathered.** The current database contains zero real-world ground-truth field depth measurements.
- **The Vision V4 readiness gate remains strictly NO-GO.** Historical checkpoints (`best_model.pt`, `model_v2.pt`, `model_v3_monsoon.pt`) remain historical artifacts and are blocked from the live operational inference path.
- **No autonomous actions (evacuations or closures) are permitted.**

---

## 2. Test Execution and Verification

The test suites and demonstration scripts were executed directly in the local environment (`.\.venv\Scripts\python.exe` on Windows).

### 2.1 Automated Unit & Integration Tests

```bash
.\.venv\Scripts\python.exe -m pytest -v
```

**Results:**
- **Total Tests:** 98
- **Passed:** 98
- **Failed:** 0
- **Skipped:** 0
- **Warnings:** 15 (Starlette deprecation warning on `TestClient`, Python `datetime.utcnow()` deprecation in feature engines)
- **Execution Time:** 8.03 seconds

**Subsystem Breakdown:**
- `tests/test_phase5_integration.py` (16 passed): Citizen report PII anonymization, near-duplicate clustering ($\le 100\text{ m}, \le 30\text{ min}$), responder verification, TSDPS/NWIC/DRF/CCTV adapter boundaries, non-silent missing rainfall telemetry, contradictory evidence surfacing, dashboard static asset delivery, and contract validation.
- `tests/test_vision_v4_phase3.py` (7 passed): Master permission register structure, zero unverified approvals, pilot site candidate definitions, and readiness gate NO-GO preservation.
- `tests/test_vision_v4_collection.py` (15 passed): Acquisition ingestion, privacy redaction, perceptual duplicate clustering, and readiness gate logic.
- `tests/test_vision_v4.py` (9 passed): Metadata leak audit preservation, cluster disjointness, advisory contract checks.
- `tests/test_vision_v3.py` (10 passed): V3 split disjointness, monsoon augmentations, image quality gate checks.
- `tests/test_transforms.py` (3 passed): Preprocessing and augmentations output tensor shapes.
- `tests/test_split_integrity.py` (5 passed): V2 split disjointness and hash integrity.
- `tests/test_model.py` & `test_inference.py` (5 passed): Architecture instantiation and empty/corrupt byte handling.
- `tests/test_image_quality_gate.py` (5 passed): Resolution, darkness, and whiteout rejections.
- `tests/test_hyderabad_risk_pipeline.py` (16 passed): Spatial decay distance scoring, rainfall feature calculations, API risk routes.
- `tests/test_api.py` (7 passed): Core FastAPI routing, input validation, and HTTP error handling.

### 2.2 Demonstration Scenario Conformance

```bash
.\.venv\Scripts\python.exe scripts/run_phase5_demo.py
```

**Results:**
- **Total Scenarios:** 10
- **Passed:** 10 ($100.0\%$)
- **Failed:** 0
- Output verified against [`reports/phase5/end_to_end_scenarios.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase5/end_to_end_scenarios.json).
- Scenarios demonstrate:
  1. Low rainfall / low vulnerability $\rightarrow$ `CLEAR`
  2. Severe rainfall / high vulnerability without observation $\rightarrow$ `WATCH` / `ELEVATED_ENVIRONMENTAL_RISK`
  3. Unverified citizen report $\rightarrow$ `ADVISORY` / `ELEVATED_ENVIRONMENTAL_RISK`
  4. Near-duplicate citizen cluster $\rightarrow$ Suppressed to single evidence event
  5. Verified deep flood ($60\text{ cm}$) $\rightarrow$ `EMERGENCY` / `OBSERVED_FLOOD_EVIDENCE`
  6. Missing telemetry $\rightarrow$ `ADVISORY` / `INSUFFICIENT_OR_STALE_DATA` (never converts missing to $0.0\text{ mm}$)
  7. Contradictory inputs (CCTV dry pavement vs citizen flood claim) $\rightarrow$ `ADVISORY` / `INCONCLUSIVE`
  8. Inconclusive optical model inference ($0.51$) $\rightarrow$ Baseline fallback
  9. Severe rainfall risk with missing current field evidence $\rightarrow$ `WATCH`
  10. Feed recovery after outage $\rightarrow$ `CLEAR`

---

## 3. Subsystem Audit & Readiness Boundary

| Component | Status at Commit `ce26c31` | Operational Limitations |
| :--- | :--- | :--- |
| **API & Endpoints** | Functional & Tested | Public web endpoints exist for report submission, verification, and feed status. |
| **Dashboard** | Functional (`/dashboard`) | Visualizes corridors on Leaflet map, distinguishes modeled risk from observed flooding. |
| **Citizen Reports** | Functional & Tested | Anonymizes phone/email with SHA-256; coarsens coordinates to 3 decimals; clusters duplicate reports within 100m/30min. |
| **Live Telemetry (TSDPS)** | Disabled / Fallback | No authorized API credentials; uses historical/fixture fallback. |
| **Telemetry (NWIC)** | Historical Replay | Open historical archive replay; flagged as simulated playback. |
| **GHMC / DRF Incidents** | Disabled / Fallback | Internal municipal network only; requires manual operator verification. |
| **Municipal CCTV** | Quarantined / Disabled | Legally restricted; optical Vision V4 gate is **NO-GO**. |
| **Ground-Truth Field Data** | Zero Observations | No calibrated water-depth measurements, sensor telemetry, or structured field logs exist in the repository. |
| **Candidate Corridors** | 4 Candidate Sites | Candidate corridors identified in Phase 3/4 are *candidates only*; zero corridors have approved field access or formal site sign-off. |

---

## 4. Ground-Truth Data Deficit

To evaluate flood prediction models scientifically, an evaluation dataset must meet the following criteria:
1. **Calibrated ground-truth labels:** Known physical water presence and depth ($\pm 5\text{ cm}$) recorded under safe, repeatable observation protocols.
2. **Negative examples:** True negative records ("no water observed on roadway") collected under active rainfall conditions.
3. **Spatial and temporal disaggregation:** Observations grouped by storm event and road segment to prevent spatial autocorrelation leakage.
4. **Zero circular validation:** Hotspot datasets used to calculate road vulnerability cannot be used as test labels for the vulnerability score.

Currently, **none** of these datasets exist in the repository. Phase 6 must establish the protocols, schemas, ingestion paths, and safety mechanisms to make acquiring this ground truth possible without endangering field teams or fabricating data.
