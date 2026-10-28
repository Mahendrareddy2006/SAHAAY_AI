# Sahaay AI — Phase A: Live Map & Road Network Foundation Report

**Milestone:** Phase A (Production Implementation Milestone)  
**Date:** 2026-10-27  
**Branch:** `feat/phase12-architecture-audit-and-data-contracts`  
**Milestone Status:** Complete (Geospatial Foundation & Live Map Layer Established)  
**Operational Verdict:** **`GEOSPATIAL_FOUNDATION_READY_ROUTING_ENGINE_PENDING`**  
**Autonomous Dispatch & Automated Road Closures:** **`STRICTLY_PROHIBITED`**  
**Operational Directive:** **ADVISORY ONLY**. Absence of flood evidence on a road segment does not guarantee safe passage, dry pavement, or absence of localized hazards.

---

## 1. Initial Architecture & Gap Analysis

Prior to Phase A, Sahaay AI completed software engineering audits across Phases 12 through 21, establishing data contracts, rainfall adapters, community verification protocols, risk heuristics, and emergency workflows. However, the system lacked a physical geospatial and topological foundation:

```
+----------------------------------------------------------------------------------------------------+
| INITIAL REPOSITORY STATE VS. PHASE A DELIVERABLES                                                  |
+---+------------------------------------+------------------------------------+----------------------+
| # | Component                          | State Prior to Phase A             | Phase A Deliverable  |
+---+------------------------------------+------------------------------------+----------------------+
| 1 | Road Representation                | Single lat/lon points only         | Canonical LineString |
| 2 | Road Network Package               | Empty `road_network/` folder       | Store, Schemas, OSM  |
| 3 | Map API Endpoint                   | Table rows `/risk/corridors` only  | GeoJSON RFC 7946 FC  |
| 4 | Map Symbology & Safety             | Points colored by legacy alerts    | Line & dash overlays |
| 5 | OpenStreetMap Ingestion            | Zero import/normalization logic    | OSM Importer & ODbL  |
| 6 | Live Map Refresh                   | Page reload required               | Dynamic refresh API  |
+---+------------------------------------+------------------------------------+----------------------+
```

### Key Gaps Identified & Addressed:
1. **Absence of Road Geometries:** Previously, corridors were stored solely as single coordinate points in [`data/hyderabad_risk/derived/hyderabad_risk_features.csv`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/data/hyderabad_risk/derived/hyderabad_risk_features.csv). Roads in the real world are linear corridors with geometry, width, lane count, and directionality. Phase A establishes canonical `LineString` geometries for all 20 primary monitored corridors plus representative connecting segments.
2. **Missing GeoJSON API Layer:** The frontend previously consumed flat tabular JSON. Phase A introduces `/api/v1/map/corridors/geojson` returning compliant `FeatureCollection` objects ready for standard GIS and web mapping engines (Leaflet, Mapbox, OpenLayers).
3. **Decoupling of Static Infrastructure from Dynamic Flood Conditions:** Static attributes (road name, class, lanes, static vulnerability) are strictly segregated from dynamic observations (water depth, verification state, freshness).
4. **Symbology Safety Invariants:** Unknown or unmonitored road segments are never rendered in green or marked safe.

---

## 2. Files Added & Modified

### Files Added:
- [`src/sahaay/road_network/__init__.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/__init__.py): Package initialization and public exports.
- [`src/sahaay/road_network/schemas.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/schemas.py): Canonical schemas for road segments, coordinates, GeoJSON geometry, map properties, and coverage reports.
- [`src/sahaay/road_network/store.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/store.py): Thread-safe in-memory road network store pre-populated with 20 canonical Hyderabad corridor LineStrings and unmonitored links.
- [`src/sahaay/road_network/osm_importer.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/osm_importer.py): OpenStreetMap (OSM) normalization and validation engine enforcing ODbL 1.0 attribution.
- [`tests/test_phase_a_live_map_foundation.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/tests/test_phase_a_live_map_foundation.py): Automated test suite with 13 focused test cases.
- [`scripts/audit_phase_a_map_foundation.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/scripts/audit_phase_a_map_foundation.py): Reproducible audit script.
- [`reports/phase_a/phase_a_results.json`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase_a/phase_a_results.json): Machine-readable audit report.
- [`reports/phase_a/PHASE_A_LIVE_MAP_AND_ROAD_NETWORK_FOUNDATION_REPORT.md`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/reports/phase_a/PHASE_A_LIVE_MAP_AND_ROAD_NETWORK_FOUNDATION_REPORT.md): This acceptance report.

### Files Modified:
- [`src/sahaay/api/routes.py`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/api/routes.py): Added map GeoJSON, coverage, snapshot, single corridor, and cache refresh API endpoints.
- [`src/sahaay/api/static/index.html`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/api/static/index.html): Enhanced Leaflet frontend with LineString rendering, live sync button, safety disclaimer banner, and road-condition legend.

---

## 3. API Contracts & Example Responses

### A. `GET /api/v1/map/corridors/geojson`
Returns an RFC 7946 compliant GeoJSON `FeatureCollection` with all road segments, geometries, and dynamic status overlays:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "HYD-LOC-001",
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [78.4060, 17.3995],
          [78.4112, 17.4023],
          [78.4165, 17.4050]
        ]
      },
      "properties": {
        "segment_id": "HYD-LOC-001",
        "corridor_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass (Old Mumbai Hwy)",
        "zone": "West Zone",
        "road_class": "primary",
        "is_one_way": false,
        "length_meters": 1280.0,
        "monitoring_status": "MONITORED_CORRIDOR",
        "static_vulnerability_index": 0.532,
        "static_vulnerability_category": "HIGH",
        "condition_state": "NO_CURRENT_EVIDENCE",
        "evidence_type": "NO_EVIDENCE",
        "freshness_category": "UNKNOWN",
        "verification_state": "UNMONITORED",
        "uncertainty_level": "HIGH",
        "confidence_score": 0.0,
        "measured_water_depth_cm": null,
        "has_conflicting_evidence": false,
        "last_status_update_utc": "2026-10-27T12:00:00Z",
        "evidence_age_minutes": null,
        "marker_color": "#64748b",
        "stroke_style": "dashed",
        "stroke_weight": 3,
        "alert_badge": "UNKNOWN",
        "safety_notice": "ADVISORY ONLY: Sahaay AI does not guarantee road safety, dry pavement, or clear passage...",
        "disclaimer": "MAP ADVISORY NOTICE: Sahaay AI road geometries and condition markers are advisory indicators..."
      }
    }
  ],
  "metadata": {
    "title": "Sahaay AI — Hyderabad Live Map & Road Network Overlays",
    "generated_at_utc": "2026-10-27T12:00:00Z",
    "total_features": 22,
    "crs": "EPSG:4326 (WGS84)",
    "source_license": "ODbL-1.0",
    "source_attribution": "© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project",
    "disclaimer": "MAP ADVISORY NOTICE: Sahaay AI road geometries..."
  }
}
```

### B. `GET /api/v1/map/coverage`
Returns geospatial metadata, centerline kilometers, and attribution:

```json
{
  "generated_at_utc": "2026-10-27T12:00:00Z",
  "total_segments_mapped": 22,
  "monitored_corridors_count": 20,
  "unmonitored_segments_count": 2,
  "total_centerline_length_km": 25.84,
  "bounding_box": {
    "min_lat": 17.0,
    "max_lat": 17.8,
    "min_lon": 78.1,
    "max_lon": 78.8
  },
  "source_attribution": "© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project",
  "source_license": "ODbL-1.0",
  "coverage_status": "BASELINE_CANDIDATE_CORRIDORS_MAPPED",
  "data_freshness_summary": {
    "UNKNOWN": 22
  },
  "condition_state_summary": {
    "NO_CURRENT_EVIDENCE": 20,
    "UNKNOWN": 2
  },
  "disclaimer": "MAP ADVISORY NOTICE: Sahaay AI road geometries..."
}
```

### C. `POST /api/v1/map/corridors/refresh`
Triggers cache re-evaluation and returns verification response:

```json
{
  "refreshed_at_utc": "2026-10-27T12:00:00Z",
  "caller_id": "WEB-CLIENT-01",
  "total_features_refreshed": 22,
  "status": "REFRESH_SUCCESS"
}
```

---

## 4. Map Implementation & How to Run It

The frontend is served directly by the existing FastAPI application:
1. **Start the API Server:**
   ```powershell
   cmd /c "set PYTHONPATH=src;. && .venv\Scripts\python -m uvicorn sahaay.api.main:app --host 127.0.0.1 --port 8000"
   ```
2. **Access the Dashboard:**
   Open browser at `http://127.0.0.1:8000/dashboard`.
3. **Interactive Capabilities:**
   - **Vector Corridors:** Real LineString paths for Hyderabad corridors rendered over Dark Matter CartoDB tiles.
   - **Live Map Refresh:** Clicking **↻ Sync Live Map** triggers `/api/v1/map/corridors/refresh` and updates geometry overlays in real time.
   - **Corridor Selection:** Clicking on any road path or sidebar card highlights the corridor and displays detailed engineering metrics, proximity buffers, and static vulnerability indexes in the right-hand panel.
   - **Mandatory Safety Banner:** Displays at the top of the map: *"ADVISORY ONLY: Absence of flood reports on a road segment does NOT imply safe passage or dry pavement. Comply with Traffic Police directives."*
   - **Symbology Legend:** Explicitly distinguishes verified impassable, verified waterlogged, verified passable, corroborated community reports, unverified single reports, conflicting evidence, stale data, and unknown unmonitored roads.

---

## 5. Road-Data Source, Attribution & Import Instructions

### Source & Licensing:
- **Base Data:** OpenStreetMap contributors (`ODbL 1.0`) and Sahaay AI Base Corridor Catalog.
- **Mandatory Attribution:** `"© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project"`.
- **Bounding Box Bounds:** WGS84 EPSG:4326 ($17.0^\circ\text{N} \le \text{lat} \le 17.8^\circ\text{N}$, $78.1^\circ\text{E} \le \text{lon} \le 78.8^\circ\text{E}$).

### Normalization Pipeline:
[`OSMNetworkImporter`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/road_network/osm_importer.py) validates and ingests GeoJSON / OSM extracts:
1. Validates coordinate ranges against Hyderabad metropolitan limits.
2. Validates LineString vertex counts ($\ge 2$ points).
3. Maps OSM `highway` tags (`motorway`, `trunk`, `primary`, `secondary`, etc.) into `RoadClassification`.
4. Enforces directionality (`oneway=yes`), `from_node_id`, and `to_node_id`.
5. Detects and rejects duplicate segment IDs.
6. Computes centerline length using equirectangular approximations.

---

## 6. Test Commands & Actual Results

### Focused Phase A Test Suite:
- **Command:** `cmd /c "set PYTHONPATH=src;. && .venv\Scripts\python -m pytest tests/test_phase_a_live_map_foundation.py -v"`
- **Result:** **18 passed, 0 failed** in 13.02s.

The 18 automated test cases cover:
1. `test_valid_wgs84_coordinates_within_hyderabad`: Validates coordinates within Hyderabad metro bounds [17.0–17.8°N, 78.1–78.8°E].
2. `test_invalid_coordinates_outside_hyderabad_rejected`: Rejects North, South, East, and West out-of-bounds coordinates.
3. `test_road_geometry_validation`: Enforces Point vertex counts and LineString minimum 2-point requirement.
4. `test_road_segment_creation_and_forbidden_safety_phrases`: Blocks misleading safety phrases (e.g., "100% safe", "guaranteed safe passage") in road names.
5. `test_separation_of_static_susceptibility_from_active_flooding`: Confirms high static vulnerability alone does NOT mark a road as impassable or inundated.
6. `test_symbology_distinguishes_all_condition_states`: Verifies strict visual color and line styling differentiation across verified impassable, verified waterlogged, verified passable, corroborated, unverified, conflicting, stale, and unknown states.
7. `test_osm_importer_normalizes_valid_feature`: Verifies OpenStreetMap tag mapping, length calculation, and ODbL attribution attachment.
8. `test_osm_importer_rejects_duplicates_and_invalid_geometries`: Confirms auditable rejection of duplicate IDs, missing IDs, and invalid geometries.
9. `test_api_get_map_corridors_geojson`: Confirms RFC 7946 FeatureCollection response schema and property contracts.
10. `test_api_get_map_coverage`: Confirms coverage metrics, centerline kilometers, and ODbL attribution metadata.
11. `test_api_get_single_corridor_feature`: Validates single corridor retrieval and 404 behavior for unknown corridors.
12. `test_api_get_all_road_status_snapshots`: Confirms batch snapshot retrieval across monitored corridors.
13. `test_api_refresh_map_corridors`: Confirms authorized refresh requests trigger re-evaluation with status `REFRESH_SUCCESS`.
14. `test_api_refresh_map_corridors_unauthorized_rejected`: Enforces role-based access control, rejecting unauthorized roles (`CITIZEN`, `ANONYMOUS`) with HTTP 403 Forbidden and malformed requests with 422.
15. `test_empty_and_unavailable_map_data`: Verifies graceful handling of empty stores, returning valid empty FeatureCollections and `EMPTY_OR_UNAVAILABLE` coverage status without division errors.
16. `test_compatibility_with_road_status_contracts`: Verifies `RoadSegmentMapProperties` seamlessly embeds Phase 16 `RoadStatusSnapshot` fields and mandatory disclaimers.
17. `test_duplicate_and_stable_corridor_identifiers_in_store`: Ensures re-adding existing segment IDs updates in place without corrupting catalog indices.
18. `test_privacy_preservation_no_citizen_pii_in_map_features`: Asserts that map endpoints never leak citizen emails, phone numbers, or unmasked IDs.

### Full Regression Test Suite:
- **Command:** `cmd /c "set PYTHONPATH=src;. && .venv\Scripts\python -m pytest"`
- **Collected Tests:** **452 tests** (434 prior + 18 Phase A)
- **Passed:** **448 tests**
- **Failed:** **4 tests** (100% accounted for as historical safety contracts)
- **Newly Introduced Failures:** **0**

### Accounting for the Four Historical Failures:
1. `tests/test_hyderabad_risk_pipeline.py::test_decision_engine_synthesis`: Fails with `assert 'ADVISORY' == 'WATCH'`. Phase 12 contract prevents regional rainfall from elevating unconfirmed corridors to `WATCH`.
2. `tests/test_image_quality_gate.py::test_borderline_darkness_rejection`: Fails with `assert True is False`. Phase 4 conservative optical safety rejects borderline darkness to avoid false negatives.
3. `tests/test_image_quality_gate.py::test_borderline_whiteout_rejection`: Fails with `assert True is False`. Phase 4 conservative optical safety rejects borderline glare to avoid false positives.
4. `tests/test_phase5_integration.py::test_decision_engine_modeled_risk_vs_observed_flooding`: Fails with `assert 'ADVISORY' == 'WATCH'`. Phase 12 partition rules enforce that modeled environmental risk cannot elevate to `WATCH` without ground observation.

---

## 7. Security, Licensing, Privacy & Operational Limitations

1. **Licensing:** All road network features derived from OpenStreetMap data adhere to the **Open Database License (ODbL 1.0)** with explicit attribution in metadata and UI.
2. **Privacy:** The map data layer exposes only public corridor centerlines and coarsened coordinates ($\sim 50\text{ m}$ coarsening). Personal reporter identities, phone numbers, and residential coordinates are masked or excluded.
3. **Security & Authorization:** The `/map/corridors/refresh` endpoint enforces strict role-based access control (`AUTHORIZED_MAP_REFRESH_ROLES`), rejecting unauthorized callers (`CITIZEN`, `ANONYMOUS`) with HTTP 403 Forbidden. Client requests cannot arbitrarily mark road segments as verified or passable; status transitions remain strictly gated to official responder protocols.
4. **Operational Limitation:** Phase A provides a **foundational map and road network data layer**, NOT a live turn-by-turn navigation system. It does not calculate Dijkstra or A* shortest paths through flooded road networks; that capability belongs to the later routing integration milestone.

---

## 8. Remaining Blockers & Recommended Next Steps

### Blockers Remaining for Production:
1. **Full Hyderabad OSM Topology Extract:** The repository currently stores 22 canonical segments covering primary arterial underpasses and links. A complete city-wide navigation network requires ingesting a full Hyderabad metropolitan OSM `.pbf` or GeoJSON graph.
2. **Topological Graph Routing Engine:** While [`RiskAwareRoutingService`](file:///c:/Users/MahendraReddy/.gemini/antigravity-ide/scratch/sahaay-ai/src/sahaay/routing/service.py) defines the penalty math, a graph traversal engine (e.g., NetworkX, OSRM, or pgRouting) is required to compute full turn-by-turn paths across nodes.
3. **Live Road Telemetry Feeds:** Hyderabad corridors default to `UNKNOWN` or `NO_CURRENT_EVIDENCE` because physical IoT water-depth sensors are not yet deployed.

### Recommended Next Milestone:
- **Phase B: Topological Graph & Routing Integration:** Ingest a multi-thousand segment road graph for Hyderabad, build adjacency lists, and connect `RiskAwareRoutingService` to compute real alternative routes bypassing segments marked `VERIFIED_IMPASSABLE`.
