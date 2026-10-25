# Sahaay AI — Hyderabad Risk Geospatial & Rainfall Data Repository (`data/hyderabad_risk/`)

## 1. Directory Purpose & Structure

This directory houses the geospatial, drainage, and hydrological rainfall datasets for **Phase 4: Hyderabad Geospatial & Rainfall Risk AI Data Pipeline**.

```
data/hyderabad_risk/
├── README.md                      # Operational guidelines and dataset provenance (this file)
├── raw/                           # [IMMUTABLE] Raw, unmodified public datasets as downloaded
│   ├── flooding_locations.kml     # 23 chronic inundation hotspots across GHMC (OpenCity / TRAC)
│   ├── hyderabad_drains.kml       # 96 stormwater drain & nala line vectors (OpenCity / GHMC)
│   ├── greater_hyderabad_waterbodies.geojson # 2,324 lake & tank polygon vectors (OpenCity / TRAC)
│   ├── hyderabad_monthly_rainfall_1901_2021.csv # 121-year monthly IMD rainfall series (OpenCity)
│   └── telangana_hourly_telemetry_rainfall_2021_2025.csv # 72,223 telemetry records (NWDP / NWIC)
└── derived/                       # Reproducibly generated feature layers and manifests
    ├── hyderabad_risk_features.csv # Unified multimodal spatial & rainfall feature layer
    └── feature_manifest.json      # Cryptographic provenance and generation metadata
```

---

## 2. Immutability & Engineering Rules

1. **Raw Directory Immutability**:
   Files in `data/hyderabad_risk/raw/` must NEVER be edited, renamed, or overwritten. If updated source data is downloaded, it must be saved with versioned filenames.
2. **Reproducibility Guarantee**:
   All artifacts in `derived/` must be generated entirely through code via `scripts/generate_hyderabad_risk_features.py`.
3. **No Silent Zero-Filling**:
   Missing rainfall readings from automated weather stations must NEVER be imputed as 0 mm without explicit flagging. Gaps are preserved as missing with degraded confidence scores.
4. **No Pseudo-Label Supervised Training**:
   The static flooding locations in `flooding_locations.kml` represent historical susceptibility hotspots, NOT time-series flood outcomes. They are utilized strictly as spatial distance features.
