# Sahaay AI — Phase 11: Evidence-Based Model Selection & Operational Dispositions

## 1. Executive Summary

This document establishes the official research and engineering dispositions for all candidate models and algorithmic engines in **Sahaay AI**.

In accordance with Phase 11 governance principles, each component is assigned exactly one of five standardized dispositions based on empirical evidence, statistical validity, leakage controls, and operational safety:

- **`RECOMMENDED_FOR_ADVISORY_EVALUATION`** (Advisory decision support under human supervision)
- **`RULE_BASELINE_ONLY`** (Deterministic or heuristic operational baseline; not trained ML)
- **`RESEARCH_ONLY`** (Diagnostic baselines or research benchmarks; not for deployment)
- **`NOT_READY_INSUFFICIENT_DATA`** (Disqualified due to dataset flaws or performance collapse)
- **`NOT_RUN`** (Blocked by lack of ground-truth outcome labels or sensor discontinuity)

> [!CAUTION]
> ### Governance Disclaimer
> These dispositions represent **research and engineering evaluations**, NOT autonomous production deployment authorizations.
> No component in Sahaay AI is authorized to autonomously execute road closures, drop physical barriers, or dispatch emergency rescue vehicles without human operator review.

---

## 2. Summary Disposition Matrix

| Component Name | Primary Task | Model Category | Selected Disposition | Primary Empirical Rationale |
| :--- | :--- | :--- | :---: | :--- |
| **`rainfall_risk_engine`** | Rainfall Intensity & Multi-Window Risk | Deterministic Rule Engine | **`RECOMMENDED_FOR_ADVISORY_EVALUATION`** | IMD meteorological standard; 21/21 checks passing; explicit confidence discounting. |
| **`image_quality_gate`** | Image Degradation Filtering | Quality Gate / Rules | **`RECOMMENDED_FOR_ADVISORY_EVALUATION`** | 100% rejection of blurred, pitch-black, and whiteout imagery before inference. |
| **`mobilenet_v3_small_v3_monsoon`** | Adverse Weather Flood Vision | Trained ML Model | **`RECOMMENDED_FOR_ADVISORY_EVALUATION`** | Best weather robustness (96.85% under rain blur; 100% dry specificity; ECE=0.024). Restricted to shadow advisory. |
| **`road_vulnerability_engine`** | Multi-Criteria Corridor Exposure | Heuristic Scoring System | **`RULE_BASELINE_ONLY`** | Transparent civil engineering baseline. Not trained ML. |
| **`mobilenet_v3_small_v3_clean`** | Clean Road Flood Vision | Trained ML Model | **`RESEARCH_ONLY`** | Valid clean baseline (97.30% acc), but superseded by V3 Monsoon under weather perturbations. |
| **`metadata_shortcut_classifier_rf`** | Non-Semantic Bias Quantification | Diagnostic ML Model | **`RESEARCH_ONLY`** | Diagnostic proof of camera sensor bias (85.97% test acc on metadata alone). |
| **`corridor_susceptibility_analysis`** | Spatial Corridor Characterization | Exploratory Analysis | **`RESEARCH_ONLY`** | Exploratory geographic proximity statistics across 20 corridors. |
| **`telemetry_continuity_diagnostics`** | Telemetry Quality Profiling | Exploratory Analysis | **`RESEARCH_ONLY`** | Profiling of regional rain gauge missingness and bucket accumulator anomalies. |
| **`mobilenet_v3_small_v1`** | Baseline Flood Vision | Trained ML Model | **`NOT_READY_INSUFFICIENT_DATA`** | Flawed split with duplicate leaks and arbitrary non-road imagery. |
| **`mobilenet_v3_small_v2`** | Deduplicated Flood Vision | Trained ML Model | **`NOT_READY_INSUFFICIENT_DATA`** | Performance collapse on unseen dry roads (94.0% FPR); learned thumbnail shortcut. |
| **`vision_v4_production_deep_model`** | Multi-Source Flood Vision | Trained ML Model | **`NOT_RUN`** | Blocked by readiness gate (Cramér's $V = 1.0000$; 0 multi-class road imagery sources). |
| **`supervised_flood_occurrence_prediction`** | Predictive Inundation ML | Supervised ML Model | **`NOT_RUN`** | Blocked by complete absence of timestamped flood outcome observations. |
| **`short_term_hourly_rainfall_forecasting`** | Temporal Telemetry Forecasting | Sequence / ML Model | **`NOT_RUN`** | Blocked by $>90\%$ missingness, 141-day gaps, and 50.82% bucket accumulator counters. |

---

## 3. Granular Evidence-Based Dispositions

### 3.1 Components `RECOMMENDED_FOR_ADVISORY_EVALUATION`

#### 1. `rainfall_risk_engine` ([`rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py))
- **Disposition:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**
- **Evidence Base:**
  - Standardized against official IMD weather forecasting thresholds ($7.5, 15.0, 35.0, 100.0\text{ mm/hr}$).
  - Passed 21 / 21 boundary, monotonicity, and multi-window surge/saturation tests without a single failure.
  - Transparently penalizes confidence based on sensor distance ($-0.01/\text{km} >15\text{ km}$) and staleness ($-0.08/\text{hr} >1.5\text{ hr}$).
  - Strictly guarantees that missing rainfall data returns `UNKNOWN` (confidence $0.10$), never silently converting dropouts into low-risk zero rainfall.
- **Operational Integration Guardrails:**
  - Advisory decision-support signal only.
  - In convective cloudbursts under $2\text{ km}$ wide, regional rain gauges ($35\text{--}50\text{ km}$ away) will underestimate intensity without radar corroboration.

---

#### 2. `image_quality_gate` ([`quality.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/data_collection_v4/quality.py))
- **Disposition:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**
- **Evidence Base:**
  - Evaluated on synthetic and real degradation cohorts ([`reports/vision_integrity/image_quality_gate_audit.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/vision_integrity/image_quality_gate_audit.json)).
  - Achieves $100\%$ non-silent rejection of severely blurred images (Laplacian variance $< 80.0$), pitch-black night images (mean intensity $< 35.0$), overexposed whiteout glare (mean intensity $> 230.0$), and low-resolution thumbnails ($< 640 \times 480$).
  - Prevents garbage-in/garbage-out degradation of downstream vision models.
- **Operational Integration Guardrails:**
  - Must run as a mandatory pre-filter before invoking any deep vision model.
  - Rejection code must be logged and surfaced as `INCONCLUSIVE_DEGRADED_IMAGE`.

---

#### 3. `mobilenet_v3_small_v3_monsoon` ([`model_v3_monsoon.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_monsoon.pt))
- **Disposition:** **`RECOMMENDED_FOR_ADVISORY_EVALUATION`**
- **Evidence Base:**
  - Tested on reserved Test V3 ($N=222$) with zero duplicate leakage: achieved **97.75% accuracy**, **97.75% macro-F1**, and **0.90% False Positive Rate**.
  - **100.0% specificity on plain dry roads** (0 false positives out of 50 images; mean flood prob $= 0.0150$).
  - **98.36% specificity on wet potholes and puddles** (only 1 false positive out of 61 hard negatives; mean flood prob $= 0.0455$).
  - Superior synthetic perturbation robustness: **96.85% accuracy under rain mist blur** (vs 70.72% for V2 and 93.24% for V3 Clean).
  - Excellent confidence calibration: $\text{ECE} = 0.0237$, Brier score $= 0.0255$, with only 5 high-confidence errors out of 222 samples.
- **Operational Integration Guardrails:**
  - **Strict Advisory Shadow Mode Only:** Because source-label confounding exists in the underlying dataset (Clemson vs Virenbr11), this model must **never** be used for autonomous dispatch or barrier control.
  - Any prediction in $[0.35, 0.65]$ must be treated as `INCONCLUSIVE`.
  - Predictions must be paired with human reviewer confirmation during pilot operations.

---

### 3.2 Components `RULE_BASELINE_ONLY`

#### 4. `road_vulnerability_engine` ([`vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py))
- **Disposition:** **`RULE_BASELINE_ONLY`**
- **Evidence Base:**
  - Transparent civil engineering multi-criteria formulation ($0.45\cdot s_h + 0.35\cdot s_d + 0.20\cdot s_w$).
  - Subscores decrease monotonically with distance; 21 / 21 automated validation checks passing.
  - Accurately captures chronic elevation and drainage vulnerability (e.g. Tolichowki Underpass scored `HIGH` at $0.532$).
- **Why NOT Machine Learning:**
  - Training an ML regressor (Ridge, Random Forest) to predict $v$ merely approximates explicit linear weights that are already deterministically calculated.
  - Rule imitation is not predictive modeling.
- **Operational Integration Guardrails:**
  - Static physical susceptibility only. A `SEVERE` corridor is completely safe in dry weather.

---

### 3.3 Components `RESEARCH_ONLY`

#### 5. `mobilenet_v3_small_v3_clean` ([`model_v3_clean.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v3/model_v3_clean.pt))
- **Disposition:** **`RESEARCH_ONLY`**
- **Evidence Base:** Solid research benchmark (97.30% accuracy on Test V3), but superseded by `model_v3_monsoon`, which exhibits greater robustness to rain blur (96.85% vs 93.24%) and lower false positive rate on dry roads (0.0% vs 6.0%). Retained for ablation studies.

#### 6. `metadata_shortcut_classifier_rf` ([`metadata_shortcut_results.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase9/metadata_shortcut_results.json))
- **Disposition:** **`RESEARCH_ONLY`**
- **Evidence Base:** Diagnostic tool that achieved 85.97% test accuracy on non-semantic metadata alone. Serves as empirical proof of dataset confounding; never to be used as a flood detector.

#### 7. `corridor_susceptibility_analysis` & `telemetry_continuity_diagnostics`
- **Disposition:** **`RESEARCH_ONLY`**
- **Evidence Base:** Exploratory spatial and time-series profiling characterizing geographic proximities and rain gauge transmission gaps.

---

### 3.4 Components `NOT_READY_INSUFFICIENT_DATA`

#### 8. `mobilenet_v3_small_v1` ([`best_model.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/best_model.pt))
- **Disposition:** **`NOT_READY_INSUFFICIENT_DATA`**
- **Evidence Base:** Disqualified due to train-test duplicate leakage and non-road class bias (indoor rooms, cats, portraits). Zero generalization to real-world roads.

#### 9. `mobilenet_v3_small_v2` ([`model_v2.pt`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/models/vision/v2/model_v2.pt))
- **Disposition:** **`NOT_READY_INSUFFICIENT_DATA`**
- **Evidence Base:** Collapsed to **53.15% accuracy** on unseen road imagery with a **94.0% False Positive Rate on plain dry roads**. Learned thumbnail resolution shortcut ($224 \times 224$ non-floods vs $>800\text{px}$ floods). Disqualified from operational use.

---

### 3.5 Components `NOT_RUN`

#### 10. `vision_v4_production_deep_model`
- **Disposition:** **`NOT_RUN`**
- **Blocking Evidence:** Cramér's $V = 1.0000$, Mutual Information $= 1.0000\text{ bits}$, metadata shortcut accuracy $= 85.97\%$, 0 field images acquired. Readiness Gate remains **`NO-GO`**.

#### 11. `supervised_flood_occurrence_prediction`
- **Disposition:** **`NOT_RUN`**
- **Blocking Evidence:** Exactly **0** timestamped flood outcome observations exist. Static KML placemarks are chronic locations without dates or water depths. Labeling static points causes 100% spatial target leakage.

#### 12. `short_term_hourly_rainfall_forecasting`
- **Disposition:** **`NOT_RUN`**
- **Blocking Evidence:** $>90\%$ temporal missingness, 141-day transmission gaps, 50.82% bucket accumulator counters, 0 stations in the GHMC urban core.
