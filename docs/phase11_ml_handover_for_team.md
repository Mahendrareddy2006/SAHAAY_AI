# Sahaay AI — Phase 11: Machine Learning Integration Handover for Teammates

## 1. Handover Overview & Scope Boundaries

**To:** Backend, API, Frontend, and Systems Integration Engineers  
**From:** AI/ML Engineering Lead  
**Subject:** Scientific Model Inventory, Output Semantics, Confidence Bounds, and Integration Cautions  
**Phase Commit:** [`e1ada07`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai)  

This handover document defines the operational contracts, statistical interpretations, missing-data behaviors, and non-negotiable safety guardrails for all AI/ML models and algorithmic engines ready for advisory integration into the Sahaay AI platform.

> [!CAUTION]
> ### Critical Operational Mandates
> 1. **Advisory Decision-Support Only:** No model, score, or engine output may autonomously trigger road closures, physical barrier drops, or 108/112 emergency dispatch. Every operational action requires human supervisor authorization.
> 2. **`NO_CURRENT_FLOOD_EVIDENCE` Does NOT Mean Road is Safe:** A vision model reporting non-flooded pavement merely indicates absence of visible standing water in that specific camera frame at that moment. The road may still have unseen potholes, debris, electrical hazards, or upstream flooding.
> 3. **Environmental Susceptibility is NOT Current Inundation:** A corridor with `SEVERE` or `HIGH` road vulnerability is completely safe and dry during non-monsoon weather.
> 4. **High Rainfall Risk is NOT a Verified Flood Observation:** High rainfall risk indicates severe atmospheric precipitation intensity, not standing water depth on the pavement.
> 5. **Missing Telemetry is `UNKNOWN`, NEVER `LOW`:** If rainfall telemetry is missing or stale, it must be surfaced as `UNKNOWN` (confidence $0.10$). It must **never** be silently imputed as $0.0\text{ mm}$ or low risk.

---

## 2. Component Integration Specifications

The table below outlines the four components approved for operational advisory integration:

```
Approved Advisory Integration Architecture:
├── Pre-Inference: Image Quality Gate (Mandatory Pre-Filter)
├── Vision Model: MobileNetV3-Small Monsoon (Shadow Advisory with Human Review)
├── Hydrological Engine: Rainfall Risk Baseline Engine (IMD Intensity & Multi-Window Risk)
└── Geospatial Engine: Road Vulnerability Engine (Static Physical Susceptibility Baseline)
```

---

### 2.1 Component 1: `image_quality_gate` (Pre-Inference Quality Filter)

- **Module Path:** [`src/sahaay/data_collection_v4/quality.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/quality.py)
- **Primary Task:** Deterministic pre-inference filter to reject degraded, blurry, or uninformative camera frames before invoking deep vision networks.
- **Expected Inputs:** Native RGB image frame (`PIL.Image` or numpy array).
- **Output Schema:**
  ```python
  class ImageQualityResult:
      passed: bool                # True if image meets quality standards for inference
      reason: Optional[str]       # None if passed; else "BLURRY", "UNDEREXPOSED", "OVEREXPOSED", "LOW_RESOLUTION"
      laplacian_variance: float   # Sharpness score (threshold >= 80.0)
      mean_brightness: float      # Brightness score (valid range [35.0, 230.0])
      dimensions: Tuple[int, int] # Native (width, height) (minimum 640x480)
  ```
- **Output Interpretation & Action:**
  - If `passed == True`: Forward frame to `mobilenet_v3_small_v3_monsoon`.
  - If `passed == False`: **Do NOT run vision inference.** Surface output as `INCONCLUSIVE_DEGRADED_IMAGE` with the specific diagnostic code (`BLURRY`, `UNDEREXPOSED`, `OVEREXPOSED`, `LOW_RESOLUTION`).
- **Known Failure Modes:** Extreme rain squalls that coat the camera lens will trigger `BLURRY` rejection. This is intended behavior to prevent confident false classifications.
- **Readiness Status:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**.

---

### 2.2 Component 2: `mobilenet_v3_small_v3_monsoon` (Advisory Vision Model)

- **Checkpoint Location:** [`models/vision/v3/model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt)
- **Model Architecture:** MobileNetV3-Small (1.52 million parameters; 18.49 MB).
- **Primary Task:** Binary flood evidence classification on street-level imagery under adverse weather conditions.
- **Expected Inputs:** RGB image frame pre-filtered by `image_quality_gate`, resized to $224 \times 224 \times 3$, and normalized with ImageNet statistics.
- **Output Interpretation:**
  ```python
  raw_prob: float                 # Continuous flood probability in [0.0, 1.0]
  calibrated_decision: str        # "FLOOD_EVIDENCE_DETECTED" | "NO_CURRENT_FLOOD_EVIDENCE" | "INCONCLUSIVE"
  confidence: float               # max(raw_prob, 1.0 - raw_prob)
  ```
- **Ambiguity & Abstention Policy:**
  - **`FLOOD_EVIDENCE_DETECTED`:** Assigned **ONLY IF** $\text{raw\_prob} \ge 0.65$.
  - **`NO_CURRENT_FLOOD_EVIDENCE`:** Assigned **ONLY IF** $\text{raw\_prob} \le 0.35$.
  - **`INCONCLUSIVE`:** If raw probability falls in the ambiguity band $(0.35, 0.65)$, the model strictly abstains. **Do not force a binary classification.**
- **Known Domain Limitations:**
  - Dataset exhibits source-label confounding (Clemson floods vs Virenbr11 negatives).
  - Model must be run in **shadow/advisory mode** alongside a human reviewer.
- **Readiness Status:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**.

---

### 2.3 Component 3: `rainfall_risk_engine` (Deterministic Rainfall Engine)

- **Module Path:** [`src/sahaay/hyderabad_risk/rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py)
- **Primary Task:** Deterministic evaluation of precipitation intensity, flash surge, and catchment saturation risk.
- **Expected Inputs:**
  - `rain_1h_mm`: float or `None` (1-hour rainfall accumulation)
  - `rain_3h_mm`: float or `None` (Rolling 3-hour accumulation)
  - `rain_6h_mm`: float or `None` (Rolling 6-hour accumulation)
  - `rain_24h_mm`: float or `None` (Rolling 24-hour accumulation)
  - `station_dist_km`: float (Distance from corridor to rain gauge)
  - `data_freshness_hours`: float (Time elapsed since observation)
- **Output Interpretation:**
  ```python
  category: str                   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN"
  rainfall_risk_score: float      # [0.0, 1.0]
  confidence: float               # [0.10, 1.0]
  escalation_reason: Optional[str]# e.g., "3h_surge_warning", "24h_catchment_saturation"
  ```
- **Missing & Stale Data Behavior (STRICT):**
  - If `rain_1h_mm is None`: Returns `category="UNKNOWN"`, `confidence=0.10`, `rainfall_risk_score=0.0`.
  - **NEVER convert missing telemetry to `0.0 mm`.**
  - If `data_freshness_hours > 1.5`: Confidence decays by $-0.08/\text{hr}$.
  - If `station_dist_km > 15.0`: Confidence decays by $-0.01/\text{km}$.
- **Multi-Window Escalations:**
  - If $r_3 \ge 40.0\text{ mm}$, category is upgraded to at least `HIGH` (score $\ge 0.70$).
  - If $r_{24} \ge 115.5\text{ mm}$, category is upgraded to `CRITICAL` (score $\ge 0.85$).
- **Readiness Status:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**.

---

### 2.4 Component 4: `road_vulnerability_engine` (Static Geospatial Vulnerability)

- **Module Path:** [`src/sahaay/hyderabad_risk/vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py)
- **Primary Task:** Compute static physical susceptibility score based on proximity to drainage nalas, water bodies, and historical hotspots.
- **Expected Inputs:**
  - `dist_to_flood_hotspot_m`: float (Distance to chronic hotspot)
  - `dist_to_nearest_drain_m`: float (Distance to open nala canal)
  - `dist_to_nearest_waterbody_m`: float (Distance to lake/tank)
- **Output Interpretation:**
  ```python
  vulnerability_index: float      # [0.0, 1.0]
  vulnerability_category: str     # "LOW" (<0.20) | "MODERATE" (0.20-0.45) | "HIGH" (0.45-0.70) | "SEVERE" (>=0.70)
  subscores: Dict[str, float]     # {"hotspot": sh, "drain": sd, "waterbody": sw}
  ```
- **Integration Caution:**
  - This index is a **static geographic baseline**, NOT an active flood prediction.
  - A corridor marked `HIGH` (e.g. Tolichowki Underpass) indicates that *if* severe rain occurs, it is vulnerable to waterlogging due to canal overflow. In dry weather, it is completely safe.
- **Readiness Status:** **`RULE_BASELINE_ONLY`**.

---

## 3. Disqualified & Blocked Components (DO NOT INTEGRATE)

For legal, safety, and scientific reasons, the following components are **DISQUALIFIED OR NOT_RUN** and must **NOT** be integrated into production feeds:

1. **`mobilenet_v3_small_v1` & `mobilenet_v3_small_v2`:**
   - **Status:** `NOT_READY_INSUFFICIENT_DATA`.
   - **Reason:** V1 has severe duplicate leakage; V2 collapses on unseen roads (94% false positive rate on dry asphalt).
2. **`vision_v4_production_deep_model`:**
   - **Status:** `NOT_RUN`.
   - **Reason:** Blocked by Vision V4 Readiness Gate due to source-label confounding ($V=1.0$).
3. **`supervised_flood_occurrence_prediction`:**
   - **Status:** `NOT_RUN`.
   - **Reason:** Zero timestamped flood outcome observations exist. Cannot be trained without 100% spatial target leakage.
4. **`short_term_hourly_rainfall_forecasting`:**
   - **Status:** `NOT_RUN`.
   - **Reason:** Telemetry data exhibits $>90\%$ transmission gaps and $50.82\%$ cumulative bucket counter confusion.

---

## 4. Teammate Integration Checklist

When integrating the approved components into API response schemas or frontend cards:

- [ ] Wrap all vision inferences with `image_quality_gate` first.
- [ ] Enforce the $[0.35, 0.65]$ ambiguity abstention band on vision probabilities.
- [ ] Surface `confidence` alongside all rainfall risk categories.
- [ ] Display `UNKNOWN` whenever rainfall observations are missing; do not display `LOW`.
- [ ] Clearly label road vulnerability as **"Static Physical Susceptibility"**, not "Current Waterlogging".
- [ ] Label vision alerts as **"Advisory AI Signal — Requires Human Verification"**.
- [ ] Ensure the frontend UI does not provide autonomous closure/dispatch buttons that bypass human review.
