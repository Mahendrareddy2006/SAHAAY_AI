# Sahaay AI — Phase 11: Definitive Model and Component Inventory

## 1. Executive Summary

This inventory establishes the authoritative classification, training provenance, evaluation evidence, and operational readiness for all thirteen (13) AI/ML models, deterministic engines, heuristic scoring algorithms, diagnostic baselines, and blocked experiments in **Sahaay AI**.

### Core Governance Directives:
- **No False Labels:** A deterministic rules-based calculation must never be represented as a machine learning model.
- **No False Detectors:** A non-semantic metadata classifier is a diagnostic tool to expose dataset bias, not a flood detector.
- **Distinction Between Provenance Types:** Components are strictly separated into empirical machine learning, deterministic rule engines, heuristic multi-criteria scores, quality gates, and exploratory analytics.

---

## 2. Taxonomy Overview

Every component in the repository is assigned to exactly one of seven rigorous categories:

```
Sahaay AI Component Taxonomy:
├── 1. Trained ML Model (mobilenet_v3_small_v1, mobilenet_v3_small_v2, mobilenet_v3_small_v3_clean, mobilenet_v3_small_v3_monsoon)
├── 2. Deterministic Rule-Based Engine (rainfall_risk_engine, image_quality_gate)
├── 3. Heuristic Scoring System (road_vulnerability_engine)
├── 4. Data Validation or Quality Gate (image_quality_gate)
├── 5. Experimental Diagnostic Model (metadata_shortcut_classifier_rf, file_size_decision_stump)
├── 6. Unsupervised Exploratory Analysis (corridor_susceptibility_analysis, telemetry_continuity_diagnostics)
└── 7. Blocked or Not-Run Experiment (vision_v4_production_deep_model, supervised_flood_occurrence_prediction, short_term_hourly_rainfall_forecasting)
```

---

## 3. Detailed Component Inventory

### 3.1 Trained Machine Learning Models

#### Component 1: `mobilenet_v3_small_v1` (Vision Baseline V1)
- **Intended Task:** Binary flood detection from street-level imagery.
- **Input Features & Shapes:** RGB image tensor ($224 \times 224 \times 3$), normalized using ImageNet mean and standard deviation.
- **Output Semantics:** Continuous probability score $p \in [0.0, 1.0]$ of inundation (decision threshold $\tau = 0.50$).
- **Training Dataset & Provenance:** Manifest V1 (2,246 images scraped from web sources under the roham1 flood dataset).
- **Checkpoint Location:** [`models/vision/best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt) (18.49 MB, MD5: `82b57acf92942266b4a6a26713515ee4`).
- **Training & Evaluation Status:** Trained; evaluation fundamentally flawed.
- **Valid Evaluation Evidence:** Historical report claimed $100.0\%$ test accuracy, but subsequent audits proved the result was contaminated by exact duplicate leakage between train and test splits, and non-flood images consisted of arbitrary non-road objects (e.g. indoor rooms, portraits, cats).
- **Known Domain Limitations:** Zero generalization to real-world road corridors; memorized background pixel artifacts.
- **Current Readiness Verdict:** **`NOT_READY_INSUFFICIENT_DATA`** (Disqualified from deployment).
- **Advisory Integration Suitability:** **No**.

---

#### Component 2: `mobilenet_v3_small_v2` (Vision Model V2)
- **Intended Task:** Binary flood detection on a deduplicated clean split.
- **Input Features & Shapes:** RGB image tensor ($224 \times 224 \times 3$).
- **Output Semantics:** Continuous probability score $p \in [0.0, 1.0]$ of inundation ($\tau = 0.50$).
- **Training Dataset & Provenance:** Manifest V2 (2,246 images; strict deduplication via 64-bit perceptual hashing).
- **Checkpoint Location:** [`models/vision/v2/model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt) (18.49 MB, MD5: `88e117abbc123bd6299e22c6374bd8c7`).
- **Training & Evaluation Status:** Trained; evaluated and disqualified on external road benchmarks.
- **Valid Evaluation Evidence:** While achieving $100.0\%$ on its own internal test set, it **completely collapsed to 53.15% accuracy on Test V3**. On plain dry roads, it exhibited a **94.0% False Positive Rate** (misclassifying 47 of 50 dry asphalt images as flooded). Calibration error was catastrophic (Test $\text{ECE} = 0.4526$, Brier score $= 0.4485$).
- **Known Domain Limitations:** Learned a 100% dimensional shortcut present in the roham1 source: all non-flood images were low-resolution $224 \times 224$ thumbnails, while all flood images were high-resolution $>800\text{px}$ photos.
- **Current Readiness Verdict:** **`NOT_READY_INSUFFICIENT_DATA`** (Disqualified from deployment).
- **Advisory Integration Suitability:** **No**.

---

#### Component 3: `mobilenet_v3_small_v3_clean` (Vision Model V3 Clean)
- **Intended Task:** Binary flood detection on balanced road imagery with wet pothole hard negatives.
- **Input Features & Shapes:** RGB image tensor ($224 \times 224 \times 3$).
- **Output Semantics:** Continuous probability score $p \in [0.0, 1.0]$ ($\tau = 0.50$).
- **Training Dataset & Provenance:** Manifest V3 (1,478 images: 739 Clemson road floods, 374 Virenbr11 plain dry roads, 365 Virenbr11 wet potholes/puddles).
- **Checkpoint Location:** [`models/vision/v3/model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt) (18.49 MB, MD5: `b553eee151c66f96b809204a638fd30e`).
- **Training & Evaluation Status:** Trained; validated as a solid research baseline.
- **Valid Evaluation Evidence:** On Test V3 ($N=222$), achieved **97.30% accuracy** and **97.30% macro-F1** (FPR $= 3.6\%$, FNR $= 1.8\%$). On wet potholes ($N=61$), achieved $98.36\%$ accuracy (only 1 false positive). However, under synthetic rain mist blur, its accuracy degraded to $93.24\%$ with a False Negative Rate of $13.51\%$.
- **Known Domain Limitations:** Susceptible to severe precipitation degradation; underlying dataset remains subject to source-label confounding (Clemson vs Virenbr11).
- **Current Readiness Verdict:** **`RESEARCH_ONLY`**.
- **Advisory Integration Suitability:** **No** (superseded by V3 Monsoon).

---

#### Component 4: `mobilenet_v3_small_v3_monsoon` (Vision Model V3 Monsoon Robust)
- **Intended Task:** Binary flood detection under harsh monsoon weather and camera lens perturbations.
- **Input Features & Shapes:** RGB image tensor ($224 \times 224 \times 3$).
- **Output Semantics:** Calibrated probability score $p \in [0.0, 1.0]$ with uncertainty abstention for confidence values in $[0.35, 0.65]$.
- **Training Dataset & Provenance:** Manifest V3 trained with aggressive physical augmentations (synthetic rain streaks, wet asphalt contrast decay, headlight glare, water droplet lens blur).
- **Checkpoint Location:** [`models/vision/v3/model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt) (18.49 MB, MD5: `818ae953fc264badf86e14e08bf9f26b`).
- **Training & Evaluation Status:** Trained; thoroughly benchmarked across real-world cohorts and synthetic perturbations.
- **Valid Evaluation Evidence:**
  - **Overall Test V3 ($N=222$):** **97.75% accuracy**, **97.75% macro-F1** (FPR $= 0.90\%$, FNR $= 3.60\%$).
  - **Plain Dry Asphalt ($N=50$):** **100.0% specificity** (0 false positives).
  - **Wet Potholes & Puddles Hard Negatives ($N=61$):** **98.36% specificity** (only 1 false positive).
  - **Synthetic Rain Mist Blur ($N=222$):** **96.85% accuracy** (vs 70.72% for V2 and 93.24% for V3 Clean).
  - **Calibration:** Expected Calibration Error $\text{ECE} = 0.0237$, Brier score $= 0.0255$.
- **Known Domain Limitations:** Source-label confounding remains in the underlying dataset (Cramér's $V = 1.0000$). Requires human supervisor confirmation.
- **Current Readiness Verdict:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`** (Advisory shadow mode only).
- **Advisory Integration Suitability:** **Yes** (Strictly advisory decision support; non-autonomous).

---

### 3.2 Deterministic Rule-Based Engines

#### Component 5: `rainfall_risk_engine` (Rainfall Baseline Engine)
- **Intended Task:** Deterministic evaluation of real-time precipitation intensity, flash surge, and catchment saturation risk.
- **Input Features & Units:**
  - `rain_1h_mm` (1-hour accumulation in mm)
  - `rain_3h_mm` (Rolling 3-hour accumulation in mm)
  - `rain_6h_mm` (Rolling 6-hour accumulation in mm)
  - `rain_24h_mm` (Rolling 24-hour accumulation in mm)
  - `station_dist_km` (Distance to reporting telemetry station in km)
  - `data_freshness_hours` (Age of telemetry observation in hours)
- **Output Semantics:** Categorical risk tier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `UNKNOWN`), risk score $s \in [0.0, 1.0]$, and confidence discount factor $c \in [0.10, 1.0]$.
- **Reference Standard:** India Meteorological Department (IMD) Standard Operating Procedure for Weather Forecasting.
- **Training Dataset:** **None (Deterministic mathematical ruleset)**.
- **Source Code Location:** [`src/sahaay/hyderabad_risk/rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py).
- **Evaluation Status:** Independently validated across 21 automated checks ([`reports/phase10/rule_baseline_validation.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase10/rule_baseline_validation.json)).
- **Valid Evaluation Evidence:**
  - Monotonicity verified across 50 increments ($0$ to $100\text{ mm/hr}$).
  - Boundary accuracy at $7.5, 15.0, 35.0, 100.0\text{ mm/hr}$.
  - Multi-window escalation: $3\text{h} \ge 40\text{ mm} \implies \text{HIGH}$; $24\text{h} \ge 115.5\text{ mm} \implies \text{CRITICAL}$.
  - Missing data policy: `rain_1h_mm=None` strictly returns `UNKNOWN` ($c=0.10, s=0.0$). Missing data is **never** silently converted to zero.
- **Known Domain Limitations:** Depends on distance to rain gauges ($>15\text{ km}$ incurs confidence penalty). Localized convective micro-bursts ($<2\text{ km}$) may escape regional sensors.
- **Current Readiness Verdict:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**.
- **Advisory Integration Suitability:** **Yes** (Primary operational benchmark for rainfall risk).

---

#### Component 6: `image_quality_gate` (Automated Pre-Inference Filter)
- **Intended Task:** Reject uninformative, degraded, blurred, or corrupted imagery prior to invoking deep vision models.
- **Input Features:** Native resolution image file or tensor.
- **Output Semantics:** Boolean decision `(pass: bool, reason: str)` where failure codes include `BLURRY`, `UNDEREXPOSED`, `OVEREXPOSED`, and `LOW_RESOLUTION`.
- **Threshold Rules:**
  - Minimum native resolution: $640 \times 480$ pixels.
  - Sharpness: Laplacian variance $\ge 80.0$.
  - Brightness: Mean pixel intensity in $[35, 230]$ (rejects night darkness and headlight whiteout).
- **Training Dataset:** **None (Deterministic image processing rules)**.
- **Source Code Location:** [`src/sahaay/data_collection_v4/quality.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/quality.py).
- **Evaluation Status:** Validated via automated test suite ([`tests/test_image_quality_gate.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_image_quality_gate.py)).
- **Valid Evaluation Evidence:** 100% non-silent rejection of artificially blurred, pitch-black, and whiteout glare images.
- **Known Domain Limitations:** Rejects severely rain-obscured scenes that may genuinely be flooded but cannot be visually verified.
- **Current Readiness Verdict:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**.
- **Advisory Integration Suitability:** **Yes** (Mandatory pre-filter for all camera streams).

---

### 3.3 Heuristic Scoring Systems

#### Component 7: `road_vulnerability_engine` (Geospatial Vulnerability Engine)
- **Intended Task:** Compute an explainable static physical flood susceptibility index for urban road corridors.
- **Input Features & Proximities:**
  - `dist_to_flood_hotspot_m`: Distance to nearest chronic waterlogging placemark (meters).
  - `dist_to_nearest_drain_m`: Distance to nearest major open stormwater canal / nala (meters).
  - `dist_to_nearest_waterbody_m`: Distance to nearest lake, tank, or pond (meters).
- **Output Semantics:** Vulnerability index $v \in [0.0, 1.0]$ and tier (`LOW`, `MODERATE`, `HIGH`, `SEVERE`).
- **Mathematical Formula:**
  $$v = 0.45 \cdot s_{\text{hotspot}}(d_h) + 0.35 \cdot s_{\text{drain}}(d_d) + 0.20 \cdot s_{\text{waterbody}}(d_w)$$
- **Training Dataset:** **None (Civil engineering multi-criteria heuristic)**.
- **Source Code Location:** [`src/sahaay/hyderabad_risk/vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py).
- **Evaluation Status:** Independently validated across 21 checks ([`reports/phase10/rule_baseline_validation.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase10/rule_baseline_validation.json)).
- **Valid Evaluation Evidence:** Subscores decrease monotonically with distance. Accurately scores Tolichowki Underpass as `HIGH` ($0.532$) and Miyapur as `MODERATE` ($0.435$).
- **Known Domain Limitations:** Represents **static physical susceptibility, NOT active inundation**. A road scored as `SEVERE` is completely dry and safe during non-monsoon periods.
- **Current Readiness Verdict:** **`RULE_BASELINE_ONLY`**.
- **Advisory Integration Suitability:** **Yes** (Contextual baseline; not predictive ML).

---

### 3.4 Experimental Diagnostic Models

#### Component 8: `metadata_shortcut_classifier_rf` (Metadata Diagnostic Classifier)
- **Intended Task:** Quantify the non-semantic predictability of dataset splits to detect camera sensor and file size confounding.
- **Input Features:** `width`, `height`, `aspect_ratio`, `file_size_kb`, `megapixels`, `bytes_per_pixel`.
- **Output Semantics:** Probability of class label without observing any visual pixel data.
- **Training Dataset:** Manifest V4 train partition ($N=988$).
- **Checkpoint Location:** Script [`scripts/diagnostics_shortcut_baseline_v4.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/diagnostics_shortcut_baseline_v4.py) and output [`reports/phase9/metadata_shortcut_results.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase9/metadata_shortcut_results.json).
- **Evaluation Status:** Executed and reproduced.
- **Valid Evaluation Evidence:** Achieves **85.97% test accuracy** and **0.9066 ROC-AUC** on Test V4 ($N=221$). File size alone yields $80.09\%$ test accuracy.
- **Known Domain Limitations:** **Not a flood detector**. Serves as mathematical proof that deep vision models trained on available data learn camera artifacts rather than flood physics.
- **Current Readiness Verdict:** **`RESEARCH_ONLY`**.
- **Advisory Integration Suitability:** **No**.

---

### 3.5 Unsupervised Exploratory Analyses

#### Component 9: `corridor_susceptibility_analysis`
- **Intended Task:** Characterize spatial distributions of 20 Hyderabad road corridors relative to drainage and water bodies.
- **Input Features:** Coordinates of 20 candidate road corridors, 96 drain lines, 2,324 water bodies, 23 historical hotspots.
- **Output Semantics:** Mean, minimum, and maximum distances across municipal corridors.
- **Dataset:** [`data/hyderabad_risk/derived/hyderabad_risk_features.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/derived/hyderabad_risk_features.csv).
- **Evaluation Status:** Completed in Phase 10 Track B.
- **Valid Evaluation Evidence:** Established mean distance to nearest hotspot ($2,263.7\text{ m}$), drain ($533.3\text{ m}$), and waterbody ($983.6\text{ m}$).
- **Known Domain Limitations:** Spatial characterization only. Cannot be used as evidence of flood probability.
- **Current Readiness Verdict:** **`RESEARCH_ONLY`**.
- **Advisory Integration Suitability:** **No**.

---

#### Component 10: `telemetry_continuity_diagnostics`
- **Intended Task:** Forensic audit of time-series continuity and sensor quality for regional automated rain gauges.
- **Input Features:** 72,223 raw records across 38 stations in Telangana (2021–2025).
- **Output Semantics:** Distribution of transmission gaps, bucket accumulator counts, and negative values.
- **Dataset:** [`data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv).
- **Evaluation Status:** Completed in Phase 10 Track B.
- **Valid Evaluation Evidence:** Discovered that **$50.82\%$ of records are seasonal cumulative bucket counters** ($>250\text{ mm}$), 19 records are negative sensor glitches, and stations suffer from **up to 141.6 consecutive days of transmission gaps**.
- **Known Domain Limitations:** Diagnostic analysis only.
- **Current Readiness Verdict:** **`RESEARCH_ONLY`**.
- **Advisory Integration Suitability:** **No**.

---

### 3.6 Blocked or Not-Run Experiments

#### Component 11: `vision_v4_production_deep_model`
- **Intended Task:** Production deep vision flood classifier trained on source-independent road imagery.
- **Intended Inputs:** Balanced road imagery with matching geographic and camera representations.
- **Execution Status:** **`NOT_RUN`**.
- **Blocking Grounds:** Vision V4 Readiness Gate locked in **`NO-GO`** status due to Cramér's $V = 1.0000$, metadata shortcut accuracy $= 85.97\% > 65\%$, and 0 acquired field images.
- **Required Unlocking Data:** At least 200 real-world street images acquired across $\ge 2$ independent sources for both flood and non-flood classes under authorized pilot operations.
- **Current Readiness Verdict:** **`NOT_RUN`**.
- **Advisory Integration Suitability:** **No**.

---

#### Component 12: `supervised_flood_occurrence_prediction`
- **Intended Task:** Supervised machine learning model predicting street inundation depth ($\ge 5\text{ cm}$) from antecedent rainfall and road susceptibility features.
- **Execution Status:** **`NOT_RUN`**.
- **Blocking Grounds:** The project repository contains exactly **0** timestamped flood outcome observations. Static KML placemarks represent chronic recurrence, not timestamped flood episodes. Treating static hotspots as positive labels causes 100% spatial target leakage.
- **Required Unlocking Data:** Minimum 50 verified flood episodes (depth $\ge 5\text{ cm}$) and 100 verified non-flood episodes across at least 4 independent storm dates collected under human supervision.
- **Current Readiness Verdict:** **`NOT_RUN`**.
- **Advisory Integration Suitability:** **No**.

---

#### Component 13: `short_term_hourly_rainfall_forecasting`
- **Intended Task:** Autoregressive or sequence neural network predicting future hourly precipitation ($t+1\text{h}, t+3\text{h}$) from rain gauge telemetry.
- **Execution Status:** **`NOT_RUN`**.
- **Blocking Grounds:** Telemetry exhibits $>90\%$ temporal transmission missingness, 141-day gaps, mixed time deltas, and $50.82\%$ cumulative bucket accumulator counters. No stations exist in the GHMC urban core. Imputing missing hours as zero violates core data integrity rules.
- **Required Unlocking Data:** Continuous urban automated weather station network within the GHMC core operating at $\ge 98\%$ uptime and 15-minute sampling.
- **Current Readiness Verdict:** **`NOT_RUN`**.
- **Advisory Integration Suitability:** **No**.

---

## 4. Master Component Summary Table

| Component Name | Category | Primary Function | Evaluation Verdict | Advisory Suitability |
| :--- | :--- | :--- | :---: | :---: |
| **`mobilenet_v3_small_v1`** | Trained ML Model | Street flood classifier (leaky split) | `NOT_READY_INSUFFICIENT_DATA` | No |
| **`mobilenet_v3_small_v2`** | Trained ML Model | Street flood classifier (clean split) | `NOT_READY_INSUFFICIENT_DATA` | No (94% FPR on dry asphalt) |
| **`mobilenet_v3_small_v3_clean`** | Trained ML Model | Road flood classifier (clean road split) | `RESEARCH_ONLY` | No |
| **`mobilenet_v3_small_v3_monsoon`** | Trained ML Model | Robust weather-augmented classifier | `RECOMMENDED_FOR_ADVISORY_EVALUATION` | **Yes (Shadow advisory only)** |
| **`rainfall_risk_engine`** | Rule-Based Engine | IMD intensity & multi-window risk | `RECOMMENDED_FOR_ADVISORY_EVALUATION` | **Yes (Primary risk benchmark)** |
| **`image_quality_gate`** | Quality Gate | Pre-inference blur & glare filter | `RECOMMENDED_FOR_ADVISORY_EVALUATION` | **Yes (Mandatory pre-filter)** |
| **`road_vulnerability_engine`** | Heuristic Scoring | Multi-criteria static exposure index | `RULE_BASELINE_ONLY` | **Yes (Contextual baseline)** |
| **`metadata_shortcut_classifier_rf`** | Diagnostic Model | Quantifies non-semantic bias | `RESEARCH_ONLY` | No (Diagnostic only) |
| **`corridor_susceptibility_analysis`** | Exploratory Analysis | 20 corridor spatial distributions | `RESEARCH_ONLY` | No |
| **`telemetry_continuity_diagnostics`** | Exploratory Analysis | Profiling rain gauge missingness | `RESEARCH_ONLY` | No |
| **`vision_v4_production_deep_model`** | Blocked Experiment | Source-independent deep vision model | `NOT_RUN` | No (Gate NO-GO) |
| **`supervised_flood_occurrence_prediction`** | Blocked Experiment | Predictive ML for road inundation | `NOT_RUN` | No (0 target labels) |
| **`short_term_hourly_rainfall_forecasting`** | Blocked Experiment | Temporal telemetry forecasting | `NOT_RUN` | No (>90% missingness) |
