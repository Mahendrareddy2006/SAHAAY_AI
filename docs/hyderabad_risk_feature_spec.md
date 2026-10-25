# Sahaay AI — Hyderabad Geospatial & Hydrological Risk Feature Specification

## 1. Overview & Spatial Scope

This document specifies the mathematical formulation, coordinate systems, units, missing-value handling, and provenance of the multi-source geospatial and hydrological feature pipeline built for Hyderabad flood intelligence in Phase 4.

### 1.1 Spatial Unit & Resolution
- **Spatial Unit**: Road Corridor Segments / Intersection Buffers (`HYD-LOC-001` through `HYD-LOC-020`).
- **Coordinate Reference System**: EPSG:4326 (WGS84 ellipsoidal latitude/longitude).
- **Spatial Precision Notice**:
  - **Static GIS Layers** (hotspots, drains, waterbodies): Precision $\pm 10\text{--}50\text{ meters}$.
  - **Telemetry Rainfall**: Regional basin-scale automated weather stations ($47\text{--}113\text{ km}$ distance from core city). Road-level precision is **NOT** claimed for telemetry rainfall; regional attribution and distance-discounted confidence metrics are enforced.

---

## 2. Feature Definitions & Formulations

### 2.1 Geospatial Proximity Features

#### `dist_to_flood_hotspot_m`
- **Definition**: Great-circle distance from the corridor reference coordinates to the nearest chronic historical waterlogging hotspot.
- **Unit**: Meters ($m$).
- **Range**: $[0.0, \infty)$.
- **Formula**:
  $$\Delta \sigma = 2 \arcsin \sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos \phi_1 \cos \phi_2 \sin^2\left(\frac{\Delta \lambda}{2}\right)}$$
  $$d = R_{\text{earth}} \cdot \Delta \sigma \quad (R_{\text{earth}} = 6,371,000\text{ m})$$
- **Source**: OpenCity / TRAC / GHMC 23 chronic waterlogging hotspots (`flooding_locations.kml`).

#### `nearest_hotspot_name`
- **Definition**: Official name of the closest historical waterlogging hotspot (e.g., `"BALKAMPET RUB"`, `"GALAXY TOLICHOWKI"`).
- **Type**: String.

#### `dist_to_nearest_drain_m`
- **Definition**: Orthogonal Euclidean distance in meters from corridor coordinates to the nearest vertex or segment of the GHMC primary storm water drainage (nala) network.
- **Unit**: Meters ($m$).
- **Range**: $[0.0, \infty)$.
- **Formula**: Point-to-segment projection on local equirectangular coordinate plane:
  $$t = \text{clamp}\left(\frac{(\mathbf{P} - \mathbf{A}) \cdot (\mathbf{B} - \mathbf{A})}{\|\mathbf{B} - \mathbf{A}\|^2}, 0, 1\right)$$
  $$\text{dist} = \|\mathbf{P} - (\mathbf{A} + t(\mathbf{B} - \mathbf{A}))\|$$
- **Source**: GHMC Open Data / OpenCity 96 primary nala networks (`hyderabad_drains.kml`).

#### `dist_to_nearest_waterbody_m`
- **Definition**: Great-circle distance from corridor coordinates to the centroid of the nearest lake, tank, or reservoir.
- **Unit**: Meters ($m$).
- **Range**: $[0.0, \infty)$.
- **Source**: HMDA / Irrigation Dept / OpenCity 2,324 water bodies (`greater_hyderabad_waterbodies.geojson`).

#### `nearest_waterbody_name`
- **Definition**: Official tank or village water body name.
- **Type**: String.

---

### 2.2 Hydrological Telemetry Features

#### `nearest_telemetry_station`
- **Definition**: Identifier of the nearest automated hydrological weather telemetry station.
- **Type**: String (e.g., `"Kondapochamma Resrvoir"`, `"Singur_1"`).
- **Source**: National Water Data Portal (NWIC) / Telangana Surface Water Dept.

#### `nearest_station_dist_km`
- **Definition**: Distance from corridor coordinates to the reporting weather station.
- **Unit**: Kilometers ($km$).
- **Role**: Directly penalizes output confidence if station is remote ($> 15\text{ km}$).

#### `telemetry_freshness_hours`
- **Definition**: Elapsed time between the prediction query timestamp $T_{\text{query}}$ and the latest valid station observation $T_{\text{obs}}$.
- **Unit**: Hours ($h$).
- **Formula**: $\Delta t = \max(0, (T_{\text{query}} - T_{\text{obs}}) / 3600)$.
- **Missingness Rule**: If $\Delta t > 1.5\text{ hours}$, flagged as stale; if $> 6\text{ hours}$, confidence severely penalized.

#### `rain_1h_mm`, `rain_3h_mm`, `rain_6h_mm`, `rain_24h_mm`
- **Definition**: Rolling accumulated rainfall over $1, 3, 6,$ and $24$ hours preceding prediction time.
- **Unit**: Millimeters ($mm$).
- **Range**: $[0.0, \infty)$.
- **Non-Silent Missingness Mandate**:
  - Missing hourly observations are **NEVER** silently imputed as $0.0\text{ mm}$.
  - If a time window has $< 50\%$ valid telemetry coverage, the value is returned as `None` / `null`, triggering a warning and confidence degradation.

---

### 2.3 Climatological Baseline Features

#### `hist_month_mean_mm`
- **Definition**: 121-year historical mean rainfall for the calendar month in Hyderabad.
- **Unit**: Millimeters ($mm$).
- **Source**: IMD Hyderabad monthly precipitation series 1901–2021.

#### `hist_month_p90_mm`
- **Definition**: 90th percentile monthly rainfall for the calendar month in Hyderabad, establishing extreme monsoonal precipitation reference levels.
- **Unit**: Millimeters ($mm$).
- **July Baseline**: Mean $= 174.6\text{ mm}$, $P_{90} = 298.2\text{ mm}$.
- **August Baseline**: Mean $= 188.1\text{ mm}$, $P_{90} = 322.4\text{ mm}$.

---

### 2.4 Component Outputs

#### `vulnerability_index`
- **Definition**: Multi-criteria weighted static vulnerability score $V \in [0.0, 1.0]$.
- **Formula**:
  $$V = 0.45 \cdot S_{\text{hotspot}} + 0.35 \cdot S_{\text{drain}} + 0.20 \cdot S_{\text{waterbody}}$$
- **Categories**:
  - $V \ge 0.70 \to$ `SEVERE`
  - $0.45 \le V < 0.70 \to$ `HIGH`
  - $0.20 \le V < 0.45 \to$ `MODERATE`
  - $V < 0.20 \to$ `LOW`

#### `rainfall_risk_score` & `rainfall_risk_category`
- **Definition**: Dynamic precipitation intensity risk based on IMD operational SOP thresholds.
- **Categories**:
  - `LOW`: Dry to Light rain ($\le 7.5\text{ mm/hr}$).
  - `MEDIUM`: Moderate rain ($7.5\text{--}15.0\text{ mm/hr}$).
  - `HIGH`: Heavy rain ($15.0\text{--}35.0\text{ mm/hr}$) or 3h surge ($> 40\text{ mm}$).
  - `CRITICAL`: Very Heavy / Cloudburst ($> 35.0\text{ mm/hr}$ or $> 100\text{ mm/hr}$) or 24h saturation ($> 115.5\text{ mm}$).
  - `UNKNOWN`: Missing 1h observation (explicit non-silent failure).

#### `confidence_score`
- **Definition**: Evidence quality metric $\in [0.10, 1.00]$.
- **Formula**:
  $$\text{Conf} = 1.0 - \min(0.35, \max(0, d_{\text{st}} - 15) \times 0.01) - \min(0.40, \max(0, t_{\text{fresh}} - 1.5) \times 0.08) - 0.08 \times N_{\text{missing\_windows}}$$
