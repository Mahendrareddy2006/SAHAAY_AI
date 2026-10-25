# Sahaay AI — Hyderabad Geospatial & Rainfall Risk AI Data Inventory

## Executive Summary

This document establishes the official data inventory, provenance records, and quality audit for the four candidate datasets acquired for **Sahaay AI Phase 4: Hyderabad Geospatial & Rainfall Risk AI Data Pipeline**.

All four datasets were acquired from original public publishers (OpenCity India and the National Water Informatics Centre / Ministry of Jal Shakti) using authorized open access protocols. Original raw files are preserved immutably in `data/hyderabad_risk/raw/`, and all derived features are generated into `data/hyderabad_risk/derived/`.

---

## 1. Inventory of Acquired Datasets

| Dataset Identifier | Owning Organization & Publisher | Source URL & Access Protocol | License & Terms | Format & Raw Path | File Size & Records | Temporal & Spatial Coverage | Primary Utility & Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`flooding_locations_kml`** | TRAC Telangana / GHMC via OpenCity | [OpenCity Dataset Resource](https://data.opencity.in/dataset/flooding-locations-in-hyderabad) (HTTP Direct) | Public Domain / Open Data | KML<br>[`data/hyderabad_risk/raw/flooding_locations.kml`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/flooding_locations.kml) | $15.98\text{ KB}$<br>23 Hotspots | Static historical recurrence points across GHMC urban core ($17.31^\circ\text{--}17.45^\circ\text{N}$, $78.40^\circ\text{--}78.51^\circ\text{E}$) | Empirical proximity feature for baseline road vulnerability index. |
| **`hyderabad_drains_kml`** | GHMC via OpenCity | [OpenCity Canals, Drains and Tanks Resource](https://data.opencity.in/dataset/4becf994-e7f5-4da3-b201-b56b126b57f7) (HTTP Direct) | Open Data / Public Domain | KML<br>[`data/hyderabad_risk/raw/hyderabad_drains.kml`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/hyderabad_drains.kml) | $570.40\text{ KB}$<br>96 LineStrings | Stormwater drain network, canals, and major nalas across Hyderabad | Distance to nearest stormwater channel / nala feature. |
| **`greater_hyderabad_waterbodies_geojson`** | TRAC Telangana via OpenCity | [OpenCity Water Bodies Resource](https://data.opencity.in/dataset/c662fa8e-e776-4896-a907-cb4fbad8f89d) (HTTP Direct) | Open Data / Public Domain | GeoJSON<br>[`data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/greater_hyderabad_waterbodies.geojson) | $4,921.57\text{ KB}$<br>2,324 Polygons | Lakes, retention basins, and tanks across Greater Hyderabad & Rangareddy | Distance to nearest retention basin / lake feature. |
| **`hyderabad_monthly_rainfall_csv`** | India Meteorological Department (IMD) via OpenCity | [OpenCity Hyderabad Rainfall Data Resource](https://data.opencity.in/dataset/hyderabad-rainfall-data) (HTTP Direct) | Open Government Data (OGD) India | CSV<br>[`data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/hyderabad_monthly_rainfall_1901_2021.csv) | $16.38\text{ KB}$<br>121 Years (1901–2021) | Hyderabad grid monthly rainfall time series (121 years) | Long-term climatological baseline and monthly precipitation percentiles. |
| **`telangana_hourly_telemetry_rainfall_csv`** | National Water Informatics Centre (NWIC), Ministry of Jal Shakti / Telangana SW Dept | [National Water Data Portal](https://nwdp.nwic.gov.in) (Direct Resource CSV) | Open Government Data (OGD) India / NWIC Access Terms | CSV<br>[`data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv`](file:///C:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv) | $8,917.67\text{ KB}$<br>72,223 Records | Automated Rain Gauge (ARG) telemetry across 38 stations in Telangana (2021–2025) | Operational rainfall accumulation calculations (1h, 3h, 6h, 24h). |

---

## 2. In-Depth Technical Audits & Known Limitations

### 2.1 Dataset 1: Hyderabad Flooding Locations (`flooding_locations.kml`)
- **Origin**: Published by TRAC Telangana based on Greater Hyderabad Municipal Corporation (GHMC) monsoon waterlogging monitoring logs.
- **Attributes**: 23 placemarks with location names (e.g., `BALKAMPET RUB`, `RETHIBOWLI JUNCTION`, `NEAR GALAXY THEATRE, TOLICHOWKI`, `LAKDIKAPUL`, `MODEL HOUSE, PUNJAGUTTA`, `SHAIKPET NALA`).
- **Coordinate Reference System (CRS)**: WGS84 geographic coordinates `<longitude, latitude, altitude>`.
- **Critical Limitations**:
  1. **Static Points**: Represents chronic historical recurrence points without individual flood event timestamps.
  2. **No Depth Telemetry**: Contains zero quantitative flood depth measurements (centimeters of standing water).
  3. **Supervised Learning Implication**: **Cannot be used as timestamped ground-truth outcome labels for supervised classification.** Using static hotspot coordinates as positive targets would introduce severe target leakage. It is strictly used as an spatial susceptibility input feature.

### 2.2 Dataset 2: Hyderabad Drains & Water Bodies (`hyderabad_drains.kml` & GeoJSON)
- **Origin**: Spatial layers of urban stormwater infrastructure in the GHMC area.
- **Drains Layer**: 96 multi-segment `LineString` elements tracing major nalas, canals, and secondary open channels.
- **Water Bodies Layer**: 2,324 polygon features covering urban and peri-urban lakes (cheruvu, kunta, tanks) across Hyderabad and Rangareddy districts.
- **Critical Limitations**:
  1. Drainage cross-sectional capacity (discharge rate in $m^3/s$) is unrecorded in the vector metadata.
  2. Culvert dimensions, drain invert levels, and active maintenance/desilting states are absent.
  3. Distance to drain/water body acts as a proxy for hydraulic connectivity rather than complete hydrodynamic simulation.

### 2.3 Dataset 3: Hyderabad Monthly Rainfall 1901–2021 (`hyderabad_monthly_rainfall_1901_2021.csv`)
- **Origin**: Gridded rainfall observations compiled by the India Meteorological Department (IMD) for the Hyderabad coordinate centroid.
- **Attributes**: 14 columns: `Year`, `Jan` through `Dec`, and annual `Total` in millimeters.
- **Climatological Monsoonal Distribution (121-Year Baseline)**:
  - July: Mean $= 175.4\text{ mm}$, 90th Percentile $= 298.2\text{ mm}$, Max $= 454.1\text{ mm}$ (1989).
  - August: Mean $= 198.6\text{ mm}$, 90th Percentile $= 322.4\text{ mm}$, Max $= 521.8\text{ mm}$ (2000).
  - September: Mean $= 158.2\text{ mm}$, 90th Percentile $= 265.1\text{ mm}$, Max $= 428.5\text{ mm}$ (1908).
- **Critical Limitations**:
  - **Resolution**: Monthly aggregations cannot forecast 1-hour flash floods.
  - **Usage Mandate**: Must NEVER be represented as real-time forecast data. It provides contextual baseline percentiles for seasonal anomaly detection.

### 2.4 Dataset 4: Telangana Hourly Telemetry Rainfall (`telangana_hourly_telemetry_rainfall_2021_2025.csv`)
- **Origin**: Automated Rain Gauge (ARG) telemetry maintained by the Telangana Surface Water (SW) Department and compiled on the National Water Data Portal (NWDP).
- **Volume**: 72,223 hourly records across 38 telemetry stations.
- **Empirical Quality Audit Findings**:
  1. **Negative Sensor Glitches**: 19 records contain negative values (down to $-448.5\text{ mm}$), representing uncalibrated sensor errors. These must be rejected by validation filters.
  2. **Cumulative Gauge Accumulator vs Incremental Hourly Rainfall**:
     - 36,702 records (50.82%) report values $> 250\text{ mm}$ (up to $3,406\text{ mm}$).
     - Forensic inspection proves that stations alternate between reporting incremental hourly rainfall and cumulative seasonal bucket gauge accumulators.
     - **Mandatory Filter**: Any raw value $> 250\text{ mm/hr}$ must be audited and decoded as an accumulator counter difference or flagged as unphysical.
  3. **Reporting Irregularity & Missing Hours**:
     - Automated telemetry stations exhibit substantial transmission skips (e.g., 2- to 8-hour gaps during network outages).
     - **Non-Negotiable Rule**: **Missing hours must NEVER be silently filled with zero rainfall.** If a station was offline during a downpour, assuming 0 mm would catastrophically underestimate flood risk. Gaps are explicitly tracked with `data_freshness_hours` and degrade output confidence.
  4. **Spatial Proximity**: Stations cover regional Telangana water basins (including Sanga Reddy, Medak, Vikarabad, and Nalgonda bordering the GHMC metropolitan boundary).

---

## 3. Storage Hierarchy & Immutability Guarantee

```
data/hyderabad_risk/
├── raw/                               # [IMMUTABLE] Original downloaded source files directly as published
│   ├── flooding_locations.kml         # OpenCity KML
│   ├── hyderabad_drains.kml           # OpenCity KML
│   ├── greater_hyderabad_waterbodies.geojson # OpenCity GeoJSON
│   ├── hyderabad_monthly_rainfall_1901_2021.csv # OpenCity CSV
│   └── telangana_hourly_telemetry_rainfall_2021_2025.csv # NWDP CSV
└── derived/                           # Generated feature sets, validated CSVs, and feature manifests
    ├── hyderabad_risk_features.csv    # Final multimodal feature layer
    └── feature_manifest.json          # Cryptographic hashes and feature provenance
```
