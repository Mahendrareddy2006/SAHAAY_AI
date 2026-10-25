# Sahaay AI — Phase 10: Experiment Protocol & Evaluation Framework

## 1. Executive Summary

This document specifies the experimental protocol, baseline reference standards, and scientific decision framework for **Sahaay AI Phase 10: Rainfall and Road-Risk Model Experiments, Baselines & Evaluation**.

The protocol enforces four distinct tracks:
- **Track A:** Rules-Based Reference Baselines (Validated across 21 boundary tests).
- **Track B:** Unsupervised & Exploratory Data Analysis (Telemetry quality and spatial susceptibility clustering).
- **Track C:** Supervised Flood Prediction Feasibility (Formally recorded as **`NOT_RUN`**).
- **Track D:** Temporal Rainfall Forecasting Feasibility (Formally recorded as **`NOT_RUN`**).

---

## 2. Track A — Rules-Based Reference Baselines

Track A establishes the deterministic, traceable mathematical standards against which future statistical models will be benchmarked:

### 2.1 Rainfall Risk Baseline Specification
The rainfall engine ([`src/sahaay/hyderabad_risk/rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py)) implements an IMD-calibrated piecewise intensity and multi-window accumulation ruleset:

$$\text{Category}(r_1) = \begin{cases}
\text{CRITICAL} & \text{if } r_1 \ge 35.0\text{ mm/hr} \\
\text{HIGH} & \text{if } 15.0 \le r_1 < 35.0\text{ mm/hr} \\
\text{MEDIUM} & \text{if } 7.5 \le r_1 < 15.0\text{ mm/hr} \\
\text{LOW} & \text{if } 0.0 \le r_1 < 7.5\text{ mm/hr} \\
\text{UNKNOWN} & \text{if } r_1 \text{ is missing (None)}
\end{cases}$$

- **Flash Surge Escalation:** If rolling $3\text{h}$ rain $\ge 40.0\text{ mm}$, category is upgraded to at least `HIGH` (score $\ge 0.70$).
- **Catchment Saturation Escalation:** If rolling $24\text{h}$ rain $\ge 64.5\text{ mm}$, category is upgraded to at least `HIGH` (score $\ge 0.65$); if $\ge 115.5\text{ mm}$, category is upgraded to `CRITICAL` (score $\ge 0.85$).
- **Confidence Quality Discounting:**
  $$\text{Confidence} = \max\Big(0.10, 1.0 - \min(0.35, \max(0, d_{\text{station}} - 15) \times 0.01) - \min(0.40, \max(0, \Delta t - 1.5) \times 0.08) - 0.08 \times N_{\text{missing\_windows}}\Big)$$

### 2.2 Road Vulnerability Baseline Specification
The road vulnerability engine ([`src/sahaay/hyderabad_risk/vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py)) computes the static physical exposure index:

$$v = 0.45 \cdot s_{\text{hotspot}}(d_h) + 0.35 \cdot s_{\text{drain}}(d_d) + 0.20 \cdot s_{\text{waterbody}}(d_w)$$

- **Vulnerability Tiers:** `SEVERE` ($v \ge 0.70$), `HIGH` ($0.45 \le v < 0.70$), `MODERATE` ($0.20 \le v < 0.45$), `LOW` ($v < 0.20$).
- **Validation Pass Rate:** 21 / 21 automated validation checks passing ([`reports/phase10/rule_baseline_validation.json`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase10/rule_baseline_validation.json)).

---

## 3. Track B — Unsupervised & Exploratory Analysis

Track B characterizes data distributions without manufacturing unsupported target labels:

### 3.1 Telemetry Quality Diagnostics
Analysis of 72,223 raw telemetry records across 38 stations in Telangana reveals:
1. **Accumulator Counter Anomaly:** $36,702$ records ($50.82\%$) report values $> 250\text{ mm}$ (up to $3,406\text{ mm}$). Stations alternate between reporting incremental hourly rainfall and cumulative seasonal bucket counter totals.
2. **Sensor Glitches:** 19 records contain negative values (down to $-448.5\text{ mm}$).
3. **Severe Temporal Discontinuity:** Stations exhibit effective temporal coverage of $< 7\%$, with transmission gaps up to 141.6 consecutive days and duplicate timestamps.
4. **Spatial Sparsity:** Zero stations exist within the GHMC urban core.

### 3.2 Spatial Susceptibility Distribution Across 20 Hyderabad Corridors
Analysis of [`data/hyderabad_risk/derived/hyderabad_risk_features.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/derived/hyderabad_risk_features.csv) demonstrates spatial variation across municipal zones:
- **Mean Proximity to Nearest Hotspot:** $2,279.3\text{ m}$ (range $64.5\text{ m}$ at Lakdikapul to $7,992.3\text{ m}$ at Miyapur).
- **Mean Proximity to Stormwater Drain (Nala):** $541.5\text{ m}$ (range $26.9\text{ m}$ at Miyapur to $1,682.4\text{ m}$ at Madhapur).
- **Mean Proximity to Water Body:** $1,057.4\text{ m}$ (range $82.2\text{ m}$ at Alwal to $2,420.1\text{ m}$ at Malakpet).
- **Vulnerability Category Distribution:**
  - `HIGH`: 1 corridor (`HYD-LOC-001` Tolichowki Underpass, index = $0.532$).
  - `MODERATE`: 9 corridors (Shaikpet, Khairatabad, Malakpet, Panjagutta, Bio-Diversity, Lakdikapul, Ameerpet, Miyapur, Alwal).
  - `LOW`: 10 corridors (Begumpet, Secunderabad, Musarambagh, Madhapur, Dilsukhnagar, Amberpet, Uppal, Bowenpally, Mehdipatnam, Balanagar).

---

## 4. Track C — Supervised Flood Prediction Feasibility

### Formal Decision: **EXPERIMENT STATUS = `NOT_RUN`**

#### Primary Blocking Reasons:
1. **Absence of Ground-Truth Target Labels:** The repository contains zero timestamped, location-linked flood event observations (water depth $\ge 5\text{ cm}$).
2. **KML Placemarks are Static Points, Not Labels:** `flooding_locations.kml` contains 23 static placemarks without timestamps, dates, or depths. Labeling static points as flood targets induces 100% spatial target leakage.
3. **Formula Imitation Prohibition:** Training an ML model to predict `vulnerability_index` or `rainfall_risk_category` measures rule imitation / formula distillation, not predictive accuracy.

#### Ground-Truth Target Required to Unlock Track C:
- Minimum 50 verified flood episodes (depth $\ge 5\text{ cm}$) and 100 non-flood episodes across at least 4 independent storm dates collected under the approved Phase 7/8 protocol.

---

## 5. Track D — Temporal Rainfall Forecasting Feasibility

### Formal Decision: **EXPERIMENT STATUS = `NOT_RUN`**

#### Primary Blocking Reasons:
1. **Massive Temporal Missingness:** Rain gauge reporting exhibits $> 90\%$ transmission missingness with multi-week gaps (up to 141.6 consecutive days with zero records).
2. **Accumulator Counter Confusion:** 50.82% of records report seasonal bucket accumulator counters ($> 250\text{ mm}$), corrupting hourly rate differencing.
3. **No Urban Core Sensors:** All 38 stations are situated in rural/reservoir basins 35–50 km outside the GHMC metropolitan core.
4. **Data Integrity Prohibition:** Imputing missing hours as zero rain violates the non-negotiable data rule and would cause severe underestimation of flood risk.

---

## 6. Preservation of Model-Safety Semantics

The following operational and scientific distinctions are strictly preserved:

> [!CAUTION]
> **Safety Semantics & Operational Invariants:**
> 1. **Environmental susceptibility is NOT proof of current inundation.** A SEVERE road is completely safe during dry weather.
> 2. **High rainfall risk is NOT a verified flood observation.** It represents atmospheric intensity, not hydraulic waterlogging.
> 3. **Missing rainfall telemetry is `UNKNOWN` (confidence 0.10), NEVER `LOW`.**
> 4. **A static hotspot is NOT a timestamped flood label.**
> 5. **Synthetic scenarios test software logic, NOT predictive accuracy.**
> 6. **Models MUST NOT autonomously authorize road closures or emergency dispatch.**
