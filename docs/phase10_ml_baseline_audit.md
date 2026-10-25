# Sahaay AI — Phase 10: Rainfall and Road-Risk ML Baseline Audit

## 1. Executive Summary

This document establishes the official AI/ML engineering baseline for **Sahaay AI Phase 10**, continuing directly from Phase 9 commit [`af588fb`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai).

The scope of Phase 10 is strictly confined to:
1. Auditing the rainfall, telemetry, and geospatial road-vulnerability pipelines.
2. Validating the rules-based baselines against edge cases and monotonicity requirements.
3. Establishing data suitability and feasibility for supervised machine learning tasks.
4. Formally recording `NOT_RUN` verdicts where target labels or temporal continuity are scientifically absent.

All frontend interfaces, APIs, live-data integrations, deployment scripts, and pilot activation gate workflows remain outside this phase. The Vision V4 readiness gate status is preserved at **`NO-GO`**.

---

## 2. Pipeline Components & Data Source Audit

A systematic forensic audit of every pipeline module in `src/sahaay/hyderabad_risk/` was conducted to establish the exact provenance of all inputs and derived scores:

### 2.1 Rainfall Risk Baseline Engine ([`rainfall_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/rainfall_engine.py))
- **Primary Function:** Computes instantaneous rainfall intensity score, categorical risk (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, `UNKNOWN`), multi-window amplification, and quality-discounted confidence.
- **Reference Standard:** India Meteorological Department (IMD) Standard Operating Procedure for Weather Forecasting.
- **Ruleset Inputs:**
  - `rain_1h_mm`: Primary 1-hour accumulation.
  - `rain_3h_mm`: Rolling 3-hour flash surge detection (threshold: $\ge 40.0\text{ mm}$).
  - `rain_6h_mm`: Rolling 6-hour accumulation (threshold: $\ge 70.0\text{ mm}$).
  - `rain_24h_mm`: Rolling 24-hour catchment saturation (thresholds: $\ge 64.5\text{ mm}$ heavy, $\ge 115.5\text{ mm}$ very heavy).
  - `station_dist_km`: Distance to rain gauge (penalized beyond $15\text{ km}$ at $-0.01/\text{km}$ up to $-0.35$).
  - `data_freshness_hours`: Age of telemetry observation (penalized beyond $1.5\text{ h}$ at $-0.08/\text{h}$ up to $-0.40$).
- **Missing Data Policy:** If `rain_1h_mm` is missing, the engine **strictly returns `UNKNOWN` with confidence $0.10$ and score $0.0$**. Missing observations are **NEVER** silently imputed as zero rainfall.

### 2.2 Road Vulnerability Baseline Engine ([`vulnerability_engine.py`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/hyderabad_risk/vulnerability_engine.py))
- **Primary Function:** Evaluates an explainable multi-criteria static physical susceptibility index ($v \in [0.0, 1.0]$) and category (`LOW`, `MODERATE`, `HIGH`, `SEVERE`).
- **Input Proximities & Heuristic Weights:**
  - **Hotspot Proximity ($45\%$ weight):** Proximity to historical recurrence placemarks. Subscore: $1.0\text{--}0.50$ ($0\text{--}250\text{ m}$), $0.50\text{--}0.0$ ($250\text{--}1000\text{ m}$), $0.0$ ($>1000\text{ m}$).
  - **Drainage Proximity ($35\%$ weight):** Proximity to open nalas and major stormwater canals. Subscore: $1.0\text{--}0.60$ ($0\text{--}100\text{ m}$), $0.60\text{--}0.0$ ($100\text{--}500\text{ m}$), $0.0$ ($>500\text{ m}$).
  - **Waterbody Proximity ($20\%$ weight):** Proximity to lake bunds, tanks, and ponds. Subscore: $1.0\text{--}0.50$ ($0\text{--}200\text{ m}$), $0.50\text{--}0.0$ ($200\text{--}800\text{ m}$), $0.0$ ($>800\text{ m}$).
- **Semantic Nature:** Represents **static physical susceptibility**, not active flooding. A road categorized as `SEVERE` is safe during dry periods.

---

## 3. Input Classification: Data Provenance Breakdown

To distinguish real-world evidence from heuristic and synthetic constructs, every input to the rainfall and vulnerability pipelines is categorized below:

| Input / Pipeline Element | Classification Category | Provenance & Source Reference | Empirical Verification Status |
| :--- | :---: | :--- | :--- |
| **`telangana_hourly_telemetry_rainfall`** | **Observed Real-World Data** | National Water Informatics Centre (NWIC) / Ministry of Jal Shakti. 72,223 raw records from 38 automated rain gauges across 22 Telangana districts. | 19 negative sensor glitches detected; 50.82% records are cumulative bucket counters ($>250\text{ mm}$). Zero stations within GHMC urban core. |
| **`hyderabad_monthly_rainfall`** | **Historical Climatology** | India Meteorological Department (IMD) gridded monthly rainfall series (1901–2021, 121 years) for Hyderabad centroid. | Verified 121-year climatological monthly means and p90 percentiles (July mean 175.4mm, August mean 198.6mm, Sept mean 158.2mm). |
| **`flooding_locations.kml`** | **Static Geography** | TRAC Telangana / GHMC monsoon monitoring logs via OpenCity India. 23 placemarks with location names. | Static chronic points only. Zero timestamps, zero dates, zero depth measurements. |
| **`hyderabad_drains.kml`** | **Static Geography** | GHMC via OpenCity India. 96 multi-segment nala/canal LineStrings. | Spatial alignments verified. Cross-sectional flow capacity ($m^3/s$) unrecorded. |
| **`greater_hyderabad_waterbodies`** | **Static Geography** | TRAC Telangana via OpenCity India. 2,324 lake and pond Polygons. | Geometry verified. Sluice gate operations and bund crest levels unrecorded. |
| **20 Road Corridors** | **Static Geography** | Project candidate corridors ([`hyderabad_risk_features.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/derived/hyderabad_risk_features.csv)). | Coordinates and buffer projections verified. |
| **Heuristic Scoring Weights** | **Heuristic Weights** | Multi-criteria weights ($0.45, 0.35, 0.20$) and IMD piecewise thresholds ($7.5, 15.0, 35.0\text{ mm/hr}$). | Calibrated against IMD literature and civil engineering guidelines. Not fitted via ML. |
| **Phase 5 Scenario Vectors** | **Synthetic Scenarios** | Test fixtures in `reports/phase5/end_to_end_scenarios.json`. | Clearly labeled as synthetic; used strictly for software logic testing. |

---

## 4. Regression Baseline Verification

Prior to conducting Phase 10 experiments, the repository regression suite was executed:
- **Baseline Commit:** `af588fb` (master branch, clean working tree).
- **Test Pass Rate:** **141 / 141 tests passed** (100% pass rate in 8.29s).
- **Subsystem Breakdown:**
  - Pilot activation, session management & blocker closure: 36 passed.
  - Hyderabad geospatial risk pipeline: 12 passed.
  - Decision engine contracts & end-to-end integration: 21 passed.
  - Vision model validation, quality gate & split integrity: 64 passed.
  - Phase 9 adversarial duplicate & audit tests: 8 passed.

---

## 5. Strategic Directives for Phase 10

1. **No Pseudo-Supervised Learning:** Do not train models that reproduce manual heuristic scores or rule thresholds. Rule imitation is not predictive modeling.
2. **No Target Leakage:** Do not use static hotspot coordinates as positive targets for flood occurrence.
3. **Transparent Baseline Reference:** Validate the existing rules-based engines across edge cases as the official operational benchmark.
4. **Honest `NOT_RUN` Accounting:** Where target labels or continuous sensor feeds do not exist, record `NOT_RUN` with full empirical justification.
