# Sahaay AI — Phase B: Topological Graph & Routing Integration Acceptance Report

**Milestone:** Phase B — Topological Graph & Routing Integration  
**Repository:** `Mahendrareddy2006/SAHAAY_AI`  
**Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**Execution Timestamp:** 2026-10-27T19:30:00+05:30  
**Overall Verdict:** **CONDITIONALLY ACCEPTED**  
*(Directed topological road graph built and verified; risk-aware Dijkstra router integrated with Phase 19 safety rules and verified impassable road pruning; 0 regressions on full test suite; metropolitan citywide routing remains constrained by the 22-segment seed catalog; production authorization remains BLOCKED pending server-side cryptographic Identity Provider).*

---

## 1. Executive Summary & Verification Objectives

Phase B builds directly upon the Phase A geospatial baseline to construct a formal, mathematically verified directed road network graph (`RoadGraph`) and integrates it with Sahaay AI's Phase 19 `RiskAwareRoutingService`.

### Core Engineering Invariants Enforced:
1. **No Artificial Topology Fabrication:** The existing 22 seed segments (~25.64 km) are largely disconnected across Hyderabad. The graph builder strictly avoids connecting roads solely because they are geographically proximate; links are formed exclusively when explicit endpoint junction node references match.
2. **Directed Traversal & Edge Provenance:** Bidirectional roads generate explicit forward (`EDGE-<id>-FWD`) and reverse (`EDGE-<id>-REV`) directed edges. One-way roads generate strictly a single forward directed edge.
3. **Strict Safety Pruning:** Verified impassable segments (confirmed flood inundation) are assigned infinite traversal weight and strictly pruned during graph traversal.
4. **Heuristic Risk Weighting:** Verified waterlogged roads incur heavy deterrence penalties (15× base travel time + 1800s delay); corroborated hazard reports and stale observations incur proportional cautionary delays.
5. **Preservation of Uncertainty:** Unmonitored road segments with absent sensor telemetry are traversed with baseline travel times but explicitly surfaced with uncertainty warnings; missing data is **never** converted into a clear or safe road assumption.
6. **No Deceptive Safety Claims:** All routing outcomes enforce non-negotiable safety disclaimers, mark `is_guaranteed_safe=False`, and prohibit forbidden phrasing (`"guaranteed safe"`, `"flood-free route"`).
7. **Production Authorization Blocked:** Caller-supplied role strings in HTTP request bodies remain unauthenticated. Production administrative endpoints are marked **BLOCKED** until server-side cryptographic authentication is approved and integrated.

---

## 2. Files Added and Modified

### Added Implementation Files:
- [`src/sahaay/road_network/graph.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/graph.py):
  Canonical directed graph data structures: `GraphNode`, `DirectedEdge`, `RoadGraph`, `RoadGraphBuilder`, `GraphTopologyMetrics`, and `GraphValidationIssue`. Implements BFS connected component detection, traversal indexes, and topology validation.
- [`src/sahaay/routing/graph_router.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/graph_router.py):
  `TopologicalGraphRouter` integrating `RoadGraph` with `RiskAwareRoutingService`. Executes risk-penalized Dijkstra shortest-path search with hard avoidance of impassable segments and demonstration route labeling.
- [`scripts/audit_phase_b_topological_graph.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/audit_phase_b_topological_graph.py):
  Automated audit script generating machine-readable JSON metrics for graph topology, demonstration routes, licensing, and security status.
- [`reports/phase_b/phase_b_results.json`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase_b/phase_b_results.json):
  Machine-readable audit findings output.
- [`tests/test_phase_b_topological_graph_routing.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase_b_topological_graph_routing.py):
  Automated test suite (13 test cases) covering graph construction, one-way/bidi traversal, disconnected component detection, duplicate edge rejection, Dijkstra detour routing, and REST API endpoints.

### Modified Files (Preserving Working Tree):
- [`src/sahaay/road_network/__init__.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/__init__.py):
  Exported canonical graph entities (`GraphNode`, `DirectedEdge`, `RoadGraph`, `RoadGraphBuilder`, `GraphTopologyMetrics`).
- [`src/sahaay/road_network/store.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/store.py):
  Added `get_road_graph()` method returning directed `RoadGraph` compiled on demand from catalog segments.
- [`src/sahaay/routing/__init__.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/__init__.py):
  Exported `TopologicalGraphRouter`.
- [`src/sahaay/api/routes.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/api/routes.py):
  Added Phase B REST API endpoints:
  - `GET /api/v1/routing/graph/metrics` (GraphTopologyMetrics)
  - `POST /api/v1/routing/demonstration/evaluate` (Demonstration topological routing)

---

## 3. Actual Graph Topology Metrics

Evaluating the default store catalog (22 seed segments, ~25.64 km centerline) against `RoadGraphBuilder` produces the following exact measurements:

| Metric | Measured Value | Topological Significance |
| :--- | :--- | :--- |
| **Total Road Segments Represented** | **22** | Discrete flood vulnerability corridors in Hyderabad |
| **Total Unique Graph Nodes** | **40** | Stable node identifiers (`NODE-<name>`) |
| **Total Directed Edges** | **44** | 22 Forward (`EDGE-*-FWD`) + 22 Reverse (`EDGE-*-REV`) |
| **Forward Edges Count** | **22** | Primary directional links |
| **Reverse Edges Count** | **22** | Reverse directional links for bidirectional segments |
| **One-Way Segments Count** | **0** | All 22 initial seed corridors are bidirectional |
| **Bidirectional Segments Count** | **22** | Fully reversible corridors |
| **Junction Nodes Count** | **3** | `NODE-RETHIBOWLI`, `NODE-SHAIKPET-ENTRY`, `NODE-MALAKPET-E` |
| **Dead-End Nodes Count** | **0** | Bidirectional graph yields symmetric in/out degree |
| **Connected Components Count** | **18** | **18 weakly connected components** (honest representation) |
| **Largest Component Size** | **5 nodes** | Tolichowki–Mehdipatnam cluster (4 segments, 5 nodes) |
| **Fully Connected Graph** | **False** | Citywide connectivity is not fabricated |
| **Topology Validation Errors** | **0** | All coordinate references valid WGS84 within Hyderabad |

### Honest Topological Component Breakdown:
- **Component 1 (5 nodes, 4 segments):**
  - Nodes: `NODE-OU-COLONY`, `NODE-SHAIKPET-ENTRY`, `NODE-RETHIBOWLI`, `NODE-MASAB-TANK`, `NODE-GUDIMALKAPUR`.
  - Segments: `HYD-LOC-002` (Shaikpet Nala Rd), `HYD-LOC-001` (Tolichowki Flyover Underpass), `HYD-LOC-018` (Mehdipatnam Rythu Bazaar Rd), `HYD-SEG-UNMON-01` (Rethibowli to Gudimalkapur Lane).
- **Component 2 (3 nodes, 2 segments):**
  - Nodes: `NODE-AMBERPET-S`, `NODE-MALAKPET-E`, `NODE-CHAITANYAPURI`.
  - Segments: `HYD-LOC-010` (Musarambagh Bridge Causeway), `HYD-LOC-012` (Dilsukhnagar Bus Depot Main Rd).
- **Components 3–18 (16 components, 2 nodes each):**
  - 16 isolated corridors with 2 distinct end nodes each (e.g., Begumpet, Khairatabad, Lakdikapul, Panjagutta, Balanagar, Alwal, etc.).

---

## 4. Demonstration Route Results

Demonstration routing was evaluated on both the seed catalog and a multi-path controlled test graph:

### 1. Connected Seed Pair (`NODE-OU-COLONY` to `NODE-RETHIBOWLI`):
- **Selected Path:** `HYD-LOC-002` → `HYD-LOC-001`
- **Total Distance:** 2,430.0 meters
- **Outcome:** `ADVISORY_TRAVERSABLE_WITH_CAUTION`
- **Safety Flags:** `is_guaranteed_safe = False`, `operational_action_authorized = False`
- **Cautionary Notices:** Contains `"DEMONSTRATION ROUTE ONLY: Path computed over bounded test road graph."` and `"Absence of reported flooding does NOT indicate dry pavement or safe transit."`

### 2. Disconnected Seed Pair (`NODE-OU-COLONY` to `NODE-PATNY-CIRCLE`):
- **Path Found:** None (nodes reside in distinct topological components).
- **Outcome:** `TOPOLOGY_UNSUPPORTED`
- **Distance:** 0.0 meters
- **Integrity Guarantee:** Did not snap or fabricate connections across disjoint corridors.

### 3. Multi-path Tolichowki Test Network (Baseline vs. Flooded Detour):
- **Baseline Direct Route (`NODE-A` → `NODE-C`):**
  - Traverses underpass: `TEST-SEG-1` → `TEST-SEG-2` (900.0 m).
- **Underpass Verified Impassable (`TEST-SEG-2` flooded with 55 cm water):**
  - Router strictly excludes `TEST-SEG-2`: `"Segment TEST-SEG-2 was pruned: Verified impassable flood inundation."`
  - Router automatically diverts traffic via northern bypass: `TEST-SEG-BYPASS-1` → `TEST-SEG-BYPASS-2` → `TEST-SEG-BYPASS-3` (1,700.0 m).
- **All Paths Flooded:**
  - When both underpass and bypass internal link are verified impassable, router returns `ALL_CANDIDATE_ROUTES_IMPASSABLE` with 0 candidate segments recommended.

---

## 5. Data Sources, Ingestion Path & Licensing

| Attribute | Specification |
| :--- | :--- |
| **Primary Seed Source** | Sahaay AI Curated Hyderabad Inundation Vulnerability Corridors |
| **Ingestion Engine** | [`OSMNetworkImporter`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/osm_importer.py) (WGS84 EPSG:4326 GeoJSON feature normalizer) |
| **License Compliance** | Open Database License (ODbL) 1.0 (OpenStreetMap contributors) |
| **Attribution Requirement** | Map symbology and API feature metadata embed mandatory OSM attribution notice: `Data © OpenStreetMap contributors, ODbL 1.0` |
| **Paid Services** | None. Zero third-party paid map or routing APIs were introduced. |
| **Data Download Policy** | Large external bulk downloads were prohibited per project constraints. |
| **Coverage Truthfulness** | Metropolitan coverage is **not claimed**. Current network represents 22 seed segments (~25.64 km) across 18 components. |

---

## 6. Authentication Security Finding & Integration Roadmap

### Current Vulnerability Status: **BLOCKED**
- **Finding:** The map corridor refresh endpoint (`POST /api/v1/map/corridors/refresh`) relies on an unverified role string (`"role": "MUNICIPAL_OFFICER"`) supplied directly within the JSON request body.
- **Security Reality:** Any anonymous HTTP client can send a crafted JSON body claiming municipal or administrator privileges. No server-side cryptographic session or token validation exists in the current environment.
- **Remediation Invariant:** Role-based authorization must not be deemed secure until identity and role claims are cryptographically verified by trusted server-side authentication.

### Documented Secure Integration Architecture (Pending Approval):
1. **RFC 7519 JSON Web Token (JWT) Standard:**
   - Require `Authorization: Bearer <token>` HTTP header on all administrative/state-mutating endpoints.
   - Utilize FastAPI's `Security(HTTPBearer())` dependency to parse the authorization header.
2. **Trusted Identity Provider (IdP):**
   - Integrate an institutional OpenID Connect (OIDC) or OAuth 2.0 provider (e.g., Keycloak, Auth0, municipal SSO, or Supabase Auth).
3. **Cryptographic Signature Verification:**
   - Validate token digital signatures against the IdP’s JSON Web Key Set (`JWKS`) endpoint (RS256/ES256) at runtime.
   - Verify token expiry (`exp`), issuer (`iss`), and audience (`aud`).
4. **Strict Request Schema Sanitization:**
   - Remove `role`, `actor_role`, and `caller_identity` parameters from request body schemas. Role claims must be extracted strictly from verified token claims (`token.claims["realm_access"]["roles"]`).
5. **Approval Blocker:**
   - Production deployment of authentication dependencies requires administrative approval prior to updating `pyproject.toml`. Production administrative actions remain marked **BLOCKED**.

---

## 7. Automated Test Suite Results

### Test Execution Commands & Results:
```powershell
# 1. Phase B Focused Topological Graph & Routing Tests
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_phase_b_topological_graph_routing.py -v
# Result: 13 passed, 0 failed in 13.16s

# 2. Phase A Live Map Foundation Regression Tests
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_phase_a_live_map_foundation.py -v
# Result: 18 passed, 0 failed in 13.18s

# 3. Phase 19 Risk-Aware Routing Contract Tests
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_phase19_risk_aware_routing.py -v
# Result: 15 passed, 0 failed in 1.80s

# 4. Full Repository Test Suite
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest -q
# Result: 461 passed, 4 failed, 6 warnings in 26.74s (465 total tests)
```

### Tracked Historical Baseline Failures (Separately Tracked, 0 New Regressions):
The 4 known historical failures were verified and tracked separately without modification:
1. `tests/test_hyderabad_risk_pipeline.py::test_decision_engine_synthesis`
2. `tests/test_image_quality_gate.py::test_borderline_darkness_rejection`
3. `tests/test_image_quality_gate.py::test_borderline_whiteout_rejection`
4. `tests/test_phase5_integration.py::test_decision_engine_modeled_risk_vs_observed_flooding`

**Zero** regressions were introduced across the entire codebase.

---

## 8. Remaining Blockers to Real-World Routing

| Blocker Item | Technical Limitation | Path to Resolution |
| :--- | :--- | :--- |
| **1. Sparse Road Topology** | Catalog contains only 22 segments (~25.64 km) across 18 disconnected components. | Ingest authorized full OpenStreetMap extract for Greater Hyderabad Municipal Corporation (GHMC) boundary using `OSMNetworkImporter`. |
| **2. Production Authentication** | Endpoints trust caller-supplied JSON roles without cryptographic verification. Marked **BLOCKED**. | Approve and configure server-side OAuth2/OIDC JWT middleware with JWKS verification. |
| **3. Live IoT Telemetry** | Road water depths and passability currently simulate responder snapshots. | Connect physical ultrasonic IoT water level sensors and real-time DRF mobile app webhooks to `RoadStatusService`. |
| **4. Operational Dispatch Gating** | Autonomous emergency dispatch and road closure triggers remain disarmed by safety contracts. | Maintain `operational_action_authorized=False` until human-in-the-loop municipal emergency operations approval is codified. |
