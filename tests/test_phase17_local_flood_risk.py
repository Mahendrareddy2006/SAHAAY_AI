"""
Sahaay AI - Phase 17: Local Flood-Risk Model Test Suite
(tests/test_phase17_local_flood_risk.py)

Comprehensive offline tests for:
1. Forensic outcome-data readiness audit (verdict strictly NO-GO)
2. Segregation of real verified outcomes from synthetic fixtures and static placemarks
3. Formal prediction target specification and decision boundary constraints
4. Three distinct separated dimensions: static susceptibility, current condition, and forward risk
5. Strict non-silent missingness semantics for precipitation telemetry
6. Rainfall intensity alone does not prove current active inundation
7. Static physical vulnerability alone does not prove current active inundation
8. Prohibition of uncalibrated probability claims
9. Prohibition of guaranteed safety assertions
10. Leakage-free event-grouped evaluation partitioning
11. Leakage-free spatial corridor evaluation partitioning
12. Protection guard isolating the sealed Vision V4 evaluation partition
13. Physical precipitation bounds and non-negativity checks
14. Spatial Hyderabad bounding box validation
15. Dispatch actionability criteria (high risk AND confidence)
"""

from datetime import datetime, timezone
import pytest

from sahaay.flood_risk.schemas import (
    FloodPredictionTargetSpec,
    OutcomeDataInventory,
    DataReadinessVerdict,
    RiskForecastCategory,
    LocalFloodRiskInput,
    LocalFloodRiskAssessment,
    EvaluationSplitSpecification,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_FLOOD_RISK_DISCLAIMER,
)
from sahaay.flood_risk.readiness import audit_outcome_data_readiness
from sahaay.flood_risk.features import LocalFloodRiskFeaturePipeline
from sahaay.flood_risk.baseline import (
    TransparentLocalFloodRiskBaseline,
    evaluate_local_flood_risk,
)
from sahaay.flood_risk.evaluation import (
    EventAndSpatialSplitter,
    create_leakage_free_evaluation_splits,
)
from sahaay.road_status.schemas import RoadConditionState, RoadFreshnessCategory


# ==============================================================================
# 1. Forensic Outcome Data Readiness & Gate Decision Tests
# ==============================================================================

def test_data_readiness_audit_verdict_is_no_go():
    """
    Forensic audit of available repository data must strictly evaluate to
    INSUFFICIENT_DATA_NO_GO because exactly 0 verified ground-truth flood outcome
    records exist on disk.
    """
    inventory = audit_outcome_data_readiness()
    
    assert inventory.data_readiness_verdict == DataReadinessVerdict.INSUFFICIENT_DATA_NO_GO
    assert inventory.supervised_training_authorized is False
    assert inventory.predictive_claims_authorized is False
    assert inventory.verified_flood_outcome_records_count == 0
    assert inventory.verified_non_flood_outcome_records_count == 0
    assert inventory.independent_storm_events_count == 0
    assert len(inventory.unresolved_blockers) >= 4
    assert len(inventory.prerequisites_to_reopen_gate) >= 4


def test_synthetic_and_template_records_excluded():
    """
    Verifies that observation templates and synthetic records are accounted for
    as synthetic artifacts and strictly excluded from real ground-truth counts.
    """
    inventory = audit_outcome_data_readiness()
    
    assert inventory.synthetic_fixtures_count >= 5  # Template rows in observation_template.csv
    assert inventory.verified_flood_outcome_records_count == 0  # Not counted as real


def test_static_placemarks_not_used_as_positive_labels():
    """
    Verifies that static historical hotspot placemarks (23 in flooding_locations.kml)
    are recognized as static spatial features, not timestamped outcome events.
    """
    inventory = audit_outcome_data_readiness()
    
    assert inventory.static_hotspot_placemarks_count == 23
    assert any("spatial target leakage" in b.lower() for b in inventory.unresolved_blockers)


# ==============================================================================
# 2. Prediction Target Specification Invariants
# ==============================================================================

def test_target_specification_invariants():
    """
    Verifies formal prediction target specification: depth threshold >= 10.0 cm,
    spatial unit, 1-3h horizon, and non-autonomous actionability.
    """
    spec = FloodPredictionTargetSpec()
    
    assert spec.target_name == "localized_road_inundation_event"
    assert spec.depth_threshold_cm == 10.0
    assert spec.lane_submersion_minimum == 1
    assert "1 to 3 hours" in spec.temporal_prediction_horizon
    assert "Road corridor segment" in spec.spatial_unit
    assert len(spec.intended_users) >= 3


# ==============================================================================
# 3. Strict Separation of Three Risk Dimensions
# ==============================================================================

def test_three_dimensions_strictly_separated():
    """
    Verifies that LocalFloodRiskAssessment strictly separates:
    1. Static physical susceptibility
    2. Current observed ground condition
    3. Forward-looking predicted risk
    """
    inp = LocalFloodRiskInput(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        vulnerability_index=0.65,
        vulnerability_category="HIGH",
        current_road_condition=RoadConditionState.NO_CURRENT_EVIDENCE,
        rainfall_1h_mm=18.0,
        rainfall_forecast_1h_mm=12.0,
    )
    
    assessment = evaluate_local_flood_risk(inp)
    
    # Dimension 1: Static Susceptibility
    assert assessment.static_vulnerability_index == 0.65
    assert assessment.static_vulnerability_category == "HIGH"
    
    # Dimension 2: Current Observed Condition
    assert assessment.current_observed_condition == "NO_CURRENT_EVIDENCE"
    
    # Dimension 3: Forward-Looking Predicted Risk
    assert assessment.predicted_risk_category in [RiskForecastCategory.MEDIUM, RiskForecastCategory.HIGH]
    assert assessment.predicted_risk_score > 0.0
    assert assessment.is_calibrated_probability is False


# ==============================================================================
# 4. Strict Non-Silent Missing Telemetry Semantics
# ==============================================================================

def test_non_silent_missing_telemetry_semantics():
    """
    CRITICAL SAFETY RULE: Missing precipitation telemetry must NEVER be silently
    imputed as 0.0 mm / safe. Must produce UNKNOWN category and confidence 0.10.
    """
    inp = LocalFloodRiskInput(
        segment_id="HYD-LOC-002",
        road_name="Shaikpet Nala Road",
        vulnerability_index=0.75,
        rainfall_1h_mm=None,
        rainfall_forecast_1h_mm=None,
    )
    
    assessment = evaluate_local_flood_risk(inp)
    
    assert assessment.predicted_risk_category == RiskForecastCategory.UNKNOWN
    assert assessment.predicted_risk_score == 0.0
    assert assessment.confidence_score == 0.10
    assert assessment.uncertainty_level == "HIGH"
    assert "rainfall_telemetry_missing" in assessment.reason_codes
    assert "rainfall_telemetry" in assessment.missing_inputs


# ==============================================================================
# 5. Isolation of Current Inundation from Rainfall & Vulnerability
# ==============================================================================

def test_rainfall_alone_not_observed_flooding():
    """
    Critical cloudburst rainfall escalates forward-looking predicted risk to CRITICAL,
    but does NOT declare the road currently inundated without ground observations.
    """
    inp = LocalFloodRiskInput(
        segment_id="HYD-LOC-003",
        road_name="Begumpet Rasoolpura Underpass",
        rainfall_1h_mm=45.0,  # Cloudburst intensity
        rainfall_forecast_1h_mm=25.0,
        vulnerability_index=0.50,
        current_road_condition=RoadConditionState.NO_CURRENT_EVIDENCE,
    )
    
    assessment = evaluate_local_flood_risk(inp)
    
    assert assessment.predicted_risk_category == RiskForecastCategory.CRITICAL
    assert assessment.predicted_risk_score >= 0.70
    # Must remain unobserved/unverified on the ground:
    assert assessment.current_observed_condition == "NO_CURRENT_EVIDENCE"


def test_static_vulnerability_alone_not_active_inundation():
    """
    Severe physical susceptibility during dry weather (0 mm rain) produces CLEAR
    risk and does NOT declare active flood inundation.
    """
    inp = LocalFloodRiskInput(
        segment_id="HYD-LOC-004",
        road_name="Khairatabad Flyover Junction",
        rainfall_1h_mm=0.0,
        rainfall_forecast_1h_mm=0.0,
        vulnerability_index=0.90,  # Severe susceptibility
        vulnerability_category="SEVERE",
    )
    
    assessment = evaluate_local_flood_risk(inp)
    
    assert assessment.predicted_risk_category in [RiskForecastCategory.CLEAR, RiskForecastCategory.LOW]
    assert assessment.predicted_risk_score <= 0.05
    assert assessment.current_observed_condition == "NO_CURRENT_EVIDENCE"


# ==============================================================================
# 6. Prohibitions on Probability Claims & Safety Assertions
# ==============================================================================

def test_prohibition_of_calibrated_probability_claims():
    """
    LocalFloodRiskAssessment validator strictly rejects is_calibrated_probability=True
    until empirical probability calibration is scientifically demonstrated.
    """
    with pytest.raises(ValueError, match="is_calibrated_probability cannot be declared True"):
        LocalFloodRiskAssessment(
            segment_id="HYD-LOC-005",
            road_name="Malakpet Railway Underbridge",
            forecast_horizon_hours=1,
            evaluation_timestamp_utc="2026-10-27T12:00:00Z",
            static_vulnerability_index=0.50,
            static_vulnerability_category="MODERATE",
            current_observed_condition="NO_CURRENT_EVIDENCE",
            current_observation_verification_state="UNMONITORED",
            predicted_risk_category=RiskForecastCategory.MEDIUM,
            predicted_risk_score=0.35,
            is_calibrated_probability=True,  # PROHIBITED!
            confidence_score=0.75,
        )


def test_prohibition_of_guaranteed_safety_claims():
    """
    LocalFloodRiskAssessment validator strictly rejects forbidden safety claims
    such as 'guaranteed safe', '100% safe', 'safe passage guaranteed', etc.
    """
    for forbidden in FORBIDDEN_SAFETY_PHRASES:
        with pytest.raises(ValueError, match="forbidden"):
            LocalFloodRiskAssessment(
                segment_id="HYD-LOC-006",
                road_name=f"Road claiming {forbidden}",
                forecast_horizon_hours=1,
                evaluation_timestamp_utc="2026-10-27T12:00:00Z",
                static_vulnerability_index=0.20,
                static_vulnerability_category="LOW",
                current_observed_condition="NO_CURRENT_EVIDENCE",
                current_observation_verification_state="UNMONITORED",
                predicted_risk_category=RiskForecastCategory.LOW,
                predicted_risk_score=0.10,
                is_calibrated_probability=False,
                confidence_score=0.80,
            )


# ==============================================================================
# 7. Leakage-Free Evaluation Splitter & Vision Guard Tests
# ==============================================================================

def test_leakage_free_evaluation_splitter_event_isolation():
    """
    Verifies that EventAndSpatialSplitter produces strictly disjoint event sets
    with zero temporal event overlap (E_train ∩ E_eval = ∅).
    """
    splitter = EventAndSpatialSplitter()
    events = ["STORM-2023-07-20", "STORM-2023-08-15", "STORM-2024-09-02", "STORM-2024-10-14"]
    segments = ["HYD-LOC-001", "HYD-LOC-002", "HYD-LOC-003", "HYD-LOC-004"]
    
    spec = splitter.generate_splits(events, segments)
    
    assert spec.is_leakage_free is True
    assert spec.event_overlap_detected is False
    assert len(set(spec.train_events).intersection(set(spec.eval_events))) == 0


def test_leakage_free_evaluation_splitter_spatial_isolation():
    """
    Verifies that EventAndSpatialSplitter produces strictly disjoint spatial segment sets
    with zero geographic corridor overlap (S_train ∩ S_eval = ∅).
    """
    splitter = EventAndSpatialSplitter()
    events = ["STORM-A", "STORM-B", "STORM-C", "STORM-D"]
    segments = ["HYD-LOC-001", "HYD-LOC-002", "HYD-LOC-003", "HYD-LOC-004"]
    
    spec = splitter.generate_splits(events, segments)
    
    assert spec.is_leakage_free is True
    assert spec.spatial_overlap_detected is False
    assert len(set(spec.train_segments).intersection(set(spec.eval_segments))) == 0


def test_vision_test_partition_protection_guard():
    """
    Verifies that EventAndSpatialSplitter intercepts and blocks any attempt to reuse
    or access the sealed Vision V4 evaluation partition.
    """
    splitter = EventAndSpatialSplitter()
    
    for forbidden_path in ["data/processed/test.csv", "manifest_v4/test.csv", "reports/phase16/evaluation_set_metadata.json"]:
        with pytest.raises(PermissionError, match="SEALED_VISION_PARTITION_VIOLATION"):
            splitter.verify_vision_partition_isolation(forbidden_path)


def test_insufficient_events_raises_error():
    """
    Attempting to split with fewer than 2 independent events must raise ValueError
    to prevent invalid evaluation holdouts.
    """
    splitter = EventAndSpatialSplitter()
    with pytest.raises(ValueError, match="Insufficient independent storm events"):
        splitter.generate_splits(["ONLY-ONE-STORM"], ["SEG-01", "SEG-02"])


# ==============================================================================
# 8. Feature Pipeline Bounds & Validation Checks
# ==============================================================================

def test_precipitation_physical_bounds_validation():
    """
    Negative values, non-finite floats, or excessive precipitation rates (>250mm/h)
    must be flagged and quarantined by the feature pipeline.
    """
    pipe = LocalFloodRiskFeaturePipeline()
    
    # Negative value
    valid_neg, errs_neg = pipe.validate_precipitation_bounds(-10.0, 5.0, 5.0)
    assert valid_neg is False
    assert "NEGATIVE_VALUE_IN_RAIN_1H_MM" in errs_neg
    
    # Excessive rate (> 250 mm/h)
    valid_exc, errs_exc = pipe.validate_precipitation_bounds(350.0, 5.0, 5.0)
    assert valid_exc is False
    assert "EXCESSIVE_RATE_IN_RAIN_1H_MM" in errs_exc


def test_spatial_bounds_validation():
    """
    Coordinates outside the GHMC metropolitan bounding box must be flagged.
    """
    pipe = LocalFloodRiskFeaturePipeline()
    valid, errs = pipe.validate_spatial_bounds(12.9716, 77.5946)  # Bengaluru coordinates
    assert valid is False
    assert "COORDINATES_OUT_OF_METRO_BOUNDING_BOX" in errs


def test_actionability_requires_high_risk_and_confidence():
    """
    Verifies that is_actionable_for_dispatch is True only when risk is HIGH/CRITICAL
    and confidence score >= 0.45.
    """
    # High risk with good confidence -> Actionable
    inp_actionable = LocalFloodRiskInput(
        segment_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity Junction",
        rainfall_1h_mm=30.0,
        rainfall_forecast_1h_mm=20.0,
        vulnerability_index=0.60,
        telemetry_station_dist_km=5.0,
        telemetry_freshness_hours=0.5,
    )
    res_actionable = evaluate_local_flood_risk(inp_actionable)
    assert res_actionable.predicted_risk_category in [RiskForecastCategory.HIGH, RiskForecastCategory.CRITICAL]
    assert res_actionable.is_actionable_for_dispatch is True
    
    # Low risk -> Not actionable
    inp_low = LocalFloodRiskInput(
        segment_id="HYD-LOC-008",
        road_name="Lakdikapul Junction",
        rainfall_1h_mm=2.0,
        rainfall_forecast_1h_mm=1.0,
        vulnerability_index=0.20,
    )
    res_low = evaluate_local_flood_risk(inp_low)
    assert res_low.is_actionable_for_dispatch is False
