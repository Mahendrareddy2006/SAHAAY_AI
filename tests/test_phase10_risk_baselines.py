"""
Unit and integration test suite for Sahaay AI Phase 10:
Rainfall and Road-Vulnerability Rules-Based Baselines, Edge Cases,
Missing-Data Semantics, and Monotonicity Checks.
"""

import pytest
import numpy as np

from sahaay.hyderabad_risk.rainfall_engine import (
    evaluate_rainfall_risk_engine,
    IMD_THRESHOLDS,
)
from sahaay.hyderabad_risk.vulnerability_engine import (
    evaluate_road_vulnerability_engine,
    calculate_hotspot_subscore,
    calculate_drain_subscore,
    calculate_waterbody_subscore,
)
from sahaay.hyderabad_risk.features import (
    haversine_distance_m,
    point_to_segment_distance_m,
)


# ==============================================================================
# 1. Rainfall Engine Intensity Threshold Boundaries
# ==============================================================================

@pytest.mark.parametrize("rain_mm,expected_cat", [
    (0.0, "LOW"),
    (5.0, "LOW"),
    (7.5, "MEDIUM"),
    (14.9, "MEDIUM"),
    (15.0, "HIGH"),
    (34.9, "HIGH"),
    (35.0, "CRITICAL"),
    (100.0, "CRITICAL"),
    (150.0, "CRITICAL"),
])
def test_rainfall_intensity_category_boundaries(rain_mm, expected_cat):
    """Verify exact category thresholds matching IMD operational standards."""
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=rain_mm,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res.risk_category == expected_cat, f"Rain {rain_mm}mm expected {expected_cat}, got {res.risk_category}"


def test_rainfall_risk_score_monotonicity():
    """Verify that risk score is strictly non-decreasing as hourly rainfall increases."""
    prev_score = -1.0
    for r in np.linspace(0.0, 100.0, 100):
        res = evaluate_rainfall_risk_engine(
            location_id="TEST-LOC",
            rain_1h_mm=r,
            station_dist_km=0.0,
            data_freshness_hours=0.0,
        )
        assert res.risk_score >= prev_score, f"Score decreased at {r}mm: {res.risk_score} < {prev_score}"
        prev_score = res.risk_score


# ==============================================================================
# 2. Missing-Value & Telemetry Semantic Integrity
# ==============================================================================

def test_missing_hourly_rain_triggers_unknown_never_low():
    """
    CRITICAL RULE: Missing rainfall observation must NEVER be silently imputed as 0.0mm.
    Must return UNKNOWN category with confidence 0.10 and risk_score 0.0.
    """
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=None,
        station_dist_km=5.0,
        data_freshness_hours=1.0,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert res.confidence == 0.10
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes
    assert "rain_1h_mm" in res.missing_inputs
    assert len(res.warnings) > 0


def test_negative_rainfall_is_clamped():
    """Negative sensor glitch is clamped to 0.0mm without crashing."""
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=-15.5,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res.risk_category == "LOW"
    assert res.risk_score == 0.02


# ==============================================================================
# 3. Multi-Window Amplification & Confidence Discounting
# ==============================================================================

def test_rolling_3h_surge_escalation():
    """Light base rain (5mm) with rolling 3h surge (45mm >= 40mm) escalates to HIGH."""
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=5.0,
        rain_3h_mm=45.0,
    )
    assert res.risk_category == "HIGH"
    assert res.risk_score >= 0.70
    assert "ROLLING_3H_FLASH_SURGE" in res.reason_codes


def test_rolling_24h_saturation_escalation():
    """Light base rain (5mm) with rolling 24h extreme saturation (120mm >= 115.5mm) escalates to CRITICAL."""
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=5.0,
        rain_24h_mm=120.0,
    )
    assert res.risk_category == "CRITICAL"
    assert res.risk_score >= 0.85
    assert "ROLLING_24H_EXTREME_SATURATION" in res.reason_codes


def test_station_distance_and_freshness_confidence_penalties():
    """Verify confidence discounting for distance (>15km) and staleness (>1.5h)."""
    # 45km station -> 30km beyond 15km threshold -> 0.30 penalty -> confidence = 0.70
    res_dist = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=20.0,
        rain_6h_mm=20.0,
        rain_24h_mm=20.0,
        station_dist_km=45.0,
        data_freshness_hours=0.5,
    )
    assert round(res_dist.confidence, 2) == 0.70

    # 4.0h age -> 2.5h beyond 1.5h threshold -> 0.20 penalty -> confidence = 0.80
    res_stale = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=20.0,
        rain_6h_mm=20.0,
        rain_24h_mm=20.0,
        station_dist_km=2.0,
        data_freshness_hours=4.0,
    )
    assert round(res_stale.confidence, 2) == 0.80

    # 3 missing windows -> 3 * 0.08 = 0.24 penalty -> confidence = 0.76
    res_win = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=None,
        rain_6h_mm=None,
        rain_24h_mm=None,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert round(res_win.confidence, 2) == 0.76


# ==============================================================================
# 4. Road Vulnerability Engine & Monotonicity
# ==============================================================================

def test_vulnerability_proximity_subscores_monotonicity():
    """Verify that all three proximity subscores decrease monotonically with distance."""
    # Hotspot
    h_dists = [0.0, 50.0, 150.0, 250.0, 500.0, 750.0, 1000.0, 1500.0]
    h_scores = [calculate_hotspot_subscore(d) for d in h_dists]
    for i in range(len(h_scores) - 1):
        assert h_scores[i] >= h_scores[i + 1]

    # Drain
    d_dists = [0.0, 25.0, 75.0, 100.0, 200.0, 350.0, 500.0, 800.0]
    d_scores = [calculate_drain_subscore(d) for d in d_dists]
    for i in range(len(d_scores) - 1):
        assert d_scores[i] >= d_scores[i + 1]

    # Waterbody
    w_dists = [0.0, 50.0, 100.0, 200.0, 400.0, 600.0, 800.0, 1200.0]
    w_scores = [calculate_waterbody_subscore(d) for d in w_dists]
    for i in range(len(w_scores) - 1):
        assert w_scores[i] >= w_scores[i + 1]


def test_vulnerability_weighted_index_calculation():
    """Verify multi-criteria weighting: 0.45*hotspot + 0.35*drain + 0.20*waterbody."""
    res = evaluate_road_vulnerability_engine(
        location_id="CORR-TEST-01",
        road_name="Tolichowki Test Underpass",
        dist_to_hotspot_m=50.0,     # s_h = 1.0 - 0.50*(50/250) = 0.90
        nearest_hotspot_name="Tolichowki Hotspot",
        dist_to_drain_m=50.0,       # s_d = 1.0 - 0.40*(50/100) = 0.80
        dist_to_waterbody_m=100.0,  # s_w = 1.0 - 0.50*(100/200) = 0.75
        nearest_waterbody_name="Shah Hatim Lake",
    )
    # Expected v_index = 0.45*0.90 + 0.35*0.80 + 0.20*0.75 = 0.405 + 0.280 + 0.150 = 0.835 -> SEVERE
    assert res.vulnerability_index == 0.835
    assert res.vulnerability_category == "SEVERE"
    assert "dist_to_hotspot_m" in res.contributing_features
    assert "road_elevation_m (Digital Elevation Model / LiDAR)" in res.missing_data


# ==============================================================================
# 5. Geospatial Haversine & Determinism
# ==============================================================================

def test_haversine_distance_accuracy_and_determinism():
    """Verify Haversine distance formula accuracy across known landmark points."""
    # Lakdikapul (17.4042, 78.4651) to Khairatabad (17.4116, 78.4611) ~ 925.8m
    d1 = haversine_distance_m(17.4042, 78.4651, 17.4116, 78.4611)
    d2 = haversine_distance_m(17.4042, 78.4651, 17.4116, 78.4611)
    assert 920.0 <= d1 <= 930.0
    assert d1 == d2, "Haversine calculation must be strictly deterministic"
