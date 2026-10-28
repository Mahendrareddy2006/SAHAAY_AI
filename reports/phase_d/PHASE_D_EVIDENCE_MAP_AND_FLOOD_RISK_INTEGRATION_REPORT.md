# Sahaay AI — Phase D: Evidence-to-Map and Flood-Risk Integration Report

**Milestone:** Phase D (Canonical Corridor Evidence Synthesis, Map GeoJSON Integration & Routing Safety)  
**Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**Evaluation Date:** October 28, 2026  
**Auditor:** Antigravity Autonomous Systems Agent (Phase D Task Lead)  
**Audit Script:** `scripts/audit_phase_d_corridor_evidence.py`  
**Machine-Readable Audit Results:** `reports/phase_d/phase_d_results.json`  
**Milestone Acceptance Status:** **ACCEPTED**  

---

## Executive Summary

Phase D unifies the distributed sensory, topological, meteorological, community, static vulnerability, and emergency assessment subsystems of Sahaay AI into a **canonical corridor-level evidence view**. This milestone establishes an authoritative, traceable multi-modal synthesis architecture while maintaining strict evidence isolation, preventing unverified assumptions from becoming ground truth, and enforcing all previously established safety boundaries.

Prior to Phase D, live road status, community verification, IMD rainfall observations, NWP numerical forecasts, static flood susceptibility, and vision inference existed across fragmented schemas and separate endpoints. Phase D integrates these components into a single canonical corridor assessment contract (`CorridorEvidenceAssessment`) exposed through both GeoJSON map properties and dedicated REST inspection endpoints, without creating duplicate risk engines or conflicting status enums.

### Key Milestones Achieved
1. **Component Reuse Without Duplication:** Reused existing Phase A (road network store), Phase B (topological graph router), Phase C (weather ingestion pipeline), Phase 15 (community reports verification), Phase 16 (road status snapshots), Phase 17 (static road vulnerability), Phase 18 (forecast risk), Phase 19 (risk-aware routing), and Phase 21 (safety contracts).
2. **Canonical Multi-Modal Synthesis:** Implemented `CorridorEvidenceService` producing a 10-tier deterministic evidence state (`CorridorEvidenceState`) and 4-tier evidence sufficiency rating (`EvidenceSufficiency`).
3. **Strict Five-Signal Separation ($F, R, V, O, H=0$):** Forecast precipitation ($F$), observed rainfall ($R$), static susceptibility ($V$), optical surveillance ($O$), and historical inundation ($H=0$) are strictly decoupled. Forecast rainfall alone and static susceptibility heuristics are programmatically barred from marking roads flooded or impassable.
4. **Decoupled Temporal Provenance:** Explicit separation among observation timestamp, ingestion timestamp, forecast valid timestamp, and assessment computation timestamp prevents false freshness claims.
5. **GeoJSON Map & Resilience:** Extended `RoadSegmentMapProperties` with corridor evidence fields while preserving 100% rendering availability and sparse seed catalog warnings (`SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE`) during telemetry provider outages.
6. **Topological Routing Safety:** Preserved strict impassable-edge pruning; caller-visible uncertainty and disconnected topological components return `TOPOLOGY_UNSUPPORTED` without creating synthetic edges.
7. **Security & Role Spoofing Denial:** Caller-supplied role names (e.g., `SUPER_ADMIN_EMERGENCY_DIRECTOR`) are denied with HTTP 403; live feed activation remains blocked; autonomous closures and dispatch remain strictly disarmed.
8. **Test Suite Integrity:** 25 focused Phase D tests passed (100%); full test suite passed with 520 passing tests and the exact same 4 historical baseline failures preserved.

---

## 1. Inspection and Reuse of Existing Components

In compliance with Milestone Instruction 1, all pre-existing services, data models, and configurations were audited and reused. No duplicate risk engines or conflicting status enums were introduced.

| Component / Subsystem | Original Phase | Module Location | Reuse Strategy | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Road Network Store** | Phase A | `sahaay.road_network.store` | Extended `build_map_feature` to embed corridor evidence properties in GeoJSON output. | Reused & Extended |
| **Topological Road Graph** | Phase B | `sahaay.routing.graph_router` | Reused for connectivity analysis, connected components, and impassable edge hard-pruning. | Reused Unchanged |
| **Weather Telemetry Pipeline** | Phase C / Phase 13 | `sahaay.hyderabad_risk.weather_pipeline` | Reused for IMD AWS/ARG observation ingestion, counter conversion, and QC flags. | Reused Unchanged |
| **Community Verification Engine** | Phase 15 | `sahaay.reports.schemas`, `sahaay.reports.verification` | Reused `CitizenReportRecord` for corroboration, privacy masking, and conflict detection. | Reused Unchanged |
| **Live Road Status Engine** | Phase 16 | `sahaay.road_status.schemas`, `sahaay.road_status.service` | Reused `RoadStatusSnapshot` as the authoritative source for official responder verifications. | Reused Unchanged |
| **Static Road Vulnerability** | Phase 17 | `sahaay.hyderabad_risk.vulnerability_index` | Reused `RoadVulnerabilityResult` as infrastructure baseline heuristic. | Reused Unchanged |
| **Forecast Precipitation Risk** | Phase 18 | `sahaay.forecast_risk.service` | Reused `ForecastRainfallInput` and NWP risk evaluation for convective horizons. | Reused Unchanged |
| **Risk-Aware Routing Service** | Phase 19 | `sahaay.routing.service` | Reused for traversability weighting, penalty multipliers, and safety disclaimer enforcement. | Reused Unchanged |
| **Emergency Assessment Boundaries**| Phase 20 / Phase 21 | `sahaay.routing.contracts` | Reused `FORBIDDEN_SAFETY_PHRASES` and disarmed operational action flags. | Reused Unchanged |

---

## 2. Canonical Corridor Evidence Assessment Data Contracts

Phase D introduces `sahaay.corridor_evidence.schemas` defining the unified corridor-level assessment model.

### 2.1 The 10-Tier Evidence State Classification (`CorridorEvidenceState`)

```
+-----------------------------------------------------------------------------------------+
|                                CORRIDOR EVIDENCE STATE HIERARCHY                        |
+-----------------------------------------------------------------------------------------+
| 1. VERIFIED_IMPASSABLE          Authorized responder confirms submerged / closed        |
| 2. VERIFIED_WATERLOGGED         Authorized responder confirms standing water (>25cm)    |
| 3. VERIFIED_PASSABLE            Authorized responder confirms dry / passable pavement   |
| 4. CONFLICTING_EVIDENCE         Contradictory citizen reports or camera vs sensor clash |
| 5. CORROBORATED_HAZARD          >=2 independent citizen reports assert waterlogging     |
| 6. UNVERIFIED_REPORT            Single citizen submission awaiting corroboration        |
| 7. ELEVATED_METEOROLOGICAL_RISK Heavy rainfall / forecast on vulnerable road (unproven) |
| 8. STALE_EVIDENCE               Telemetry / reports aged beyond 180 min validity window |
| 9. NO_CURRENT_EVIDENCE          Monitored corridor with zero observations in window     |
| 10. UNMONITORED_UNKNOWN         Seed graph corridor lacking telemetry station coverage  |
+-----------------------------------------------------------------------------------------+
```

### 2.2 Seven Distinct Evidence Signal Sections

Every `CorridorEvidenceAssessment` exposes seven distinctly typed evidence sections:

1. **`RoadStatusEvidenceSection`**:
   - Reflects the active condition state, verification authority, freshness, and whether the road is officially impassable, waterlogged, or passable.
2. **`CommunityReportsEvidenceSection`**:
   - Captures raw report volume, count of independent contributors, verification state, age of oldest/newest report, and explicit conflict summaries.
3. **`ObservedRainfallEvidenceSection`**:
   - Contains 1h, 3h, 6h, 24h accumulations, station ID, station distance (km), data availability (`AVAILABLE`, `STALE`, `MISSING_TELEMETRY`, `OUTAGE_OR_MISSING_DATA`), and `is_valid_measured_zero` boolean.
4. **`ForecastRainfallEvidenceSection`**:
   - Contains advisory precipitation band, horizon (hours), source type, and a strict Pydantic validator enforcing `does_forecast_prove_inundation=False`.
5. **`StaticSusceptibilityEvidenceSection`**:
   - Contains terrain elevation bounds, vulnerability index, category, and a strict Pydantic validator enforcing `is_current_flood_status=False`.
6. **`VisionEvidenceSection`**:
   - Contains predicted class, calibrated confidence, quality gate flag, and `is_inconclusive_abstention=True` if confidence is in the $[0.35, 0.65]$ band or quality checks fail.
7. **`HistoricalInundationEvidenceSection`**:
   - Explicitly records verified historical inundation records (`has_verified_historical_flood_record=False` default; uninvented).

### 2.3 Strict Temporal Decoupling

The assessment contract programmatically decouples source timestamps via `source_timestamps`:
```json
{
  "road_status_observation_utc": "2026-10-28T05:30:00Z",
  "road_status_ingestion_utc": "2026-10-28T05:32:10Z",
  "rainfall_observation_utc": "2026-10-28T05:00:00Z",
  "forecast_issue_utc": "2026-10-28T03:00:00Z",
  "forecast_valid_utc": "2026-10-28T06:00:00Z",
  "vision_inference_utc": null,
  "assessment_generated_utc": "2026-10-28T06:15:00Z"
}
```
Timestamps and sensor readings are never invented or carried forward without provenance.

---

## 3. Enforcement of Safety Semantics & Invariants

| Safety Invariant | Implementation Mechanism | Validation Result |
| :--- | :--- | :--- |
| **No Synthetic Dry Zeros** | When telemetry is missing or sensor reports an outage, `rainfall_1h_mm` remains `None` and `data_availability="MISSING_TELEMETRY"`. It is never defaulted to `0.0 mm`. | **PASS** (`test_missing_telemetry_evaluates_to_insufficient_data_never_zero`) |
| **Valid Measured Zero Distinction** | When calibrated telemetry confirms `0.0 mm` rain, `is_valid_measured_zero=True` is set, distinguishing verified dry weather from unmonitored roads. | **PASS** (`test_valid_measured_zero_rainfall_distinction`) |
| **Forecast Rainfall $\ne$ Road Inundation** | Pydantic field validator rejects `does_forecast_prove_inundation=True`. Elevated forecast evaluates to `ELEVATED_METEOROLOGICAL_RISK`, keeping `is_traversable_for_routing=True`. | **PASS** (`test_forecast_alone_cannot_prove_inundation_validator`, `test_forecast_alone_never_marks_road_inundated_or_impassable`) |
| **Static Vulnerability $\ne$ Flood Status** | Pydantic field validator rejects `is_current_flood_status=True`. Static vulnerability is identified as `STATIC_INFRASTRUCTURE_HEURISTIC`. | **PASS** (`test_static_vulnerability_cannot_be_current_flood_status_validator`) |
| **Citizen Reports $\ne$ Ground Truth** | Citizen reports of waterlogging evaluate to `UNVERIFIED_REPORT` or `CORROBORATED_HAZARD` with degraded sufficiency, but cannot mark road impassable or closed. | **PASS** (`test_community_reports_alone_cannot_close_roads`) |
| **Explicit Conflict Preservation** | Conflicting citizen claims (flooded vs dry) or cross-modal contradictions (camera dry vs citizen flooded) evaluate to `CONFLICTING_EVIDENCE` and `has_unresolved_conflicts=True`. | **PASS** (`test_conflicting_citizen_reports_handling`, `test_cross_modal_conflict_vision_dry_vs_citizen_flooded`) |
| **Vision Abstention Propagation** | Optical probabilities in $[0.35, 0.65]$ or luminance/contrast gate failures strictly yield `predicted_class="inconclusive"` and `is_inconclusive_abstention=True`. | **PASS** (`test_vision_abstention_boundary_propagation`, `test_vision_quality_gate_failure_propagation`) |
| **Authorized Verification Rule** | Only an official responder field inspection (`RoadVerificationState.VERIFIED_BY_RESPONDER`) can assign `VERIFIED_IMPASSABLE` or `VERIFIED_WATERLOGGED`. | **PASS** (`test_official_responder_verified_impassable_closes_corridor`) |
| **Disarmed Operational Action** | `operational_action_authorized` is hardcoded to `False` on all assessments and route outputs. Autonomous closures and automated dispatch are blocked. | **PASS** (`test_operational_action_strictly_disarmed`) |
| **Forbidden Safety Phrasing** | The 8 forbidden phrases (`"safe"`, `"guaranteed passable"`, `"all clear"`, `"flood-free"`, etc.) are prohibited by validators across all explanation fields. | **PASS** (`test_forbidden_safety_phrasing_in_corridor_assessment`) |

---

## 4. Map & GeoJSON Integration

The road network store (`sahaay.road_network.store`) was updated to synthesize canonical corridor evidence into GeoJSON feature properties:

### 4.1 GeoJSON Feature Properties
Every map feature generated via `GET /api/v1/map/network` or `store.build_map_feature()` includes:
- `evidence_state`: String enum value of `CorridorEvidenceState`.
- `evidence_explanation`: Compact explanation of why the state was assigned.
- `evidence_sufficiency`: String enum value of `EvidenceSufficiency`.
- `has_unresolved_conflicts`: Boolean flag alerting UI to contradictory evidence.
- `observed_rainfall_1h_mm`: Real measured hourly rainfall, or `null`.
- `forecast_precipitation_band`: Advisory forecast intensity, or `null`.
- `vision_state`: Optical inference classification (`"flooded"`, `"not_flooded"`, `"inconclusive"`, or `null`).
- `coverage_warning`: Explicit sparse seed catalog disclosure: `"SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE"`.

### 4.2 Graceful Degradation Under Telemetry Provider Outage
When the weather telemetry provider or road status service is unreachable:
- Map feature synthesis catches provider exceptions and falls back to `condition_state=UNKNOWN`, `evidence_state=NO_CURRENT_EVIDENCE` or `UNMONITORED_UNKNOWN`.
- Map endpoints continue to return HTTP 200 with full vector geometries and cartographic symbology.
- At no point does a provider failure cause map blanking, 500 Internal Server Errors, or uncaught exceptions.

---

## 5. Topological Routing Integration

The topological router (`sahaay.routing.graph_router.TopologicalGraphRouter`) was audited against Phase D evidence inputs:

1. **Pruning of Verified Impassable Edges:**
   - When a corridor segment is confirmed `VERIFIED_IMPASSABLE` by an authorized responder, the router removes that edge from traversal consideration and attempts alternate bypass routing (e.g., Paramount Bypass detour around Tolichowki Underpass).
   - The pruned segment is returned in `excluded_segments` with explicit explanation.
2. **Disconnected Components Rejection:**
   - When origin and destination reside in disconnected components of the seed graph (e.g., Tolichowki in West Zone vs Musarambagh in East Zone), the router returns `RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED` with `engine_status="DISCONNECTED_TOPOLOGICAL_COMPONENTS"`.
   - The router strictly refuses to create synthetic edges to bridge disconnected components.
3. **Forecast & Static Susceptibility Isolation:**
   - Segments with heavy forecast rainfall or severe static vulnerability are penalized with increased traversal weights, but are **never marked impassable** or pruned from the graph.

---

## 6. Security and Operational Boundaries

1. **Caller Role Spoofing Denial:**
   - Any client request to `/api/v1/corridor-evidence/evaluate` containing unverified elevated role names (e.g., `caller_role="SUPER_ADMIN_EMERGENCY_DIRECTOR"`) or flags requesting live feed activation (`request_live_feed_activation=True`) is immediately rejected with **HTTP 403 Forbidden**.
   - Client-provided roles are unauthenticated and untrusted.
2. **Blocked External Telemetry Feeds:**
   - Live external IMD/TSDPS API connections remain `BLOCKED_PENDING_INSTITUTIONAL_APPROVAL`.
   - No mock adapter or synthetic fixture claims external institutional authorization.
3. **No Added Dependencies:**
   - Zero changes made to `pyproject.toml` or external package dependencies.

---

## 7. Changed Files and Test Execution

### 7.1 Changed and Created Files

| File Path | Nature of Change | Purpose |
| :--- | :--- | :--- |
| `src/sahaay/corridor_evidence/__init__.py` | **NEW** | Module package export for Phase D corridor evidence models and service. |
| `src/sahaay/corridor_evidence/schemas.py` | **NEW** | Canonical corridor assessment schema, 7 evidence sections, safety validators. |
| `src/sahaay/corridor_evidence/service.py` | **NEW** | Unified `CorridorEvidenceService` synthesizing multi-modal evidence streams. |
| `src/sahaay/hyderabad_risk/schemas.py` | **MODIFIED** | Added optional rainfall fields (`station_name`, `rain_1h_mm`, etc.) to `RainfallRiskResult`. |
| `src/sahaay/hyderabad_risk/rainfall_engine.py`| **MODIFIED** | Populated `rain_1h_mm`, rolling windows, and `instantaneous_rate_mm_hr` in returns. |
| `src/sahaay/road_network/schemas.py` | **MODIFIED** | Added Phase D corridor evidence properties to `RoadSegmentMapProperties`. |
| `src/sahaay/road_network/store.py` | **MODIFIED** | Integrated corridor evidence into `build_map_feature` with outage fallback. |
| `src/sahaay/api/routes.py` | **MODIFIED** | Added Phase D endpoints: single corridor, batch assessments, and secure evaluate. |
| `tests/test_phase_d_corridor_evidence_integration.py` | **NEW** | 25 focused regression tests for Phase D contracts, safety, and API endpoints. |
| `scripts/audit_phase_d_corridor_evidence.py` | **NEW** | Forensic audit script producing machine-readable verification summary. |
| `reports/phase_d/phase_d_results.json` | **NEW** | Machine-readable audit output verifying all invariants and contracts. |
| `reports/phase_d/PHASE_D_EVIDENCE_MAP_AND_FLOOD_RISK_INTEGRATION_REPORT.md` | **NEW** | Comprehensive Phase D architectural audit and implementation milestone report. |

### 7.2 Focused Test Suite Execution
```powershell
$env:PYTHONPATH="src;."; .venv\Scripts\python -m pytest tests/test_phase_d_corridor_evidence_integration.py -v
```
**Results:** **25 passed, 0 failed in 7.69s (100% pass rate)**

### 7.3 Full Repository Test Suite Execution
```powershell
$env:PYTHONPATH="src;."; .venv\Scripts\python -m pytest -q
```
**Results:** **520 passed, 4 failed in 20.33s**  
The four failed tests are the documented historical Phase 12 baselines:
1. `tests/test_hyderabad_risk_pipeline.py::test_decision_engine_synthesis` (historical alert level threshold assertion)
2. `tests/test_image_quality_gate.py::test_borderline_darkness_rejection` (historical luminance threshold assertion)
3. `tests/test_image_quality_gate.py::test_borderline_whiteout_rejection` (historical luminance threshold assertion)
4. `tests/test_phase5_integration.py::test_decision_engine_modeled_risk_vs_observed_flooding` (historical alert level threshold assertion)

No regressions were introduced across any of the 520 passing tests.

---

## 8. Separation of Technical Boundaries

To maintain rigorous engineering honesty, the system state is categorized into four distinct levels:

### 8.1 Implemented Behavior (Proven in Code)
- Canonical corridor evidence synthesis fusing static road data, live status, IMD telemetry, NWP forecast risk, community submissions, and vision inference.
- Multi-modal contradiction detection flagging citizen vs citizen and camera vs citizen conflicts.
- Strict Pydantic validators preventing forecast rainfall or static susceptibility from claiming road inundation.
- GeoJSON map properties exposing corridor evidence state, explanation, sufficiency, and sparse seed catalog disclosures.
- Graceful map feature degradation during provider outages.
- Topological routing hard-pruning verified impassable segments and rejecting disconnected components.
- Caller-supplied role spoofing denied with HTTP 403.

### 8.2 Tested Behavior (Verified by Automated Tests)
- 25 dedicated Phase D tests covering schema validators, missing telemetry, stale data decay, citizen conflict, camera contradiction, forecast isolation, vision quality gates, official responder verification, GeoJSON properties, router pruning, disconnected components, and API routes.
- Comprehensive forensic audit script (`scripts/audit_phase_d_corridor_evidence.py`) validating all invariants and writing `reports/phase_d/phase_d_results.json`.

### 8.3 Unverified Assumptions (Explicitly Not Implemented / Unproven)
- **Local Flood Prediction is NOT Validated:** Atmospheric forecast rainfall is not a calibrated physical hydrodynamic flood model; water accumulation depends on local storm drain blockages, silt levels, and surface micro-topography.
- **Vision Model Generalization is NOT Proven:** The MobileNetV3 vision model is calibrated against historical test sets, but unverified under extreme night-time lens glare or flood debris.
- **No Production Authorization:** Phase D does not authorize live emergency deployment, public alerts, or automated road closures.

### 8.4 External Blockers (Institutional Dependencies)
- **IMD / TSDPS Live Gateway Access:** Live weather telemetry requires executed data-sharing MOUs with the India Meteorological Department and Telangana State Development Planning Society. Live connections remain blocked.
- **Traffic Police / GHMC Verification:** Official responder road closures require integration with authorized municipal dispatch radios or field responder tablets.

---

## 9. Phase D Acceptance Verdict

**Verdict:** **ACCEPTED**

**Sign-off Rationale:**  
Phase D delivers a coherent, robust, and rigorously tested evidence-to-map integration. Evidence separation is strictly preserved across all sensory modalities, missingness and temporal provenance remain explicit, routing safety invariants hold without synthetic edge creation, and privileged actions are securely disarmed. No unsupported claims of operational readiness or predictive accuracy were introduced.
