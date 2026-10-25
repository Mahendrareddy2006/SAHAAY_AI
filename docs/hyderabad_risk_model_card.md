# Sahaay AI Model Card: Hyderabad Geospatial & Rainfall Risk Baseline Engine (v1.0)

## 1. Engine Overview

| Parameter | Specification |
| :--- | :--- |
| **Engine Name** | Hyderabad Geospatial & Rainfall Risk Baseline Engine |
| **Version** | `hyderabad_risk_baseline_v1.0` |
| **Model Type** | Explainable, Physics-Calibrated Multi-Criteria Decision Engine (Rules-Based Baseline) |
| **Primary Geographic Domain** | Greater Hyderabad Municipal Corporation (GHMC) & Outer Ring Road (ORR) catchments |
| **Primary Modalities** | Geospatial KML/GeoJSON layers, IMD climatological baselines, automated hydrological telemetry |
| **Status** | **Operational Baseline Engine (Supervised Machine Learning NOT Justified)** |

---

## 2. Intended Use & Operational Boundary

### 2.1 Intended Use
- **Environmental Hazard Awareness**: Quantifies elevated risk of urban surface runoff and flash inundation across road corridors.
- **Decision Engine Integration**: Ingested by Sahaay AI Decision Engine to cross-reference with visual camera evidence and citizen advisories.
- **Transparent Reasoning**: Exposes explicit reason codes (`IMD_HEAVY_INTENSITY_EXCEEDED`, `ROLLING_3H_FLASH_SURGE`) and missing input warnings.

### 2.2 Prohibited Use Cases
- **NO Autonomous Road Closures**: Must **NOT** trigger automated vehicular barriers or traffic stoppages without physical field verification.
- **NO Emergency Dispatch Pre-emption**: Must **NOT** cancel emergency dispatches or declare roads definitively safe.
- **NO Predictive Inundation Depth Claims**: Does **NOT** predict exact millimeter-level water depth on asphalt.

---

## 3. Scientific Justification: Why Supervised ML is NOT Justified

A foundational finding of Phase 4 is that **supervised flood-prediction model training is currently scientifically unjustified and invalid**:

1. **Absence of Ground-Truth Outcome Labels**:
   - `flooding_locations.kml` contains 23 static points representing historical waterlogging recurrence. It contains **zero time-series observations** (no event timestamps, no duration, no depth measurements).
   - Telangana NWIC telemetry contains hourly rainfall, but **zero linked flood outcome records**.
2. **Severe Target Leakage Risk**:
   - Training a machine learning classifier on static hotspot presence would cause 100% circular target leakage—the model would merely memorize coordinates rather than learning hydrodynamic relationships.
3. **Scientific Safeguard**:
   - In accordance with Sahaay AI integrity principles, an explainable baseline engine calibrated against India Meteorological Department (IMD) standards is delivered instead of a deceptive "trained" model.

---

## 4. Component Architectures

### 4.1 Component A: Dynamic Rainfall Risk Engine
- **Traceable IMD SOP Thresholds**:
  - Light Rain ($\le 7.5\text{ mm/hr}$): `LOW`
  - Moderate Rain ($7.5\text{--}15.0\text{ mm/hr}$): `MEDIUM`
  - Heavy Rain ($15.0\text{--}35.0\text{ mm/hr}$): `HIGH`
  - Very Heavy Rain ($> 35.0\text{ mm/hr}$): `CRITICAL`
  - Cloudburst ($\ge 100.0\text{ mm/hr}$): `CRITICAL`
- **Rolling Surge Rules**:
  - $3\text{h} \ge 40\text{ mm} \to$ elevates to `HIGH` (flash storm surge).
  - $24\text{h} \ge 115.5\text{ mm} \to$ elevates to `CRITICAL` (extreme catchment saturation).
- **Non-Silent Missingness Mandate**:
  - Missing hourly rainfall returns `UNKNOWN` and logs an explicit warning.
  - Missing rainfall is **NEVER** silently imputed as $0.0\text{ mm}$.

### 4.2 Component B: Static Road Vulnerability Engine
- **Multi-Criteria Weighted Index**:
  $$V = 0.45 \cdot S_{\text{hotspot}} + 0.35 \cdot S_{\text{drain}} + 0.20 \cdot S_{\text{waterbody}}$$
- **Physical Rationale**:
  - Chronic hotspot recurrence ($45\%$ weight): Historical empirical waterlogging evidence.
  - Open nala proximity ($35\%$ weight): Vulnerability to storm drain overflow and backflow.
  - Lake/tank proximity ($20\%$ weight): Inundation buffer and low-elevation catchment depression.
- **Separation Principle**:
  - A road with `SEVERE` vulnerability is **NOT** currently flooded unless heavy rainfall or active standing water is present.

---

## 5. Confidence Degradation & Evidence Quality

Outputs include an evidence-quality indicator $\text{Conf} \in [0.10, 1.00]$:
1. **Station Remoteness**: Telemetry stations $> 15\text{ km}$ away degrade confidence by $-0.01$ per km (nearest Hyderabad station is $50.6\text{ km}$ away, yielding base penalty $\approx -0.35$).
2. **Data Staleness**: Telemetry $> 1.5\text{ hours}$ old degrades confidence by $-0.08$ per hour.
3. **Missing Windows**: Each missing rolling window degrades confidence by $-0.08$.

---

## 6. Vision V4 Gate Independence

- This risk engine operates as an independent environmental stream (`STREAM-ENV`).
- It does **NOT** weaken or bypass the **Vision V4 Production Training Gate** (which remains strictly **NO-GO** until authentic, consent-verified field imagery is collected).
- Decision Engine treats rainfall risk as advisory environmental context, never as substitute for visual evidence.
