# Sahaay AI — Phase 5 Integration Audit: Existing Architecture & Live-Data Readiness

## 1. Executive Summary

This audit establishes the baseline architectural state of Sahaay AI prior to Phase 5 integration. It inspects existing route contracts, the Decision Engine, the Phase 4 Hyderabad risk modules, the Vision V1–V4 safety gates, the citizen reporting mechanisms, and frontend readiness.

The principal objective of Phase 5 is to unify these disparate components into a cohesive, production-grade, explainable flood intelligence platform with live-data adapter boundaries—**without manufacturing accuracy, altering historical checkpoints, or bypassing the Vision V4 readiness gate.**

---

## 2. Component Architecture Audit

### 2.1 Backend API & Routing (`src/sahaay/api/`)
- **Current State**:
  - FastAPI application in `src/sahaay/api/main.py` mounting router from `src/sahaay/api/routes.py`.
  - Exposes:
    - `GET /api/v1/health`: System health.
    - `GET /api/v1/vision/health`: Vision model loading status.
    - `POST /api/v1/vision/predict`: Vision inference with MIME checking and payload size limits ($15\text{ MB}$).
    - `POST /api/v1/decision/evaluate`: Decision synthesis endpoint.
    - `POST /api/v1/risk/rainfall/estimate`: Phase 4 IMD rainfall risk evaluation.
    - `POST /api/v1/risk/vulnerability/calculate`: Phase 4 GIS road vulnerability index calculation.
    - `GET /api/v1/risk/corridors`: Pre-computed feature vectors for 20 candidate corridors.
- **Identified Gaps for Phase 5**:
  - No dedicated endpoint for ingesting, validating, and managing citizen reports.
  - Corridor list endpoint does not expose dynamic real-time synthesis combining live citizen reports with environmental risk.
  - No health check differentiating operational service liveness from upstream telemetry data freshness.

### 2.2 Decision Engine (`src/sahaay/decision/contracts.py`)
- **Current State**:
  - Defines `DecisionInput`, `DecisionOutput`, `AlertLevel` (`CLEAR`, `ADVISORY`, `WATCH`, `WARNING`, `EMERGENCY`), and `HazardNature` (`OBSERVED_HAZARD`, `PREDICTED_RISK`, `COMMUNITY_REPORT`, `MAINTENANCE_NOTICE`).
  - Synthesizes vision predictions, rainfall scores, and vulnerability indices.
- **Identified Gaps for Phase 5**:
  - Lacks explicit `current_flood_evidence_status` enumeration (fails to explicitly distinguish "Observed flood evidence", "Elevated environmental risk", "No current evidence available", "Inconclusive / Contradictory", and "Insufficient / Stale data").
  - Lacks machine-readable `stale_inputs` and `missing_inputs` tracking.
  - Confidence calculation is partially hardcoded ($0.90$ vs $0.70$) rather than dynamically calibrated against evidence quality, station distance, and report corroboration.
  - Does not handle contradictory multi-source evidence (e.g., visual check says dry pavement while citizen report claims deep water).

### 2.3 Hyderabad Geospatial & Rainfall Risk Package (`src/sahaay/hyderabad_risk/`)
- **Current State**:
  - Ingestion: [`ingest.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/ingest.py) handles KML hotspots, KML drains, GeoJSON waterbodies, IMD monthly rainfall, and NWIC telemetry rainfall.
  - Validation: [`validate.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/validate.py) filters negative sensor faults (19 detected) and accumulator spikes $> 250\text{ mm}$ ($36,398$ detected), and tracks multi-hour gaps without silent zero-imputation.
  - Features: [`features.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/features.py) calculates Haversine and point-to-segment distances to hotspots, nalas, and waterbodies.
  - Engines: [`rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py) (IMD SOP rules) and [`vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py) (multi-criteria GIS index).
- **Identified Role in Phase 5**:
  - Serves as the primary environmental risk and physical susceptibility provider for all corridor evaluations.

### 2.4 Vision Stream & Safety Gates
- **Current State**:
  - Historical checkpoints: `models/vision/best_model.pt` (V1), `models/vision/v2/model_v2.pt` (V2), `models/vision/v3/model_v3_monsoon.pt` (V3).
  - Vision V4 readiness gate: Formally **NO-GO** in [`reports/vision_integrity/v4_phase3_pilot_audit.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/v4_phase3_pilot_audit.json). Zero real-world images ingested; zero permissions approved.
- **Mandate for Phase 5**:
  - Vision remains strictly advisory.
  - The Vision V4 NO-GO readiness gate must remain preserved and untouched.
  - Automated image quality gate (`src/sahaay/vision/quality.py`) flags ambiguous or degraded images as `inconclusive`, preventing false-positive flood alerts.

### 2.5 Citizen Reporting & Verification
- **Current State**:
  - Reports in Phase 1–4 were conceptual inputs passed as parameters (`report_age_minutes`, `citizen_report_count_in_zone`) without a persistent lifecycle or deduplication module.
- **Identified Requirement for Phase 5**:
  - Implement a dedicated report module under `src/sahaay/reports/` with deduplication (spatial radius $\le 100\text{ m}$, temporal window $\le 30\text{ min}$), privacy redaction, corroboration tracking, and explicit verification rules.

### 2.6 Frontend & Map Experience
- **Current State**:
  - No active frontend web application exists in the repository.
- **Identified Requirement for Phase 5**:
  - In accordance with the prompt and `<web_application_development>` guidelines, deliver an API-backed, high-aesthetic HTML/CSS/Vanilla JS dashboard (`src/sahaay/api/static/index.html`) served directly by FastAPI.
  - Interactive corridor map, live status cards, scenario selectors, report submission modal, and clear visual separation between observed flooding and modeled environmental risk. Never render `UNKNOWN` as green or safe.

---

## 3. Integration Plan & Action Items

| Item | Action | Target Location |
| :--- | :--- | :--- |
| **Unified Contract** | Define Pydantic V2 schema with 5-status evidence enum and full provenance | `src/sahaay/decision/contracts.py`, `docs/phase5_decision_contract.md` |
| **Citizen Reports** | Build report ingestion, validation, deduplication, corroboration, and privacy masking | `src/sahaay/reports/` |
| **Live Adapters** | Build adapter interfaces for TSDPS, NWIC, GHMC DRF, and CCTV with fallback behavior | `src/sahaay/adapters/`, `docs/phase5_live_data_readiness.md` |
| **Decision Hardening** | Implement contradictory evidence resolution, emergency policy constraints, and decision tables | `src/sahaay/decision/synthesis.py`, `docs/phase5_decision_rules.md` |
| **Corridor Map UI** | Deliver interactive, high-aesthetic vanilla HTML/CSS/JS dashboard | `src/sahaay/api/static/index.html` |
| **Demonstration** | Implement 10 reproducible labeled fixtures and runner script | `data/phase5_demo/`, `reports/phase5/end_to_end_scenarios.json` |
| **Regression Tests** | Ensure all 82 existing tests pass, add comprehensive Phase 5 suite | `tests/test_phase5_integration.py` |
