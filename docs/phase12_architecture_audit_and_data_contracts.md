# Phase 12 — Architecture Audit and Canonical Data Contracts

**Project:** Sahaay AI — Predict. Prevent. Protect.  
**Phase:** 12  
**Status:** Audit and contract specification  
**Baseline branch:** `main`  
**Baseline commit reviewed:** `0bc467df5e7821ba5dfa6864d3dee6f2601bd497` (Phase 11)  
**Scope:** AI/ML architecture, component readiness, cross-component data contracts, and integration gaps. This phase does not train a new model, activate live feeds, or deploy the system.

---

## 1. Phase 12 outcome

This document establishes a shared contract for the next phases. It distinguishes:

1. **Observed evidence** — a time- and location-specific observation, with source and verification state.
2. **Current road status** — the best available state of a road segment, including uncertainty and freshness.
3. **Forecast risk** — a future-looking estimate tied to a forecast issue time and valid period.
4. **Static susceptibility** — a geographic baseline that does not assert current flooding.
5. **Routing** — a graph-search result that uses road status and risk inputs; it is not itself a flood detector.
6. **Decision/advisory output** — an explainable synthesis of the above, with abstention when evidence is insufficient.

A component must not silently convert one category into another. For example, high rainfall risk is not a confirmed flood observation, and a road with no current report is not a confirmed safe road.

## 2. Repository audit

### 2.1 Components found in the reviewed source

| Component | Reviewed location | What the code currently establishes |
|---|---|---|
| Vision architecture | `src/sahaay/vision/model.py` | MobileNetV3-Small and ResNet-18 construction; two-class classifier head |
| Vision inference | `src/sahaay/vision/inference.py` | Checkpoint selection, image decoding, quality checks, inference scores and warnings |
| API request/response schemas | `src/sahaay/api/schemas.py` | Vision response, rainfall estimate request, road vulnerability request |
| Rainfall baseline | `src/sahaay/hyderabad_risk/rainfall_engine.py` | Deterministic intensity/accumulation rules, confidence adjustments and UNKNOWN for missing primary hourly rainfall |
| Road susceptibility | `src/sahaay/hyderabad_risk/vulnerability_engine.py` | Static weighted proximity heuristic |
| Geospatial/rainfall schemas | `src/sahaay/hyderabad_risk/schemas.py` | Telemetry, feature-vector and risk-result Pydantic models |
| Decision contract | `src/sahaay/decision/contracts.py` | Alert level, hazard nature, decision status, current-evidence status and decision inputs/outputs |
| API routes | `src/sahaay/api/routes.py` | Vision, rainfall/vulnerability calculations, citizen reports, source status and human-review endpoints |
| Model inventory | `docs/phase11_model_inventory.md` | Phase 11 disposition of trained checkpoints, rule engines and not-run experiments |
| ML handover | `docs/phase11_ml_handover_for_team.md` | Advisory semantics and intended integration guardrails |

This is a source-level review of the named files, not a claim that every service has been run end-to-end. The connected GitHub review does not itself execute the test suite.

### 2.2 Confirmed gaps for the requested product

The reviewed source does not establish a complete end-to-end implementation of the following capabilities:

- Authorized, operational IMD forecast/observation ingestion with persistence, retries, source timestamps and feed-health monitoring.
- A verified road-segment status store with expiry/clearance semantics.
- A calibrated, locally validated road-segment flood probability model.
- A forecast-to-road-segment risk projection validated against real Hyderabad flood outcomes.
- A road-network routing service that avoids confirmed impassable segments and incorporates uncertainty.
- A verified hospital/shelter directory with current access/availability information.
- A complete pipeline from photo upload through inference, report verification, road-state update and map event.

Some related primitives exist (risk calculation endpoints, report workflows, review queue, source-status reporting); these should be reused rather than duplicated. API, frontend, map, external feed access and routing implementation remain integration work for the responsible teammates.

### 2.3 Important source-of-truth mismatches

These are Phase 12 blockers to reconcile before a later phase treats the contracts as implemented behavior.

**A. Quality-gate thresholds differ.** The Phase 11 handover documents a minimum image size of 640×480, blur Laplacian variance threshold of 80, and brightness range [35, 230]. The reviewed implementation in `src/sahaay/vision/inference.py` instead rejects dimensions below 64×64, darkness below mean luminance 10, near-white images above mean 248 with standard deviation below 8, and a blur condition below variance 15 when luminance standard deviation exceeds 12. These are not equivalent. The team must choose one versioned policy, add tests, and update code and handover together. Do not silently assume the handover thresholds are active.

**B. Vision abstention is not fully represented in inference output.** The handover specifies flood probability ≥0.65 as flood evidence, ≤0.35 as no current visual evidence, and the open interval (0.35, 0.65) as inconclusive. The reviewed inference code sets `is_ambiguous` when the winning class confidence is below 0.65, but still returns an argmax class and `is_inconclusive: false` for an image that passes the quality gate. Later implementation work must enforce the documented three-way decision contract explicitly.

**C. Older README/model-card claims conflict with later audits.** The README and original model card describe an earlier baseline and perfect internal test results. Phase 11 inventory documents duplicate leakage/source-label confounding and disqualifies V1/V2 for operational use. The Phase 11 inventory and handover, plus reproducible evaluation artifacts, take precedence over historical accuracy claims. The README/model card should be revised in a documentation follow-up so the repository does not imply production readiness.

**D. Rule output is not a learned probability.** Rainfall risk scores and road vulnerability indices are rule-based scores. They must not be presented as empirically calibrated probabilities of a particular road flooding.

---

## 3. Canonical shared metadata

Every event or estimate exchanged between components should carry the following fields where applicable:

| Field | Meaning |
|---|---|
| `schema_version` | Version of the contract, e.g. `1.0` |
| `event_id` | Stable unique identifier for this event/record |
| `source_type` | `citizen`, `field_inspection`, `imd_observation`, `imd_forecast`, `vision_model`, `rules_engine`, or `official_authority` |
| `source_id` | Identifier for the originating report, station, feed, model, or authority record |
| `observed_at_utc` | When a real-world observation was captured; null when not applicable/unknown |
| `issued_at_utc` | When a forecast or advisory was issued; required for forecast records |
| `valid_from_utc`, `valid_to_utc` | Validity interval for forecast/status/estimate records when applicable |
| `received_at_utc` | When Sahaay AI received the record |
| `location` | Latitude/longitude or a stable road-segment/area identifier; coordinate order must be explicit |
| `verification_status` | `UNVERIFIED`, `CORROBORATED`, `FIELD_VERIFIED`, `OFFICIAL`, or `REJECTED` as appropriate |
| `quality_status` | `VALID`, `DEGRADED`, `MISSING`, `STALE`, or `INVALID` |
| `expires_at_utc` | When the record should stop influencing current-state decisions, if applicable |
| `provenance` | Human-readable source/processing lineage, including model/ruleset version where applicable |

Timestamps must be timezone-aware UTC ISO-8601 strings. Unknown values remain null/unknown; do not fabricate timestamps or replace missing rainfall with zero.

## 4. Canonical component contracts

These are logical contract definitions for implementation. Existing Pydantic classes may be adapted, but do not create duplicate models with conflicting meanings.

### 4.1 Image evidence event

Required fields:

- `schema_version`
- `event_id`
- `report_id`
- `captured_at_utc` (nullable if not supplied)
- `received_at_utc`
- `latitude`, `longitude` (nullable; never infer GPS from image pixels)
- `image_reference` (storage reference, not raw image bytes in downstream events)
- `quality_status`: `PASS` | `REJECTED` | `UNKNOWN`
- `quality_reason_codes`
- `model_name`, `model_version`
- `flood_probability` (nullable float in [0,1])
- `vision_status`: `FLOOD_EVIDENCE_DETECTED` | `NO_CURRENT_FLOOD_EVIDENCE` | `INCONCLUSIVE` | `INCONCLUSIVE_DEGRADED_IMAGE`
- `verification_status`: `UNVERIFIED` | `CORROBORATED` | `FIELD_VERIFIED` | `REJECTED`

Decision rule: quality rejection must short-circuit vision inference. Otherwise, with the documented thresholds, probability ≥0.65 yields `FLOOD_EVIDENCE_DETECTED`, probability ≤0.35 yields `NO_CURRENT_FLOOD_EVIDENCE`, and intermediate or unavailable scores yield `INCONCLUSIVE`. Even the negative status does not imply passability.

### 4.2 Weather observation

Required fields:

- `schema_version`, `event_id`, `source_id` (station/feed)
- `source_type = imd_observation` when sourced from IMD
- `observed_at_utc`, `received_at_utc`
- `latitude`, `longitude` (station location)
- `measurement_kind`: `INCREMENTAL_RAINFALL` | `CUMULATIVE_COUNTER` | `ROLLING_ACCUMULATION`
- `rainfall_mm` (nullable non-negative value)
- `interval_start_utc`, `interval_end_utc` and/or `interval_minutes` when applicable
- `quality_status`, `quality_flags`
- `station_distance_km` relative to the road/area being evaluated, if calculated

Do not treat a cumulative counter as incremental rainfall. Do not derive a rolling accumulation across a data gap without an explicit quality flag. Missing/stale/invalid observation data must remain unknown.

### 4.3 Weather forecast

Required fields:

- `schema_version`, `event_id`, `source_id`
- `source_type = imd_forecast`
- `issued_at_utc`, `received_at_utc`
- `valid_from_utc`, `valid_to_utc`
- `geographic_coverage` (station, grid cell, district, polygon or other explicit spatial support)
- `forecast_variable` and `value`/category, with units and accumulation period
- `official_warning_level` when present in the source
- `quality_status`, `source_reference`

A forecast is not an observation. A district-level forecast must not be presented as a precise prediction for an individual road without a separately validated downscaling/risk method.

### 4.4 Road hazard/status record

Required fields:

- `schema_version`, `event_id`, `road_segment_id`
- `status`: `CONFIRMED_FLOODED` | `REPORTED_FLOODED` | `SUSPECTED_HAZARD` | `CLEARED_VERIFIED` | `UNKNOWN`
- `hazard_type` (e.g. standing water, impassable, debris, closure)
- `observed_at_utc`, `received_at_utc`, `expires_at_utc`
- `verification_status`, `source_event_ids`
- `water_depth_cm` (nullable; only when measured/estimated with provenance)
- `confidence` (nullable and not automatically a calibrated probability)
- `status_reason`

Rules: reports and model suggestions must not be silently upgraded to confirmed status. A stale flood report must not be treated as current indefinitely. A road becomes cleared only through an explicit, sufficiently trustworthy clearance observation or authorized source. Otherwise status becomes unknown after expiry.

### 4.5 Road susceptibility / forecast risk estimate

Required fields:

- `schema_version`, `event_id`, `road_segment_id`
- `risk_kind`: `STATIC_SUSCEPTIBILITY` | `FORECAST_CONDITIONAL_RISK`
- `risk_level`: `LOW` | `MODERATE` | `HIGH` | `CRITICAL` | `UNKNOWN`
- `risk_score` (nullable [0,1] heuristic score)
- `flood_probability` (nullable; populated only by a separately validated/calibrated model)
- `forecast_event_id` (required for forecast-conditional risk)
- `valid_from_utc`, `valid_to_utc`
- `method_name`, `method_version`, `reason_codes`, `missing_inputs`
- `confidence` or uncertainty description

Static susceptibility must never be displayed as current flooding. If there is no validated model, describe output as a rule-based scenario/risk category, not a learned probability.

### 4.6 Unified decision/advisory output

Required fields:

- `schema_version`, `decision_id`, `location_id`, `road_segment_id` (when available)
- `decision_status`: `EVALUATED` | `INSUFFICIENT_DATA` | `STALE_DATA` | `INCONCLUSIVE_CONTRADICTORY`
- `current_evidence_status`: `OBSERVED_FLOOD_EVIDENCE` | `ELEVATED_ENVIRONMENTAL_RISK` | `NO_CURRENT_EVIDENCE_AVAILABLE` | `INCONCLUSIVE` | `INSUFFICIENT_OR_STALE_DATA`
- `hazard_nature`: observed hazard, predicted risk, community report, or maintenance notice
- `alert_level`, `confidence`, `explanation`, `reason_codes`
- `evidence_event_ids`, `source_timestamps`, `missing_inputs`, `stale_inputs`
- `ruleset_version`, `created_at_utc`, `expires_at_utc`

The existing enums in `src/sahaay/decision/contracts.py` should be reused or migrated deliberately. Avoid a second competing enum set. Decision output must preserve whether the underlying evidence is observed, forecast, unverified, stale or missing.

### 4.7 Route request and route response

**Request** fields:

- `schema_version`, `request_id`
- `origin` (GPS coordinates and capture time)
- `destination` (coordinates or a verified destination ID)
- `departure_at_utc`
- `travel_mode`
- `route_preference`: `FASTEST` | `RISK_AWARE` | `EMERGENCY`
- `risk_policy_version`

**Response** fields:

- `schema_version`, `request_id`, `generated_at_utc`, `valid_until_utc)
- `routes[]`, each containing ordered `road_segment_ids`, geometry/reference, distance, estimated duration, risk summary, unknown/stale segment count, excluded hazards and explanation
- `route_status`: `ROUTE_FOUND` | `NO_RELIABLE_ROUTE` | `INSUFFICIENT_ROAD_DATA`
- `data_freshness_summary`, `warnings`

A routing engine must not describe a route as guaranteed safe. Confirmed impassable segments should be excluded when the network supports it. Unknown segments must be surfaced and handled according to the risk policy, not silently assigned zero risk. If no sufficiently reliable route is available, return that fact instead of inventing a safe route.

### 4.8 Emergency destination record

Required fields:

- `schema_version`, `destination_id`, `destination_type`: `HOSPITAL` | `OFFICIAL_SHELTER`
- `name`, `location`, `official_source`
- `last_verified_at_utc`, `received_at_utc`
- `operating_status`: `OPEN` | `CLOSED` | `UNKNOWN`
- `capacity_status`: `AVAILABLE` | `FULL` | `UNKNOWN` (where authoritative data exists)
- `access_status`: `ACCESSIBLE_VERIFIED` | `ACCESS_UNCERTAIN` | `INACCESSIBLE_VERIFIED` | `UNKNOWN`
- `contact_reference`, `warnings`

Do not infer that a shelter is open, has capacity, or is reachable merely because its coordinates are known.

---

## 5. Contract invariants

These invariants apply across the system and must have automated tests:

1. Missing rainfall never becomes zero rainfall; absent primary telemetry returns `UNKNOWN`.
2. Forecasts and observations have distinct source types and timestamp semantics.
3. A model score and a verified observation are different evidence types.
4. Vision quality rejection yields `INCONCLUSIVE_DEGRADED_IMAGE` and does not assert flood absence.
5. Vision probability in (0.35, 0.65) yields `INCONCLUSIVE` under the documented policy.
6. `NO_CURRENT_FLOOD_EVIDENCE` never means road safe/passable.
7. Static susceptibility never means current inundation.
8. Every hazard/status has provenance and a freshness/expiry policy.
9. A reported or model-suggested hazard cannot become field-verified without a verification action/source.
10. Unknown road segments are not silently treated as hazard-free during routing.
11. No autonomous road closure, physical barrier activation, evacuation order or emergency dispatch.
12. Risk scores from deterministic rules are not labelled calibrated probabilities.

## 6. Ownership boundaries

| Workstream | Primary owner | Phase 12 deliverable |
|---|---|---|
| Model readiness, semantics and evaluation criteria | AI/ML | Audit findings and model/risk contract review |
| IMD access, ingestion, storage and retries | Backend/integration | Confirm source/API access and map provider payloads to Weather Observation/Forecast contracts |
| API schemas and persistence | Backend/integration | Reuse or migrate Pydantic models to the canonical contracts |
| Road graph, map overlays and route UX | Frontend/backend | Confirm road-segment identifiers and route request/response integration |
| Emergency destination directory | Backend/product/operations | Identify authoritative hospital/shelter sources and freshness owner |
| Cross-component acceptance tests | Shared | Add contract tests for invariants in Section 5 |

## 7. Phase 12 acceptance checklist

- [x] Identify core existing vision, rainfall, vulnerability, decision and API modules.
- [x] Record the Phase 11 baseline commit reviewed.
- [x] Identify the quality-gate and vision-abstention contract mismatches.
- [x] Define canonical contracts for image evidence, weather observations, forecasts, road status, risk estimates, decisions, routes and emergency destinations.
- [x] Document safety invariants and ownership boundaries.
- [ ] Resolve threshold mismatch in implementation and tests (follow-up implementation task).
- [ ] Implement forecast ingestion and routing interfaces (later phases).
- [ ] Run repository test suite after code changes (not performed by this documentation-only audit).

**Phase status:** Architecture audit and contract specification drafted. The phase is complete as a documentation/audit deliverable; implementation gaps remain intentionally assigned to later phases.
