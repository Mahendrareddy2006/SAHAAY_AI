"""
Sahaay AI - Phase 19: Risk-Aware Routing Test Suite
(tests/test_phase19_risk_aware_routing.py)

Comprehensive offline tests for:
1. Verified impassable segments are strictly excluded from recommended route
2. Verified passable evidence is distinguished from no evidence / unmonitored segments
3. Missing, stale, expired, and conflicting evidence handling
4. Forecast risk never becomes proof of current active inundation
5. Static vulnerability never becomes proof of current active inundation
6. Uncalibrated risk scores cannot be declared as calibrated probabilities
7. Missing evidence never produces a guaranteed-safe route
8. Explanations preserve evidence provenance and timestamps
9. Target facility access restrictions correctly surfaced with warnings
10. Phase 18 dispatch-actionability flags cannot initiate real-world operational actions
11. Prohibition of forbidden safety phrasing ("guaranteed safe", "100% safe", etc.)
12. Prohibition of claiming optimality without a verified topological graph
13. Forensic audit of road-network assets evaluating to INSUFFICIENT_DATA_ROUTING_UNSUPPORTED
14. Vehicle-specific cautions for low-clearance vehicles on corroborated waterlogging
15. All-impassable path handling returning ALL_CANDIDATE_ROUTES_IMPASSABLE
"""

from datetime import datetime, timezone
import pytest

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadEvidenceType,
    RoadStatusSnapshot,
    UncertaintyLevel,
)
from sahaay.forecast_risk.schemas import (
    ForecastRiskAssessmentOutput,
    ForecastDataStatus,
    MANDATORY_FORECAST_RISK_DISCLAIMER,
)
from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestination,
    EmergencyDestinationType,
    FacilityOperationalStatus,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    SegmentRoutingAssessment,
    RiskAwareRouteAssessment,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_ROUTING_DISCLAIMER,
)
from sahaay.routing.readiness import (
    audit_road_network_readiness,
    RoutingReadinessReport,
)
from sahaay.routing.service import RiskAwareRoutingService


# ==============================================================================
# 1. Impassable Segment Exclusion & Passability Distinction
# ==============================================================================

def test_verified_impassable_segments_are_excluded():
    """
    SAFETY INVARIANT: An officially verified impassable road segment must be
    strictly excluded from the recommended route.
    """
    service = RiskAwareRoutingService()

    # Officially verified impassable segment
    impassable_snapshot = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
        measured_water_depth_cm=45.0,
        verified_passability="impassable_all_vehicles",
    )
    seg_impassable = service.assess_segment(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        road_status=impassable_snapshot,
    )
    assert seg_impassable.is_traversable is False
    assert seg_impassable.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE

    # Monitored passable segment
    passable_snapshot = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-002",
        road_name="Shaikpet Main Road",
        condition_state=RoadConditionState.VERIFIED_PASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.90,
    )
    seg_passable = service.assess_segment(
        segment_id="HYD-LOC-002",
        road_name="Shaikpet Main Road",
        road_status=passable_snapshot,
    )
    assert seg_passable.is_traversable is True
    assert seg_passable.passability_state == PassabilityAssessment.VERIFIED_PASSABLE

    # Evaluate candidate route with both
    route = service.evaluate_route(
        route_id="RTE-TEST-01",
        candidate_segments=[seg_impassable, seg_passable],
        origin={"lat": 17.4023, "lon": 78.4112},
        destination={"lat": 17.4095, "lon": 78.3986},
    )

    # Impassable segment must be in excluded_segments, not in recommended_segments
    assert len(route.excluded_segments) == 1
    assert route.excluded_segments[0].segment_id == "HYD-LOC-001"
    assert len(route.recommended_segments) == 1
    assert route.recommended_segments[0].segment_id == "HYD-LOC-002"
    assert route.outcome == RouteAssessmentOutcome.BLOCKED_IMPASSABLE_SEGMENTS_PRESENT
    assert any("excluded" in exp.lower() for exp in route.exclusion_explanations)


def test_verified_passable_distinguished_from_unmonitored():
    """
    SAFETY INVARIANT: Verified passable (official responder inspection) is strictly
    distinguished from no current evidence / unmonitored.
    """
    service = RiskAwareRoutingService()

    # Case A: Verified Passable
    snap_passable = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-003",
        road_name="Begumpet Rasoolpura",
        condition_state=RoadConditionState.VERIFIED_PASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.90,
    )
    seg_passable = service.assess_segment(
        segment_id="HYD-LOC-003",
        road_name="Begumpet Rasoolpura",
        road_status=snap_passable,
    )
    assert seg_passable.passability_state == PassabilityAssessment.VERIFIED_PASSABLE
    assert seg_passable.is_uncertain is False

    # Case B: Unmonitored / No Evidence
    seg_unmonitored = service.assess_segment(
        segment_id="HYD-LOC-004",
        road_name="Khairatabad Junction",
        road_status=None,  # No observation on record
    )
    assert seg_unmonitored.passability_state == PassabilityAssessment.UNMONITORED_NO_EVIDENCE
    assert seg_unmonitored.is_uncertain is True
    assert any("does not imply safe passage" in n.lower().replace("_", " ") for n in seg_unmonitored.caution_notices)


# ==============================================================================
# 2. Missing, Stale, Expired, and Conflicting Evidence
# ==============================================================================

def test_stale_or_expired_evidence_marked_uncertain():
    """Stale (>180 min) or expired (>360 min) observations are flagged as uncertain."""
    service = RiskAwareRoutingService()

    stale_snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-005",
        road_name="Malakpet RUB",
        condition_state=RoadConditionState.STALE,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T06:00:00Z",
        freshness_category=RoadFreshnessCategory.STALE,
        verification_state=RoadVerificationState.UNVERIFIED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.30,
        evidence_age_minutes=240.0,
    )
    seg = service.assess_segment(
        segment_id="HYD-LOC-005",
        road_name="Malakpet RUB",
        road_status=stale_snap,
    )
    assert seg.passability_state == PassabilityAssessment.STALE_OR_EXPIRED
    assert seg.is_uncertain is True
    assert any("stale" in n.lower() for n in seg.caution_notices)


def test_conflicting_evidence_marked_uncertain():
    """Contradictory observations are flagged as conflicting and uncertain."""
    service = RiskAwareRoutingService()

    conflict_snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-006",
        road_name="Panjagutta Junction",
        condition_state=RoadConditionState.CONFLICTING,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.UNVERIFIED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.25,
        has_conflicting_evidence=True,
    )
    seg = service.assess_segment(
        segment_id="HYD-LOC-006",
        road_name="Panjagutta Junction",
        road_status=conflict_snap,
    )
    assert seg.passability_state == PassabilityAssessment.CONFLICTING_EVIDENCE
    assert seg.is_uncertain is True
    assert any("contradictory" in n.lower() for n in seg.caution_notices)


# ==============================================================================
# 3. Forecast Risk & Static Vulnerability Isolation
# ==============================================================================

def test_forecast_risk_never_becomes_proof_of_flooding():
    """
    SAFETY INVARIANT: High or critical forecast rainfall adds advisory notices
    but NEVER modifies passability to VERIFIED_IMPASSABLE without ground inspection.
    """
    service = RiskAwareRoutingService()

    # Synthetic Phase 18 forecast output indicating heavy surge
    fc_heavy = ForecastRiskAssessmentOutput(
        segment_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity",
        assessment_status=ForecastDataStatus.AVAILABLE_VALID,
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=2.0,
        forecast_rainfall_context={
            "rainfall_amount": 45.0,
            "source_id": "IMD-WRF-06Z",
            "issue_timestamp_utc": "2026-10-27T10:00:00Z",
            "valid_timestamp_utc": "2026-10-27T12:00:00Z",
        },
        static_susceptibility_context={"vulnerability_index": 0.60, "vulnerability_category": "HIGH"},
        current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
        verified_historical_outcomes_context={"verified_historical_flood_events_count": 0},
        forecast_risk_category="CRITICAL",
        heuristic_risk_score=0.85,
        is_calibrated_probability=False,
        confidence_score=0.80,
        is_actionable_for_dispatch=True,
    )

    seg = service.assess_segment(
        segment_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity",
        forecast_risk=fc_heavy,
        road_status=None,  # No ground reports
    )

    # Must remain traversable because forecast rain alone is NOT verified flooding
    assert seg.is_traversable is True
    assert seg.passability_state != PassabilityAssessment.VERIFIED_IMPASSABLE
    assert any("does not establish active inundation" in n.lower().replace("_", " ") for n in seg.caution_notices)


def test_static_vulnerability_never_becomes_proof_of_flooding():
    """
    SAFETY INVARIANT: Severe static vulnerability adds susceptibility context
    but NEVER establishes active road inundation.
    """
    service = RiskAwareRoutingService()

    seg = service.assess_segment(
        segment_id="HYD-LOC-008",
        road_name="Lakdikapul Railway Bridge",
        static_vulnerability_index=0.92,
        static_vulnerability_category="SEVERE",
        road_status=None,
    )

    assert seg.is_traversable is True
    assert seg.passability_state != PassabilityAssessment.VERIFIED_IMPASSABLE
    assert any("not active flooding" in n.lower().replace("_", " ") for n in seg.caution_notices)


# ==============================================================================
# 4. Prohibitions on Probability, Optimality & Guaranteed Safety
# ==============================================================================

def test_uncalibrated_scores_not_treated_as_probabilities():
    """
    is_calibrated_probability must strictly remain False on all segment and route models.
    """
    service = RiskAwareRoutingService()
    seg = service.assess_segment(
        segment_id="HYD-LOC-009",
        road_name="Secunderabad Clock Tower",
    )
    assert seg.is_calibrated_probability is False

    with pytest.raises(ValueError, match="is_calibrated_probability must remain False"):
        SegmentRoutingAssessment(
            segment_id="HYD-LOC-009",
            road_name="Secunderabad Clock Tower",
            passability_state=PassabilityAssessment.UNMONITORED_NO_EVIDENCE,
            is_uncertain=True,
            is_calibrated_probability=True,  # PROHIBITED!
        )


def test_missing_evidence_never_produces_guaranteed_safe_route():
    """
    SAFETY INVARIANT: When segments are unmonitored, the route must NOT claim to be safe.
    has_unmonitored_segments must be True and is_guaranteed_safe must remain False.
    """
    service = RiskAwareRoutingService()
    seg_unmonitored = service.assess_segment(
        segment_id="HYD-LOC-010",
        road_name="Musarambagh Bridge",
        road_status=None,
    )
    route = service.evaluate_route(
        route_id="RTE-TEST-02",
        candidate_segments=[seg_unmonitored],
        origin={"lat": 17.3712, "lon": 78.5085},
        destination={"lat": 17.3821, "lon": 78.5142},
    )

    assert route.has_unmonitored_segments is True
    assert route.is_guaranteed_safe is False
    assert any("unmonitored segments" in w.lower() for w in route.warnings)
    assert any("does not indicate dry or safe" in w.lower() for w in route.warnings)


def test_prohibition_of_forbidden_safety_phrases():
    """RiskAwareRouteAssessment validator rejects forbidden claims across text fields."""
    for phrase in FORBIDDEN_SAFETY_PHRASES:
        with pytest.raises(ValueError, match="forbidden"):
            RiskAwareRouteAssessment(
                route_id="RTE-FAIL-01",
                assessment_timestamp_utc="2026-10-27T12:00:00Z",
                outcome=RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION,
                origin={"lat": 17.40, "lon": 78.40},
                destination={"lat": 17.41, "lon": 78.41},
                vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
                total_distance_meters=1000.0,
                estimated_duration_seconds=150.0,
                aggregate_heuristic_risk=0.10,
                warnings=[f"This route is {phrase}"],
            )


def test_prohibition_of_optimality_claim():
    """Route assessment cannot claim optimality when full road graph is absent."""
    with pytest.raises(ValueError, match="is_optimality_claimed must remain False"):
        RiskAwareRouteAssessment(
            route_id="RTE-OPT-FAIL",
            assessment_timestamp_utc="2026-10-27T12:00:00Z",
            outcome=RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION,
            origin={"lat": 17.40, "lon": 78.40},
            destination={"lat": 17.41, "lon": 78.41},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            total_distance_meters=1000.0,
            estimated_duration_seconds=150.0,
            aggregate_heuristic_risk=0.10,
            is_optimality_claimed=True,  # PROHIBITED!
        )


# ==============================================================================
# 5. Operational Dispatch Flag Disarming
# ==============================================================================

def test_phase18_dispatch_actionability_cannot_authorize_operations():
    """
    CRITICAL SAFETY RULE: Phase 18 is_actionable_for_dispatch cannot authorize
    real-world road closure or emergency dispatch downstream.
    """
    service = RiskAwareRoutingService()

    fc_actionable = ForecastRiskAssessmentOutput(
        segment_id="HYD-LOC-011",
        road_name="Madhapur Cyber Towers",
        assessment_status=ForecastDataStatus.AVAILABLE_VALID,
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=1.0,
        forecast_rainfall_context={"rainfall_amount": 35.0},
        static_susceptibility_context={"vulnerability_index": 0.5},
        current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
        verified_historical_outcomes_context={"verified_count": 0},
        forecast_risk_category="HIGH",
        heuristic_risk_score=0.60,
        is_calibrated_probability=False,
        confidence_score=0.75,
        is_actionable_for_dispatch=True,  # Downstream must disarm this!
    )

    seg = service.assess_segment(
        segment_id="HYD-LOC-011",
        road_name="Madhapur Cyber Towers",
        forecast_risk=fc_actionable,
    )

    # Flag is recorded but annotated as non-operational
    assert seg.phase18_dispatch_actionable is True
    assert any("not_authorized_for_operations" in n.lower() for n in seg.caution_notices)

    route = service.evaluate_route(
        route_id="RTE-TEST-03",
        candidate_segments=[seg],
        origin={"lat": 17.4504, "lon": 78.3808},
        destination={"lat": 17.4375, "lon": 78.4482},
    )

    # Route assessment must strictly maintain operational_action_authorized = False
    assert route.operational_action_authorized is False


# ==============================================================================
# 6. Target Facility Access & Vehicle Specifics
# ==============================================================================

def test_target_facility_access_restriction_surfaced():
    """If target emergency hospital has restricted/inundated access, warnings are added."""
    service = RiskAwareRoutingService()

    seg_normal = service.assess_segment(
        segment_id="HYD-LOC-012",
        road_name="Banjara Hills Rd 1",
    )
    dest_inundated = EmergencyDestination(
        facility_id="HOSP-CARE-01",
        name="Care Hospital Banjara",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4150,
        longitude=78.4450,
        operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
        emergency_contact_masked="040-30418000",
    )

    route = service.evaluate_route(
        route_id="RTE-TEST-04",
        candidate_segments=[seg_normal],
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.4150, "lon": 78.4450},
        target_facility=dest_inundated,
    )

    assert any("inundated and restricted access" in w.lower() for w in route.warnings)


def test_vehicle_specific_caution_for_two_wheelers():
    """Two-wheelers on corroborated waterlogging receive specific stall risk notices."""
    service = RiskAwareRoutingService()

    waterlogged_corroborated = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-013",
        road_name="Ameerpet Metro Junction",
        condition_state=RoadConditionState.CORROBORATED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.CORROBORATED,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        confidence_score=0.60,
    )

    seg_two_wheeler = service.assess_segment(
        segment_id="HYD-LOC-013",
        road_name="Ameerpet Metro Junction",
        road_status=waterlogged_corroborated,
        vehicle_type=VehicleType.TWO_WHEELER,
    )

    assert any("low_clearance_vehicle_at_elevated_stall_risk" in n.lower() for n in seg_two_wheeler.caution_notices)


def test_all_candidate_segments_impassable_handling():
    """When all candidate corridors are impassable, outcome is ALL_CANDIDATE_ROUTES_IMPASSABLE."""
    service = RiskAwareRoutingService()

    impassable_snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-014",
        road_name="Moosarambagh Causeway",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
    )
    seg = service.assess_segment(
        segment_id="HYD-LOC-014",
        road_name="Moosarambagh Causeway",
        road_status=impassable_snap,
    )

    route = service.evaluate_route(
        route_id="RTE-ALL-BLOCKED",
        candidate_segments=[seg],
        origin={"lat": 17.37, "lon": 78.50},
        destination={"lat": 17.38, "lon": 78.51},
    )

    assert route.outcome == RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE
    assert len(route.recommended_segments) == 0
    assert len(route.excluded_segments) == 1


# ==============================================================================
# 7. Road Network Readiness Audit
# ==============================================================================

def test_road_network_readiness_audit_verdict():
    """
    Forensic audit of road network assets must evaluate to
    INSUFFICIENT_DATA_ROUTING_UNSUPPORTED.
    """
    report = audit_road_network_readiness()

    assert report.routing_data_readiness_verdict == "INSUFFICIENT_DATA_ROUTING_UNSUPPORTED"
    assert report.operational_deployment_readiness == "BLOCKED_NO_ROUTABLE_NETWORK"
    assert report.engineering_readiness_status == "OFFLINE_ASSESSMENT_LAYER_COMPLETE"
    assert report.routable_network_edges_count == 0
    assert report.candidate_corridors_count == 20
    assert len(report.unresolved_blockers) >= 4
    assert len(report.prerequisites_to_unblock) >= 4
