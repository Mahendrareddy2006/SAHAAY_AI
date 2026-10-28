"""
Sahaay AI - Phase 20: Emergency Mode Test Suite
(tests/test_phase20_emergency_mode.py)

Comprehensive offline tests for:
1. Valid emergency-state transitions and state machine progression
2. Rejection of invalid state transitions (no auto-resolution, no bypass)
3. Role authorization checks for human incident review and resolution
4. Resolution requirements (justification notes >= 10 chars, SHA-256 audit hash)
5. Deterministic review prioritization (P1, P2, P3, P4, P0) with inspectable reasons
6. Verified vs unverified evidence handling (distinguishing urgency from certainty)
7. Degraded mode on conflicting, stale, or expired telemetry
8. Forecast-only and static-vulnerability-only escalation boundaries
9. Prohibition of automatic resolution from timeouts or telemetry silence
10. Strict disarming of autonomous dispatch, closures, alerts, or external side effects
11. Personal-data minimization and reporter tokenization
12. Prohibition of forbidden safety assertions and uncalibrated probability claims
13. Forensic emergency-readiness audit evaluating to BLOCKED_PENDING_INSTITUTIONAL_AUTHORIZATION
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
)
from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestination,
    EmergencyDestinationType,
    FacilityOperationalStatus,
)
from sahaay.routing.schemas import (
    RouteAssessmentOutcome,
    RiskAwareRouteAssessment,
)
from sahaay.emergency.schemas import (
    EmergencyState,
    EmergencyPriority,
    AuthorizedReviewerRole,
    EmergencyResolutionRecord,
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_EMERGENCY_MODE_DISCLAIMER,
)
from sahaay.emergency.workflow import (
    EmergencyWorkflowEngine,
    VALID_STATE_TRANSITIONS,
)
from sahaay.emergency.readiness import (
    audit_emergency_mode_readiness,
    EmergencyModeReadinessReport,
)


# ==============================================================================
# 1. State Machine & Transition Invariants
# ==============================================================================

def test_valid_state_progression_with_human_resolution():
    """
    Verifies valid emergency lifecycle progression:
    INACTIVE -> ACTIVE_ASSESSMENT -> NEEDS_HUMAN_REVIEW -> RESOLVED_BY_AUTHORIZED_REVIEW
    """
    engine = EmergencyWorkflowEngine()

    # Step 1: Ingest urgent verified impassable report -> NEEDS_HUMAN_REVIEW
    snap_impassable = RoadStatusSnapshot(
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
    input_data = EmergencyAssessmentInput(
        incident_id="INC-2026-001",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        road_status_snapshot=snap_impassable,
        is_synthetic_fixture=True,
    )

    assessment = engine.evaluate_emergency_assessment(input_data)
    assert assessment.current_state == EmergencyState.NEEDS_HUMAN_REVIEW
    assert assessment.review_priority == EmergencyPriority.P1_URGENT_VERIFIED
    assert assessment.resolution_record is None

    # Step 2: Authorized human reviewer resolves incident
    resolved_assessment = engine.resolve_emergency(
        assessment=assessment,
        reviewer_role=AuthorizedReviewerRole.GHMC_DRF_SUPERVISOR,
        reviewer_id="DRF-OFFICER-442",
        action_type="DISPATCH_MANUAL_WATER_PUMP_TENDER",
        justification_notes="Verified 45cm flooding at Tolichowki underpass. Deployed manual suction pump team.",
    )

    assert resolved_assessment.current_state == EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW
    assert resolved_assessment.resolution_record is not None
    assert resolved_assessment.resolution_record.reviewer_role == AuthorizedReviewerRole.GHMC_DRF_SUPERVISOR
    assert len(resolved_assessment.resolution_record.audit_hash) == 64
    assert len(resolved_assessment.state_transition_history) >= 1


def test_rejection_of_resolution_without_authorized_role():
    """Attempting resolution with an unauthorized role or string raises PermissionError."""
    engine = EmergencyWorkflowEngine()

    assessment = EmergencyModeAssessment(
        incident_id="INC-2026-002",
        corridor_id="HYD-LOC-002",
        road_name="Shaikpet Nala Road",
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
        review_priority=EmergencyPriority.P2_HIGH_CORROBORATED,
        urgency_heuristic_score=0.75,
        is_calibrated_probability=False,
        ground_status_evidence={},
        forecast_rainfall_context={},
        static_susceptibility_context={},
        routing_impact_context={},
    )

    with pytest.raises(PermissionError, match="not an authorized municipal reviewer"):
        engine.resolve_emergency(
            assessment=assessment,
            reviewer_role="UNAUTHORIZED_CITIZEN_USER",  # Invalid!
            reviewer_id="ANON-USER-1",
            action_type="CLOSE_INCIDENT",
            justification_notes="Looks fine now according to social media.",
        )


def test_rejection_of_resolution_with_insufficient_justification():
    """Attempting resolution without substantive justification (<10 chars) raises ValueError."""
    engine = EmergencyWorkflowEngine()

    assessment = EmergencyModeAssessment(
        incident_id="INC-2026-003",
        corridor_id="HYD-LOC-003",
        road_name="Begumpet Underpass",
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
        review_priority=EmergencyPriority.P1_URGENT_VERIFIED,
        urgency_heuristic_score=0.90,
        is_calibrated_probability=False,
        ground_status_evidence={},
        forecast_rainfall_context={},
        static_susceptibility_context={},
        routing_impact_context={},
    )

    with pytest.raises(ValueError, match="minimum 10 characters"):
        engine.resolve_emergency(
            assessment=assessment,
            reviewer_role=AuthorizedReviewerRole.TRAFFIC_POLICE_DUTY_OFFICER,
            reviewer_id="TP-DUTY-101",
            action_type="RESOLVE",
            justification_notes="Done.",  # Too short!
        )


def test_prohibition_of_auto_resolution_on_timeout():
    """
    CRITICAL SAFETY INVARIANT: Emergencies can NEVER resolve automatically
    due to timeout, silence, or elapsed time.
    """
    engine = EmergencyWorkflowEngine()
    assessment = EmergencyModeAssessment(
        incident_id="INC-2026-004",
        corridor_id="HYD-LOC-004",
        road_name="Khairatabad Junction",
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
        review_priority=EmergencyPriority.P1_URGENT_VERIFIED,
        urgency_heuristic_score=0.95,
        is_calibrated_probability=False,
        ground_status_evidence={},
        forecast_rainfall_context={},
        static_susceptibility_context={},
        routing_impact_context={},
    )

    with pytest.raises(RuntimeError, match="Automatic resolution of emergency mode .* is strictly prohibited"):
        engine.attempt_auto_resolve_on_timeout(assessment)


# ==============================================================================
# 2. Prioritization & Evidence Distinction (Urgency vs Certainty)
# ==============================================================================

def test_p1_urgent_priority_for_verified_impassable_flooding():
    """Verified impassable flooding triggers P1 Urgent review with high certainty."""
    engine = EmergencyWorkflowEngine()

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-005",
        road_name="Malakpet RUB",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
        measured_water_depth_cm=35.0,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-P1-01",
        corridor_id="HYD-LOC-005",
        road_name="Malakpet RUB",
        road_status_snapshot=snap,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.review_priority == EmergencyPriority.P1_URGENT_VERIFIED
    assert res.evidence_certainty_level == "VERIFIED"
    assert res.urgency_heuristic_score >= 0.90
    assert any("verified_impassable" in r.lower() for r in res.priority_reason_codes)


def test_p1_urgent_priority_for_inundated_hospital_access():
    """Inundated emergency hospital access triggers P1 Urgent priority."""
    engine = EmergencyWorkflowEngine()

    hosp = EmergencyDestination(
        facility_id="HOSP-CARE-01",
        name="Care Hospital Banjara",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4150,
        longitude=78.4450,
        operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
        emergency_contact_masked="040-30418000",
    )
    route_assessment = RiskAwareRouteAssessment(
        route_id="RTE-HOSP-01",
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        outcome=RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION,
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.415, "lon": 78.445},
        vehicle_type=VehicleType.HIGH_CLEARANCE_SUV,
        target_facility=hosp,
        total_distance_meters=2000.0,
        estimated_duration_seconds=300.0,
        aggregate_heuristic_risk=0.80,
        warnings=["Target emergency facility has restricted access."],
    )

    inp = EmergencyAssessmentInput(
        incident_id="INC-HOSP-01",
        corridor_id="HYD-LOC-006",
        road_name="Road No 1 Banjara Hills",
        route_assessment_output=route_assessment,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.review_priority == EmergencyPriority.P1_URGENT_VERIFIED
    assert any("hospital_access_inundated" in r.lower() for r in res.priority_reason_codes)


def test_p2_high_priority_for_corroborated_citizen_reports():
    """Corroborated citizen reports trigger P2 High review with CORROBORATED certainty."""
    engine = EmergencyWorkflowEngine()

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-007",
        road_name="Panjagutta Junction",
        condition_state=RoadConditionState.CORROBORATED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.CORROBORATED,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        confidence_score=0.65,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-P2-01",
        corridor_id="HYD-LOC-007",
        road_name="Panjagutta Junction",
        road_status_snapshot=snap,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.review_priority == EmergencyPriority.P2_HIGH_CORROBORATED
    assert res.evidence_certainty_level == "CORROBORATED"
    assert res.urgency_heuristic_score == 0.75


def test_p3_medium_priority_for_unverified_single_report():
    """Single uncorroborated report triggers P3 Medium review with UNVERIFIED certainty."""
    engine = EmergencyWorkflowEngine()

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-008",
        road_name="Lakdikapul Corridor",
        condition_state=RoadConditionState.UNVERIFIED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.UNVERIFIED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.40,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-P3-01",
        corridor_id="HYD-LOC-008",
        road_name="Lakdikapul Corridor",
        road_status_snapshot=snap,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.review_priority == EmergencyPriority.P3_MEDIUM_UNVERIFIED
    assert res.evidence_certainty_level == "UNVERIFIED"
    assert res.urgency_heuristic_score == 0.50


# ==============================================================================
# 3. Degraded Mode on Defective / Stale Telemetry
# ==============================================================================

def test_degraded_mode_on_conflicting_evidence():
    """Contradictory evidence triggers DEGRADED_INSUFFICIENT_DATA and P0 priority."""
    engine = EmergencyWorkflowEngine()

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-009",
        road_name="Secunderabad Subway",
        condition_state=RoadConditionState.CONFLICTING,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T12:00:00Z",
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.UNVERIFIED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.20,
        has_conflicting_evidence=True,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-DEG-01",
        corridor_id="HYD-LOC-009",
        road_name="Secunderabad Subway",
        road_status_snapshot=snap,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.current_state == EmergencyState.DEGRADED_INSUFFICIENT_DATA
    assert res.review_priority == EmergencyPriority.P0_DEGRADED_TRIAGE
    assert "CONFLICTING_REPORTS" in res.quality_flags


def test_degraded_mode_on_expired_evidence():
    """Expired telemetry triggers DEGRADED_INSUFFICIENT_DATA and P0 priority."""
    engine = EmergencyWorkflowEngine()

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-010",
        road_name="Musarambagh Bridge",
        condition_state=RoadConditionState.EXPIRED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc="2026-10-27T04:00:00Z",
        freshness_category=RoadFreshnessCategory.EXPIRED,
        verification_state=RoadVerificationState.EXPIRED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.15,
        evidence_age_minutes=480.0,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-DEG-02",
        corridor_id="HYD-LOC-010",
        road_name="Musarambagh Bridge",
        road_status_snapshot=snap,
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    assert res.current_state == EmergencyState.DEGRADED_INSUFFICIENT_DATA
    assert res.review_priority == EmergencyPriority.P0_DEGRADED_TRIAGE
    assert "EXPIRED_TELEMETRY" in res.quality_flags


# ==============================================================================
# 4. Forecast & Vulnerability Escalation Boundaries
# ==============================================================================

def test_forecast_and_vulnerability_escalate_urgency_not_closure():
    """
    Critical forecast surge on severe vulnerability corridor escalates priority to P2
    for human attention, but does NOT declare road closures or autonomous dispatch.
    """
    engine = EmergencyWorkflowEngine()

    fc_surge = ForecastRiskAssessmentOutput(
        segment_id="HYD-LOC-011",
        road_name="Madhapur Corridor",
        assessment_status=ForecastDataStatus.AVAILABLE_VALID,
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=2.0,
        forecast_rainfall_context={"rainfall_amount": 42.0},
        static_susceptibility_context={"vulnerability_index": 0.85, "vulnerability_category": "SEVERE"},
        current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
        verified_historical_outcomes_context={"verified_count": 0},
        forecast_risk_category="CRITICAL",
        heuristic_risk_score=0.88,
        is_calibrated_probability=False,
        confidence_score=0.80,
        is_actionable_for_dispatch=True,
    )
    inp = EmergencyAssessmentInput(
        incident_id="INC-FC-01",
        corridor_id="HYD-LOC-011",
        road_name="Madhapur Corridor",
        forecast_risk_output=fc_surge,
        static_vulnerability_index=0.85,
        static_vulnerability_category="SEVERE",
        is_synthetic_fixture=True,
    )

    res = engine.evaluate_emergency_assessment(inp)
    # Escalated to P2 for expedited human oversight
    assert res.review_priority == EmergencyPriority.P2_HIGH_CORROBORATED
    assert res.current_state == EmergencyState.NEEDS_HUMAN_REVIEW
    # Crucial safety invariants:
    assert res.operational_action_authorized is False
    assert res.external_side_effects_triggered is False


# ==============================================================================
# 5. Operational Safety Boundaries & Privacy
# ==============================================================================

def test_operational_action_prohibited_invariant():
    """EmergencyModeAssessment strictly rejects operational_action_authorized=True."""
    with pytest.raises(ValueError, match="operational_action_authorized must remain False"):
        EmergencyModeAssessment(
            incident_id="INC-FAIL-01",
            corridor_id="HYD-LOC-012",
            road_name="Balanagar Cross Road",
            assessment_timestamp_utc="2026-10-27T12:00:00Z",
            current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
            review_priority=EmergencyPriority.P1_URGENT_VERIFIED,
            urgency_heuristic_score=0.95,
            is_calibrated_probability=False,
            ground_status_evidence={},
            forecast_rainfall_context={},
            static_susceptibility_context={},
            routing_impact_context={},
            operational_action_authorized=True,  # PROHIBITED!
        )


def test_external_side_effects_prohibited_invariant():
    """EmergencyModeAssessment strictly rejects external_side_effects_triggered=True."""
    with pytest.raises(ValueError, match="external_side_effects_triggered must remain False"):
        EmergencyModeAssessment(
            incident_id="INC-FAIL-02",
            corridor_id="HYD-LOC-013",
            road_name="Alwal Low-Lying Area",
            assessment_timestamp_utc="2026-10-27T12:00:00Z",
            current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
            review_priority=EmergencyPriority.P1_URGENT_VERIFIED,
            urgency_heuristic_score=0.95,
            is_calibrated_probability=False,
            ground_status_evidence={},
            forecast_rainfall_context={},
            static_susceptibility_context={},
            routing_impact_context={},
            external_side_effects_triggered=True,  # PROHIBITED!
        )


def test_personal_data_masking_enforced():
    """personal_data_masked must remain True: reporter PII must be protected."""
    with pytest.raises(ValueError, match="personal_data_masked must remain True"):
        EmergencyModeAssessment(
            incident_id="INC-FAIL-03",
            corridor_id="HYD-LOC-014",
            road_name="Mehdipatnam Road",
            assessment_timestamp_utc="2026-10-27T12:00:00Z",
            current_state=EmergencyState.ACTIVE_ASSESSMENT,
            review_priority=EmergencyPriority.P4_LOW_ADVISORY,
            urgency_heuristic_score=0.10,
            is_calibrated_probability=False,
            ground_status_evidence={},
            forecast_rainfall_context={},
            static_susceptibility_context={},
            routing_impact_context={},
            personal_data_masked=False,  # PROHIBITED!
        )


def test_prohibition_of_forbidden_safety_phrases():
    """EmergencyModeAssessment validator rejects forbidden phrasing across reason codes."""
    for phrase in FORBIDDEN_SAFETY_PHRASES:
        with pytest.raises(ValueError, match="forbidden"):
            EmergencyModeAssessment(
                incident_id="INC-FAIL-04",
                corridor_id="HYD-LOC-015",
                road_name="Miyapur Junction",
                assessment_timestamp_utc="2026-10-27T12:00:00Z",
                current_state=EmergencyState.ACTIVE_ASSESSMENT,
                review_priority=EmergencyPriority.P4_LOW_ADVISORY,
                urgency_heuristic_score=0.10,
                is_calibrated_probability=False,
                ground_status_evidence={},
                forecast_rainfall_context={},
                static_susceptibility_context={},
                routing_impact_context={},
                priority_reason_codes=[f"Claiming {phrase}"],
            )


# ==============================================================================
# 6. Institutional Readiness Audit Verification
# ==============================================================================

def test_emergency_mode_readiness_audit_verdict():
    """
    Forensic audit of emergency-response prerequisites must evaluate to
    BLOCKED_PENDING_INSTITUTIONAL_AUTHORIZATION.
    """
    report = audit_emergency_mode_readiness()

    assert report.emergency_readiness_verdict == "BLOCKED_PENDING_INSTITUTIONAL_AUTHORIZATION"
    assert report.operational_deployment_readiness == "BLOCKED_NO_LEGAL_DISPATCH_AUTHORITY"
    assert report.software_engineering_status == "OFFLINE_ASSESSMENT_LAYER_COMPLETE"
    assert report.authorized_prerequisites_count == 0
    assert report.active_live_integrations_count == 0
    assert report.total_prerequisites_audited == 4
    assert len(report.unresolved_blockers) >= 4
    assert len(report.prerequisites_to_unblock) >= 4
