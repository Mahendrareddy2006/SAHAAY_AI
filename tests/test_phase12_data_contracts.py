"""
Sahaay AI - Phase 12 Regression and Data Contract Test Suite
Validates formal data contracts, missing data semantics, safety invariants,
vision decision boundaries, and non-autonomous advisory constraints.
"""

import pytest
from pydantic import ValidationError

from sahaay.decision.contracts import (
    AlertLevel,
    CurrentFloodEvidenceStatus,
    DecisionInput,
    DecisionOutput,
    DecisionStatus,
    HazardNature,
    evaluate_decision,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.vulnerability_engine import evaluate_road_vulnerability_engine
from sahaay.routing.contracts import (
    EmergencyDestination,
    EmergencyDestinationType,
    FacilityOperationalStatus,
    MANDATORY_SAFETY_DISCLAIMER,
    RouteRequest,
    RouteResponse,
    RouteSegmentRisk,
    VehicleType,
)
from sahaay.vision.policy import (
    CalibratedVisionDecision,
    DEFAULT_ABSTENTION_LOWER_BOUND,
    DEFAULT_ABSTENTION_UPPER_BOUND,
    FLOOD_CLASS_INDEX,
    NOT_FLOODED_CLASS_INDEX,
    evaluate_vision_abstention_boundary,
)


# ==============================================================================
# 1. Vision Decision Boundaries & Abstention Policy
# ==============================================================================

def test_vision_class_index_mapping():
    """Verify class index mapping and probability direction."""
    assert FLOOD_CLASS_INDEX == 1, "Flooded class must be index 1 (positive class)"
    assert NOT_FLOODED_CLASS_INDEX == 0, "Not flooded class must be index 0 (negative class)"


@pytest.mark.parametrize("prob,expected_decision,expected_ambiguous", [
    # Lower boundary tests
    (0.000, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.200, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.349, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.350, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),  # Exact lower endpoint
    (0.351, CalibratedVisionDecision.INCONCLUSIVE, True),                 # Immediately inside band
    # Interior ambiguity band tests
    (0.400, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.500, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.600, CalibratedVisionDecision.INCONCLUSIVE, True),
    # Upper boundary tests
    (0.649, CalibratedVisionDecision.INCONCLUSIVE, True),                 # Immediately inside band
    (0.650, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),     # Exact upper endpoint
    (0.651, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
    (0.850, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
    (1.000, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
])
def test_vision_abstention_band_boundaries(prob, expected_decision, expected_ambiguous):
    """Test both endpoints (0.35, 0.65) and values immediately outside and inside the band."""
    decision, confidence, is_ambiguous = evaluate_vision_abstention_boundary(prob)
    assert decision == expected_decision
    assert is_ambiguous == expected_ambiguous
    if prob >= 0.65:
        assert confidence == round(prob, 4)
    elif prob <= 0.35:
        assert confidence == round(1.0 - prob, 4)


def test_vision_probability_out_of_bounds_rejection():
    """Verify invalid probability inputs raise ValueError."""
    with pytest.raises(ValueError):
        evaluate_vision_abstention_boundary(-0.01)
    with pytest.raises(ValueError):
        evaluate_vision_abstention_boundary(1.01)
    with pytest.raises(TypeError):
        evaluate_vision_abstention_boundary("0.5")  # type: ignore


# ==============================================================================
# 2. Rainfall Telemetry Non-Silent Missingness & Staleness Semantics
# ==============================================================================

def test_missing_rainfall_telemetry_returns_unknown():
    """Verify missing 1h rainfall is NEVER imputed as 0.0 mm or LOW risk."""
    res = evaluate_rainfall_risk_engine(
        location_id="CORR-01",
        rain_1h_mm=None,
        rain_3h_mm=20.0,
        rain_24h_mm=50.0,
    )
    assert res.risk_category == "UNKNOWN", "Missing rainfall must produce UNKNOWN category"
    assert res.risk_score == 0.0, "Risk score must be 0.0 when uncomputed"
    assert res.confidence == 0.10, "Confidence must be minimal (0.10) for missing telemetry"
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes
    assert "rain_1h_mm" in res.missing_inputs


def test_decision_engine_missing_rainfall_triggers_insufficient_data():
    """Verify decision engine handles UNKNOWN rainfall risk without default safe classification."""
    decision_input = DecisionInput(
        location_id="LOC-TEST-01",
        road_name="Tolichowki Corridor",
        rainfall_risk_category="UNKNOWN",
        missing_inputs=["rain_1h_mm"],
    )
    res = evaluate_decision(decision_input)
    assert res.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert res.current_flood_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
    assert res.requires_human_verification is True
    assert res.alert_level == AlertLevel.ADVISORY
    assert "TELEMETRY_DATA_MISSING_OR_STALE" in res.reason_codes


def test_rainfall_station_distance_and_freshness_decay():
    """Verify confidence decay for distant gauges and stale telemetry."""
    # Stale telemetry (5.5 hours old) and distant gauge (25 km away)
    res = evaluate_rainfall_risk_engine(
        location_id="CORR-02",
        rain_1h_mm=20.0,
        station_dist_km=25.0,        # 10 km beyond 15km -> 0.10 penalty
        data_freshness_hours=5.5,    # 4.0 hr beyond 1.5h -> 0.32 penalty
    )
    assert res.risk_category == "HIGH"
    assert res.confidence < 0.70, f"Confidence expected decayed below 0.70, got {res.confidence}"
    assert "TELEMETRY_DATA_STALE" in res.reason_codes


# ==============================================================================
# 3. Static Susceptibility vs Active Inundation Safety Separation
# ==============================================================================

def test_severe_vulnerability_dry_weather_not_flooded():
    """A corridor with SEVERE vulnerability during dry weather must NOT be marked flooded."""
    res_vuln = evaluate_road_vulnerability_engine(
        location_id="VULN-01",
        road_name="Tolichowki Underpass",
        dist_to_hotspot_m=50.0,
        nearest_hotspot_name="Tolichowki Junction",
        dist_to_drain_m=20.0,
        dist_to_waterbody_m=100.0,
        nearest_waterbody_name="Mir Alam Tank",
    )
    assert res_vuln.vulnerability_category == "SEVERE"
    assert res_vuln.vulnerability_index >= 0.70

    # Feed into decision engine under dry weather (LOW rain, no visual flood)
    decision_input = DecisionInput(
        location_id="CORR-01",
        road_name="Tolichowki Underpass",
        rainfall_risk_category="LOW",
        rainfall_risk_score=0.02,
        vulnerability_category=res_vuln.vulnerability_category,
        vulnerability_index=res_vuln.vulnerability_index,
    )
    res_decision = evaluate_decision(decision_input)
    assert res_decision.alert_level == AlertLevel.CLEAR
    assert res_decision.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert res_decision.hazard_nature == HazardNature.PREDICTED_RISK
    assert res_decision.alert_level != AlertLevel.EMERGENCY
    assert res_decision.alert_level != AlertLevel.WARNING


def test_heavy_rainfall_on_vulnerable_road_is_predicted_not_observed():
    """Severe rain on vulnerable corridor triggers WATCH (PREDICTED_RISK), NOT OBSERVED_HAZARD."""
    decision_input = DecisionInput(
        location_id="CORR-02",
        road_name="Shaikpet Flyover Junction",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.90,
        vulnerability_category="SEVERE",
        vulnerability_index=0.85,
    )
    res = evaluate_decision(decision_input)
    assert res.alert_level == AlertLevel.WATCH
    assert res.hazard_nature == HazardNature.PREDICTED_RISK
    assert res.current_flood_evidence_status == CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
    assert res.current_flood_evidence_status != CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
    assert any("NOT confirmed flooded now" in w for w in res.warnings)


# ==============================================================================
# 4. Contradictory Evidence & Negative Vision Invariants
# ==============================================================================

def test_negative_vision_does_not_mean_road_is_safe():
    """Negative vision model check asserts no visible standing water; does not certify safety."""
    decision_input = DecisionInput(
        location_id="CORR-03",
        road_name="Banjara Hills Rd 12",
        vision_predicted_class="not_flooded",
        vision_confidence=0.85,
        vision_is_ambiguous=False,
        rainfall_risk_category="LOW",
        vulnerability_category="LOW",
    )
    res = evaluate_decision(decision_input)
    assert res.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert "VISUAL_DRY_SURFACE_CHECKED" in res.reason_codes
    # Confirm it does not declare guaranteed safety
    assert res.alert_level == AlertLevel.CLEAR


def test_contradictory_evidence_detection():
    """Contradiction between dry optical surveillance and citizen deep flood forces human verification."""
    decision_input = DecisionInput(
        location_id="CORR-04",
        road_name="Mehdipatnam Corridor",
        vision_predicted_class="not_flooded",
        vision_confidence=0.80,
        vision_is_ambiguous=False,
        water_depth_estimate="KNEE_DEEP",
        citizen_report_count_in_zone=1,
        report_age_minutes=25.0,
    )
    res = evaluate_decision(decision_input)
    assert res.decision_status == DecisionStatus.INCONCLUSIVE_CONTRADICTORY
    assert res.current_flood_evidence_status == CurrentFloodEvidenceStatus.INCONCLUSIVE
    assert res.requires_human_verification is True
    assert res.confidence == 0.35
    assert "CONTRADICTORY_OBSERVATIONS_DETECTED" in res.reason_codes


# ==============================================================================
# 5. Routing Contracts & Safety Invariant Validation
# ==============================================================================

def test_route_request_coordinate_bounds():
    """RouteRequest enforces valid Hyderabad geographical coordinates."""
    # Valid Hyderabad coordinates
    req = RouteRequest(
        origin_latitude=17.3850,
        origin_longitude=78.4867,
        destination_latitude=17.4399,
        destination_longitude=78.3908,
        vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
    )
    assert req.origin_latitude == 17.3850

    # Out of bounds latitude (< 17.0)
    with pytest.raises(ValidationError):
        RouteRequest(
            origin_latitude=16.5,
            origin_longitude=78.4867,
            destination_latitude=17.4399,
            destination_longitude=78.3908,
        )


def test_emergency_destination_schema():
    """Validates emergency hospital and shelter destination schemas."""
    dest = EmergencyDestination(
        facility_id="HOSP-OSMANIA-01",
        name="Osmania General Hospital",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.3775,
        longitude=78.4735,
        operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
        has_dedicated_emergency_bay=True,
        verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
        emergency_contact_masked="040-24600121",
    )
    assert dest.destination_type == EmergencyDestinationType.HOSPITAL
    assert dest.has_dedicated_emergency_bay is True


def test_route_response_mandatory_safety_disclaimer():
    """RouteResponse mandates safety disclaimer and rejects claims of guaranteed safe routes."""
    # Valid response with standard disclaimer
    resp = RouteResponse(
        route_id="RTE-HYD-001",
        origin={"lat": 17.3850, "lon": 78.4867},
        destination={"lat": 17.4399, "lon": 78.3908},
        vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
        total_distance_meters=8500.0,
        estimated_duration_seconds=1200.0,
        aggregate_risk_score=0.25,
        has_unmonitored_segments=True,
        unmonitored_segments_count=1,
        warnings=["Route contains unmonitored segments with unknown waterlogging risk."],
    )
    assert resp.safety_disclaimer == MANDATORY_SAFETY_DISCLAIMER
    assert resp.engine_status == "SPECIFICATION_CONTRACT_ONLY_NOT_IMPLEMENTED"

    # Rejecting response that attempts to claim guaranteed safety in warnings
    with pytest.raises(ValidationError, match="must NEVER claim a route is guaranteed safe"):
        RouteResponse(
            route_id="RTE-HYD-002",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=8500.0,
            estimated_duration_seconds=1200.0,
            aggregate_risk_score=0.0,
            warnings=["This route is guaranteed safe and flood-free."],
        )

    # Rejecting response where disclaimer was emptied
    with pytest.raises(ValidationError, match="Mandatory safety disclaimer must explicitly state"):
        RouteResponse(
            route_id="RTE-HYD-003",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=8500.0,
            estimated_duration_seconds=1200.0,
            aggregate_risk_score=0.1,
            safety_disclaimer="Safe route provided.",
        )
