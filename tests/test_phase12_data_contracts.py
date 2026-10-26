"""
Sahaay AI - Phase 12 Regression and Data Contract Test Suite
Validates formal data contracts, missing data semantics, safety invariants,
vision decision boundaries, and non-autonomous advisory constraints.
"""

import math
import pytest
from pydantic import ValidationError

from sahaay.api.schemas import VisionPredictionResponse

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
    map_vision_probabilities_to_decision,
)


# ==============================================================================
# 1. Vision Decision Boundaries & Inclusive Abstention Policy
# ==============================================================================

def test_vision_class_index_mapping():
    """Verify class index mapping and probability direction."""
    assert FLOOD_CLASS_INDEX == 1, "Flooded class must be index 1 (positive class)"
    assert NOT_FLOODED_CLASS_INDEX == 0, "Not flooded class must be index 0 (negative class)"


@pytest.mark.parametrize("prob,expected_decision,expected_ambiguous", [
    # Strictly below 0.35 produces NO_CURRENT_FLOOD_EVIDENCE
    (0.000, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.100, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.200, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    (0.349, CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, False),
    # Inclusive abstention interval [0.35, 0.65]: Endpoints MUST produce INCONCLUSIVE
    (0.350, CalibratedVisionDecision.INCONCLUSIVE, True),  # Exact lower inclusive endpoint
    (0.351, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.400, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.500, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.600, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.649, CalibratedVisionDecision.INCONCLUSIVE, True),
    (0.650, CalibratedVisionDecision.INCONCLUSIVE, True),  # Exact upper inclusive endpoint
    # Strictly above 0.65 produces FLOOD_EVIDENCE_DETECTED
    (0.651, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
    (0.700, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
    (0.850, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
    (1.000, CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, False),
])
def test_vision_abstention_band_boundaries(prob, expected_decision, expected_ambiguous):
    """Test inclusive interval [0.35, 0.65], both endpoints, and values immediately outside and inside."""
    decision, confidence, is_ambiguous = evaluate_vision_abstention_boundary(prob)
    assert decision == expected_decision
    assert is_ambiguous == expected_ambiguous
    if prob > 0.65:
        assert confidence == round(prob, 4)
    elif prob < 0.35:
        assert confidence == round(1.0 - prob, 4)
    else:
        assert confidence == round(max(prob, 1.0 - prob), 4)


def test_vision_non_finite_and_malformed_rejection():
    """Verify non-finite (NaN, inf), Boolean, and out-of-range probability inputs are rejected."""
    # NaN and infinities must raise ValueError
    with pytest.raises(ValueError, match="finite number"):
        evaluate_vision_abstention_boundary(float("nan"))
    with pytest.raises(ValueError, match="finite number"):
        evaluate_vision_abstention_boundary(float("inf"))
    with pytest.raises(ValueError, match="finite number"):
        evaluate_vision_abstention_boundary(float("-inf"))

    # Booleans must raise TypeError
    with pytest.raises(TypeError, match="Boolean"):
        evaluate_vision_abstention_boundary(True)
    with pytest.raises(TypeError, match="Boolean"):
        evaluate_vision_abstention_boundary(False)

    # Out of range must raise ValueError
    with pytest.raises(ValueError, match="range"):
        evaluate_vision_abstention_boundary(-0.01)
    with pytest.raises(ValueError, match="range"):
        evaluate_vision_abstention_boundary(1.01)

    # String must raise TypeError
    with pytest.raises(TypeError):
        evaluate_vision_abstention_boundary("0.5")  # type: ignore


def test_map_vision_probabilities_to_decision():
    """Verify mapping continuous probabilities into standardized API response fields."""
    # 1. Definite non-flood (< 0.35)
    cls_name, conf, ambig, inconcl, reasons = map_vision_probabilities_to_decision(0.20)
    assert cls_name == "not_flooded"
    assert conf == 0.80
    assert not ambig
    assert not inconcl
    assert len(reasons) == 0

    # 2. Lower inclusive endpoint (0.35)
    cls_name, conf, ambig, inconcl, reasons = map_vision_probabilities_to_decision(0.35)
    assert cls_name == "inconclusive"
    assert conf == 0.65
    assert ambig
    assert inconcl
    assert len(reasons) == 1
    assert "ambiguity abstention band" in reasons[0]

    # 3. Interior ambiguous (0.50)
    cls_name, conf, ambig, inconcl, reasons = map_vision_probabilities_to_decision(0.50)
    assert cls_name == "inconclusive"
    assert conf == 0.50
    assert ambig
    assert inconcl

    # 4. Upper inclusive endpoint (0.65)
    cls_name, conf, ambig, inconcl, reasons = map_vision_probabilities_to_decision(0.65)
    assert cls_name == "inconclusive"
    assert conf == 0.65
    assert ambig
    assert inconcl

    # 5. Definite flood (> 0.65)
    cls_name, conf, ambig, inconcl, reasons = map_vision_probabilities_to_decision(0.85)
    assert cls_name == "flooded"
    assert conf == 0.85
    assert not ambig
    assert not inconcl
    assert len(reasons) == 0


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


def test_decision_input_defaults_to_unknown_rainfall():
    """Verify DecisionInput defaults rainfall_risk_category to UNKNOWN if omitted."""
    inp = DecisionInput(location_id="CORR-DEF-01", road_name="Default Risk Test Corridor")
    assert inp.rainfall_risk_category == "UNKNOWN"

    # Evaluated through decision engine: missing telemetry must yield INSUFFICIENT_DATA and ADVISORY
    out = evaluate_decision(inp)
    assert out.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
    assert out.alert_level == AlertLevel.ADVISORY
    assert out.alert_level != AlertLevel.CLEAR
    assert "TELEMETRY_DATA_MISSING_OR_STALE" in out.reason_codes


def test_decision_input_from_rainfall_result_helper():
    """Verify from_rainfall_result factory helper correctly transfers UNKNOWN and missing inputs."""
    res_rain = evaluate_rainfall_risk_engine(location_id="CORR-01", rain_1h_mm=None)
    inp = DecisionInput.from_rainfall_result(
        location_id="CORR-01",
        road_name="Khairatabad Circle",
        rainfall_result=res_rain,
        vulnerability_category="MODERATE",
        vulnerability_index=0.30,
    )
    assert inp.rainfall_risk_category == "UNKNOWN"
    assert inp.rainfall_risk_score == 0.0
    assert "rain_1h_mm" in inp.missing_inputs

    out = evaluate_decision(inp)
    assert out.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert out.alert_level == AlertLevel.ADVISORY
    assert out.alert_level != AlertLevel.CLEAR
    assert any("not be interpreted as zero rainfall" in w.lower() for w in out.warnings)


def test_decision_input_invalid_rainfall_category():
    """Verify invalid rainfall category values are rejected by field validator."""
    with pytest.raises(ValidationError):
        DecisionInput(
            location_id="CORR-ERR-01",
            road_name="Error Corridor",
            rainfall_risk_category="EXTREME_UNVALIDATED",
        )


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
    # Output must be NO_CURRENT_EVIDENCE_AVAILABLE, which strictly means:
    # "No current reports; not a declaration of safety"
    assert res.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert "VISUAL_DRY_SURFACE_CHECKED" in res.reason_codes

    # Verify that neither explanation nor warnings assert that the road is safe or guaranteed clear
    for w in res.warnings:
        assert "guaranteed safe" not in w.lower()
        assert "road is safe" not in w.lower()
    assert "guaranteed safe" not in res.explanation.lower()


def test_contradictory_evidence_detection():
    """Contradiction between dry optical surveillance and citizen deep flood forces human verification."""
    decision_input = DecisionInput(
        location_id="CORR-04",
        road_name="Mehdipatnam Corridor",
        vision_predicted_class="not_flooded",
        vision_confidence=0.80,
        vision_is_ambiguous=False,
        rainfall_risk_category="LOW",
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

@pytest.mark.parametrize("lat,lon,should_pass", [
    (17.3850, 78.4867, True),   # Valid central Hyderabad
    (17.0000, 78.1000, True),   # Valid lower boundaries
    (17.8000, 78.8000, True),   # Valid upper boundaries
    (16.9999, 78.4867, False),  # Latitude below 17.0
    (17.8001, 78.4867, False),  # Latitude above 17.8
    (17.3850, 78.0999, False),  # Longitude below 78.1
    (17.3850, 78.8001, False),  # Longitude above 78.8
])
def test_route_request_coordinate_bounds(lat, lon, should_pass):
    """RouteRequest enforces valid Hyderabad geographical bounding box coordinates."""
    if should_pass:
        req = RouteRequest(
            origin_latitude=lat,
            origin_longitude=lon,
            destination_latitude=17.4399,
            destination_longitude=78.3908,
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
        )
        assert req.origin_latitude == lat
        assert req.origin_longitude == lon
    else:
        with pytest.raises(ValidationError):
            RouteRequest(
                origin_latitude=lat,
                origin_longitude=lon,
                destination_latitude=17.4399,
                destination_longitude=78.3908,
            )


def test_emergency_destination_schema():
    """Validates emergency hospital and shelter destination schemas and rejection of malformed IDs."""
    # Valid destination
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

    # Invalid facility ID: Missing HOSP- or SHELTER- prefix
    with pytest.raises(ValidationError):
        EmergencyDestination(
            facility_id="CLINIC-GENERAL-01",
            name="General Clinic",
            destination_type=EmergencyDestinationType.HOSPITAL,
            latitude=17.3775,
            longitude=78.4735,
            emergency_contact_masked="040-00000000",
        )

    # Invalid facility ID: Random digits without prefix
    with pytest.raises(ValidationError):
        EmergencyDestination(
            facility_id="12345678",
            name="Unknown Facility",
            destination_type=EmergencyDestinationType.OFFICIAL_SHELTER,
            latitude=17.3775,
            longitude=78.4735,
            emergency_contact_masked="040-00000000",
        )


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
        segments=[
            RouteSegmentRisk(
                segment_id="SEG-01",
                road_name="Unmonitored Link Road",
                length_meters=500.0,
                current_alert_level=AlertLevel.ADVISORY,
                current_evidence_status=CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA,
                rainfall_risk_category="UNKNOWN",
                vulnerability_category="LOW",
                segment_risk_score=0.20,
            )
        ],
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

    # Rejecting response with synonym "completely safe"
    with pytest.raises(ValidationError, match="must NEVER claim a route is guaranteed safe"):
        RouteResponse(
            route_id="RTE-HYD-002B",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=8500.0,
            estimated_duration_seconds=1200.0,
            aggregate_risk_score=0.0,
            warnings=["Road is completely safe for all drivers."],
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


def test_route_response_cross_field_consistency():
    """Verify cross-field invariants: unmonitored segments, emergency segments, and restricted destinations."""
    unmonitored_seg = RouteSegmentRisk(
        segment_id="SEG-UNMON-01",
        road_name="Unmonitored Sector Link",
        length_meters=800.0,
        current_alert_level=AlertLevel.ADVISORY,
        current_evidence_status=CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA,
        rainfall_risk_category="UNKNOWN",
        vulnerability_category="LOW",
        segment_risk_score=0.20,
    )
    emergency_seg = RouteSegmentRisk(
        segment_id="SEG-EMERG-01",
        road_name="Flooded Canal Underpass",
        length_meters=300.0,
        current_alert_level=AlertLevel.EMERGENCY,
        current_evidence_status=CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE,
        rainfall_risk_category="CRITICAL",
        vulnerability_category="SEVERE",
        segment_risk_score=0.95,
        is_passable_for_vehicle=False,
    )

    # Invariant 1: Unmonitored segment present but has_unmonitored_segments is False -> raises ValidationError
    with pytest.raises(ValidationError, match="has_unmonitored_segments must be True"):
        RouteResponse(
            route_id="RTE-CONS-01",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.20,
            segments=[unmonitored_seg],
            has_unmonitored_segments=False,  # Contradiction!
            unmonitored_segments_count=0,
        )

    # Invariant 2: EMERGENCY/impassable segment present but aggregate_risk_score is 0.0 -> raises ValidationError
    with pytest.raises(ValidationError, match="aggregate_risk_score cannot be 0.0"):
        RouteResponse(
            route_id="RTE-CONS-02",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.0,  # Contradiction!
            segments=[emergency_seg],
            warnings=["Submerged canal underpass ahead."],
        )

    # Invariant 3: Destination is access restricted, but no access warning provided -> raises ValidationError
    inundated_hospital = EmergencyDestination(
        facility_id="HOSP-CARE-01",
        name="Care Hospital Banjara",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4150,
        longitude=78.4450,
        operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
        verified_access_road_status=CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE,
        emergency_contact_masked="040-30418000",
    )
    with pytest.raises(ValidationError, match="restricted or inundated access"):
        RouteResponse(
            route_id="RTE-CONS-03",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4150, "lon": 78.4450},
            vehicle_type=VehicleType.HIGH_CLEARANCE_SUV,
            target_facility=inundated_hospital,
            total_distance_meters=5000.0,
            estimated_duration_seconds=900.0,
            aggregate_risk_score=0.85,
            warnings=["Standard advisory route provided."],  # Missing access restriction warning!
        )

    # Invariant 3 satisfied: With explicit access warning -> passes
    valid_restricted_resp = RouteResponse(
        route_id="RTE-CONS-03-VALID",
        origin={"lat": 17.3850, "lon": 78.4867},
        destination={"lat": 17.4150, "lon": 78.4450},
        vehicle_type=VehicleType.HIGH_CLEARANCE_SUV,
        target_facility=inundated_hospital,
        total_distance_meters=5000.0,
        estimated_duration_seconds=900.0,
        aggregate_risk_score=0.85,
        warnings=["WARNING: Target facility has inundated, restricted access roads. Approach with caution."],
    )
    assert valid_restricted_resp.target_facility.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED


def test_route_response_unmonitored_count_invariant():
    """Verify unmonitored_segments_count must equal computed count for all cases (rejecting undercounts & overcounts)."""
    unmon_seg_1 = RouteSegmentRisk(
        segment_id="SEG-UNMON-01",
        road_name="Unmonitored Link A",
        length_meters=400.0,
        current_alert_level=AlertLevel.ADVISORY,
        current_evidence_status=CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA,
        rainfall_risk_category="UNKNOWN",
        vulnerability_category="LOW",
        segment_risk_score=0.20,
    )
    unmon_seg_2 = RouteSegmentRisk(
        segment_id="SEG-UNMON-02",
        road_name="Unmonitored Link B",
        length_meters=600.0,
        current_alert_level=AlertLevel.ADVISORY,
        current_evidence_status=CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA,
        rainfall_risk_category="UNKNOWN",
        vulnerability_category="LOW",
        segment_risk_score=0.20,
    )

    # Undercount Case 1: 2 actual unmonitored segments with reported count 1 -> rejected
    with pytest.raises(ValidationError, match=r"unmonitored_segments_count \(1\) must match count of unmonitored segments \(2\)"):
        RouteResponse(
            route_id="RTE-COUNT-01",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.20,
            segments=[unmon_seg_1, unmon_seg_2],
            has_unmonitored_segments=True,
            unmonitored_segments_count=1,  # Undercount!
        )

    # Undercount Case 2: 1 actual unmonitored segment with reported count 0 -> rejected
    with pytest.raises(ValidationError, match=r"unmonitored_segments_count \(0\) must match count of unmonitored segments \(1\)"):
        RouteResponse(
            route_id="RTE-COUNT-02",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.20,
            segments=[unmon_seg_1],
            has_unmonitored_segments=True,
            unmonitored_segments_count=0,  # Undercount!
        )

    # Overcount Case 1: 0 actual unmonitored segments with reported count 1 -> rejected
    with pytest.raises(ValidationError, match=r"unmonitored_segments_count \(1\) must match count of unmonitored segments \(0\)"):
        RouteResponse(
            route_id="RTE-COUNT-03",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.10,
            segments=[],
            has_unmonitored_segments=False,
            unmonitored_segments_count=1,  # Overcount!
        )

    # Overcount Case 2: 2 actual unmonitored segments with reported count 3 -> rejected
    with pytest.raises(ValidationError, match=r"unmonitored_segments_count \(3\) must match count of unmonitored segments \(2\)"):
        RouteResponse(
            route_id="RTE-COUNT-04",
            origin={"lat": 17.3850, "lon": 78.4867},
            destination={"lat": 17.4399, "lon": 78.3908},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=300.0,
            aggregate_risk_score=0.20,
            segments=[unmon_seg_1, unmon_seg_2],
            has_unmonitored_segments=True,
            unmonitored_segments_count=3,  # Overcount!
        )

    # Exact Count Case: 2 actual unmonitored segments with reported count 2 and has_unmonitored_segments=True -> passes
    valid_resp = RouteResponse(
        route_id="RTE-COUNT-VALID",
        origin={"lat": 17.3850, "lon": 78.4867},
        destination={"lat": 17.4399, "lon": 78.3908},
        vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
        total_distance_meters=1000.0,
        estimated_duration_seconds=300.0,
        aggregate_risk_score=0.20,
        segments=[unmon_seg_1, unmon_seg_2],
        has_unmonitored_segments=True,
        unmonitored_segments_count=2,
    )
    assert valid_resp.unmonitored_segments_count == 2
    assert valid_resp.has_unmonitored_segments is True


def test_vision_prediction_response_schema_inconclusive():
    """Verify VisionPredictionResponse schema serializes inconclusive results without forcing binary labels."""
    resp = VisionPredictionResponse(
        prediction_id="pred_inconclusive_contract_01",
        predicted_class="inconclusive",
        confidence=0.65,
        class_scores={"not_flooded": 0.50, "flooded": 0.50},
        is_ambiguous=True,
        is_inconclusive=True,
        inconclusive_reasons=["Score 0.500 in [0.35, 0.65] ambiguity band"],
        model_name="mobilenetv3_large_baseline",
        model_version="v3.0.0",
        device="cpu",
        inference_latency_ms=10.2,
        created_at="2026-10-26T12:00:00Z",
        warnings=["Model evaluation is inconclusive. Manual field verification recommended."]
    )
    assert resp.predicted_class == "inconclusive"
    assert resp.is_inconclusive is True
    assert resp.is_ambiguous is True
    assert resp.confidence == 0.65
    assert len(resp.inconclusive_reasons) == 1
    # Verify serialization to dict and JSON roundtrip
    dumped = resp.model_dump()
    assert dumped["predicted_class"] == "inconclusive"
    assert dumped["is_inconclusive"] is True

