# Sahaay AI — Phase 4 Completion Report: Hyderabad Geospatial & Rainfall Risk AI Data Pipeline and Baseline Engine

## Executive Summary

Phase 4 successfully built and evaluated the first reproducible, data-driven Hyderabad flood-risk pipeline and explainable baseline engine for Sahaay AI. In strict accordance with scientific integrity guidelines:
- **No unsupported claims of predictive flood-forecasting accuracy are made.**
- **Supervised model training was determined to be scientifically unjustified** due to the absence of time-series flood occurrence/depth labels in candidate public datasets.
- An explainable, physics-informed baseline engine calibrated against India Meteorological Department (IMD) intensity standards was built and integrated into the Sahaay AI Decision Engine.
- The **Vision V4 readiness decision remains strictly NO-GO**, and all historical Vision models, manifests, and audits remain untouched.

---

## 1. Datasets Successfully Obtained

All four candidate datasets identified in the mission brief were successfully acquired, verified, and placed into immutable storage under `data/hyderabad_risk/raw/`:

| Dataset Identifier | Publisher / Source | Format | Local Path | Verified SHA-256 (Prefix) |
| :--- | :--- | :--- | :--- | :--- |
| **Hyderabad Flooding Locations** | OpenCity / TRAC / GHMC | KML | `data/hyderabad_risk/raw/flooding_locations.kml` | `c37b018b1ba48099...` |
| **Hyderabad Open GIS & Drains** | OpenCity / GHMC Open Data | KML | `data/hyderabad_risk/raw/hyderabad_drains.kml` | `b6ef5c3577d3aa05...` |
| **Greater Hyderabad Water Bodies** | HMDA / Irrigation Dept / OpenCity | GeoJSON | `data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson` | `ab5318dbcb5db680...` |
| **Hyderabad Historical Monthly Rainfall** | IMD / OpenCity | CSV | `data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv` | `0b77747970868f1c...` |
| **Telangana Hourly Telemetry Rainfall** | National Water Data Portal (NWIC) | CSV | `data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv` | `0d94f738f73a388b...` |

---

## 2. Datasets Inaccessible or Incomplete

1. **Municipal CCTV Telemetry & Sensor Stream**: Inaccessible / pending legal MOU execution under Phase 3 (`STREAM-01-MUNICIPAL-CCTV`).
2. **LiDAR Elevation / Micro-Topography (DEM)**: Not available in public open data; elevation was not manufactured and is documented as a missing feature in the vulnerability spec.
3. **Hydraulic Culvert / Drainage Capacity Data (cusecs)**: OpenCity GIS provides drain centerlines and lengths, but cross-sectional dimensions, siltation ratios, and discharge capacities are absent.

---

## 3. Actual Data Counts and Spatial/Temporal Coverage

| Dataset | Record Count | Geographic Extent | Temporal Span | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **Flooding Locations** | 23 points | Core GHMC zones ($17.36^\circ\text{--}17.47^\circ\text{N}$, $78.41^\circ\text{--}78.53^\circ\text{E}$) | Static historical compilation | Point-level ($\pm 10\text{ m}$) |
| **Drains & Nalas** | 277 segments (14,368 vertices) | GHMC jurisdiction | Static survey | LineString ($\pm 15\text{ m}$) |
| **Water Bodies** | 2,324 polygons | Greater Hyderabad & Rangareddy catchment basins | Static cadastral survey | Polygon ($\pm 25\text{ m}$) |
| **IMD Historical Rainfall** | 121 annual records | Hyderabad District | 1901 to 2021 (121 years) | Monthly aggregations |
| **NWIC Hourly Telemetry** | 72,223 raw rows (29,779 valid QC) | 38 stations across 22 Telangana districts | 2021 to 2025 | Regional AWS ($47\text{--}113\text{ km}$ from city) |

---

## 4. Data-Quality Problems, Exclusions, and Forensic Findings

1. **Cumulative Gauge Accumulator vs. Incremental Hourly Rain**:
   - Out of 72,223 telemetry records, **36,398 rows ($50.4\%$) report rainfall $> 250\text{ mm/hr}$** (up to $3,406\text{ mm}$).
   - Forensic analysis established that these are **cumulative seasonal/daily bucket accumulators**, not incremental hourly precipitation.
   - *Filter Applied*: Flagged as `QC_ACCUMULATOR_SPIKE` and excluded from instantaneous intensity calculations.
2. **Negative Sensor Faults**:
   - 19 records reported negative precipitation (down to $-448.5\text{ mm}$), indicative of electrical sensor disconnects.
   - *Filter Applied*: Flagged as `QC_NEGATIVE_VAL` and purged.
3. **Duplicate Timestamps**:
   - 6,027 repeated timestamp entries across stations were identified and deduplicated.
4. **Spatial Remoteness of Telemetry Stations**:
   - The nearest reporting AWS (`Kondapochamma Resrvoir`) is located **$50.65\text{ km}$** from central Hyderabad.
   - *Safeguard Enforced*: Enforced distance-decay confidence discounting ($\text{penalty} = (d - 15) \times 0.01$). Regional attribution is explicitly documented; road-level precipitation precision is **never** claimed.
5. **Non-Silent Missingness**:
   - Station transmission gaps (e.g. multi-hour skips) are tracked. Missing values are **never** silently imputed as $0.0\text{ mm}$; missing primary observations return `UNKNOWN` and discount output confidence.

---

## 5. Features Successfully Derived

Multi-source feature vectors were generated across 20 candidate corridors (`HYD-LOC-001` through `HYD-LOC-020`):

1. **`dist_to_flood_hotspot_m` & `nearest_hotspot_name`**: Great-circle distance to nearest chronic waterlogging hotspot (range: $76\text{ m}$ to $2,300\text{ m}$).
2. **`dist_to_nearest_drain_m`**: Orthogonal distance to GHMC primary open nala network (range: $18\text{ m}$ to $850\text{ m}$).
3. **`dist_to_nearest_waterbody_m` & `nearest_waterbody_name`**: Distance to nearest lake/tank centroid (range: $110\text{ m}$ to $1,800\text{ m}$).
4. **`nearest_telemetry_station` & `nearest_station_dist_km`**: Spatial attribution to regional telemetry station.
5. **`telemetry_freshness_hours`**: Data age tracker enforcing temporal decay.
6. **`rain_1h_mm`, `rain_3h_mm`, `rain_6h_mm`, `rain_24h_mm`**: Rolling accumulations with non-silent missingness tracking.
7. **`hist_month_mean_mm` & `hist_month_p90_mm`**: 121-year monsoonal baseline percentiles.
8. **`vulnerability_index` & `vulnerability_category`**: Multi-criteria static susceptibility ($V \in [0, 1]$, categories: `LOW`, `MODERATE`, `HIGH`, `SEVERE`).
9. **`rainfall_risk_score` & `rainfall_risk_category`**: Dynamic IMD intensity risk (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
10. **`confidence_score`**: Transparent evidence quality metric ($\text{Conf} \in [0.10, 1.00]$).

Derived files:
- `data/hyderabad_risk/derived/hyderabad_risk_features.csv`
- `data/hyderabad_risk/derived/feature_manifest.json`

---

## 6. Whether Reliable Flood Outcome Labels Exist

**NO.**
- The flooding locations dataset (`flooding_locations.kml`) represents static spatial recurrence, not time-series flood outcomes.
- There are **zero time-series records** specifying event start times, water depth measurements, or recession times.
- No historical dispatch logs or depth gauge telemetry were linked to these points.

---

## 7. Whether a Model Was Trained or Only a Baseline Built

**ONLY AN EXPLAINABLE RULES-BASED BASELINE ENGINE WAS BUILT.**
- Training a supervised machine learning model on static hotspots would introduce fatal circular target leakage (memorizing coordinates rather than predicting flood events).
- The baseline engine implements:
  - IMD Standard Operating Procedure rainfall thresholds.
  - Multi-criteria GIS physical vulnerability weighting.
  - Non-silent missingness handling and confidence discounting.

---

## 8. Evaluation Results and Engineering Limitations

| Evaluation Category | Finding / Metric | Status |
| :--- | :--- | :--- |
| **Supervised Training Decision** | `NO-GO_SUPERVISED_TRAINING_UNJUSTIFIED` | **Enforced** |
| **Coordinate Transformation** | KML (lon, lat) vs Python (lat, lon) verified | **PASS** |
| **Anomaly Filtering** | 19 negative values and 36,398 accumulator spikes filtered | **PASS** |
| **Non-Silent Missingness** | Missing 1h observation returns `UNKNOWN`, missing windows penalize confidence | **PASS** |
| **IMD Tiers Calibration** | Light ($5\text{ mm}$), Moderate ($12\text{ mm}$), Heavy ($25\text{ mm}$), Very Heavy ($45\text{ mm}$), Cloudburst ($110\text{ mm}$) | **PASS** |
| **Confidence Degradation** | Distance ($50\text{ km} \to 0.65$), Staleness ($4\text{h} \to 0.44$), Missing ($2\text{ windows} \to 0.48$) | **PASS** |
| **Decision Engine Synthesis** | High rain + High vulnerability $\to$ `WATCH` / `PREDICTED_RISK` | **PASS** |

---

## 9. API and Test Results

### 9.1 API Endpoints Verified
- `POST /api/v1/risk/rainfall/estimate` $\to$ Returns `RainfallRiskResult` with IMD category and confidence.
- `POST /api/v1/risk/vulnerability/calculate` $\to$ Returns `RoadVulnerabilityResult` with GIS feature breakdown.
- `GET /api/v1/risk/corridors` $\to$ Returns 20 analyzed corridor feature vectors.
- `POST /api/v1/decision/evaluate` $\to$ Synthesizes environmental risk with vision evidence into explainable alert levels.

### 9.2 Test Suite Execution
- **Phase 4 Pipeline Tests**: 14/14 passed (`tests/test_hyderabad_risk_pipeline.py`).
- **Full Repository Test Suite**: **82/82 passed** (100% pass rate).
- **Vision V4 Gate Preservation**: Verified `reports/vision_integrity/v4_phase3_pilot_audit.json` remains strictly `NO-GO`.

---

## 10. Exact Next Steps to Improve the Risk Engine

1. **Deploy Micro-AWS or Integrate Telangana TSDPS Automatic Weather Stations**:
   - Ingest hyper-local weather stations situated within the GHMC urban boundary (e.g. TSDPS stations in Khairatabad, Shaikpet, Jubilee Hills) to reduce telemetry distance from $50\text{ km}$ to $< 5\text{ km}$.
2. **Acquire Historical GHMC DRF Waterlogging Incident Logs**:
   - Obtain timestamped municipal pump deployment and DRF dispatch logs to establish true historical flood event start and end times.
3. **Integrate Digital Elevation Model (DEM)**:
   - Ingest high-resolution elevation data (e.g., CartoDEM or TanDEM-X) to derive physical slope, topographic wetness index (TWI), and depression catchment volume.
4. **Conduct Supervised Experiment ONLY After Paired Labels Are Obtained**:
   - Once timestamped water depth measurements or verified dispatch logs are acquired, execute a leakage-free time-split experiment across held-out monsoon seasons.
