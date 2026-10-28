# Sahaay AI — Phase E: Safe Routing and Emergency Destinations Report

**Milestone:** Phase E (Safe Routing, Emergency Destination Registry, Transparent Suitability Ranking & Human Review Boundaries)  
**Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**Evaluation Date:** October 28, 2026  
**Auditor:** Antigravity Autonomous Systems Agent (Phase E Task Lead)  
**Audit Script:** `scripts/audit_phase_e_routing_and_destinations.py`  
**Machine-Readable Audit Results:** `reports/phase_e/phase_e_results.json`  
**Milestone Acceptance Status:** **ACCEPTED**  

---

## Executive Summary

Phase E extends Sahaay AI's routing and emergency management architecture by implementing **destination-aware safe routing** and an authoritative **emergency destination registry**. This milestone fuses the Phase B topological directed road graph and Phase D corridor-level multi-modal evidence with emergency destination facility records while strictly maintaining all safety invariants, human review boundaries, missing-data contracts, and non-fabrication guarantees.

Prior to Phase E, route assessment operated without destination facility intelligence, and emergency destinations existed only as an offline specification without topological integration, operating status verification, or GeoJSON map rendering. Phase E bridges these subsystems into a unified, transparent decision-support pipeline that:
1. Validates origin and destination endpoints against graph topology, explicitly rejecting missing nodes and disconnected components without fabricating synthetic edges.
2. Hard-prunes segments verified impassable by authorized responders while explaining candidate route selections and exclusions.
3. Decouples geographic proximity from topological route feasibility and facility operational status, ensuring that physically closer facilities in disconnected components or with inundated access bays are never recommended over reachable, operational facilities.
4. Integrates candidate destination assessments into the human-reviewed emergency workflow (`EmergencyWorkflowEngine`), automatically escalating inundated hospital access corridors to `P1_URGENT_VERIFIED` review without triggering autonomous side-effects (`operational_action_authorized=False`).
5. Establishes a software audit hash disclaimer on emergency resolution records explicitly stating that a software SHA-256 hash does not constitute proof of legal signer identity or tamper-proof physical storage.
6. Enforces robust security gates across REST endpoints, denying caller-supplied role tokens and autonomous dispatch requests with HTTP 403 Forbidden.

### Milestone Verification Overview

| Metric / Check Category | Status | Notes |
| :--- | :--- | :--- |
| **Audit Script Verdict** | **ACCEPTED** | Verified via `scripts/audit_phase_e_routing_and_destinations.py` |
| **Reused Components** | **7 Reused (0 Duplicated)** | Phase A, B, C, D, 19, 20, 21 components reused directly |
| **Focused Phase E Test Suite** | **24 Passed / 24 Run (100%)** | `tests/test_phase_e_safe_routing_and_emergency_destinations.py` |
| **Full Repository Regression Suite** | **544 Passed, 4 Tracked Baseline Failures** | Zero regressions; 4 Phase 12 baseline failures preserved |
| **Non-Fabrication Invariant** | **Enforced (Zero Synthetic Edges)** | Disconnected components return `TOPOLOGY_UNSUPPORTED` |
| **Operational Action Status** | **Strictly Disarmed** | `operational_action_authorized=False` across all workflows |
| **Security Gate** | **HTTP 403 Forbidden** | Role spoofing and autonomous dispatch attempts denied |

---

## 1. Inspection and Component Reuse Accounting

In strict compliance with Milestone Requirement 1, Phase E reuses existing components across the repository and introduces zero competing routing engines or duplicate corridor-status models.

| Component / Subsystem | Source Phase | Module Path | Reuse Strategy | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Road Network Store & Catalog** | Phase A | `sahaay.road_network.store` | Reused for seed road segment geometries (22 segments), coordinate bounding boxes, and map features. | Reused Unchanged |
| **Topological Graph & Router** | Phase B | `sahaay.routing.graph_router` | Reused `RoadGraph` and `TopologicalGraphRouter` for Dijkstra shortest path search, connected component detection, and impassable-edge pruning. | Reused Unchanged |
| **Weather & Rainfall Pipeline** | Phase C | `sahaay.hyderabad_risk.weather_pipeline` | Reused IMD AWS observation normalization, freshness QC, and NWP forecast risk context. | Reused Unchanged |
| **Canonical Corridor Evidence** | Phase D | `sahaay.corridor_evidence.service` | Reused `CorridorEvidenceAssessment` and live road condition evidence for corridor passability checks. | Reused Unchanged |
| **Routing Contracts** | Phase 20 | `sahaay.routing.contracts` | Extended `EmergencyDestination`, `VehicleType`, `FacilityOperationalStatus`, and `MANDATORY_SAFETY_DISCLAIMER`. | Reused & Extended |
| **Emergency Workflow Engine** | Phase 19/20 | `sahaay.emergency.workflow` | Connected route and destination assessments to deterministic triage state machine and authorized human review. | Reused & Extended |
| **End-to-End Safety Scenarios** | Phase 21 | `sahaay.phase21` | Reused safety assertion contracts, offline fallbacks, and non-actionability disclaimers. | Reused Unchanged |

---

## 2. Route Feasibility, Disconnected Components & Explanations

The routing query behavior in `sahaay.routing.graph_router.TopologicalGraphRouter` and `sahaay.emergency_destinations.service.DestinationAwareRoutingService` was verified against strict feasibility and explanation requirements:

### 2.1 Endpoint Validation and Component Isolation
- **Missing or Unknown Node Identifiers:** When an origin or destination node identifier is not present in the road graph, the routing engine immediately halts and returns `RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED` with `engine_status="TOPOLOGY_MISSING_NODE_REFERENCE"`. It does not guess an approximate node or fabricate an edge.
- **Disconnected Topological Components:** When origin and destination nodes reside in disjoint graph components (e.g., Tolichowki West Zone vs Musarambagh South Zone, or test nodes `NODE-A` and `NODE-ISOLATED-2`), the engine identifies the topological cut and returns `outcome=RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED` with `engine_status="DISCONNECTED_TOPOLOGICAL_COMPONENTS"`.
- **Zero Synthetic Edge Fabrication:** The system guarantees that no artificial or inferred edges are ever inserted into the graph to "bridge" disconnected components or unsupported locations.

### 2.2 Impassable Segment Pruning and Viable Detours
- **Strict Evidence Rules:** Only road segments with authoritative responder verification (`condition_state=RoadConditionState.VERIFIED_IMPASSABLE`) are hard-pruned from the candidate graph traversal.
- **Detour Navigation:** If an alternate topological path exists around the pruned segment (e.g., Paramount Bypass detour when Tolichowki Flyover Underpass is flooded), the engine navigates the detour, reports `outcome=RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION`, places the flooded road into `excluded_segments`, and appends an auditable exclusion explanation (`exclusion_explanations`).
- **All Paths Blocked:** If all candidate topological paths to the destination contain verified impassable segments, the router returns `outcome=RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE`.

### 2.3 Distance, Edge Provenance & Non-Optimality Disclosures
- **Accurate Metric Traversal:** Route distance (`total_distance_meters`) and duration (`estimated_duration_seconds`) are calculated strictly from graph edge weights and speed limits, never from Euclidean straight-line assumptions.
- **Demonstration Route Labeling:** All routes computed over the bounded seed graph catalog (~22 segments) are explicitly marked with `is_demonstration=True` (or include statutory caution notices in `warnings`), accompanied by the mandatory advisory disclaimer:
  > *"ADVISORY ROUTING ONLY: Sahaay AI does not guarantee safe passage or optimal routing. Urban waterlogging conditions change rapidly during severe monsoon downpours. Autonomous road closures and automated emergency dispatch are strictly prohibited."*
- **No Optimality or Safety Guarantees:** `is_optimality_claimed` and `is_guaranteed_safe` remain strictly `False`. Forbidden safety phrases (e.g., *"guaranteed safe"*, *"100% safe"*, *"safe passage guaranteed"*) are programmatically blocked by schema validators.

---

## 3. Emergency Destination Registry & Data Quality Contracts

Phase E establishes `sahaay.emergency_destinations.registry.EmergencyDestinationRegistry` backed by strict Pydantic schemas in `sahaay.emergency_destinations.schemas.EmergencyDestinationRecord`.

### 3.1 Registry Data Fields and Provenance
Each destination record maintains:
1. **Stable Identifiers & Naming:** Validated identifier (e.g., `HOSP-OSMANIA-01`, `SHELTER-TOLICHOWKI-01`) and sanitized institutional name.
2. **Coordinates & Location Provenance:** Verified geographic coordinates bounded within Hyderabad (`17.0–7.8° N`, `78.1–78.8° E`) with explicit source authority (e.g., `TS_HEALTH_DIRECTORATE_GIS_CATALOG`, `GHMC_DISASTER_MANAGEMENT_CELL`).
3. **Graph Topology Mapping:** Nearest validated `RoadGraph` node ID (`nearest_graph_node_id`) connecting the facility to the topological network.
4. **Operating Status Evidence & Freshness:** 4-tier operational status (`OPERATIONAL_VERIFIED`, `OPERATIONAL_CAPACITY_CONSTRAINED`, `INUNDATED_ACCESS_RESTRICTED`, `UNVERIFIED`) accompanied by audit evidence summaries, verification timestamps, and freshness categories (`FRESH`, `AGING`, `STALE`, `UNKNOWN`).
5. **Verified Service Capabilities:** Capabilities such as `has_emergency_department`, `has_icu_beds`, `has_trauma_care`, `has_backup_power`, and `bed_capacity_total` are populated **only where officially verified**. When unverified, they remain `None` (`UNKNOWN`).
6. **Data Quality & Unknown Field Indicators:** `unknown_fields` and `data_quality_flags` explicitly list missing attributes (e.g., `["operational_status", "bed_capacity_total", "icu_availability"]`), preventing the system from treating missing information as operational confirmation.

### 3.2 Non-Fabrication Boundaries and Synthetic Fixtures
- **No Hallucinated Hospitals or Shelters:** The registry strictly prohibits inventing facilities, capacities, or open status.
- **Synthetic Fixture Disclosure:** Where authoritative live state feeds from municipal hospital boards are not yet connected, baseline demonstration records are explicitly marked with:
  - `is_synthetic_fixture=True`
  - `fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Synthetic record for pipeline verification only. Do NOT use for actual emergency dispatch or evacuation."`
  - Schema validators enforce that setting `is_synthetic_fixture=True` requires a non-empty `fixture_warning`.
- **Prohibition of Existence-Based Operational Inferences:** The system never infers that a facility is open or operational merely because a record exists in the GIS catalog. If `operational_status == UNVERIFIED`, it is categorized as degraded and cannot be claimed operationally suitable.

---

## 4. Destination-Aware Safe Routing & Transparent Ranking

Phase E implements `sahaay.emergency_destinations.service.DestinationAwareRoutingService`, providing transparent multi-criteria evaluation of candidate destinations.

### 4.1 Separation of Proximity from Feasibility and Suitability
A critical safety requirement of Phase E is decoupling geographic proximity from topological route feasibility and facility operational status:
- **Case 1: Disconnected Near vs Connected Far:** A candidate facility physically located 1.5 km away in an isolated graph component (`NODE-ISOLATED-2`) has smaller straight-line distance than a facility 3.5 km away in a connected component (`NODE-C`). The service correctly assigns `DISCONNECTED_TOPOLOGY` and `UNSUITABLE_UNREACHABLE` to the closer facility and ranks the further, connected facility as #1.
- **Case 2: Inundated Access Bay:** A candidate hospital located on a connected road whose grounds or ambulance access bay are flooded (`INUNDATED_ACCESS_RESTRICTED`) is categorized as `RESTRICTED_ACCESS_INUNDATED` and rejected (`is_operationally_suitable=False`), redirecting routing to alternative operational facilities.
- **Case 3: Unverified Operating Status:** A reachable facility whose operational status is `UNVERIFIED` is classified as `DEGRADED_UNVERIFIED_STATUS`. When `require_verified_operational=True` is requested, it is strictly excluded from suitable candidates.

### 4.2 Transparent Candidate Ranking Criteria
Candidate destinations are evaluated and ranked via a documented, deterministic scoring formula:

$$\text{Score} = \text{BaseScore}(\text{Feasibility}, \text{OperationalStatus}) - \text{DistancePenalty} - \text{RiskPenalty}$$

1. **Topological Connectivity:** Connected & traversable (Base 1.0); blocked by floodwater (Base 0.10); disconnected component (Base 0.0); unsupported location (Base 0.0).
2. **Operational Status:** `OPERATIONAL_VERIFIED` (1.00); `OPERATIONAL_CAPACITY_CONSTRAINED` (0.80); `UNVERIFIED` (0.40); `INUNDATED_ACCESS_RESTRICTED` (0.05).
3. **Distance & Risk Penalty:** Penalties scale proportionally with risk-penalized Dijkstra travel distance along the topological graph.
4. **Rationale and Explanations:** Every candidate evaluation outputs an explicit `selection_or_rejection_explanation` detailing the exact reasons for its rank.

---

## 5. Emergency Workflow Integration & Human Review Boundaries

Phase E connects destination-aware routing assessments to the existing `EmergencyWorkflowEngine` (`sahaay.emergency.workflow`) without introducing autonomous operational side-effects.

### 5.1 Hospital Access Inundation & Deterministic Triage Escalation
- When an emergency assessment input contains a route assessment indicating that an emergency facility access corridor is cut or the facility itself is `INUNDATED_ACCESS_RESTRICTED`, the engine automatically:
  1. Escalates triage priority to **`EmergencyPriority.P1_URGENT_VERIFIED`**.
  2. Sets workflow state to **`EmergencyState.NEEDS_HUMAN_REVIEW`**.
  3. Appends priority reason code `EMERGENCY_HOSPITAL_ACCESS_INUNDATED_AND_RESTRICTED`.

### 5.2 Mandatory Human Review and Action Disarming
- **Human Authorization Required:** Resolution of emergency states requires an explicit review by an `AuthorizedReviewerRole` (e.g., `GHMC_DRF_SUPERVISOR`, `TRAFFIC_POLICE_DUTY_OFFICER`) with a documented operational justification (minimum 10 characters). Automated resolution is prohibited.
- **Autonomous Actions Disarmed:** Across all evaluation paths, `operational_action_authorized` and `external_side_effects_triggered` remain strictly `False`. Sahaay AI does not independently dispatch responders, contact emergency numbers (112/100/108), close roads, or issue public alerts.

### 5.3 Cryptographic Audit Hash Disclaimer
To maintain legal and technical honesty regarding software audit trails, `EmergencyResolutionRecord` incorporates a mandatory audit disclaimer:
```python
audit_disclaimer: str = (
    "AUDIT DISCLAIMER: Software SHA-256 hash records state snapshot only; "
    "does not prove legal identity or tamper-proof storage."
)
```
The system explicitly recognizes that an in-memory or application-computed SHA-256 hash does not constitute digital signature proof of physical signer identity or hardware-tamper-proof storage.

---

## 6. REST API and Map GeoJSON Integration

Phase E exposes versioned, validated endpoints under `/api/v1` in `sahaay.api.routes`:

| HTTP Method | Route | Response Model | Description & Security Controls |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/emergency-destinations/` | `List[EmergencyDestinationRecord]` | Returns registered destinations with filtering by type, zone, operational status, and connectivity. |
| `GET` | `/api/v1/emergency-destinations/{facility_id}` | `EmergencyDestinationRecord` | Retrieves complete audit profile for a single facility; returns 404 for unmapped IDs. |
| `POST` | `/api/v1/emergency-destinations/assess-suitability` | `DestinationSuitabilityResponse` | Ranks candidate destinations from specified origin. Gated: role spoofing denied with 403. |
| `GET` | `/api/v1/map/emergency-destinations` | `GeoJSON FeatureCollection` | Returns Point features for all registered facilities with operational badges and fixture disclosures. |
| `POST` | `/api/v1/routing/safe-route` | `RiskAwareRouteAssessment` | Executes risk-aware topological routing with impassable pruning. Gated: role spoofing denied with 403. |
| `GET` | `/api/v1/map/route-overlay` | `GeoJSON FeatureCollection` | Returns LineString features for computed routes with blue (recommended) and red (pruned impassable) symbology. |

### 6.1 Security Gating and Denial of Role Spoofing
Caller-supplied role tokens (e.g., `caller_role="ROOT_DISPATCHER"`, `caller_role="ADMIN_OVERRIDE"`) or flags requesting privileged dispatch (`request_emergency_dispatch=True`) are strictly treated as unauthenticated inputs and rejected with **HTTP 403 Forbidden**:
```json
{
  "detail": "Client-supplied role tokens and autonomous dispatch requests are strictly rejected."
}
```

---

## 7. Forensic Audit & Test Execution Results

### 7.1 Focused Phase E Test Suite (`tests/test_phase_e_safe_routing_and_emergency_destinations.py`)

A comprehensive suite of 24 focused tests was authored and executed. All 24 tests passed (100% pass rate):

```
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_destination_schema_forbidden_safety_phrases PASSED [  4%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_unverified_operational_status_populates_unknown_fields PASSED [  8%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_synthetic_fixture_disclosure_required PASSED [ 12%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_destination_registry_lookup_and_filtering PASSED [ 16%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_destination_registry_geojson_export PASSED [ 20%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_proximity_separated_from_topological_feasibility PASSED [ 25%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_facility_with_unknown_status_not_operationally_suitable PASSED [ 29%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_inundated_facility_access_bay_rejected PASSED [ 33%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_unknown_origin_or_destination_node_unsupported PASSED [ 37%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_disconnected_graph_components_unsupported PASSED [ 41%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_verified_impassable_segment_pruning_with_viable_detour PASSED [ 45%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_all_paths_impassable_unsupported PASSED [ 50%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_demonstration_route_label_and_non_optimality PASSED [ 54%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_blocked_hospital_access_triggers_p1_urgent_review PASSED [ 58%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_emergency_resolution_requires_authorized_role_and_justification PASSED [ 62%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_audit_hash_disclaimer_present PASSED [ 66%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_autonomous_action_disarmed_across_workflow PASSED [ 70%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_list_emergency_destinations PASSED [ 75%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_get_single_emergency_destination PASSED [ 79%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_assess_destination_suitability PASSED [ 83%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_map_emergency_destinations_geojson PASSED [ 87%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_safe_route_evaluation PASSED [ 91%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_map_route_overlay_geojson PASSED [ 95%]
tests/test_phase_e_safe_routing_and_emergency_destinations.py::test_api_security_role_spoofing_denied PASSED [100%]

======================== 24 passed, 1 warning in 7.75s ========================
```

### 7.2 Full Repository Regression Test Suite
Execution of the complete repository test suite (`pytest -q`) confirmed **zero regressions**:
- **Passed:** 544 tests passed.
- **Tracked Baseline Failures:** Exactly 4 historical baseline failures from Phase 12 remained visible and unchanged:
  1. `tests/test_hyderabad_risk_pipeline.py::test_decision_engine_synthesis`
  2. `tests/test_image_quality_gate.py::test_borderline_darkness_rejection`
  3. `tests/test_image_quality_gate.py::test_borderline_whiteout_rejection`
  4. `tests/test_phase5_integration.py::test_decision_engine_modeled_risk_vs_observed_flooding`

### 7.3 Forensic Audit Script Output (`reports/phase_e/phase_e_results.json`)
The forensic audit script (`scripts/audit_phase_e_routing_and_destinations.py`) completed with verdict **`ACCEPTED`**. All check groups evaluated to `true`:
- `all_route_feasibility_checks_satisfied`: `true`
- `all_emergency_destination_registry_checks_satisfied`: `true`
- `all_destination_aware_routing_checks_satisfied`: `true`
- `all_workflow_and_safety_checks_satisfied`: `true`
- `all_api_and_security_checks_satisfied`: `true`

---

## 8. Exact Files Changed and Created

### 8.1 Newly Created Files
1. `src/sahaay/emergency_destinations/__init__.py`: Package export initialization.
2. `src/sahaay/emergency_destinations/schemas.py`: Data contracts for destination records, feasibility/suitability tiers, ranking criteria, and safety validators.
3. `src/sahaay/emergency_destinations/registry.py`: Destination registry managing canonical facilities, querying, filtering, and GeoJSON export.
4. `src/sahaay/emergency_destinations/service.py`: Destination-aware routing service evaluating proximity vs feasibility, ranking candidates, and bridging to emergency triage.
5. `tests/test_phase_e_safe_routing_and_emergency_destinations.py`: 24 focused verification tests.
6. `scripts/audit_phase_e_routing_and_destinations.py`: Standalone forensic audit script.
7. `reports/phase_e/phase_e_results.json`: Machine-readable audit output.
8. `reports/phase_e/PHASE_E_SAFE_ROUTING_AND_EMERGENCY_DESTINATIONS_REPORT.md`: This comprehensive implementation report.

### 8.2 Modified Files
1. `src/sahaay/emergency/schemas.py`: Added `audit_disclaimer` field to `EmergencyResolutionRecord` disclosing SHA-256 software hash limitations.
2. `src/sahaay/api/routes.py`: Added 6 REST endpoints for destination lookup, suitability evaluation, safe routing, and GeoJSON map overlays, with strict HTTP 403 role-spoofing security gates.

---

## 9. Limitations, Assumptions, and Institutional Blockers

To maintain strict operational honesty, Phase E explicitly states the current boundaries and external blockers preventing live deployment:

1. **Sparse Seed Road Graph Catalog (~22 Segments):** The active road graph catalog comprises only ~22 seed segments primarily focused on Tolichowki, Shaikpet, Khairatabad, and Musarambagh. Citywide routing across Greater Hyderabad is topologically unsupported.
2. **Synthetic Demonstration Destination Fixtures:** In the absence of live API feeds from the Telangana Health Directorate or GHMC Disaster Management Cell, facilities in the registry are synthetic demonstration fixtures (`is_synthetic_fixture=True`). They must NOT be used for real-life navigation or emergency evacuation.
3. **Absence of Real-Time Hospital Bed Telemetry:** Live bed occupancy, ICU capacity, and power status are currently unavailable via automated institutional APIs and remain `None` (`UNKNOWN`).
4. **Offline Advisory Routing Only:** The system cannot guarantee safe passage, bed admission, or open transit. Physical field confirmation by authorized emergency personnel is mandatory.
5. **No Cryptographic Proof of Signer Identity:** Application-layer SHA-256 hashes record state transitions in memory; they do not constitute legal digital signatures or hardware-secured audit storage.

---

## 10. Milestone Acceptance Recommendation

Phase E satisfies all requirements established in the milestone objective:
- Fully reuses Phase A, B, C, D, and emergency contracts without competing engines.
- Prohibits synthetic edge fabrication, returning explicit unsupported outcomes for disconnected components.
- Decouples geographic proximity from topological route feasibility and facility operational status.
- Integrates with the human-reviewed emergency triage workflow with disarmed autonomous actions.
- Gated API endpoints deny caller role spoofing and privileged dispatch with HTTP 403.
- All 24 focused tests pass; zero regressions across the 544 passing repository tests; 4 baseline failures preserved.

**Verdict: ACCEPTED**
