"""
Sahaay AI - Phase D: Evidence-to-Map and Flood-Risk Integration Test Suite
(tests/test_phase_d_corridor_evidence_integration.py)

Comprehensive verification testing for:
1. Canonical corridor evidence assessment schemas and safety validators.
2. Non-silent missingness and sensor outage handling (no synthetic dry zero).
3. Stale evidence decay and explanation codes.
4. Contradictory evidence detection and unresolved conflict propagation.
5. Strict 5-signal evidence separation (Forecast, Observed Rain, Susceptibility, Road Status, History = 0).
6. Vision abstention boundary [0.35, 0.65] and quality gate failure propagation (INCONCLUSIVE).
7. Temporal provenance decoupling (observation vs ingestion vs assessment timestamps).
8. Authorized responder gating for impassable closures (community reports cannot close roads).
9. Map GeoJSON integration with evidence states and resilience under provider outage.
10. Sparse road network disclosure and non-citywide coverage disclaimer.
11. Risk-aware topological routing with verified-impassable pruning and forecast tolerance.
12. Disconnected topological component handling (no synthetic edge fabrication).
13. Security boundaries: caller-supplied role spoofing rejection and privileged-action blocking.
14. Disarmed operational action boundaries (autonomous closures and emergency dispatch prohibited).
15. REST API endpoint contracts (/api/v1/corridor-evidence/*).
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.corridor_evidence.schemas import (
    CorridorEvidenceState,
    EvidenceSufficiency,
    RoadStatusEvidenceSection,
    CommunityReportsEvidenceSection,
    ObservedRainfallEvidenceSection,
    ForecastRainfallEvidenceSection,
    StaticSusceptibilityEvidenceSection,
    VisionEvidenceSection,
    HistoricalInundationEvidenceSection,
    CorridorEvidenceAssessment,
)
from sahaay.corridor_evidence.service import (
    CorridorEvidenceService,
    default_corridor_evidence_service,
)
from sahaay.road_network.schemas import (
    RoadSegment,
    RoadClassification,
    RoadMonitoringStatus,
    RoadGeometry,
    GeoJSONGeometryType,
)
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    RoadStatusSnapshot,
    UncertaintyLevel,
)
from sahaay.hyderabad_risk.schemas import RainfallRiskResult
from sahaay.forecast_risk.schemas import (
    ForecastRainfallInput,
    ForecastSourceType,
    PrecipitationUnit,
    AccumulationInterval,
    ForecastRiskAssessmentOutput,
)
from sahaay.hyderabad_risk.weather_pipeline import default_weather_pipeline
from sahaay.reports.schemas import (
    CitizenReportRecord,
    ReportCondition,
    ReportVerificationStatus,
    WaterDepthEstimate,
)
from sahaay.routing.contracts import VehicleType
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import PassabilityAssessment, RouteAssessmentOutcome
from tests.test_phase_b_topological_graph_routing import create_tolichowki_test_graph

client = TestClient(app)


# ==============================================================================
# 1. Schema Invariants and Forbidden Safety Language Tests
# ==============================================================================

def test_forecast_alone_cannot_prove_inundation_validator():
    """
    Safety validator rejects any schema instance that sets does_forecast_prove_inundation = True.
    """
    with pytest.raises(ValueError, match="Forecast rainfall alone cannot prove ground inundation"):
        ForecastRainfallEvidenceSection(
            forecast_source_status="AVAILABLE_OFFLINE_TEST",
            does_forecast_prove_inundation=True,
        )


def test_static_vulnerability_cannot_be_current_flood_status_validator():
    """
    Safety validator rejects any schema instance that sets is_current_flood_status = True.
    """
    with pytest.raises(ValueError, match="Static vulnerability cannot be represented as current flood status"):
        StaticSusceptibilityEvidenceSection(
            vulnerability_index=0.85,
            is_current_flood_status=True,
        )


def test_forbidden_safety_phrasing_in_corridor_assessment():
    """
    Rejects safety notice or road name containing deceptive phrases like 'guaranteed safe'.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValueError, match="forbidden phrasing"):
        CorridorEvidenceAssessment(
            corridor_id="HYD-LOC-TEST",
            road_name="Tolichowki Corridor",
            assessment_timestamp_utc=now_iso,
            evidence_state=CorridorEvidenceState.NO_CURRENT_EVIDENCE,
            evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT_DATA,
            compact_explanation="Test explanation",
            road_status=RoadStatusEvidenceSection(),
            community_reports=CommunityReportsEvidenceSection(),
            observed_rainfall=ObservedRainfallEvidenceSection(),
            forecast_rainfall=ForecastRainfallEvidenceSection(),
            static_susceptibility=StaticSusceptibilityEvidenceSection(vulnerability_index=0.2),
            vision_evidence=VisionEvidenceSection(),
            safety_notice="This route is guaranteed safe for all travelers.",
        )


# ==============================================================================
# 2. Missing Evidence & Sensor Outage Tests (Zero Synthetic Dry Zeros)
# ==============================================================================

def test_missing_telemetry_evaluates_to_insufficient_data_never_zero():
    """
    When weather telemetry is in outage or missing, the corridor evidence state
    evaluates to NO_CURRENT_EVIDENCE or UNMONITORED_UNKNOWN with INSUFFICIENT_DATA.
    Observed rainfall is None and is NEVER converted to 0.0 mm dry weather.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    outage_weather = RainfallRiskResult(
        location_id="HYD-LOC-001",
        rain_1h_mm=None,
        rain_3h_mm=None,
        rain_6h_mm=None,
        rain_24h_mm=None,
        risk_category="UNKNOWN",
        risk_score=0.0,
        confidence=0.0,
        qc_flags=["QC_MISSING_VALUE"],
        data_timestamp=now_iso,
        data_freshness_hours=99.0,
        reason_codes=["PRIMARY_TELEMETRY_OUTAGE"],
        missing_inputs=["rain_1h_mm", "rain_3h_mm"],
        warnings=["Telemetry feed unavailable"],
        provider="IMD-AWS-TELEMETRY",
        station_id="HYD-STN-BEGUMPET",
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        weather_result=outage_weather,
    )

    assert assessment.observed_rainfall.data_availability == "OUTAGE_OR_MISSING_DATA"
    assert assessment.observed_rainfall.rainfall_1h_mm is None
    assert assessment.observed_rainfall.is_valid_measured_zero is False
    assert assessment.evidence_sufficiency == EvidenceSufficiency.INSUFFICIENT_DATA
    assert "RAINFALL_TELEMETRY_UNAVAILABLE_OR_OUTAGE" in assessment.explanation_codes


def test_valid_measured_zero_rainfall_distinction():
    """
    A valid measured zero (0.0 mm confirmed by operational gauge) is distinctly tagged
    and separated from sensor dropouts or missing data.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    zero_weather = RainfallRiskResult(
        location_id="HYD-LOC-001",
        rain_1h_mm=0.0,
        rain_3h_mm=0.0,
        rain_6h_mm=0.0,
        rain_24h_mm=0.0,
        risk_category="LOW",
        risk_score=0.05,
        confidence=0.90,
        qc_flags=["QC_VALID", "VALID_MEASURED_ZERO"],
        data_timestamp=now_iso,
        data_freshness_hours=0.2,
        reason_codes=["VALID_MEASURED_ZERO"],
        missing_inputs=[],
        warnings=[],
        provider="IMD-AWS-TELEMETRY",
        station_id="HYD-STN-BEGUMPET",
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        weather_result=zero_weather,
    )

    assert assessment.observed_rainfall.data_availability == "AVAILABLE"
    assert assessment.observed_rainfall.rainfall_1h_mm == 0.0
    assert assessment.observed_rainfall.is_valid_measured_zero is True


# ==============================================================================
# 3. Stale Evidence Decay Tests
# ==============================================================================

def test_stale_evidence_handling():
    """
    Evidence aged beyond the freshness window (>180 min) degrades to STALE_EVIDENCE.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    stale_snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        condition_state=RoadConditionState.STALE,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        verification_state=RoadVerificationState.CORROBORATED,
        freshness_category=RoadFreshnessCategory.STALE,
        evidence_age_minutes=240.0,
        uncertainty_level=UncertaintyLevel.HIGH,
        confidence_score=0.35,
        last_status_update_utc=now_iso,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        road_status_snapshot=stale_snap,
    )

    assert assessment.evidence_state == CorridorEvidenceState.STALE_EVIDENCE
    assert assessment.evidence_sufficiency == EvidenceSufficiency.DEGRADED
    assert "OBSERVATION_FRESHNESS_DECAYED" in assessment.explanation_codes


# ==============================================================================
# 4. Conflicting Evidence Tests
# ==============================================================================

def test_conflicting_citizen_reports_handling():
    """
    Simultaneous citizen claims of flooded and dry pavement evaluate to CONFLICTING_EVIDENCE.
    """
    service = CorridorEvidenceService()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat().replace("+00:00", "Z")

    r1 = CitizenReportRecord(
        report_id="REP-001",
        corridor_id="HYD-LOC-001",
        submission_timestamp_utc=now_iso,
        observation_timestamp_utc=now_iso,
        latitude_coarsened=17.40,
        longitude_coarsened=78.42,
        location_precision_m=50.0,
        description_sanitized="Flooded underpass road",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        reporter_id_masked="USR-MASK-01",
        verification_status=ReportVerificationStatus.UNVERIFIED,
    )
    r2 = CitizenReportRecord(
        report_id="REP-002",
        corridor_id="HYD-LOC-001",
        submission_timestamp_utc=now_iso,
        observation_timestamp_utc=now_iso,
        latitude_coarsened=17.40,
        longitude_coarsened=78.42,
        location_precision_m=50.0,
        description_sanitized="Road is clear and dry",
        estimated_depth=WaterDepthEstimate.PUDDLE_SURFACE_WET,
        reported_condition=ReportCondition.DRY_ROAD_CLEAR,
        reporter_id_masked="USR-MASK-02",
        verification_status=ReportVerificationStatus.UNVERIFIED,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        community_reports=[r1, r2],
    )

    assert assessment.evidence_state == CorridorEvidenceState.CONFLICTING_EVIDENCE
    assert assessment.evidence_sufficiency == EvidenceSufficiency.CONFLICTING
    assert assessment.has_unresolved_conflicts is True
    assert "CONTRADICTORY_OBSERVATIONS_UNRESOLVED" in assessment.explanation_codes


def test_cross_modal_conflict_vision_dry_vs_citizen_flooded():
    """
    Optical surveillance confirms dry pavement with high confidence, but citizen reports assert
    flooding. Cross-modal conflict is flagged; evidence becomes CONFLICTING_EVIDENCE.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        condition_state=RoadConditionState.CORROBORATED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        verification_state=RoadVerificationState.CORROBORATED,
        freshness_category=RoadFreshnessCategory.FRESH,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        confidence_score=0.60,
        last_status_update_utc=now_iso,
    )

    vision_dry = {
        "inference_available": True,
        "predicted_class": "not_flooded",
        "confidence": 0.88,
        "raw_probability": 0.12,
        "is_inconclusive": False,
    }

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        road_status_snapshot=snap,
        vision_result=vision_dry,
    )

    assert assessment.evidence_state == CorridorEvidenceState.CONFLICTING_EVIDENCE
    assert assessment.has_unresolved_conflicts is True
    assert "CONTRADICTORY_OBSERVATIONS_UNRESOLVED" in assessment.explanation_codes


# ==============================================================================
# 5. Strict Five-Signal Separation Tests
# ==============================================================================

def test_five_signals_strictly_separated():
    """
    Verifies that Forecast (F), Observed Rain (R), Static Vulnerability (V),
    Current Road Status (O), and History (H = 0) are kept in isolated sections.
    """
    service = CorridorEvidenceService()
    assessment = service.assess_corridor(corridor_id="HYD-LOC-001")

    # 1. Road status
    assert isinstance(assessment.road_status, RoadStatusEvidenceSection)
    # 2. Community reports
    assert isinstance(assessment.community_reports, CommunityReportsEvidenceSection)
    # 3. Observed rainfall
    assert isinstance(assessment.observed_rainfall, ObservedRainfallEvidenceSection)
    # 4. Forecast rainfall
    assert isinstance(assessment.forecast_rainfall, ForecastRainfallEvidenceSection)
    assert assessment.forecast_rainfall.does_forecast_prove_inundation is False
    # 5. Static susceptibility
    assert isinstance(assessment.static_susceptibility, StaticSusceptibilityEvidenceSection)
    assert assessment.static_susceptibility.is_current_flood_status is False
    # 6. Vision
    assert isinstance(assessment.vision_evidence, VisionEvidenceSection)
    # 7. History
    assert isinstance(assessment.historical_inundation, HistoricalInundationEvidenceSection)
    assert assessment.historical_inundation.verified_historical_outcomes_count == 0
    assert assessment.historical_inundation.has_calibrated_statistical_model is False


def test_forecast_alone_never_marks_road_inundated_or_impassable():
    """
    Severe torrential forecast precipitation (e.g. 80mm in 1h) elevates meteorological
    risk but NEVER marks the road impassable or inundated on ground.
    """
    service = CorridorEvidenceService()
    now_dt = datetime.now(timezone.utc)
    valid_dt = now_dt + timedelta(hours=1)
    severe_fc_in = ForecastRainfallInput(
        location_id="HYD-LOC-001",
        source_id="NWP-LOCAL-TEST",
        source_type=ForecastSourceType.NUMERICAL_WEATHER_PREDICTION_NWP,
        issue_timestamp_utc=now_dt.isoformat().replace("+00:00", "Z"),
        valid_timestamp_utc=valid_dt.isoformat().replace("+00:00", "Z"),
        forecast_horizon_hours=1.0,
        rainfall_amount=85.0,
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_1H,
        is_synthetic_fixture=True,
    )
    severe_fc = default_weather_pipeline.evaluate_corridor_forecast_risk(
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        corridor_lat=17.40,
        corridor_lon=78.45,
        forecast_inputs=[severe_fc_in],
        reference_time_utc=now_dt,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        forecast_result=severe_fc,
    )

    assert assessment.evidence_state == CorridorEvidenceState.ELEVATED_METEOROLOGICAL_RISK
    assert assessment.is_traversable_for_routing is True
    assert assessment.road_status.is_verified_impassable is False
    assert "ELEVATED_METEOROLOGICAL_VIGILANCE_INUNDATION_UNPROVEN" in assessment.explanation_codes


# ==============================================================================
# 6. Computer Vision Abstention Boundary [0.35, 0.65] Tests
# ==============================================================================

def test_vision_abstention_boundary_propagation():
    """
    Probabilities from 0.35 to 0.65 inclusive strictly propagate as INCONCLUSIVE.
    """
    service = CorridorEvidenceService()

    # Case 1: Mid-band probability (0.50)
    res_mid = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        vision_result={"inference_available": True, "raw_probability": 0.50},
    )
    assert res_mid.vision_evidence.is_inconclusive_abstention is True
    assert res_mid.vision_evidence.predicted_class == "inconclusive"
    assert "VISION_ABSTENTION_INCONCLUSIVE" in res_mid.explanation_codes

    # Case 2: Boundary point 0.35
    res_lower = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        vision_result={"inference_available": True, "raw_probability": 0.35},
    )
    assert res_lower.vision_evidence.is_inconclusive_abstention is True
    assert res_lower.vision_evidence.predicted_class == "inconclusive"

    # Case 3: Boundary point 0.65
    res_upper = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        vision_result={"inference_available": True, "raw_probability": 0.65},
    )
    assert res_upper.vision_evidence.is_inconclusive_abstention is True
    assert res_upper.vision_evidence.predicted_class == "inconclusive"

    # Case 4: Clear flood probability (0.85) -> FLOOD
    res_flood = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        vision_result={"inference_available": True, "raw_probability": 0.85},
    )
    assert res_flood.vision_evidence.is_inconclusive_abstention is False
    assert res_flood.vision_evidence.predicted_class == "flooded"


def test_vision_quality_gate_failure_propagation():
    """
    Vision image quality gate failures (luminance/variance out of bounds) strictly
    propagate as INCONCLUSIVE with quality_gate_passed = False.
    """
    service = CorridorEvidenceService()
    res_qg = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        vision_result={
            "inference_available": True,
            "predicted_class": "inconclusive",
            "is_inconclusive": True,
            "confidence": 0.50,
            "rejection_reason": "Image quality gate failed (luminance out of bounds)",
        },
    )

    assert res_qg.vision_evidence.quality_gate_passed is False
    assert res_qg.vision_evidence.is_inconclusive_abstention is True
    assert res_qg.vision_evidence.predicted_class == "inconclusive"


# ==============================================================================
# 7. Temporal Provenance Decoupling Tests
# ==============================================================================

def test_temporal_provenance_decoupling():
    """
    Preserves strict separation between physical observation time, submission/ingestion time,
    and assessment generation time.
    """
    service = CorridorEvidenceService()
    now_utc = datetime.now(timezone.utc)
    t_obs = (now_utc - timedelta(minutes=45)).isoformat().replace("+00:00", "Z")
    t_ingest = (now_utc - timedelta(minutes=40)).isoformat().replace("+00:00", "Z")
    t_assess = now_utc.isoformat().replace("+00:00", "Z")

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        condition_state=RoadConditionState.CORROBORATED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        verification_state=RoadVerificationState.CORROBORATED,
        observation_timestamp_utc=t_obs,
        ingestion_timestamp_utc=t_ingest,
        freshness_category=RoadFreshnessCategory.FRESH,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        confidence_score=0.60,
        last_status_update_utc=t_ingest,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        road_status_snapshot=snap,
        evaluation_timestamp_utc=t_assess,
    )

    assert assessment.source_timestamps["road_status_observation_utc"] == t_obs
    assert assessment.source_timestamps["road_status_ingestion_utc"] == t_ingest
    assert assessment.source_timestamps["assessment_generated_utc"] == t_assess
    assert assessment.source_timestamps["road_status_observation_utc"] != assessment.source_timestamps["assessment_generated_utc"]


# ==============================================================================
# 8. Ground Truth Gating (Authorized Responder Verification) Tests
# ==============================================================================

def test_community_reports_alone_cannot_close_roads():
    """
    Community reports (even corroborated by multiple independent submitters)
    yield CORROBORATED_HAZARD but remain traversable.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        condition_state=RoadConditionState.CORROBORATED,
        evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
        verification_state=RoadVerificationState.CORROBORATED,
        freshness_category=RoadFreshnessCategory.FRESH,
        uncertainty_level=UncertaintyLevel.MEDIUM,
        confidence_score=0.65,
        last_status_update_utc=now_iso,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        road_status_snapshot=snap,
    )

    assert assessment.evidence_state == CorridorEvidenceState.CORROBORATED_HAZARD
    assert assessment.is_traversable_for_routing is True
    assert assessment.road_status.is_verified_impassable is False


def test_official_responder_verified_impassable_closes_corridor():
    """
    Only official responder verification of VERIFIED_IMPASSABLE can mark a road
    non-traversable for routing.
    """
    service = CorridorEvidenceService()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    snap = RoadStatusSnapshot(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
        evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
        verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
        verified_by_entity="GHMC_DRF_OFFICER",
        measured_water_depth_cm=55.0,
        freshness_category=RoadFreshnessCategory.FRESH,
        uncertainty_level=UncertaintyLevel.LOW,
        confidence_score=0.95,
        last_status_update_utc=now_iso,
    )

    assessment = service.assess_corridor(
        corridor_id="HYD-LOC-001",
        road_status_snapshot=snap,
    )

    assert assessment.evidence_state == CorridorEvidenceState.VERIFIED_IMPASSABLE
    assert assessment.is_traversable_for_routing is False
    assert assessment.routing_penalty_multiplier == 999.0
    assert "OFFICIAL_INSPECTION_CONFIRMED_IMPASSABLE" in assessment.explanation_codes


# ==============================================================================
# 9. Map GeoJSON Integration & Graceful Outage Degradation Tests
# ==============================================================================

def test_map_geojson_includes_corridor_evidence_fields():
    """
    The map GeoJSON endpoint (/api/v1/map/corridors/geojson) includes the canonical
    evidence properties in each feature while remaining RFC 7946 compliant.
    """
    res = client.get("/api/v1/map/corridors/geojson")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0

    first_feat = fc["features"][0]
    props = first_feat["properties"]

    assert "evidence_state" in props
    assert "evidence_explanation" in props
    assert "evidence_sufficiency" in props
    assert "coverage_warning" in props
    assert "SPARSE_SEED_CATALOG" in props["coverage_warning"]


def test_map_feature_usable_when_evidence_providers_unavailable():
    """
    Even when external weather/status pipelines are unavailable, building a map feature
    degrades gracefully without raising errors.
    """
    seg = default_road_network_store.get_segment("HYD-LOC-001")
    assert seg is not None

    feat = default_road_network_store.build_map_feature(segment=seg, status_snapshot=None)
    assert feat.properties.segment_id == "HYD-LOC-001"
    assert feat.properties.coverage_warning == "SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE"


# ==============================================================================
# 10. Sparse Network Disclosure & Non-Citywide Navigation Tests
# ==============================================================================

def test_sparse_road_network_warning_preservation():
    """
    All corridor evidence assessments and coverage reports explicitly disclose
    that the ~22-segment seed catalog does not provide citywide coverage.
    """
    assessment = default_corridor_evidence_service.assess_corridor("HYD-LOC-001")
    assert "SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE" in assessment.coverage_warning


# ==============================================================================
# 11. Topological Routing & Impassable Pruning Tests
# ==============================================================================

def test_topological_router_excludes_verified_impassable_segments():
    """
    Topological router hard-prunes verified impassable segments while permitting
    demonstration routing over passable alternate bypass segments.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Provider marking primary link TEST-SEG-2 as officially verified impassable
    def _status_provider(seg_id: str):
        if seg_id == "TEST-SEG-2":
            return RoadStatusSnapshot(
                road_segment_id=seg_id,
                road_name="Tolichowki Flyover Underpass",
                condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
                evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
                freshness_category=RoadFreshnessCategory.FRESH,
                uncertainty_level=UncertaintyLevel.LOW,
                confidence_score=0.98,
                last_status_update_utc="2026-10-28T00:00:00Z",
            )
        return None

    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        segment_status_provider=_status_provider,
    )

    # Impassable edge is pruned; router takes bypass A -> D -> E -> C
    assert route.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
    assert len(route.excluded_segments) == 1
    assert route.excluded_segments[0].segment_id == "TEST-SEG-2"
    assert any("TEST-SEG-BYPASS" in s.segment_id for s in route.recommended_segments)


def test_disconnected_topological_components_yields_unsupported():
    """
    Routing between nodes in disconnected components returns TOPOLOGY_UNSUPPORTED
    without creating synthetic connecting edges.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Routing from connected cluster (NODE-A) to isolated cluster (NODE-ISOLATED-2)
    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-ISOLATED-2",
    )

    assert route.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert route.engine_status == "DISCONNECTED_TOPOLOGICAL_COMPONENTS"
    assert "disconnected topological components" in route.warnings[0].lower()


# ==============================================================================
# 12. Security & Role Spoofing Denial Tests
# ==============================================================================

def test_security_caller_supplied_role_spoofing_denied():
    """
    Attempting to activate live feeds with a client-supplied role string
    ('SUPER_ADMIN_EMERGENCY_DIRECTOR') is denied with HTTP 403.
    """
    payload = {
        "corridor_id": "HYD-LOC-001",
        "caller_role": "SUPER_ADMIN_EMERGENCY_DIRECTOR",
        "request_live_feed_activation": True,
    }
    res = client.post("/api/v1/corridor-evidence/evaluate", json=payload)
    assert res.status_code == 403
    assert "SECURITY GATE" in res.json()["detail"]


def test_operational_action_strictly_disarmed():
    """
    Verifies operational_action_authorized remains False across all generated assessments.
    Autonomous closures and emergency dispatch are strictly prohibited.
    """
    assessment = default_corridor_evidence_service.assess_corridor("HYD-LOC-001")
    assert assessment.operational_action_authorized is False


# ==============================================================================
# 13. REST API Endpoint Contract Tests
# ==============================================================================

def test_api_corridor_evidence_assessment_endpoint():
    """
    Tests GET /api/v1/corridor-evidence/assessment/{corridor_id}
    """
    res = client.get("/api/v1/corridor-evidence/assessment/HYD-LOC-001")
    assert res.status_code == 200
    data = res.json()
    assert data["corridor_id"] == "HYD-LOC-001"
    assert "road_status" in data
    assert "community_reports" in data
    assert "observed_rainfall" in data
    assert "forecast_rainfall" in data
    assert "static_susceptibility" in data
    assert "vision_evidence" in data
    assert "historical_inundation" in data
    assert data["forecast_rainfall"]["does_forecast_prove_inundation"] is False
    assert data["static_susceptibility"]["is_current_flood_status"] is False


def test_api_corridor_evidence_assessments_batch_endpoint():
    """
    Tests GET /api/v1/corridor-evidence/assessments batch endpoint
    """
    res = client.get("/api/v1/corridor-evidence/assessments")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 20  # Catalog has 20 canonical corridors + 2 seed links


def test_api_corridor_evidence_evaluate_endpoint():
    """
    Tests POST /api/v1/corridor-evidence/evaluate with custom scenarios.
    """
    payload = {
        "corridor_id": "HYD-LOC-001",
        "verified_impassable_by_responder": True,
        "observed_rainfall_1h_mm": 45.0,
        "forecast_rainfall_band": "HEAVY",
    }
    res = client.post("/api/v1/corridor-evidence/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["evidence_state"] == "VERIFIED_IMPASSABLE"
    assert data["is_traversable_for_routing"] is False
    assert data["observed_rainfall"]["rainfall_1h_mm"] == 45.0
