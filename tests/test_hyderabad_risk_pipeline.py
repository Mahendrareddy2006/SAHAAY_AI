"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Pipeline Tests
Validates dataset parsers, coordinate checks, QC anomaly filters, non-silent missingness,
spatial proximity calculations, IMD threshold calibration, API endpoints, Decision Engine
synthesis, and preservation of the historical Vision V4 readiness gate.
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.decision.contracts import DecisionInput, evaluate_decision
from sahaay.hyderabad_risk.features import (
    compute_drain_proximity,
    compute_hotspot_proximity,
    compute_rolling_rainfall,
    compute_waterbody_proximity,
    find_nearest_telemetry_station,
    haversine_distance_m,
    point_to_segment_distance_m,
)
from sahaay.hyderabad_risk.ingest import (
    load_monthly_rainfall,
    load_telemetry_rainfall,
    parse_drains_kml,
    parse_flooding_hotspots,
    parse_waterbodies_geojson,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.validate import (
    HYDERABAD_BBOX,
    TELANGANA_BBOX,
    validate_drains,
    validate_hotspots,
    validate_monthly_rainfall,
    validate_telemetry_rainfall,
    validate_waterbodies,
)
from sahaay.hyderabad_risk.vulnerability_engine import evaluate_road_vulnerability_engine

RAW_DIR = Path("data/hyderabad_risk/raw")
DERIVED_DIR = Path("data/hyderabad_risk/derived")


# ---------------------------------------------------------------------------
# 1. Dataset Ingestion & Coordinate Validation Tests
# ---------------------------------------------------------------------------

def test_kml_hotspots_ingestion_and_schema():
    hotspots = parse_flooding_hotspots(RAW_DIR / "flooding_locations.kml")
    assert len(hotspots) == 23, f"Expected 23 chronic hotspots, got {len(hotspots)}"
    
    # Coordinate validation
    for h in hotspots:
        assert HYDERABAD_BBOX["min_lat"] <= h.latitude <= HYDERABAD_BBOX["max_lat"]
        assert HYDERABAD_BBOX["min_lon"] <= h.longitude <= HYDERABAD_BBOX["max_lon"]
        # Coordinate inversion safeguard: lat should be ~17.4, lon should be ~78.4
        assert h.latitude < h.longitude, f"Latitude {h.latitude} and longitude {h.longitude} appear inverted!"

    report = validate_hotspots(hotspots)
    assert report["status"] == "PASS"
    assert report["within_hyderabad_bbox"] == 23


def test_drains_ingestion_and_geometry():
    drains = parse_drains_kml(RAW_DIR / "hyderabad_drains.kml")
    assert len(drains) > 50, "Expected at least 50 drain segments"
    
    total_pts = sum(d.point_count for d in drains)
    assert total_pts > 10000, f"Expected >10,000 points, got {total_pts}"

    report = validate_drains(drains)
    assert report["status"] == "PASS"


def test_waterbodies_ingestion_and_centroids():
    waterbodies = parse_waterbodies_geojson(RAW_DIR / "greater_hyderabad_waterbodies.geojson")
    assert len(waterbodies) == 2324, f"Expected 2324 waterbodies, got {len(waterbodies)}"
    
    # Check valid centroids
    for wb in waterbodies[:50]:
        assert TELANGANA_BBOX["min_lat"] <= wb.centroid_lat <= TELANGANA_BBOX["max_lat"]
        assert TELANGANA_BBOX["min_lon"] <= wb.centroid_lon <= TELANGANA_BBOX["max_lon"]

    report = validate_waterbodies(waterbodies)
    assert report["status"] == "PASS"


def test_monthly_rainfall_ingestion_and_climatology():
    monthly_df = load_monthly_rainfall(RAW_DIR / "hyderabad_monthly_rainfall_1901_2021.csv")
    assert len(monthly_df) == 121, "Expected 121 years from 1901 to 2021"
    
    report = validate_monthly_rainfall(monthly_df)
    assert report["status"] == "PASS"
    assert report["negative_rainfall_values"] == 0
    assert report["missing_null_values"] == 0
    assert report["mean_annual_monsoon_rainfall_mm"] > 500.0


# ---------------------------------------------------------------------------
# 2. Telemetry Quality Control & Anomaly Filtering Tests
# ---------------------------------------------------------------------------

def test_telemetry_qc_filtering_and_anomalies():
    telemetry_raw = load_telemetry_rainfall(RAW_DIR / "telangana_hourly_telemetry_rainfall_2021_2025.csv")
    clean_df, qc_report = validate_telemetry_rainfall(telemetry_raw)
    
    # Negative sensor error detection
    assert qc_report["qc_negative_sensor_faults"] == 19
    # Accumulator detection (>250mm cumulative gauge values)
    assert qc_report["qc_accumulator_spikes_over_250mm"] > 30000
    # Duplicate timestamps deduplicated
    assert qc_report["duplicate_timestamps_removed"] > 5000
    # Clean records contain valid qc flags
    assert qc_report["valid_qc_records"] > 25000
    
    # Check that nearest station is identified
    assert "station" in qc_report["closest_station_to_hyderabad"]
    assert qc_report["closest_station_to_hyderabad"]["dist_km"] > 40.0


def test_non_silent_missingness_mandate():
    """
    Mandate: Missing rainfall must NEVER be silently imputed as 0.0 mm.
    """
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=None,  # Missing!
        rain_3h_mm=None,
        station_dist_km=10.0,
        data_freshness_hours=0.0
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "rain_1h_mm" in res.missing_inputs
    assert any("missing" in w.lower() for w in res.warnings)


# ---------------------------------------------------------------------------
# 3. Spatial Math & Geometry Tests
# ---------------------------------------------------------------------------

def test_haversine_and_geometry():
    # Hyderabad Charminar (17.3616, 78.4747) to Secunderabad Station (17.4344, 78.5015) is ~8.5km
    dist_m = haversine_distance_m(17.3616, 78.4747, 17.4344, 78.5015)
    assert 8000.0 < dist_m < 9500.0

    # Point to segment orthogonal distance
    # Segment along latitude 17.40 from lon 78.40 to 78.50
    # Point at lat 17.401, lon 78.45 (approx 111 meters north of segment)
    seg_dist = point_to_segment_distance_m(
        p_lat=17.401, p_lon=78.45,
        a_lat=17.400, a_lon=78.40,
        b_lat=17.400, b_lon=78.50
    )
    assert 100.0 < seg_dist < 125.0


def test_corridor_proximities():
    hotspots = parse_flooding_hotspots(RAW_DIR / "flooding_locations.kml")
    drains = parse_drains_kml(RAW_DIR / "hyderabad_drains.kml")
    waterbodies = parse_waterbodies_geojson(RAW_DIR / "greater_hyderabad_waterbodies.geojson")
    
    # Tolichowki Flyover Underpass (17.4023, 78.4112)
    dist_h, name_h = compute_hotspot_proximity(17.4023, 78.4112, hotspots)
    assert dist_h < 1500.0
    assert len(name_h) > 0

    dist_d = compute_drain_proximity(17.4023, 78.4112, drains)
    assert dist_d < 1000.0

    dist_wb, name_wb = compute_waterbody_proximity(17.4023, 78.4112, waterbodies)
    assert dist_wb < 1500.0


# ---------------------------------------------------------------------------
# 4. Rainfall Risk & Road Vulnerability Baseline Engine Tests
# ---------------------------------------------------------------------------

def test_rainfall_engine_imd_tiers():
    # Tier 1: Dry / Light
    r_dry = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=0.0)
    assert r_dry.risk_category == "LOW"

    r_light = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=5.0)
    assert r_light.risk_category == "LOW"

    # Tier 2: Moderate (7.5 to 15.0 mm/hr)
    r_mod = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=12.0)
    assert r_mod.risk_category == "MEDIUM"

    # Tier 3: Heavy (15.0 to 35.0 mm/hr)
    r_heavy = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=25.0)
    assert r_heavy.risk_category == "HIGH"
    assert "IMD_HEAVY_INTENSITY_EXCEEDED" in r_heavy.reason_codes

    # Tier 4: Very Heavy (>35.0 mm/hr)
    r_vheavy = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=50.0)
    assert r_vheavy.risk_category == "CRITICAL"
    assert "IMD_VERY_HEAVY_INTENSITY_EXCEEDED" in r_vheavy.reason_codes

    # Multi-window flash surge
    r_surge = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=10.0, rain_3h_mm=45.0)
    assert r_surge.risk_category == "HIGH"
    assert "ROLLING_3H_FLASH_SURGE" in r_surge.reason_codes

def test_confidence_degradation():
    # Ideal nearby fresh observation with all 4 rolling windows
    c_ideal = evaluate_rainfall_risk_engine(
        "LOC",
        rain_1h_mm=10.0,
        rain_3h_mm=10.0,
        rain_6h_mm=10.0,
        rain_24h_mm=10.0,
        station_dist_km=5.0,
        data_freshness_hours=0.5,
    )
    assert c_ideal.confidence == 1.0

    # Distant station (50 km away)
    c_dist = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=10.0, station_dist_km=50.0, data_freshness_hours=0.5)
    assert c_dist.confidence < 1.0

    # Stale data (4 hours old)
    c_stale = evaluate_rainfall_risk_engine("LOC", rain_1h_mm=10.0, station_dist_km=5.0, data_freshness_hours=4.0)
    assert c_stale.confidence < 1.0
    assert any("stale" in w.lower() for w in c_stale.warnings)


def test_road_vulnerability_engine():
    # Direct hotspot zone
    v_severe = evaluate_road_vulnerability_engine(
        location_id="VULN-01",
        road_name="Severe Nala Road",
        dist_to_hotspot_m=50.0,
        nearest_hotspot_name="HOTSPOT A",
        dist_to_drain_m=20.0,
        dist_to_waterbody_m=100.0,
        nearest_waterbody_name="LAKE A"
    )
    assert v_severe.vulnerability_category == "SEVERE"
    assert v_severe.vulnerability_index >= 0.70

    # Upland road far from drains or hotspots
    v_low = evaluate_road_vulnerability_engine(
        location_id="VULN-02",
        road_name="Highland Ridge",
        dist_to_hotspot_m=2000.0,
        nearest_hotspot_name="HOTSPOT B",
        dist_to_drain_m=1500.0,
        dist_to_waterbody_m=2000.0,
        nearest_waterbody_name="LAKE B"
    )
    assert v_low.vulnerability_category == "LOW"
    assert v_low.vulnerability_index == 0.0


# ---------------------------------------------------------------------------
# 5. API Endpoints & Decision Engine Synthesis Tests
# ---------------------------------------------------------------------------

def test_api_risk_endpoints():
    client = TestClient(app)

    # Test rainfall estimate
    res_rain = client.post("/api/v1/risk/rainfall/estimate", json={
        "location_id": "HYD-LOC-001",
        "rain_1h_mm": 20.0,
        "rain_3h_mm": 35.0,
        "station_dist_km": 10.0,
        "data_freshness_hours": 0.5
    })
    assert res_rain.status_code == 200
    data_rain = res_rain.json()
    assert data_rain["risk_category"] == "HIGH"
    assert data_rain["confidence"] > 0.8

    # Test road vulnerability
    res_vuln = client.post("/api/v1/risk/vulnerability/calculate", json={
        "location_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
        "dist_to_hotspot_m": 120.0,
        "nearest_hotspot_name": "GALAXY TOLICHOWKI",
        "dist_to_drain_m": 80.0,
        "dist_to_waterbody_m": 450.0,
        "nearest_waterbody_name": "Shah Hatim Talab"
    })
    assert res_vuln.status_code == 200
    data_vuln = res_vuln.json()
    assert data_vuln["vulnerability_category"] == "HIGH"

    # Test corridor list endpoint
    res_corr = client.get("/api/v1/risk/corridors")
    assert res_corr.status_code == 200
    assert res_corr.json()["total_corridors"] == 20


def test_decision_engine_synthesis():
    """
    Test Decision Engine synthesizes high rainfall + high vulnerability into WATCH alert level
    when station proximity is verified as local urban telemetry.
    """
    client = TestClient(app)

    payload = {
        "location_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
        "vision_predicted_class": None,
        "vision_confidence": None,
        "vision_is_ambiguous": False,
        "rainfall_risk_category": "HIGH",
        "rainfall_risk_score": 0.70,
        "rainfall_proximity_tier": "LOCAL_URBAN",
        "vulnerability_category": "HIGH",
        "vulnerability_index": 0.55,
        "report_age_minutes": 10.0,
        "is_field_verified": False,
        "citizen_report_count_in_zone": 1
    }

    res = client.post("/api/v1/decision/evaluate", json=payload)
    assert res.status_code == 200
    out = res.json()
    assert out["alert_level"] == "WATCH"
    assert out["hazard_nature"] == "PREDICTED_RISK"
    assert "anticipated" in out["explanation"].lower()


def test_decision_engine_unknown_proximity_safety_downgrade():
    """
    Mandatory Safety Contract: Missing or UNKNOWN station proximity cannot produce
    an actionable WATCH alert on rainfall alone, even with HIGH rainfall and HIGH vulnerability.
    It MUST be downgraded to qualified ADVISORY to prevent uncalibrated dispatch.
    """
    client = TestClient(app)

    payload = {
        "location_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
        "rainfall_risk_category": "HIGH",
        "rainfall_risk_score": 0.70,
        "rainfall_proximity_tier": "UNKNOWN",
        "vulnerability_category": "HIGH",
        "vulnerability_index": 0.55,
        "report_age_minutes": 10.0,
        "is_field_verified": False,
        "citizen_report_count_in_zone": 0
    }

    res = client.post("/api/v1/decision/evaluate", json=payload)
    assert res.status_code == 200
    out = res.json()
    assert out["alert_level"] == "ADVISORY"
    assert out["hazard_nature"] == "PREDICTED_RISK"
    assert "UNKNOWN_PROXIMITY_TELEMETRY_DISCOUNTED" in out["reason_codes"]
    assert out["is_actionable_for_crews"] is False



# ---------------------------------------------------------------------------
# 6. Vision V4 Readiness Gate Preservation Test
# ---------------------------------------------------------------------------

def test_vision_v4_gate_preservation():
    """
    Mandate: Phase 4 must NOT weaken or bypass the Vision V4 readiness gate.
    Check that Phase 3 audit still records NO-GO and pending authorizations.
    """
    audit_file = Path("reports/vision_integrity/v4_phase3_pilot_audit.json")
    assert audit_file.exists(), "Vision V4 Phase 3 pilot audit must remain intact."

    with open(audit_file, "r", encoding="utf-8") as f:
        audit = json.load(f)

    assert audit["permission_summary"]["approved_streams"] == 0
    assert audit["data_inventory"]["real_world_images_received"] == 0
    assert "maintain no-go" in audit["recommendation"].lower()

    # Verify historical vision checkpoints still exist and are untouched
    checkpoints = [
        Path("models/vision/best_model.pt"),
        Path("models/vision/v2/model_v2.pt"),
        Path("models/vision/v3/model_v3_monsoon.pt"),
    ]
    for cp in checkpoints:
        assert cp.exists(), f"Historical checkpoint {cp} must be preserved."
