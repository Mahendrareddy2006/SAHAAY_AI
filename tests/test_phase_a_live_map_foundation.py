"""
Sahaay AI - Phase A: Live Map and Road Network Foundation Test Suite
(tests/test_phase_a_live_map_foundation.py)

Tests for:
1. Valid and invalid corridor geometry (coordinate bounding box, LineString vertices).
2. Stable corridor identifiers, duplicate detection, and malformed inputs.
3. Separation of static road attributes from dynamic flood observations.
4. Map API response contracts (GeoJSON FeatureCollection, snapshots, coverage report).
5. Symbology styling for verified, unverified, conflicting, stale, and unknown states.
6. OpenStreetMap importer normalization, tag mapping, and attribution tracking (ODbL 1.0).
7. Safety invariants: absence of evidence is never marked as safe passage or zero risk.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.road_network.schemas import (
    RoadClassification,
    RoadMonitoringStatus,
    GeoJSONGeometryType,
    RoadGeometry,
    RoadSegment,
    RoadSegmentMapFeature,
    RoadNetworkFeatureCollection,
    MapCoverageReport,
    HYDERABAD_MIN_LAT,
    HYDERABAD_MAX_LAT,
    HYDERABAD_MIN_LON,
    HYDERABAD_MAX_LON,
    validate_wgs84_coordinate,
    MANDATORY_MAP_DATA_DISCLAIMER,
)
from sahaay.road_network.store import (
    RoadNetworkStore,
    default_road_network_store,
    calculate_symbology,
)
from sahaay.road_network.osm_importer import (
    OSMNetworkImporter,
    OSMImportResult,
)
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    RoadStatusSnapshot,
)


client = TestClient(app)


# ==============================================================================
# 1. Geometry Validation Tests
# ==============================================================================

def test_valid_wgs84_coordinates_within_hyderabad():
    """Valid coordinates within Hyderabad bounding box pass cleanly."""
    lon, lat = validate_wgs84_coordinate(78.4500, 17.4200)
    assert lon == 78.4500
    assert lat == 17.4200


def test_invalid_coordinates_outside_hyderabad_rejected():
    """Coordinates outside Hyderabad bounding box raise ValueError."""
    # North of Hyderabad
    with pytest.raises(ValueError, match="outside Hyderabad bounds"):
        validate_wgs84_coordinate(78.4500, 19.5000)

    # South of Hyderabad
    with pytest.raises(ValueError, match="outside Hyderabad bounds"):
        validate_wgs84_coordinate(78.4500, 16.5000)

    # West of Hyderabad (e.g. Mumbai)
    with pytest.raises(ValueError, match="outside Hyderabad bounds"):
        validate_wgs84_coordinate(72.8500, 17.4200)

    # East of Hyderabad (e.g. Vijayawada)
    with pytest.raises(ValueError, match="outside Hyderabad bounds"):
        validate_wgs84_coordinate(80.6500, 17.4200)


def test_road_geometry_validation():
    """Valid Point and LineString geometries pass; malformed ones fail."""
    # Valid LineString
    geom_valid = RoadGeometry(
        type=GeoJSONGeometryType.LINESTRING,
        coordinates=[[78.4060, 17.3995], [78.4112, 17.4023]],
    )
    assert geom_valid.type == GeoJSONGeometryType.LINESTRING
    assert len(geom_valid.coordinates) == 2

    # Malformed LineString with only 1 point fails
    with pytest.raises(ValueError, match="at least 2 coordinate pairs"):
        RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4060, 17.3995]],
        )

    # Malformed Point with only 1 coordinate fails
    with pytest.raises(ValueError, match="at least"):
        RoadGeometry(
            type=GeoJSONGeometryType.POINT,
            coordinates=[78.4060],
        )


# ==============================================================================
# 2. RoadSegment Model & Safety Invariant Tests
# ==============================================================================

def test_road_segment_creation_and_forbidden_safety_phrases():
    """Road segments cannot contain misleading absolute safety claims in road names."""
    geom = RoadGeometry(
        type=GeoJSONGeometryType.LINESTRING,
        coordinates=[[78.4060, 17.3995], [78.4112, 17.4023]],
    )

    # Valid name
    seg = RoadSegment(
        segment_id="HYD-LOC-TEST-01",
        road_name="Tolichowki Main Flyover Link",
        road_class=RoadClassification.PRIMARY,
        geometry=geom,
    )
    assert seg.segment_id == "HYD-LOC-TEST-01"
    assert seg.source_license == "ODbL-1.0"

    # Forbidden phrase "100% safe" raises ValueError
    with pytest.raises(ValueError, match="misleading safety claim"):
        RoadSegment(
            segment_id="HYD-LOC-TEST-02",
            road_name="Tolichowki 100% safe corridor",
            road_class=RoadClassification.PRIMARY,
            geometry=geom,
        )


def test_separation_of_static_susceptibility_from_active_flooding():
    """High static vulnerability index does NOT automatically mark road as flooded or impassable."""
    store = RoadNetworkStore()
    seg = store.get_segment("HYD-LOC-001")
    assert seg is not None
    assert seg.static_vulnerability_index == 0.532
    assert seg.static_vulnerability_category == "HIGH"

    # With no dynamic flood observations, feature must reflect UNKNOWN or NO_CURRENT_EVIDENCE, NOT impassable
    feat = store.build_map_feature(seg, status_snapshot=None)
    assert feat.properties.condition_state in [RoadConditionState.UNKNOWN, RoadConditionState.NO_CURRENT_EVIDENCE]
    assert feat.properties.condition_state != RoadConditionState.VERIFIED_IMPASSABLE
    assert feat.properties.marker_color == "#64748b"  # Neutral slate gray
    assert feat.properties.alert_badge == "UNKNOWN"
    assert "DOES NOT imply safe passage" in feat.properties.disclaimer


# ==============================================================================
# 3. Symbology Styling & Status Representation Tests
# ==============================================================================

def test_symbology_distinguishes_all_condition_states():
    """Visual styles strictly separate verified, unverified, conflicting, stale, and unknown states."""
    # 1. Verified Impassable -> Crimson Red Solid
    s_impassable = calculate_symbology(
        RoadConditionState.VERIFIED_IMPASSABLE,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.VERIFIED_BY_RESPONDER,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_impassable["marker_color"] == "#e11d48"
    assert s_impassable["stroke_style"] == "solid"
    assert s_impassable["stroke_weight"] == 6

    # 2. Verified Passable -> Emerald Green Solid
    s_passable = calculate_symbology(
        RoadConditionState.VERIFIED_PASSABLE,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.VERIFIED_BY_RESPONDER,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_passable["marker_color"] == "#10b981"
    assert s_passable["stroke_style"] == "solid"

    # 3. Verified Waterlogged -> Deep Orange Solid
    s_waterlogged = calculate_symbology(
        RoadConditionState.VERIFIED_WATERLOGGED,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.VERIFIED_BY_RESPONDER,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_waterlogged["marker_color"] == "#f97316"
    assert s_waterlogged["stroke_style"] == "solid"

    # 4. Corroborated Reports -> Orange Dashed
    s_corroborated = calculate_symbology(
        RoadConditionState.CORROBORATED,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.CORROBORATED,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_corroborated["marker_color"] == "#f97316"
    assert s_corroborated["stroke_style"] == "dashed"

    # 5. Unverified Report -> Amber Dashed
    s_unverified = calculate_symbology(
        RoadConditionState.UNVERIFIED,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.UNVERIFIED,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_unverified["marker_color"] == "#f59e0b"
    assert s_unverified["stroke_style"] == "dashed"

    # 6. Conflicting Evidence -> Purple Dashed
    s_conflict = calculate_symbology(
        RoadConditionState.CONFLICTING,
        RoadFreshnessCategory.FRESH,
        RoadVerificationState.UNVERIFIED,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_conflict["marker_color"] == "#a855f7"
    assert s_conflict["stroke_style"] == "dashed"

    # 7. Stale Data -> Muted Stone Gray
    s_stale = calculate_symbology(
        RoadConditionState.STALE,
        RoadFreshnessCategory.STALE,
        RoadVerificationState.CORROBORATED,
        RoadMonitoringStatus.MONITORED_CORRIDOR,
    )
    assert s_stale["marker_color"] == "#78716c"

    # 8. Unknown / Unmonitored -> Slate Gray (never green)
    s_unknown = calculate_symbology(
        RoadConditionState.UNKNOWN,
        RoadFreshnessCategory.UNKNOWN,
        RoadVerificationState.UNMONITORED,
        RoadMonitoringStatus.UNMONITORED_NETWORK,
    )
    assert s_unknown["marker_color"] == "#64748b"
    assert s_unknown["stroke_style"] == "dashed"


# ==============================================================================
# 4. OpenStreetMap Importer & Normalization Tests
# ==============================================================================

def test_osm_importer_normalizes_valid_feature():
    """OSM importer extracts tags, validates LineString, and computes length."""
    importer = OSMNetworkImporter(default_zone="West Zone")
    raw_feature = {
        "id": "way/100200300",
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[78.4100, 17.4010], [78.4150, 17.4040]],
        },
        "properties": {
            "name": "Tolichowki Internal Service Road",
            "highway": "secondary",
            "oneway": "yes",
            "maxspeed": "40 km/h",
            "lanes": "2",
        },
    }

    result = importer.import_geojson_features({"type": "FeatureCollection", "features": [raw_feature]})
    assert result.total_records_processed == 1
    assert result.valid_segments_imported == 1
    assert result.invalid_records_rejected == 0

    seg = result.imported_segments[0]
    assert seg.segment_id == "way/100200300"
    assert seg.road_class == RoadClassification.SECONDARY
    assert seg.is_one_way is True
    assert seg.speed_limit_kph == 40
    assert seg.lanes_count == 2
    assert seg.length_meters > 0.0
    assert "© OpenStreetMap contributors, ODbL 1.0" in seg.source_attribution


def test_osm_importer_rejects_duplicates_and_invalid_geometries():
    """OSM importer rejects duplicate IDs and out-of-bounds geometries with clear logs."""
    importer = OSMNetworkImporter()
    raw_features = [
        # Valid feature
        {
            "id": "OSM-001",
            "geometry": {"type": "LineString", "coordinates": [[78.41, 17.40], [78.42, 17.41]]},
            "properties": {"name": "Road A", "highway": "primary"},
        },
        # Duplicate feature with same ID
        {
            "id": "OSM-001",
            "geometry": {"type": "LineString", "coordinates": [[78.41, 17.40], [78.42, 17.41]]},
            "properties": {"name": "Duplicate Road A", "highway": "primary"},
        },
        # Out-of-bounds coordinate feature
        {
            "id": "OSM-002",
            "geometry": {"type": "LineString", "coordinates": [[72.50, 19.50], [72.51, 19.51]]},
            "properties": {"name": "Mumbai Road Outside Hyderabad", "highway": "primary"},
        },
        # Missing ID
        {
            "geometry": {"type": "LineString", "coordinates": [[78.41, 17.40], [78.42, 17.41]]},
            "properties": {"name": "No ID Road"},
        },
    ]

    result = importer.import_geojson_features({"type": "FeatureCollection", "features": raw_features})
    assert result.total_records_processed == 4
    assert result.valid_segments_imported == 1
    assert result.invalid_records_rejected == 3

    issue_codes = [issue.code for issue in result.validation_issues]
    assert "DUPLICATE_IDENTIFIER" in issue_codes
    assert "INVALID_GEOMETRY_COORDINATES" in issue_codes
    assert "MISSING_IDENTIFIER" in issue_codes


# ==============================================================================
# 5. Live Map API Endpoint Tests
# ==============================================================================

def test_api_get_map_corridors_geojson():
    """GET /api/v1/map/corridors/geojson returns compliant FeatureCollection with all 20 corridors."""
    res = client.get("/api/v1/map/corridors/geojson")
    assert res.status_code == 200
    data = res.json()

    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) >= 20

    # Inspect first feature
    f1 = data["features"][0]
    assert f1["type"] == "Feature"
    assert "id" in f1
    assert f1["geometry"]["type"] in ["LineString", "MultiLineString"]
    assert "coordinates" in f1["geometry"]

    props = f1["properties"]
    assert "road_name" in props
    assert "condition_state" in props
    assert "verification_state" in props
    assert "marker_color" in props
    assert "safety_notice" in props
    assert "disclaimer" in props


def test_api_get_map_coverage():
    """GET /api/v1/map/coverage returns coverage metrics and ODbL attribution."""
    res = client.get("/api/v1/map/coverage")
    assert res.status_code == 200
    cov = res.json()

    assert cov["total_segments_mapped"] >= 20
    assert cov["monitored_corridors_count"] >= 20
    assert cov["total_centerline_length_km"] > 0.0
    assert cov["source_license"] == "ODbL-1.0"
    assert "OpenStreetMap" in cov["source_attribution"]
    assert "bounding_box" in cov
    assert cov["bounding_box"]["min_lat"] == HYDERABAD_MIN_LAT


def test_api_get_single_corridor_feature():
    """GET /api/v1/map/corridor/{id} returns feature for valid ID and 404 for unknown."""
    # Valid corridor
    res_valid = client.get("/api/v1/map/corridor/HYD-LOC-001")
    assert res_valid.status_code == 200
    feat = res_valid.json()
    assert feat["id"] == "HYD-LOC-001"
    assert "Tolichowki" in feat["properties"]["road_name"]

    # Unknown corridor
    res_invalid = client.get("/api/v1/map/corridor/UNKNOWN-CORRIDOR-999")
    assert res_invalid.status_code == 404


def test_api_get_all_road_status_snapshots():
    """GET /api/v1/map/road-status/snapshots returns snapshots for monitored corridors."""
    res = client.get("/api/v1/map/road-status/snapshots")
    assert res.status_code == 200
    snapshots = res.json()
    assert isinstance(snapshots, list)
    assert len(snapshots) >= 20

    snap1 = snapshots[0]
    assert "road_segment_id" in snap1
    assert "condition_state" in snap1
    assert "confidence_score" in snap1


def test_api_refresh_map_corridors():
    """POST /api/v1/map/corridors/refresh successfully re-evaluates map features."""
    payload = {
        "caller_role": "DASHBOARD_OPERATOR",
        "caller_id": "TEST-CLIENT-01",
        "reason": "PERIODIC_TEST_SYNC"
    }
    res = client.post("/api/v1/map/corridors/refresh", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "REFRESH_SUCCESS"
    assert data["total_features_refreshed"] >= 20
    assert data["caller_id"] == "TEST-CLIENT-01"


def test_api_refresh_map_corridors_unauthorized_rejected():
    """POST /api/v1/map/corridors/refresh rejects unauthorized roles with 403 Forbidden."""
    # Unauthorized role CITIZEN
    payload_citizen = {
        "caller_role": "CITIZEN",
        "caller_id": "CITIZEN-USER-999",
        "reason": "MALICIOUS_OVERRIDE_ATTEMPT"
    }
    res_citizen = client.post("/api/v1/map/corridors/refresh", json=payload_citizen)
    assert res_citizen.status_code == 403
    assert "not authorized" in res_citizen.json()["detail"]

    # Unauthorized role ANONYMOUS
    payload_anon = {
        "caller_role": "ANONYMOUS",
        "caller_id": "ANON-01",
        "reason": "SYNC"
    }
    res_anon = client.post("/api/v1/map/corridors/refresh", json=payload_anon)
    assert res_anon.status_code == 403

    # Malformed payload (missing caller_id) fails with 422
    res_malformed = client.post("/api/v1/map/corridors/refresh", json={"caller_role": "OPERATOR"})
    assert res_malformed.status_code == 422


def test_empty_and_unavailable_map_data():
    """Empty road network store handles queries and exports gracefully without errors."""
    empty_store = RoadNetworkStore(populate_defaults=False)
    assert len(empty_store.list_segments()) == 0

    # GeoJSON export with 0 segments produces valid empty FeatureCollection
    fc = empty_store.to_geojson_feature_collection()
    assert fc.type == "FeatureCollection"
    assert fc.features == []
    assert fc.metadata["total_features"] == 0

    # Coverage report with 0 segments returns EMPTY_OR_UNAVAILABLE status without division errors
    cov = empty_store.get_coverage_report()
    assert cov.total_segments_mapped == 0
    assert cov.total_centerline_length_km == 0.0
    assert cov.coverage_status == "EMPTY_OR_UNAVAILABLE"
    assert cov.monitored_corridors_count == 0

    # Missing corridor lookup returns None
    assert empty_store.get_segment("HYD-LOC-999") is None


def test_compatibility_with_road_status_contracts():
    """RoadSegmentMapProperties preserves Phase 16 road status contracts and safety notices."""
    store = RoadNetworkStore()
    seg = store.get_segment("HYD-LOC-001")
    assert seg is not None

    snapshot = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name=seg.road_name,
        condition_state=RoadConditionState.VERIFIED_WATERLOGGED,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
        measured_water_depth_cm=35.0,
        has_conflicting_evidence=False,
        evidence_summary="GHMC DRF physical depth check confirmed waterlogging",
        last_status_update_utc="2026-10-27T12:00:00Z",
        evidence_age_minutes=5.0,
    )

    feat = store.build_map_feature(seg, status_snapshot=snapshot)
    assert feat.properties.condition_state == RoadConditionState.VERIFIED_WATERLOGGED
    assert feat.properties.verification_state == RoadVerificationState.VERIFIED_BY_RESPONDER
    assert feat.properties.confidence_score == 0.95
    assert feat.properties.measured_water_depth_cm == 35.0
    assert feat.properties.marker_color == "#f97316"
    assert feat.properties.stroke_style == "solid"
    assert "DOES NOT imply safe passage" in feat.properties.disclaimer
    assert "ADVISORY" in feat.properties.safety_notice


def test_duplicate_and_stable_corridor_identifiers_in_store():
    """Re-adding an existing segment ID updates the entry cleanly without creating duplicates."""
    store = RoadNetworkStore()
    initial_count = len(store.list_segments())

    seg = store.get_segment("HYD-LOC-001")
    assert seg is not None

    # Re-add with modified speed limit
    updated_seg = seg.model_copy(update={"speed_limit_kph": 65})
    store.add_segment(updated_seg)

    # Count must remain unchanged (no duplicate entry created)
    assert len(store.list_segments()) == initial_count
    retrieved = store.get_segment("HYD-LOC-001")
    assert retrieved is not None
    assert retrieved.speed_limit_kph == 65


def test_privacy_preservation_no_citizen_pii_in_map_features():
    """Map GeoJSON features and snapshots never leak citizen phone numbers, emails, or personal names."""
    res = client.get("/api/v1/map/corridors/geojson")
    assert res.status_code == 200
    raw_text = res.text.lower()

    # Common PII indicators
    pii_indicators = ["@gmail.com", "@yahoo.com", "phone_number", "citizen_phone", "reporter_name", "aadhaar"]
    for indicator in pii_indicators:
        assert indicator not in raw_text, f"Potential PII indicator '{indicator}' found in map GeoJSON output!"
