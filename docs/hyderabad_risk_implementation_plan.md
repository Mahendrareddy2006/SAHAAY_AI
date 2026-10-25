# Sahaay AI — Phase 4 Hyderabad Geospatial & Rainfall Risk AI Implementation Plan

## Objective
Build the first data-driven, Hyderabad-specific flood-risk geospatial and rainfall feature pipeline and explainable baseline engine using four authentic public datasets, fully integrated with the Sahaay AI Decision Engine while preserving historical Vision safeguards.

---

## 1. Candidate Datasets & Acquisition Protocol
1. **Hyderabad Flooding Locations**:
   - Source: OpenCity / Greater Hyderabad Municipal Corporation (GHMC) / TRAC Telangana.
   - Format: KML (spatial points of recurring waterlogging hotspots).
2. **Hyderabad GIS & Drainage Layers**:
   - Source: OpenCity / GHMC (Canals, Drains, Major Nalas KML & Greater Hyderabad Waterbodies GeoJSON).
   - Format: KML vector lines & GeoJSON polygons.
3. **Hyderabad Historical Rainfall Baseline**:
   - Source: OpenCity / India Meteorological Department (IMD) Grid Series.
   - Format: CSV (Monthly rainfall records 1901–2021).
4. **Telangana Hourly Telemetry Rainfall**:
   - Source: National Water Data Portal (NWIC) / Telangana Surface Water (SW) Irrigation & CAD Department / CWC.
   - Format: Hourly telemetry CSV (Automated Rain Gauge - ARG time series).

*Storage Rule*: Store raw, unmodified source files in `data/hyderabad_risk/raw/`. Derived feature sets stored in `data/hyderabad_risk/derived/`.

---

## 2. Architecture & Package Structure
We will introduce a cohesive, modular package under `src/sahaay/hyderabad_risk/`:
- `schemas.py`: Pydantic models for spatial points, drainage lines, rainfall telemetry, and feature vectors.
- `ingest.py`: Download and raw format parsers (KML, GeoJSON, CSV) with immutable raw caching.
- `validate.py`: Coordinate bounds validation (WGS84 for Hyderabad $17.0^\circ\text{--}17.7^\circ\text{N}, 78.1^\circ\text{--}78.8^\circ\text{E}$), timestamp parsing, missingness audits, unit checks.
- `features.py`: Geospatial distance calculations (Haversine / Euclidean point-to-point and point-to-line), rolling rainfall accumulation (1h, 3h, 6h, 24h), seasonal baseline percentile, confidence indicators.
- `rainfall_engine.py`: Enhanced rainfall risk component honoring data freshness, station distance, and IMD intensity thresholds.
- `vulnerability_engine.py`: Data-driven road vulnerability index computing proximity to historical hotspots, nalas, and water bodies.

---

## 3. Scientific Integrity Constraints
1. **No Pseudo-Supervised Learning**: Since OpenCity flooding hotspots represent static spatial recurrence points without timestamped hourly inundation labels, **no supervised classifier will be trained on hotspot pseudo-labels**. We implement a transparent, physics-informed baseline risk engine.
2. **Missing Data Policy**: Missing rainfall is NEVER interpreted as zero rainfall. Missing hours or stale stations explicitly degrade confidence.
3. **Temporal Leakage Prevention**: Features for prediction timestamp $T$ strictly use observations $\le T$.
4. **Decision Engine & Vision Isolation**: Vision predictions remain strictly advisory. Vision V4 readiness gate remains NO-GO and unmodified.
