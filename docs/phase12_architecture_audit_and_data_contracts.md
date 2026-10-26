# Sahaay AI — Phase 12: Architecture Audit and Formal Data Contracts

**Repository:** `Mahendrareddy2006/SAHAAY_AI`  
**Starting Commit:** [`0bc467d`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai) on `main`  
**Active Working Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**Document Classification:** Source-Grounded Architecture Audit & Canonical Contract Specification  
**Phase Scope Boundary:** Pure Architecture Audit, Canonical Contract Definitions, and Safety Regression Tests. (Zero new ML model training, zero live IMD integrations, zero routing engine implementations, zero pilot readiness closures).

---

## 1. Executive Summary & Audit Mandate

This document establishes the definitive, source-verified architecture audit and formal data-contract specification for **Sahaay AI: Predict. Prevent. Protect.**

Every finding in this audit is grounded directly in the inspected source code, configuration files, and empirical test results of the repository. Roadmap projections, model aspirations, and unverified headings have been systematically separated from verified code artifacts.

### Authoritative Capability Classification Matrix

| Sub-System Area | Component / Capability | Implementation Status | Source Evidence (Path & Symbols) |
| :--- | :--- | :--- | :--- |
| **1. Photo Intake & Vision** | Image Quality Gating (Blur, Lum, Res) | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/vision/inference.py:L91-136`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py#L91-L136) (`evaluate_image_quality`) |
| **1. Photo Intake & Vision** | Deep Inference Pipeline (MobileNetV3) | `BLOCKED_BY_ENVIRONMENT_OR_DATA` | [`src/sahaay/vision/inference.py:L64-90`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py#L64-L90) (Requires `torch` & `PIL`, not installed in Python 3.14) |
| **1. Photo Intake & Vision** | Calibrated Vision Decision & Abstention | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/vision/policy.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/policy.py) (`evaluate_vision_abstention_boundary`) |
| **2. Road Status & Flood Evidence** | Multi-Evidence Decision Engine | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/decision/contracts.py:L102-376`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/decision/contracts.py#L102-L376) (`evaluate_decision`) |
| **2. Road Status & Flood Evidence** | Contradictory Evidence Arbiter | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/decision/contracts.py:L135-194`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/decision/contracts.py#L135-L194) (`DecisionStatus.INCONCLUSIVE_CONTRADICTORY`) |
| **3. Rainfall Risk & Telemetry** | Deterministic IMD Rainfall Engine | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/hyderabad_risk/rainfall_engine.py:L29-164`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py#L29-L164) (`evaluate_rainfall_risk_engine`) |
| **3. Rainfall Risk & Telemetry** | Non-Silent `UNKNOWN` Missing Data Handling | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/hyderabad_risk/rainfall_engine.py:L62-77`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py#L62-L77) (Returns `category="UNKNOWN"`, `conf=0.10`) |
| **3. Rainfall Risk & Telemetry** | Live IMD Auto-Ingestion & Forecast API | `NOT_IMPLEMENTED` | No automated IMD API caller exists; only static CSVs and manual test fixtures |
| **4. Road Susceptibility** | Multi-Criteria Geospatial Vulnerability | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/hyderabad_risk/vulnerability_engine.py:L64-135`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py#L64-L135) (`evaluate_road_vulnerability_engine`) |
| **4. Road Susceptibility** | Dynamic Hydraulic Runoff Model | `NOT_IMPLEMENTED` | Digital Elevation Models and culvert flow rates are listed as missing data |
| **5. Risk-Aware Routing** | Graph Traversal & Cost Functions | `NOT_IMPLEMENTED` | Zero routing engines, OSMnx graphs, or NetworkX pipelines exist in repository |
| **5. Risk-Aware Routing** | Emergency Destinations (Hospitals/Shelters) | `SPECIFICATION_ONLY` | Defined via [`src/sahaay/routing/contracts.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/contracts.py) (`EmergencyDestination`); database not populated |
| **6. Community Reports & Clearance** | Citizen Report Intake & Privacy Masking | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/reports/service.py:L43-150`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/reports/service.py#L43-L150) (`CitizenReportService`) |
| **6. Community Reports & Clearance** | Human Supervisory Review Queue | `IMPLEMENTED_AND_TESTED` | [`src/sahaay/review/workflow.py:L50-112`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/review/workflow.py#L50-L112) (`ReviewQueueService` with SHA-256 audit hashing) |
| **6. Community Reports & Clearance** | Road Clearance Lifecycle State Machine | `SPECIFICATION_ONLY` | Clearances currently rely on 360-min expiration or supervisor dismissal; no municipal certification workflow |

---

## 2. In-Depth Sub-System Architecture Audits

---

### Area 1: Photo Intake, Image Quality Gating, and Vision Evidence

#### 1.1 Current Implementation Status & Source Evidence
- **Status:** `IMPLEMENTED_AND_TESTED` for algorithmic quality gating and contract parsing; `BLOCKED_BY_ENVIRONMENT_OR_DATA` for deep model inference in the current environment due to missing `PIL` and `torch` packages.
- **Source Module:** [`src/sahaay/vision/inference.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py).
- **Quality Gating Logic:**
  - Blur Variance: 3x3 discrete 2D Laplacian operator convolution over luminance channel (`np.var(lap)`). Threshold: $\ge 15.0$ required on non-uniform scenes.
  - Luminance Bounds: Mean luminance must fall in $[10.0, 248.0]$. Values $< 10.0$ trigger `underexposed/pitch-black`; values $> 248.0$ with $\sigma < 8.0$ trigger `washed-out whiteout`.
  - Spatial Dimensions: Enforces minimum $64 \times 64$ pixels to reject uninformative thumbnails.
- **Handover Discrepancy Flagged:**
  In [`docs/phase11_ml_handover_for_team.md:L38`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/docs/phase11_ml_handover_for_team.md#L38), the module path was cited as `src/sahaay/data_collection_v4/quality.py` with a $640 \times 480$ resolution and $\ge 80.0$ Laplacian variance threshold. In the actual codebase, `quality.py` does not exist in that path; the live implementation is embedded in [`src/sahaay/vision/inference.py:L91`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py#L91) using thresholds of $64 \times 64$ and $15.0$ variance.

#### 1.2 Decision Boundaries & Calibrated Abstention
- **Class Index Mapping:**
  - Index `0` $\to$ `not_flooded` (Negative Class)
  - Index `1` $\to$ `flooded` (Positive Class)
- **Calibrated Abstention Band (Inclusive $[0.35, 0.65]$):**
  - Continuous output $p = P(\text{flooded} \mid \text{image})$.
  - If $p > 0.65$: Calibrated decision is `FLOOD_EVIDENCE_DETECTED` ($\text{confidence} = p$, $\text{is\_ambiguous} = \text{False}$).
  - If $p < 0.35$: Calibrated decision is `NO_CURRENT_FLOOD_EVIDENCE` ($\text{confidence} = 1.0 - p$, $\text{is\_ambiguous} = \text{False}$).
  - If $0.35 \le p \le 0.65$: The model **strictly abstains**; decision is `INCONCLUSIVE` ($\text{confidence} = \max(p, 1-p)$, $\text{is\_ambiguous} = \text{True}$). Specifically, the exact endpoints $0.350$ and $0.650$ abstain.
  - Rejection of Non-Finite & Non-Numeric Inputs: Float `NaN`, positive/negative infinity, and Boolean inputs are explicitly rejected with `ValueError` and `TypeError`.
  - Continuous probabilities reflect laboratory prototype models and are **not** claimed as calibrated for real-world Hyderabad conditions.
- **Inference Integration & Status:**
  - Implemented in [`src/sahaay/vision/policy.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/policy.py) via `evaluate_vision_abstention_boundary` and `map_vision_probabilities_to_decision`.
  - Integrated into [`src/sahaay/vision/inference.py:L236-245`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py#L236-L245) inside `FloodVisionInference.predict`, ensuring probabilities in $[0.35, 0.65]$ produce `predicted_class="inconclusive"` and `is_inconclusive=True`.
  - **Environment Blocker:** Runtime forward-pass verification of `FloodVisionInference.predict` with real weights is blocked because `torch` and `PIL` are not installed in the Python 3.14 environment. The integration logic is unit-tested without loading PyTorch weights.

#### 1.3 Mandatory Safety Invariants
1. **`NO_CURRENT_FLOOD_EVIDENCE` is NOT Safe Passage:** A negative optical prediction indicates solely that standing water is not visible in that specific frame at that timestamp. It does not establish road passability, structural integrity, absence of submerged debris, or upstream safety.
2. **Degraded Imagery Fail-Closed:** Images triggering the quality gate (blurry, pitch-dark, overexposed, thumbnail) must return `predicted_class="inconclusive"` and `is_inconclusive=True`. They must never be defaulted to `not_flooded`.

---

### Area 2: Current Road Status and Observed Flood Evidence

#### 2.1 Current Implementation Status & Source Evidence
- **Status:** `IMPLEMENTED_AND_TESTED`.
- **Source Module:** [`src/sahaay/decision/contracts.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/decision/contracts.py).
- **Core Function:** `evaluate_decision(input_data: DecisionInput) -> DecisionOutput`.
- **Tested Behavior:** 18 tests passing in Phase 10; contract tests in Phase 12.

#### 2.2 Canonical Schemas & Enums
- **`AlertLevel`:** `CLEAR` (0.10), `ADVISORY` (0.20-0.45), `WATCH` (0.70-0.75), `WARNING` (0.85-0.88), `EMERGENCY` (0.95).
- **`HazardNature`:**
  - `OBSERVED_HAZARD`: Verified ground truth from photo or on-site responder inspection.
  - `PREDICTED_RISK`: Anticipated from rainfall telemetry and road vulnerability.
  - `COMMUNITY_REPORT`: Unverified citizen submission awaiting verification.
  - `MAINTENANCE_NOTICE`: Municipal desilting or drainage clearance log.
- **`DecisionStatus`:** `EVALUATED`, `INSUFFICIENT_DATA`, `STALE_DATA`, `INCONCLUSIVE_CONTRADICTORY`.
- **`CurrentFloodEvidenceStatus`:**
  - `OBSERVED_FLOOD_EVIDENCE`: Confirmed standing water on corridor.
  - `ELEVATED_ENVIRONMENTAL_RISK`: Environmental hazard modeled; inundation unproven.
  - `NO_CURRENT_EVIDENCE_AVAILABLE`: No verified observations; **not a declaration of safety**.
  - `INCONCLUSIVE`: Conflicting or ambiguous inputs.
  - `INSUFFICIENT_OR_STALE_DATA`: Primary telemetry missing or expired.

#### 2.3 Contradictory Evidence Arbiter
- **Audit Rule:** If fresh optical surveillance asserts dry pavement (`not_flooded`, confidence $\ge 0.75$, not ambiguous) but a citizen report asserts deep water (`KNEE_DEEP` or `WAIST_DEEP_OR_MORE` within 180 min):
  - `decision_status` $\to$ `DecisionStatus.INCONCLUSIVE_CONTRADICTORY`
  - `current_flood_evidence_status` $\to$ `CurrentFloodEvidenceStatus.INCONCLUSIVE`
  - `alert_level` $\to$ `AlertLevel.ADVISORY`
  - `requires_human_verification` $\to$ `True`
  - `confidence` $\to$ `0.35`
  - The system explicitly avoids blind majority voting and alerts human dispatchers.

---

### Area 3: Rainfall Observations, IMD Forecasts, Missing Data, and Staleness

#### 3.1 Current Implementation Status & Source Evidence
- **Status:** Baseline engine is `IMPLEMENTED_AND_TESTED`; Live IMD feed is `NOT_IMPLEMENTED`.
- **Source Module:** [`src/sahaay/hyderabad_risk/rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py).
- **Core Function:** `evaluate_rainfall_risk_engine(...) -> RainfallRiskResult`.

#### 3.2 IMD Intensity Calibration Thresholds
Calibrated strictly against India Meteorological Department (IMD) Standard Operating Procedures:
- `rain_1h_mm` $\le 7.5\text{ mm/hr}$ $\to$ `LOW` intensity
- $7.5 < \text{rain\_1h\_mm} \le 15.0\text{ mm/hr}$ $\to$ `MEDIUM` intensity
- $15.0 < \text{rain\_1h\_mm} \le 35.0\text{ mm/hr}$ $\to$ `HIGH` intensity
- $\text{rain\_1h\_mm} > 35.0\text{ mm/hr}$ $\to$ `CRITICAL` intensity (Cloudburst trigger $\ge 100.0\text{ mm/hr}$)
- Rolling 3-hour flash surge trigger: $\text{rain\_3h\_mm} \ge 40.0\text{ mm}$ escalates score to $\ge 0.70$ (`HIGH`).
- Rolling 24-hour catchment saturation trigger: $\text{rain\_24h\_mm} \ge 115.5\text{ mm}$ escalates score to $\ge 0.85$ (`CRITICAL`).

#### 3.3 Strict Missing-Data Semantics (Non-Silent Missingness)
- If `rain_1h_mm is None`:
  - `risk_category` $\to$ `"UNKNOWN"`
  - `risk_score` $\to$ `0.0`
  - `confidence` $\to$ `0.10`
  - `reason_codes` $\to$ `["INSUFFICIENT_TELEMETRY_DATA"]`
  - **NON-NEGOTIABLE RULE:** Missing rainfall telemetry must **NEVER** be silently imputed as $0.0\text{ mm}$ or classified as `LOW` risk.
- **Decision Engine Integration:**
  - `DecisionInput.rainfall_risk_category` defaults strictly to `"UNKNOWN"`. If telemetry is omitted, the input automatically triggers `DecisionStatus.INSUFFICIENT_DATA` and `AlertLevel.ADVISORY`.
  - Pydantic validator enforces `rainfall_risk_category in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}`.
  - Provided `DecisionInput.from_rainfall_result` factory method to guarantee that missing telemetry flags and categories are reliably mapped.
- **Documented Downstream Consumer Risk:**
  - In `RainfallRiskResult`, `risk_score` is defined as a non-nullable `float = Field(..., ge=0.0, le=1.0)` to maintain backward API compatibility.
  - **WARNING TO DOWNSTREAM CLIENTS:** Any frontend widget, map color gradient, or external system that binds solely to the numeric `risk_score` field without inspecting `risk_category == "UNKNOWN"` or `confidence == 0.10` risks displaying missing telemetry as "Zero Risk" (green). Downstream consumers must check the category enum first.

#### 3.4 Confidence Discounting Equations
- **Station Distance Decay:** If gauge distance $d > 15.0\text{ km}$:
  $$\text{Penalty}_{\text{dist}} = \min(0.35, (d - 15.0) \times 0.01)$$
- **Data Freshness Decay:** If telemetry age $t > 1.5\text{ hours}$:
  $$\text{Penalty}_{\text{fresh}} = \min(0.40, (t - 1.5) \times 0.08)$$
- Final confidence is bounded in $[0.10, 1.00]$.

---

### Area 4: Static Road Susceptibility versus Active Inundation

#### 4.1 Current Implementation Status & Source Evidence
- **Status:** `IMPLEMENTED_AND_TESTED`.
- **Source Module:** [`src/sahaay/hyderabad_risk/vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py).
- **Core Function:** `evaluate_road_vulnerability_engine(...) -> RoadVulnerabilityResult`.

#### 4.2 Multi-Criteria Proximity Scoring
Weighted static susceptibility index:
$$V = 0.45 \cdot S_{\text{hotspot}} + 0.35 \cdot S_{\text{drain}} + 0.20 \cdot S_{\text{waterbody}}$$
- **Hotspot Subscore ($S_{\text{hotspot}}$):**
  - $\le 250\text{m}$: $1.0 - 0.50 \times (\text{dist} / 250.0)$
  - $250\text{m} - 1000\text{m}$: $0.50 \times (1.0 - (\text{dist} - 250.0) / 750.0)$
  - $> 1000\text{m}$: $0.0$
- **Drainage Network Subscore ($S_{\text{drain}}$):**
  - $\le 100\text{m}$: $1.0 - 0.40 \times (\text{dist} / 100.0)$
  - $100\text{m} - 500\text{m}$: $0.60 \times (1.0 - (\text{dist} - 100.0) / 400.0)$
  - $> 500\text{m}$: $0.0$
- **Waterbody Subscore ($S_{\text{waterbody}}$):**
  - $\le 200\text{m}$: $1.0 - 0.50 \times (\text{dist} / 200.0)$
  - $200\text{m} - 800\text{m}$: $0.50 \times (1.0 - (\text{dist} - 200.0) / 600.0)$
  - $> 800\text{m}$: $0.0$

#### 4.3 Categories & Separation from Inundation
- $V \ge 0.70 \to \text{SEVERE}$; $0.45 \le V < 0.70 \to \text{HIGH}$; $0.20 \le V < 0.45 \to \text{MODERATE}$; $V < 0.20 \to \text{LOW}$.
- **INVARIANT:** High vulnerability is a static environmental characteristic. During dry weather, a corridor with `SEVERE` vulnerability is completely dry and safe for traffic.
- Under heavy rain, high vulnerability amplifies alert level to `WATCH` (`PREDICTED_RISK`), but **never** to `OBSERVED_FLOOD_EVIDENCE`.

---

### Area 5: Risk-Aware Routing and Emergency Destinations

#### 5.1 Current Implementation Status & Source Evidence
- **Status:** `SPECIFICATION_ONLY` / `NOT_IMPLEMENTED`.
- **Grounded Audit Finding:** A search across the repository for routing algorithms (Dijkstra, A*, Contraction Hierarchies), graph models (OSMnx, NetworkX), hospital databases, and shelter registries confirms **zero implementation code**.
- **Formal Integration Contract:** Introduced in [`src/sahaay/routing/contracts.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/contracts.py).

#### 5.2 Canonical Routing Contracts & Schemas
- **`EmergencyDestination`:**
  - `facility_id`: Regex `^(HOSP|SHELTER)-[A-Z0-9\-]{3,25}$`
  - `destination_type`: `HOSPITAL` | `OFFICIAL_SHELTER`
  - `operational_status`: `OPERATIONAL_VERIFIED`, `OPERATIONAL_CAPACITY_CONSTRAINED`, `INUNDATED_ACCESS_RESTRICTED`, `UNVERIFIED`
  - `verified_access_road_status`: `CurrentFloodEvidenceStatus`
  - `emergency_contact_masked`: str
- **`RouteRequest`:**
  - `origin_latitude`, `origin_longitude`, `destination_latitude`, `destination_longitude` (strictly validated within Hyderabad bounding box $[17.0, 17.8]^\circ\text{N}$, $[78.1, 78.8]^\circ\text{E}$)
  - `vehicle_type`: `TWO_WHEELER`, `THREE_WHEELER_AUTO`, `LIGHT_MOTOR_VEHICLE`, `HIGH_CLEARANCE_SUV`, `HEAVY_COMMERCIAL`
  - `avoid_high_susceptibility`: bool
- **`RouteResponse`:**
  - `route_id`: str
  - `total_distance_meters`: float
  - `estimated_duration_seconds`: float
  - `aggregate_risk_score`: float in $[0.0, 1.0]$
  - `has_unmonitored_segments`: bool
  - `unmonitored_segments_count`: int
  - `safety_disclaimer`: Mandatory non-negotiable legal disclaimer.
  - `engine_status`: `"SPECIFICATION_CONTRACT_ONLY_NOT_IMPLEMENTED"`.

#### 5.3 Non-Negotiable Safety Invariants for Routing
1. **Never Claim a Route is Guaranteed Safe:** Pydantic validators in [`src/sahaay/routing/contracts.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/contracts.py) enforce that any payload claiming "guaranteed safe", "100% safe", "completely safe", or "passable with zero risk" fails validation across warnings and segment notices. *(Limitation: Heuristic phrase matching mitigates overt misleading safety declarations but cannot detect every possible linguistically subtle claim of guaranteed safety).*
2. **Cross-Field Unmonitored Segments Consistency:** If a route traverses segments where rainfall or road observations are `UNKNOWN` or stale, `has_unmonitored_segments` is strictly required to be `True`, and `unmonitored_segments_count` must match the segment count.
3. **Cross-Field Emergency / Impassable Risk Consistency:** If any segment on the route has `current_alert_level == EMERGENCY` or `is_passable_for_vehicle == False`, `aggregate_risk_score` cannot be set to 0.0.
4. **Inundated Emergency Destination Warning:** If the target facility has `INUNDATED_ACCESS_RESTRICTED` status or an inundated access road, `warnings` must contain an explicit access restriction warning.
5. **No Autonomous Dispatch:** Routes provided to emergency ambulances or relief vehicles are strictly advisory; human dispatch officers must confirm road passability.

---

### Area 6: Community Reports, Evidence Verification, and Road-Clearance Lifecycle

#### 6.1 Current Implementation Status & Source Evidence
- **Status:** `PARTIALLY_IMPLEMENTED`.
  - Report intake, privacy coarsening, near-duplicate clustering, and corroboration tracking: `IMPLEMENTED_AND_TESTED` in [`src/sahaay/reports/service.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/reports/service.py).
  - Human review queue with cryptographic hashing: `IMPLEMENTED_AND_TESTED` in [`src/sahaay/review/workflow.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/review/workflow.py).
  - Municipal road-clearance recertification: `SPECIFICATION_ONLY`.

#### 6.2 Existing Report Lifecycle
- **Freshness Classification:**
  - `FRESH`: $\le 60\text{ minutes}$ (Full weight)
  - `AGING`: $60 - 180\text{ minutes}$ (Discounted confidence)
  - `STALE`: $180 - 360\text{ minutes}$ (Advisory only)
  - `EXPIRED`: $> 360\text{ minutes}$ (Archived from active routing)
- **Privacy Protections:**
  - Reporter contact information is permanently masked with SHA-256 (`ANON-{hash[:8]}`).
  - Precise GPS coordinates with precision $< 50\text{m}$ are coarsened to 3 decimal places (~$110\text{m}$ resolution) to prevent residential identification.
- **Corroboration & Clustering:**
  - Reports submitted within $100\text{m}$ and $30\text{ minutes}$ are clustered as near-duplicates to prevent spam amplification.
  - $\ge 3$ independent corroborating reports escalate corridor status to `WATCH` (`COMMUNITY_REPORT`).

#### 6.3 Clearance Lifecycle Specification (Future Work)
- **Target State Machine:**
  $$\text{REPORTED\_UNVERIFIED} \longrightarrow \text{VERIFIED\_INUNDATED} \longrightarrow \text{RECEDING\_PENDING\_INSPECTION} \longrightarrow \text{DRAINED\_VERIFIED} \longrightarrow \text{ROAD\_PASSABLE\_CERTIFIED}$$
- **Invariant:** A reported flood hazard cannot be cleared solely by model negative prediction or timer expiration. Clearance requires human on-site responder confirmation or multi-sensor corroboration.

---

## 3. Discrepancy & Gap Analysis

| Item | Handbook / Assumption | Actual Repository State | Architectural Resolution / Policy |
| :--- | :--- | :--- | :--- |
| **Quality Gate Module Path** | Cited as `src/sahaay/data_collection_v4/quality.py` | Embedded inside [`src/sahaay/vision/inference.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/inference.py) | Documented actual path; isolated pure policy in [`src/sahaay/vision/policy.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/vision/policy.py) |
| **Vision Abstention Interval (F-01)** | Mandated inclusive $[0.35, 0.65]$ band | Previously open interval $(0.35, 0.65)$ | Corrected in `policy.py` to strict inclusive interval where $0.350$ and $0.650$ produce `INCONCLUSIVE` |
| **Inference Integration (F-02)** | Handover mandated abstention in inference | Previously `inference.py` assigned argmax class | Integrated `map_vision_probabilities_to_decision` into `predict()`; documented `torch`/`PIL` test blocker |
| **Rainfall UNKNOWN Default (F-03)** | Missing telemetry must mean `UNKNOWN` | `DecisionInput` previously defaulted to `LOW` | Corrected `DecisionInput` default to `UNKNOWN` with field validator; documented downstream client risk |
| **Non-Finite & Bool Inputs (F-04)** | Valid probabilities in $[0.0, 1.0]$ | NaN and Booleans previously bypassed validation | Added explicit rejection for `NaN`, $\pm\infty$, and `bool` in `policy.py` |
| **Routing Consistency (F-05, F-09)** | Safety invariants across routes | `RouteResponse` lacked cross-field consistency checks and allowed non-zero count mismatches | Added cross-field validators; strictly enforce `unmonitored_segments_count == len(unmonitored)` rejecting undercounts and overcounts |
| **Dashboard Missingness (F-08)** | Map visualizer must show uncertainty | Prototype UI mapped null rain on low vulnerability to `CLEAR` | Corrected `index.html` to map missing telemetry to `UNKNOWN` / `INSUFFICIENT_DATA` with slate styling |
| **Deep Vision Test Environment (F-07, F-10)** | Assumed PyTorch & Pillow present | Python 3.14 lacks `torch` and `PIL` | Pure-Python policy tests added; deep inference marked `BLOCKED_BY_ENVIRONMENT`; legacy test assertion updated for inconclusive |
| **Routing Engine** | Assumed active risk-aware routing | Zero routing code exists in repo | Established formal Pydantic contracts in [`src/sahaay/routing/contracts.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/contracts.py) |
| **IMD Feed Ingestion** | Assumed live weather feed | Static CSV and manual parameters only | Formally classified as `NOT_IMPLEMENTED` |

---

## 4. Conclusion & Handover to Testing

The architecture audit confirms that the core safety baselines (IMD rainfall engine, road vulnerability engine, multi-evidence decision engine, and citizen privacy service) are mathematically robust, fully implemented, and strictly fail-closed. Missing capabilities (live IMD feeds, deep routing engines, municipal clearance certification) have been rigorously documented as specification-only, preventing premature or dangerous operational claims.
