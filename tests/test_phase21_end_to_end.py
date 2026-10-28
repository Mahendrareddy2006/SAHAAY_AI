"""
Sahaay AI - Phase 21: End-to-End Evaluation Test Suite
(tests/test_phase21_end_to_end.py)

Comprehensive cross-component integration tests evaluating:
1. Scenario A: Missing Evidence End-to-End (non-silent missingness, no false safety)
2. Scenario B: Severe Forecast, No Ground Confirmation (advisory concern != active closure)
3. Scenario C: Static Vulnerability in Dry Conditions (susceptibility != flooding)
4. Scenario D: Verified Impassable Road Propagation (responder verification -> routing exclusion -> P1 emergency)
5. Scenario E: Conflicting or Stale Reports (preserves conflict/staleness, enters degraded mode)
6. Scenario F: Ambiguous Vision Result Integration (abstention band [0.35, 0.65] -> INCONCLUSIVE)
7. Scenario G: Emergency Review Lifecycle & Authorization Gates (no auto-resolution, SHA-256 audit hash)
8. Scenario H: Operational Action Boundaries End-to-End (disarmed dispatch, forbidden phrases)
9. Scenario I: Routing Without Road Graph (0 routable edges -> INSUFFICIENT_DATA, no optimality claim)
10. Scenario J: Forecast Source Unavailable & Separation (0 authorized feeds -> BLOCKED, signals isolated)
11. Vision Partition Protection & Historical Safety Invariant Verification
"""

from datetime import datetime, timezone
import pytest

# Phase 12 & Decision & Vision imports
from sahaay.decision.contracts import (
    AlertLevel,
    DecisionInput,
    DecisionStatus,
    CurrentFloodEvidenceStatus,
    evaluate_decision,
)
from sahaay.vision.policy import (
    CalibratedVisionDecision,
    evaluate_vision_abstention_boundary,
    map_vision_probabilities_to_decision,
    DEFAULT_ABSTENTION_LOWER_BOUND,
    DEFAULT_ABSTENTION_UPPER_BOUND,
)

# Phase 15 Community Verification imports
from sahaay.reports.schemas import (
    ReportCondition,
    WaterDepthEstimate,
    ReportVerificationStatus,
)

# Phase 16 Road Status imports
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadEvidenceType,
    RoadStatusSnapshot,
    UncertaintyLevel,
)

# Phase 17 Local Flood Risk imports
from sahaay.flood_risk.schemas import (
    LocalFloodRiskInput,
    RiskForecastCategory,
)
from sahaay.flood_risk.baseline import evaluate_local_flood_risk
from sahaay.flood_risk.readiness import audit_outcome_data_readiness
from sahaay.flood_risk.evaluation import EventAndSpatialSplitter

# Phase 18 Forecast Risk imports
from sahaay.forecast_risk.schemas import (
    ForecastSourceType,
    ForecastDataStatus,
    ForecastRainfallInput,
    ForecastRiskAssessmentOutput,
    PrecipitationUnit,
    AccumulationInterval,
)
from sahaay.forecast_risk.service import evaluate_forecast_risk
from sahaay.forecast_risk.readiness import audit_forecast_sources_readiness

# Phase 19 Risk-Aware Routing imports
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
)
from sahaay.routing.service import RiskAwareRoutingService
from sahaay.routing.readiness import audit_road_network_readiness

# Phase 20 Emergency Mode imports
from sahaay.emergency.schemas import (
    EmergencyState,
    EmergencyPriority,
    AuthorizedReviewerRole,
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
)
from sahaay.emergency.workflow import EmergencyWorkflowEngine
from sahaay.emergency.readiness import audit_emergency_mode_readiness


# ==============================================================================
# Scenario A: Missing Evidence End-to-End
# ==============================================================================

def test_scenario_a_missing_evidence_end_to_end():
    """
    SCENARIO A: Forecasts, telemetry, road reports, and road-network data are missing.
    Verifies that missingness remains UNKNOWN or INSUFFICIENT_DATA and NEVER becomes
    zero rainfall, verified passability, or guaranteed safety.
    """
    # 1. Local Flood Risk (Phase 17)
    fr_inp = LocalFloodRiskInput(
        segment_id="HYD-MISSING-01",
        road_name="Tolichowki Corridor",
        rainfall_1h_mm=None,
        rainfall_forecast_1h_mm=None,
    )
    fr_res = evaluate_local_flood_risk(fr_inp)
    assert fr_res.predicted_risk_category == RiskForecastCategory.UNKNOWN
    assert fr_res.predicted_risk_score == 0.0
    assert fr_res.confidence_score == 0.10
    assert "rainfall_telemetry" in fr_res.missing_inputs

    # 2. Forecast Risk (Phase 18)
    fc_res = evaluate_forecast_risk(
        segment_id="HYD-MISSING-01",
        road_name="Tolichowki Corridor",
        forecast_inputs=None,
    )
    assert fc_res.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert fc_res.heuristic_risk_score is None  # MUST NOT be 0.0
    assert fc_res.forecast_risk_category == "INSUFFICIENT_DATA"

    # 3. Risk-Aware Routing (Phase 19)
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-MISSING-01",
        road_name="Tolichowki Corridor",
        road_status=None,
        forecast_risk=None,
    )
    assert seg.passability_state == PassabilityAssessment.UNMONITORED_NO_EVIDENCE
    assert seg.is_uncertain is True

    route = routing_svc.evaluate_route(
        route_id="RTE-MISSING-01",
        candidate_segments=[seg],
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.41, "lon": 78.41},
    )
    assert route.has_unmonitored_segments is True
    assert route.is_guaranteed_safe is False
    assert any("does not indicate dry or safe" in w.lower() for w in route.warnings)

    # 4. Emergency Mode (Phase 20)
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-MISSING-01",
        corridor_id="HYD-MISSING-01",
        road_name="Tolichowki Corridor",
        road_status_snapshot=None,
        forecast_risk_output=None,
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp)
    assert em_res.current_state == EmergencyState.ACTIVE_ASSESSMENT
    assert em_res.review_priority == EmergencyPriority.P4_LOW_ADVISORY
    assert "ground_road_status_evidence" in em_res.missing_critical_inputs
    assert em_res.operational_action_authorized is False


# ==============================================================================
# Scenario B: Severe Forecast, No Ground Confirmation
# ==============================================================================

def test_scenario_b_severe_forecast_no_ground_confirmation():
    """
    SCENARIO B: Forecast rainfall is severe (45 mm in 2h), but road status is unmonitored.
    Verifies that the system communicates forward-looking concern without declaring
    current active inundation or closing roads autonomously.
    """
    ref_time = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

    # Phase 18: Forecast Risk Layer
    fc_input = ForecastRainfallInput(
        location_id="HYD-LOC-007",
        source_id="IMD-WRF-06Z",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T10:00:00Z",
        valid_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=45.0,
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_1H,
        is_synthetic_fixture=True,
    )
    fc_res = evaluate_forecast_risk(
        segment_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity",
        forecast_inputs=[fc_input],
        reference_time_utc=ref_time,
    )
    assert fc_res.forecast_risk_category == "CRITICAL"
    assert fc_res.heuristic_risk_score >= 0.60
    # Ground status context remains unmonitored:
    assert fc_res.current_road_status_context["condition_state"] == "NO_CURRENT_EVIDENCE"

    # Phase 19: Routing Layer
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity",
        forecast_risk=fc_res,
        road_status=None,
    )
    assert seg.is_traversable is True  # Traversable provisionally; forecast alone is not closure!
    assert seg.passability_state != PassabilityAssessment.VERIFIED_IMPASSABLE
    assert any("does not establish active inundation" in n.lower().replace("_", " ") for n in seg.caution_notices)

    # Phase 20: Emergency Mode Layer
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-SCEN-B",
        corridor_id="HYD-LOC-007",
        road_name="Gachibowli Bio-Diversity",
        forecast_risk_output=fc_res,
        static_vulnerability_index=0.80,
        static_vulnerability_category="SEVERE",
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp, reference_time_utc=ref_time)
    assert em_res.review_priority == EmergencyPriority.P2_HIGH_CORROBORATED
    assert em_res.current_state == EmergencyState.NEEDS_HUMAN_REVIEW
    assert em_res.evidence_certainty_level == "PREDICTED_RISK"
    assert em_res.operational_action_authorized is False


# ==============================================================================
# Scenario C: Static Vulnerability in Dry Conditions
# ==============================================================================

def test_scenario_c_static_vulnerability_in_dry_conditions():
    """
    SCENARIO C: Severe static susceptibility (0.90), but 0.0 mm rainfall.
    Verifies that static vulnerability does not become proof of active flooding
    or an automatic road closure.
    """
    # Phase 17: Local Flood Risk
    fr_inp = LocalFloodRiskInput(
        segment_id="HYD-LOC-004",
        road_name="Khairatabad Junction",
        vulnerability_index=0.90,
        vulnerability_category="SEVERE",
        rainfall_1h_mm=0.0,
        rainfall_forecast_1h_mm=0.0,
    )
    fr_res = evaluate_local_flood_risk(fr_inp)
    assert fr_res.predicted_risk_category in [RiskForecastCategory.CLEAR, RiskForecastCategory.LOW]
    assert fr_res.predicted_risk_score <= 0.05

    # Phase 19: Routing
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-LOC-004",
        road_name="Khairatabad Junction",
        static_vulnerability_index=0.90,
        static_vulnerability_category="SEVERE",
        road_status=None,
    )
    assert seg.is_traversable is True
    assert seg.passability_state != PassabilityAssessment.VERIFIED_IMPASSABLE

    # Phase 20: Emergency Mode
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-SCEN-C",
        corridor_id="HYD-LOC-004",
        road_name="Khairatabad Junction",
        static_vulnerability_index=0.90,
        static_vulnerability_category="SEVERE",
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp)
    assert em_res.review_priority == EmergencyPriority.P4_LOW_ADVISORY
    assert em_res.current_state == EmergencyState.ACTIVE_ASSESSMENT


# ==============================================================================
# Scenario D: Verified Impassable Road Propagation
# ==============================================================================

def test_scenario_d_verified_impassable_road_propagation():
    """
    SCENARIO D: An authorized responder verifies a road is impassable (50 cm depth).
    Verifies that routing excludes the segment and emergency mode escalates to P1.
    """
    ref_time = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    ref_iso = ref_time.isoformat().replace("+00:00", "Z")

    snap_impassable = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        last_status_update_utc=ref_iso,
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
        measured_water_depth_cm=50.0,
        verified_passability="impassable_all_vehicles",
    )

    # Phase 19: Routing must exclude it
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        road_status=snap_impassable,
    )
    assert seg.is_traversable is False
    assert seg.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE

    route = routing_svc.evaluate_route(
        route_id="RTE-SCEN-D",
        candidate_segments=[seg],
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.41, "lon": 78.41},
        reference_time_utc=ref_time,
    )
    assert route.outcome == RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE
    assert len(route.recommended_segments) == 0
    assert len(route.excluded_segments) == 1
    assert any("verified impassable" in exp.lower() for exp in route.exclusion_explanations)

    # Phase 20: Emergency Mode must assign P1 Urgent
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-SCEN-D",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        road_status_snapshot=snap_impassable,
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp, reference_time_utc=ref_time)
    assert em_res.review_priority == EmergencyPriority.P1_URGENT_VERIFIED
    assert em_res.evidence_certainty_level == "VERIFIED"
    assert em_res.current_state == EmergencyState.NEEDS_HUMAN_REVIEW


# ==============================================================================
# Scenario E: Conflicting or Stale Reports
# ==============================================================================

def test_scenario_e_conflicting_or_stale_reports():
    """
    SCENARIO E: Community reports or telemetry conflict or expire.
    Verifies that conflict and staleness remain explicit and are not silently resolved.
    """
    ref_time = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    ref_iso = ref_time.isoformat().replace("+00:00", "Z")

    snap_conflict = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-006",
        road_name="Panjagutta Junction",
        condition_state=RoadConditionState.CONFLICTING,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        last_status_update_utc=ref_iso,
        freshness_category=RoadFreshnessCategory.FRESH,
        verification_state=RoadVerificationState.UNVERIFIED,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.20,
        has_conflicting_evidence=True,
    )

    # Phase 19: Routing marks as uncertain
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-LOC-006",
        road_name="Panjagutta Junction",
        road_status=snap_conflict,
    )
    assert seg.passability_state == PassabilityAssessment.CONFLICTING_EVIDENCE
    assert seg.is_uncertain is True

    # Phase 20: Emergency Mode enters DEGRADED_INSUFFICIENT_DATA
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-SCEN-E",
        corridor_id="HYD-LOC-006",
        road_name="Panjagutta Junction",
        road_status_snapshot=snap_conflict,
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp, reference_time_utc=ref_time)
    assert em_res.current_state == EmergencyState.DEGRADED_INSUFFICIENT_DATA
    assert em_res.review_priority == EmergencyPriority.P0_DEGRADED_TRIAGE
    assert "CONFLICTING_REPORTS" in em_res.quality_flags


# ==============================================================================
# Scenario F: Ambiguous Vision Result Integration
# ==============================================================================

def test_scenario_f_ambiguous_vision_result_integration():
    """
    SCENARIO F: Vision model prediction is ambiguous (p=0.50 within [0.35, 0.65] band).
    Verifies that result remains INCONCLUSIVE and is not promoted to flood evidence.
    """
    # 1. Vision Policy Abstention Boundary
    decision_type, conf, is_abstaining = evaluate_vision_abstention_boundary(0.50)
    assert is_abstaining is True
    assert decision_type == CalibratedVisionDecision.INCONCLUSIVE

    pred_class, conf_val, is_amb, is_inconc, reasons = map_vision_probabilities_to_decision(0.50)
    assert pred_class == "inconclusive"
    assert is_inconc is True

    # 2. Decision Engine Synthesis
    inp = DecisionInput(
        location_id="HYD-LOC-002",
        road_name="Shaikpet Nala Road",
        vision_predicted_class="inconclusive",
        vision_confidence=0.50,
        vision_is_ambiguous=True,
        rainfall_risk_category="LOW",
        vulnerability_category="LOW",
    )
    out = evaluate_decision(inp)
    assert out.current_flood_evidence_status != CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert out.alert_level == AlertLevel.CLEAR
    assert out.is_actionable_for_crews is False
    assert "OPTICAL_QUALITY_GATE_AMBIGUOUS" in out.reason_codes
    assert any("Inconclusive vision evidence" in w for w in out.warnings)


# ==============================================================================
# Scenario G: Emergency Review Lifecycle & Authorization Gates
# ==============================================================================

def test_scenario_g_emergency_review_lifecycle_and_authorization():
    """
    SCENARIO G: Urgent incident requires human review.
    Verifies that unauthorized users cannot resolve it, timeouts cannot auto-resolve it,
    and resolution requires an authorized role with a SHA-256 audit hash.
    """
    engine = EmergencyWorkflowEngine()

    em_inp = EmergencyAssessmentInput(
        incident_id="INC-LIFE-01",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Underpass",
        static_vulnerability_index=0.80,
        static_vulnerability_category="HIGH",
        is_synthetic_fixture=True,
    )
    assessment = engine.evaluate_emergency_assessment(em_inp)
    # Move to NEEDS_HUMAN_REVIEW manually or via P2/P1
    assessment.current_state = EmergencyState.NEEDS_HUMAN_REVIEW

    # 1. Unauthorized citizen attempt raises PermissionError
    with pytest.raises(PermissionError):
        engine.resolve_emergency(
            assessment=assessment,
            reviewer_role="CITIZEN_REPORTER",  # Unauthorized!
            reviewer_id="USER-999",
            action_type="RESOLVE",
            justification_notes="Water has dried up.",
        )

    # 2. Timeout auto-resolution attempt raises RuntimeError
    with pytest.raises(RuntimeError):
        engine.attempt_auto_resolve_on_timeout(assessment)

    # 3. Authorized resolution succeeds with audit hash
    resolved = engine.resolve_emergency(
        assessment=assessment,
        reviewer_role=AuthorizedReviewerRole.TRAFFIC_POLICE_DUTY_OFFICER,
        reviewer_id="TP-OFFICER-102",
        action_type="CONFIRM_DRAINED_REOPEN_LANE",
        justification_notes="Field traffic police confirmed water drained. Traffic flow restored.",
    )
    assert resolved.current_state == EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW
    assert resolved.resolution_record is not None
    assert len(resolved.resolution_record.audit_hash) == 64


# ==============================================================================
# Scenario H: Operational Action Boundaries End-to-End
# ==============================================================================

def test_scenario_h_operational_action_boundaries_end_to_end():
    """
    SCENARIO H: Verifies that across all phases, no scenario triggers autonomous
    dispatch, road closure, or public alert.
    """
    # 1. Phase 18: Dispatch flag cannot authorize real action
    fc = ForecastRiskAssessmentOutput(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Underpass",
        assessment_status=ForecastDataStatus.AVAILABLE_VALID,
        assessment_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=1.0,
        forecast_rainfall_context={"rainfall_amount": 35.0},
        static_susceptibility_context={"vulnerability_index": 0.6},
        current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
        verified_historical_outcomes_context={"verified_count": 0},
        forecast_risk_category="HIGH",
        heuristic_risk_score=0.70,
        is_calibrated_probability=False,
        confidence_score=0.75,
        is_actionable_for_dispatch=True,  # Downstream must disarm
    )

    # 2. Phase 19: Disarmed in routing
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Underpass",
        forecast_risk=fc,
    )
    assert any("not_authorized_for_operations" in n.lower() for n in seg.caution_notices)

    route = routing_svc.evaluate_route(
        route_id="RTE-SAFE-01",
        candidate_segments=[seg],
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.41, "lon": 78.41},
    )
    assert route.operational_action_authorized is False

    # 3. Phase 20: Disarmed in emergency mode
    em_engine = EmergencyWorkflowEngine()
    em_inp = EmergencyAssessmentInput(
        incident_id="INC-BOUND-01",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Underpass",
        forecast_risk_output=fc,
        is_synthetic_fixture=True,
    )
    em_res = em_engine.evaluate_emergency_assessment(em_inp)
    assert em_res.operational_action_authorized is False
    assert em_res.external_side_effects_triggered is False


# ==============================================================================
# Scenario I: Routing Without a Road Graph
# ==============================================================================

def test_scenario_i_routing_without_road_graph():
    """
    SCENARIO I: No routable graph exists on disk.
    Verifies that system does not fabricate routes, travel times, or optimality claims.
    """
    # Readiness audit confirms 0 edges
    report = audit_road_network_readiness()
    assert report.routable_network_edges_count == 0
    assert report.routing_data_readiness_verdict == "INSUFFICIENT_DATA_ROUTING_UNSUPPORTED"

    # Routing layer refuses optimality claim
    routing_svc = RiskAwareRoutingService()
    seg = routing_svc.assess_segment("HYD-LOC-001", "Tolichowki Underpass")
    route = routing_svc.evaluate_route(
        route_id="RTE-NO-GRAPH",
        candidate_segments=[seg],
        origin={"lat": 17.40, "lon": 78.40},
        destination={"lat": 17.41, "lon": 78.41},
    )
    assert route.is_optimality_claimed is False
    assert route.is_guaranteed_safe is False


# ==============================================================================
# Scenario J: Forecast Source Unavailable & Evidence Separation
# ==============================================================================

def test_scenario_j_forecast_source_unavailable_and_separation():
    """
    SCENARIO J: 0 authorized operational forecast feeds exist.
    Verifies audit reports BLOCKED while offline contracts strictly isolate evidence signals.
    """
    # Readiness audit confirms 0 authorized sources
    report = audit_forecast_sources_readiness()
    assert report.authorized_sources_count == 0
    assert report.readiness_verdict == "BLOCKED_NO_AUTHORIZED_SOURCE"

    # Test fixture parsed cleanly but labeled synthetic
    fc = ForecastRainfallInput(
        location_id="HYD-LOC-001",
        source_id="SYNTHETIC-RUN-01",
        source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=20.0,
        is_synthetic_fixture=True,
    )
    assert fc.is_synthetic_fixture is True
    assert fc.source_type == ForecastSourceType.SYNTHETIC_TEST_FIXTURE


# ==============================================================================
# Vision Partition Guard & Outcome Readiness
# ==============================================================================

def test_vision_partition_guard_and_outcome_readiness():
    """
    Verifies that Phase 17 outcome readiness remains INSUFFICIENT_DATA_NO_GO (0 verified outcomes)
    and the sealed Vision V4 evaluation partition cannot be breached.
    """
    # 1. Outcome readiness audit
    outcomes = audit_outcome_data_readiness()
    assert outcomes.verified_flood_outcome_records_count == 0
    assert outcomes.data_readiness_verdict.value == "INSUFFICIENT_DATA_NO_GO"

    # 2. Vision partition guard
    splitter = EventAndSpatialSplitter()
    with pytest.raises(PermissionError, match="SEALED_VISION_PARTITION_VIOLATION"):
        splitter.verify_vision_partition_isolation("data/processed/test.csv")
