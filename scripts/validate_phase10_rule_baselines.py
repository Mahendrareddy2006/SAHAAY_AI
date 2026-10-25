"""
Sahaay AI — Phase 10 Rules-Based Baseline Validation Tool
Tests boundary conditions, monotonicity, missing-value semantics, and confidence discounting
for rainfall_engine and vulnerability_engine, and exports rule_baseline_validation.json.
"""

import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sahaay.hyderabad_risk.rainfall_engine import (
    evaluate_rainfall_risk_engine,
    IMD_THRESHOLDS
)
from sahaay.hyderabad_risk.vulnerability_engine import (
    evaluate_road_vulnerability_engine,
    calculate_hotspot_subscore,
    calculate_drain_subscore,
    calculate_waterbody_subscore
)
from sahaay.hyderabad_risk.features import haversine_distance_m, point_to_segment_distance_m

def validate_rule_baselines(output_path: str = "reports/phase10/rule_baseline_validation.json"):
    print("Executing Phase 10 Rules-Based Baseline Validation...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    test_results = []

    # 1. Rainfall Boundary Tests
    boundaries = [
        {"input_mm": 0.0, "expected_category": "LOW", "desc": "Dry zero precipitation boundary"},
        {"input_mm": 5.0, "expected_category": "LOW", "desc": "Light rain below 7.5 mm/hr"},
        {"input_mm": 7.5, "expected_category": "MEDIUM", "desc": "IMD moderate threshold boundary (7.5 mm/hr)"},
        {"input_mm": 14.9, "expected_category": "MEDIUM", "desc": "Upper moderate threshold (14.9 mm/hr)"},
        {"input_mm": 15.0, "expected_category": "HIGH", "desc": "IMD heavy threshold boundary (15.0 mm/hr)"},
        {"input_mm": 34.9, "expected_category": "HIGH", "desc": "Upper heavy threshold (34.9 mm/hr)"},
        {"input_mm": 35.0, "expected_category": "CRITICAL", "desc": "IMD very heavy / severe boundary (35.0 mm/hr)"},
        {"input_mm": 100.0, "expected_category": "CRITICAL", "desc": "Cloudburst intensity (100.0 mm/hr)"},
        {"input_mm": 150.0, "expected_category": "CRITICAL", "desc": "Extreme cloudburst saturation (150.0 mm/hr)"},
    ]

    boundary_pass = True
    for b in boundaries:
        res = evaluate_rainfall_risk_engine(
            location_id="TEST-LOC",
            rain_1h_mm=b["input_mm"],
            station_dist_km=2.0,
            data_freshness_hours=0.5
        )
        passed = (res.risk_category == b["expected_category"])
        if not passed:
            boundary_pass = False
        test_results.append({
            "test_group": "rainfall_intensity_boundaries",
            "name": b["desc"],
            "input_1h_mm": b["input_mm"],
            "expected_category": b["expected_category"],
            "observed_category": res.risk_category,
            "risk_score": round(res.risk_score, 4),
            "passed": passed
        })

    # 2. Monotonicity of Rainfall Risk Score
    monotonic_pass = True
    prev_score = -1.0
    for r in np.linspace(0.0, 100.0, 50):
        res = evaluate_rainfall_risk_engine(
            location_id="TEST-LOC",
            rain_1h_mm=r,
            station_dist_km=0.0,
            data_freshness_hours=0.0
        )
        if res.risk_score < prev_score:
            monotonic_pass = False
        prev_score = res.risk_score

    test_results.append({
        "test_group": "monotonicity",
        "name": "Rainfall score monotonic non-decreasing check across 50 increments (0 to 100 mm/hr)",
        "passed": monotonic_pass
    })

    # 3. Missing Value & Unknown Semantic Check
    missing_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=None,
        station_dist_km=5.0,
        data_freshness_hours=1.0
    )
    unknown_pass = (
        missing_res.risk_category == "UNKNOWN" and
        missing_res.risk_score == 0.0 and
        missing_res.confidence == 0.10 and
        "INSUFFICIENT_TELEMETRY_DATA" in missing_res.reason_codes
    )
    test_results.append({
        "test_group": "missing_data_semantics",
        "name": "Missing hourly rain yields UNKNOWN category (never silently assumed 0.0mm)",
        "passed": unknown_pass,
        "observed_category": missing_res.risk_category,
        "observed_confidence": missing_res.confidence
    })

    # 4. Multi-Window Amplification
    surge_3h_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=5.0,  # Light base
        rain_3h_mm=45.0, # Surge >= 40mm
    )
    surge_pass = (surge_3h_res.risk_category == "HIGH" and "ROLLING_3H_FLASH_SURGE" in surge_3h_res.reason_codes)
    test_results.append({
        "test_group": "multi_window_amplification",
        "name": "Rolling 3h surge (45mm) elevates light base rain (5mm) to HIGH category",
        "passed": surge_pass
    })

    sat_24h_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=5.0,
        rain_24h_mm=120.0 # Extreme saturation >= 115.5mm
    )
    sat_pass = (sat_24h_res.risk_category == "CRITICAL" and "ROLLING_24H_EXTREME_SATURATION" in sat_24h_res.reason_codes)
    test_results.append({
        "test_group": "multi_window_amplification",
        "name": "Rolling 24h extreme saturation (120mm) elevates light base rain (5mm) to CRITICAL category",
        "passed": sat_pass
    })

    # 5. Confidence Discounting Penalties
    dist_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=20.0,
        rain_6h_mm=20.0,
        rain_24h_mm=20.0,
        station_dist_km=45.0,  # 30km beyond 15km threshold -> 0.30 penalty
        data_freshness_hours=0.5
    )
    dist_pass = (round(dist_res.confidence, 2) == 0.70)
    test_results.append({
        "test_group": "confidence_discounting",
        "name": "Station distance penalty: 45km station distance discounts confidence from 1.0 to 0.70",
        "passed": dist_pass,
        "observed_confidence": dist_res.confidence
    })

    stale_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=20.0,
        rain_6h_mm=20.0,
        rain_24h_mm=20.0,
        station_dist_km=2.0,
        data_freshness_hours=4.0  # 2.5h beyond 1.5h threshold -> 0.20 penalty
    )
    stale_pass = (round(stale_res.confidence, 2) == 0.80)
    test_results.append({
        "test_group": "confidence_discounting",
        "name": "Data staleness penalty: 4.0h age discounts confidence from 1.0 to 0.80",
        "passed": stale_pass,
        "observed_confidence": stale_res.confidence
    })

    window_res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=20.0,
        rain_3h_mm=None,
        rain_6h_mm=None,
        rain_24h_mm=None,
        station_dist_km=2.0,
        data_freshness_hours=0.5
    )
    # 3 missing windows -> 3 * 0.08 = 0.24 penalty -> confidence = 1.0 - 0.24 = 0.76
    window_pass = (round(window_res.confidence, 2) == 0.76)
    test_results.append({
        "test_group": "confidence_discounting",
        "name": "Missing rolling windows penalty: 3 missing windows discounts confidence to 0.76",
        "passed": window_pass,
        "observed_confidence": window_res.confidence
    })

    # 6. Road Vulnerability Monotonicity & Subscore Checks
    hotspot_mono = True
    prev_h = 2.0
    for d in [0.0, 50.0, 150.0, 250.0, 500.0, 750.0, 1000.0, 1500.0]:
        score = calculate_hotspot_subscore(d)
        if score > prev_h:
            hotspot_mono = False
        prev_h = score
    test_results.append({
        "test_group": "vulnerability_subscores",
        "name": "Hotspot proximity subscore monotonically decreases with distance",
        "passed": hotspot_mono
    })

    drain_mono = True
    prev_d = 2.0
    for d in [0.0, 25.0, 75.0, 100.0, 200.0, 350.0, 500.0, 800.0]:
        score = calculate_drain_subscore(d)
        if score > prev_d:
            drain_mono = False
        prev_d = score
    test_results.append({
        "test_group": "vulnerability_subscores",
        "name": "Drain network proximity subscore monotonically decreases with distance",
        "passed": drain_mono
    })

    waterbody_mono = True
    prev_w = 2.0
    for d in [0.0, 50.0, 100.0, 200.0, 400.0, 600.0, 800.0, 1200.0]:
        score = calculate_waterbody_subscore(d)
        if score > prev_w:
            waterbody_mono = False
        prev_w = score
    test_results.append({
        "test_group": "vulnerability_subscores",
        "name": "Waterbody proximity subscore monotonically decreases with distance",
        "passed": waterbody_mono
    })

    # Multi-criteria weighted index evaluation check
    vuln_res = evaluate_road_vulnerability_engine(
        location_id="CORR-TEST-01",
        road_name="Tolichowki Test Underpass",
        dist_to_hotspot_m=50.0,     # s_h = 1.0 - 0.50*(50/250) = 0.90
        nearest_hotspot_name="Tolichowki Hotspot",
        dist_to_drain_m=50.0,       # s_d = 1.0 - 0.40*(50/100) = 0.80
        dist_to_waterbody_m=100.0,  # s_w = 1.0 - 0.50*(100/200) = 0.75
        nearest_waterbody_name="Shah Hatim Lake"
    )
    # Expected v_index = 0.45*0.90 + 0.35*0.80 + 0.20*0.75 = 0.405 + 0.280 + 0.150 = 0.835 -> SEVERE
    vuln_expected = 0.835
    vuln_pass = (vuln_res.vulnerability_index == vuln_expected and vuln_res.vulnerability_category == "SEVERE")
    test_results.append({
        "test_group": "vulnerability_weighted_index",
        "name": "Multi-criteria weighted index computation: 45% hotspot + 35% drain + 20% waterbody = 0.835 (SEVERE)",
        "expected_index": vuln_expected,
        "observed_index": vuln_res.vulnerability_index,
        "observed_category": vuln_res.vulnerability_category,
        "passed": vuln_pass
    })

    # 7. Coordinate Haversine and Segment Distance Checks
    # Distance between Lakdikapul (17.4042, 78.4651) and Khairatabad (17.4116, 78.4611) ~ 920m
    dist_calc = haversine_distance_m(17.4042, 78.4651, 17.4116, 78.4611)
    dist_pass = (900.0 <= dist_calc <= 950.0)
    test_results.append({
        "test_group": "geospatial_calculations",
        "name": "Haversine distance between Lakdikapul and Khairatabad is ~920m (observed: {:.1f}m)".format(dist_calc),
        "passed": dist_pass
    })

    all_passed = all(t["passed"] for t in test_results)
    report = {
        "report_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "phase": "Phase 10 Rules-Based Baseline Validation",
        "validation_verdict": "ALL_RULES_BASELINES_VERIFIED_PASSING" if all_passed else "FAILURE_DETECTED",
        "total_checks": len(test_results),
        "passed_checks": sum(1 for t in test_results if t["passed"]),
        "failed_checks": sum(1 for t in test_results if not t["passed"]),
        "test_results": test_results,
        "baseline_specifications": {
            "rainfall_engine": {
                "imd_intensity_thresholds_mm_hr": IMD_THRESHOLDS,
                "multi_window_escalation": "3h surge >= 40mm -> HIGH, 24h extreme >= 115.5mm -> CRITICAL",
                "missing_data_policy": "rain_1h_mm=None -> UNKNOWN (conf=0.10, score=0.0)",
                "confidence_penalties": "Distance penalty (-0.01/km >15km, max -0.35), Staleness penalty (-0.08/h >1.5h, max -0.40)"
            },
            "vulnerability_engine": {
                "weights": {"hotspot_proximity": 0.45, "drain_proximity": 0.35, "waterbody_proximity": 0.20},
                "category_thresholds": {"SEVERE": ">= 0.70", "HIGH": ">= 0.45", "MODERATE": ">= 0.20", "LOW": "< 0.20"},
                "semantic_invariance": "Static vulnerability represents physical exposure, NOT current inundation."
            }
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved {output_path} ({report['passed_checks']}/{report['total_checks']} checks passed)")
    return report

if __name__ == "__main__":
    validate_rule_baselines()
