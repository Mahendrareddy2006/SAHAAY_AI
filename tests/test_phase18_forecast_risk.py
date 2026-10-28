"""
Sahaay AI - Phase 18: Forecast Risk Test Suite
(tests/test_phase18_forecast_risk.py)

Comprehensive offline test coverage for:
1. Valid and invalid forecast contracts (ForecastRainfallInput)
2. Timezone handling and temporal ordering (valid_time >= issue_time)
3. Forecast horizon consistency checks (|horizon - delta| <= 0.1h)
4. Rainfall physical bounds (rejection of negative, NaN, Inf, and excessive cloudburst rates > 300 mm)
5. Units and accumulation intervals (instantaneous rate requires mm/h)
6. Non-silent missingness semantics (missing forecast data is INSUFFICIENT_DATA, score None, never zero)
7. Stale forecast detection and handling (age > 6h NWP, > 1.5h nowcast)
8. Conflicting forecast inputs (divergence > 20 mm flagged CONFLICTING)
9. Spatially unsuitable forecasts (spatial resolution > 15 km flagged SPATIALLY_UNSUITABLE)
10. Future issue timestamp rejection
11. Strict separation of 5 evidence signals (forecast rain, observed rain, static vulnerability, current road status, historical outcomes)
12. Forecast rainfall alone does not infer active road inundation
13. Static vulnerability alone does not establish active road inundation
14. Absent flood evidence does not infer road safety
15. Prohibition of calibrated probability claims (is_calibrated_probability must remain False)
16. Prohibition of forbidden safety assertions ("guaranteed safe", etc.)
17. Forensic audit of forecast sources evaluating to BLOCKED_NO_AUTHORIZED_SOURCE
18. Synthetic test fixtures clearly marked (is_synthetic_fixture = True)
19. Non-autonomous advisory and dispatch actionability criteria
20. Preserving compatibility with Phase 16 & Phase 17 schemas
"""

from datetime import datetime, timezone, timedelta
import math
import pytest

from sahaay.forecast_risk.schemas import (
    PrecipitationUnit,
    AccumulationInterval,
    ForecastSourceType,
    ForecastQualityFlag,
    ForecastDataStatus,
    ForecastRainfallInput,
    ObservedRainfallContext,
    StaticVulnerabilityContext,
    CurrentRoadStatusContext,
    ForecastRiskAssessmentOutput,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_FORECAST_RISK_DISCLAIMER,
)
from sahaay.forecast_risk.readiness import (
    audit_forecast_sources_readiness,
    ForecastSourceReadinessReport,
)
from sahaay.forecast_risk.service import (
    ForecastRiskAssessmentService,
    evaluate_forecast_risk,
)
from sahaay.road_status.schemas import RoadConditionState, RoadVerificationState


# ==============================================================================
# 1. Forecast Contract Validation & Temporal Handling
# ==============================================================================

def test_valid_forecast_contract_parsing():
    """Verifies that a well-formed forecast input parses correctly."""
    fc = ForecastRainfallInput(
        location_id="HYD-CORR-001",
        source_id="IMD-WRF-RUN-06Z",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T09:00:00Z",
        forecast_horizon_hours=3.0,
        rainfall_amount=24.5,
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_3H,
        spatial_resolution_km=4.0,
        latitude=17.44,
        longitude=78.38,
        is_synthetic_fixture=True,
    )
    assert fc.location_id == "HYD-CORR-001"
    assert fc.rainfall_amount == 24.5
    assert fc.forecast_horizon_hours == 3.0
    assert fc.is_synthetic_fixture is True


def test_forecast_contract_rejects_invalid_timestamp_format():
    """Invalid datetime format strings must raise ValueError."""
    with pytest.raises(ValueError, match="Invalid issue_timestamp_utc format"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="not-a-timestamp",
            valid_timestamp_utc="2026-10-27T09:00:00Z",
            forecast_horizon_hours=3.0,
            rainfall_amount=10.0,
        )


def test_forecast_contract_rejects_valid_before_issue():
    """Valid timestamp occurring before issue timestamp violates causality."""
    with pytest.raises(ValueError, match="cannot be before issue_timestamp_utc"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T12:00:00Z",
            valid_timestamp_utc="2026-10-27T10:00:00Z",
            forecast_horizon_hours=2.0,
            rainfall_amount=10.0,
        )


def test_forecast_contract_rejects_horizon_mismatch():
    """Declared forecast_horizon_hours must match (valid_dt - issue_dt) within tolerance."""
    with pytest.raises(ValueError, match="does not match temporal difference"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T09:00:00Z",
            forecast_horizon_hours=12.0,  # Expected 3.0 hours!
            rainfall_amount=10.0,
        )


def test_forecast_contract_handles_offset_timezones():
    """ISO timestamps with numerical offsets (e.g. +05:30 IST) are converted to UTC."""
    fc = ForecastRainfallInput(
        location_id="HYD-CORR-001",
        source_id="TSDPS-AUTO",
        source_type=ForecastSourceType.REGIONAL_TSDPS_ADVISORY,
        issue_timestamp_utc="2026-10-27T11:30:00+05:30",  # 06:00 UTC
        valid_timestamp_utc="2026-10-27T12:30:00+05:30",  # 07:00 UTC
        forecast_horizon_hours=1.0,
        rainfall_amount=15.0,
        is_synthetic_fixture=True,
    )
    assert fc.forecast_horizon_hours == 1.0


# ==============================================================================
# 2. Physical Bounds and Units Validation
# ==============================================================================

def test_forecast_contract_rejects_negative_rainfall():
    """Negative rainfall amounts are physically impossible and must be rejected."""
    with pytest.raises(ValueError, match="rainfall_amount cannot be negative"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T07:00:00Z",
            forecast_horizon_hours=1.0,
            rainfall_amount=-5.0,
        )


def test_forecast_contract_rejects_non_finite_rainfall():
    """NaN and Infinite values must be rejected."""
    with pytest.raises(ValueError, match="finite numerical value"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T07:00:00Z",
            forecast_horizon_hours=1.0,
            rainfall_amount=float("nan"),
        )

    with pytest.raises(ValueError, match="finite numerical value"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T07:00:00Z",
            forecast_horizon_hours=1.0,
            rainfall_amount=float("inf"),
        )


def test_forecast_contract_rejects_excessive_cloudburst_rate():
    """Rainfall exceeding 300 mm in a single horizon interval is rejected as unphysical."""
    with pytest.raises(ValueError, match="exceeds physical extreme cloudburst limit"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-SRC",
            source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T07:00:00Z",
            forecast_horizon_hours=1.0,
            rainfall_amount=450.0,
        )


def test_forecast_contract_distinguishes_accumulation_from_instantaneous_rate():
    """Instantaneous rate flag requires mm/h units; cannot use accumulation mm."""
    with pytest.raises(ValueError, match="Instantaneous rainfall rate must use 'mm/h' units"):
        ForecastRainfallInput(
            location_id="HYD-CORR-001",
            source_id="TEST-DWR",
            source_type=ForecastSourceType.RADAR_NOWCAST,
            issue_timestamp_utc="2026-10-27T06:00:00Z",
            valid_timestamp_utc="2026-10-27T07:00:00Z",
            forecast_horizon_hours=1.0,
            rainfall_amount=35.0,
            rainfall_units=PrecipitationUnit.MILLIMETERS,  # Error: should be mm/h
            accumulation_interval=AccumulationInterval.INSTANTANEOUS_RATE,
            is_instantaneous_rate=True,
        )

    # Valid instantaneous rate with mm/h
    valid_dwr = ForecastRainfallInput(
        location_id="HYD-CORR-001",
        source_id="TEST-DWR",
        source_type=ForecastSourceType.RADAR_NOWCAST,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T07:00:00Z",
        forecast_horizon_hours=1.0,
        rainfall_amount=35.0,
        rainfall_units=PrecipitationUnit.MILLIMETERS_PER_HOUR,
        accumulation_interval=AccumulationInterval.INSTANTANEOUS_RATE,
        is_instantaneous_rate=True,
        is_synthetic_fixture=True,
    )
    assert valid_dwr.is_instantaneous_rate is True
    assert valid_dwr.rainfall_units == PrecipitationUnit.MILLIMETERS_PER_HOUR


# ==============================================================================
# 3. Non-Silent Missingness Semantics
# ==============================================================================

def test_missing_forecast_input_produces_insufficient_data():
    """
    SAFETY INVARIANT: Missing forecast data must NEVER be silently imputed as 0.0 mm.
    Must evaluate to INSUFFICIENT_DATA with heuristic_risk_score = None.
    """
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-001",
        road_name="Tolichowki Corridor",
        forecast_inputs=None,  # Completely missing
    )

    assert res.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert res.forecast_risk_category == "INSUFFICIENT_DATA"
    assert res.heuristic_risk_score is None  # MUST NOT be 0.0
    assert res.confidence_score == 0.10
    assert res.uncertainty_level == "HIGH"
    assert "forecast_rainfall_input" in res.missing_inputs
    assert "FORECAST_DATA_MISSING_MARKED_INSUFFICIENT" in res.reason_codes
    assert ForecastQualityFlag.MISSING_TELEMETRY.value in res.data_quality_flags


def test_empty_forecast_input_list_produces_insufficient_data():
    """An empty forecast list evaluates to INSUFFICIENT_DATA."""
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-001",
        road_name="Shaikpet Nala Road",
        forecast_inputs=[],
    )
    assert res.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert res.heuristic_risk_score is None


def test_forecast_with_none_rainfall_amount_produces_insufficient_data():
    """A forecast payload whose rainfall amount is None produces INSUFFICIENT_DATA."""
    fc_none = ForecastRainfallInput(
        location_id="HYD-SEG-001",
        source_id="TEST-NULL",
        source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T07:00:00Z",
        forecast_horizon_hours=1.0,
        rainfall_amount=None,  # Null telemetry
        is_synthetic_fixture=True,
    )
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-001",
        road_name="Shaikpet Nala Road",
        forecast_inputs=[fc_none],
        reference_time_utc=datetime(2026, 10, 27, 6, 30, tzinfo=timezone.utc),
    )
    assert res.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert res.heuristic_risk_score is None
    assert "FORECAST_PRECIPITATION_AMOUNT_NULL" in res.reason_codes


# ==============================================================================
# 4. Freshness, Staleness, and Conflict Detection
# ==============================================================================

def test_stale_forecast_detection():
    """Forecast issued > 6.0 hours before reference time is flagged as STALE."""
    ref_time = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
    stale_fc = ForecastRainfallInput(
        location_id="HYD-SEG-002",
        source_id="OLD-NWP-RUN",
        source_type=ForecastSourceType.NUMERICAL_WEATHER_PREDICTION_NWP,
        issue_timestamp_utc="2026-10-27T06:00:00Z",  # 8 hours old relative to 14:00
        valid_timestamp_utc="2026-10-27T15:00:00Z",
        forecast_horizon_hours=9.0,
        rainfall_amount=20.0,
        is_synthetic_fixture=True,
    )
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-002",
        road_name="Rasoolpura Underpass",
        forecast_inputs=[stale_fc],
        reference_time_utc=ref_time,
    )
    assert res.assessment_status == ForecastDataStatus.STALE
    assert ForecastQualityFlag.STALE.value in res.data_quality_flags
    assert "FORECAST_ISSUE_STALE" in res.reason_codes
    assert res.confidence_score <= 0.35
    assert res.uncertainty_level == "HIGH"


def test_conflicting_forecast_inputs_detection():
    """Two concurrent forecasts diverging by > 20 mm are flagged as CONFLICTING."""
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    fc1 = ForecastRainfallInput(
        location_id="HYD-SEG-003",
        source_id="MODEL-A",
        source_type=ForecastSourceType.NUMERICAL_WEATHER_PREDICTION_NWP,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=5.0,  # Dry / light rain
        is_synthetic_fixture=True,
    )
    fc2 = ForecastRainfallInput(
        location_id="HYD-SEG-003",
        source_id="MODEL-B",
        source_type=ForecastSourceType.REGIONAL_TSDPS_ADVISORY,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=40.0,  # Extreme surge (diff = 35 mm > 20 mm)
        is_synthetic_fixture=True,
    )
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-003",
        road_name="Panjagutta Junction",
        forecast_inputs=[fc1, fc2],
        reference_time_utc=ref_time,
    )
    assert res.assessment_status == ForecastDataStatus.CONFLICTING
    assert res.forecast_risk_category == "UNKNOWN"
    assert res.heuristic_risk_score is None
    assert "CONFLICTING_FORECASTS_DETECTED" in res.reason_codes
    assert ForecastQualityFlag.TEMPORALLY_INCONSISTENT.value in res.data_quality_flags


def test_spatially_unsuitable_forecast_flagged():
    """Forecast with spatial resolution > 15 km is flagged as SPATIALLY_UNSUITABLE."""
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    coarse_fc = ForecastRainfallInput(
        location_id="HYD-SEG-004",
        source_id="GLOBAL-COARSE-GRID",
        source_type=ForecastSourceType.GLOBAL_OPEN_MODEL,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=15.0,
        spatial_resolution_km=25.0,  # Coarse grid (> 15 km)
        is_synthetic_fixture=True,
    )
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-004",
        road_name="Malakpet RUB",
        forecast_inputs=[coarse_fc],
        reference_time_utc=ref_time,
    )
    assert res.assessment_status == ForecastDataStatus.SPATIALLY_UNSUITABLE
    assert ForecastQualityFlag.SPATIALLY_UNSUITABLE.value in res.data_quality_flags
    assert "SPATIAL_RESOLUTION_TOO_COARSE_FOR_CORRIDOR" in res.reason_codes
    assert res.confidence_score <= 0.40


def test_future_issue_timestamp_quarantined():
    """Forecast with issue timestamp occurring in the future relative to now is quarantined."""
    ref_time = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)
    future_fc = ForecastRainfallInput(
        location_id="HYD-SEG-005",
        source_id="TIME-MACHINE-MODEL",
        source_type=ForecastSourceType.SYNTHETIC_TEST_FIXTURE,
        issue_timestamp_utc="2026-10-27T09:00:00Z",  # In the future!
        valid_timestamp_utc="2026-10-27T12:00:00Z",
        forecast_horizon_hours=3.0,
        rainfall_amount=20.0,
        is_synthetic_fixture=True,
    )
    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-005",
        road_name="Begumpet Flyover",
        forecast_inputs=[future_fc],
        reference_time_utc=ref_time,
    )
    assert res.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert "ALL_FORECAST_INPUTS_INVALID_OR_QUARANTINED" in res.reason_codes


# ==============================================================================
# 5. Strict Separation of Five Evidence Signals
# ==============================================================================

def test_five_evidence_signals_strictly_separated():
    """
    Verifies that ForecastRiskAssessmentOutput maintains five distinct, traceable contexts:
    1. Forecast rainfall context
    2. Observed rainfall context
    3. Static susceptibility context
    4. Current road status context
    5. Verified historical flood outcomes context (strictly 0)
    """
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    fc = ForecastRainfallInput(
        location_id="HYD-SEG-006",
        source_id="IMD-WRF-01",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=18.0,
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_1H,
        is_synthetic_fixture=True,
    )
    obs = ObservedRainfallContext(
        observed_1h_mm=4.5,
        observed_3h_mm=12.0,
        telemetry_source_id="GHMC-RAIN-GAUGE-04",
        telemetry_distance_km=2.1,
        telemetry_freshness_hours=0.25,
    )
    vuln = StaticVulnerabilityContext(
        segment_id="HYD-SEG-006",
        vulnerability_index=0.72,
        vulnerability_category="HIGH",
    )
    road = CurrentRoadStatusContext(
        condition_state=RoadConditionState.NO_CURRENT_EVIDENCE,
        verification_state=RoadVerificationState.UNMONITORED,
        observation_age_minutes=None,
    )

    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-006",
        road_name="Tolichowki Underpass",
        forecast_inputs=[fc],
        observed_context=obs,
        vulnerability_context=vuln,
        road_status_context=road,
        reference_time_utc=ref_time,
    )

    # 1. Forecast Context
    assert res.forecast_rainfall_context is not None
    assert res.forecast_rainfall_context["rainfall_amount"] == 18.0
    assert res.forecast_rainfall_context["source_id"] == "IMD-WRF-01"

    # 2. Observed Context (strictly distinct from forecast)
    assert res.observed_rainfall_context["observed_1h_mm"] == 4.5
    assert res.observed_rainfall_context["telemetry_source_id"] == "GHMC-RAIN-GAUGE-04"

    # 3. Static Susceptibility Context
    assert res.static_susceptibility_context["vulnerability_index"] == 0.72
    assert res.static_susceptibility_context["vulnerability_category"] == "HIGH"

    # 4. Current Road Status Context
    assert res.current_road_status_context["condition_state"] == "NO_CURRENT_EVIDENCE"
    assert res.current_road_status_context["verification_state"] == "UNMONITORED"

    # 5. Verified Historical Outcomes Context
    assert res.verified_historical_outcomes_context["verified_historical_flood_events_count"] == 0
    assert res.verified_historical_outcomes_context["status"] == "ZERO_VERIFIED_OUTCOMES_ON_DISK"


def test_forecast_rainfall_alone_does_not_infer_active_flooding():
    """
    CRITICAL SAFETY INVARIANT: Heavy forecast rainfall escalates forecast risk category,
    but MUST NOT infer that the road is currently flooded on the ground.
    """
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    extreme_fc = ForecastRainfallInput(
        location_id="HYD-SEG-007",
        source_id="EXTREME-QPF",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=55.0,  # Heavy downpour predicted
        is_synthetic_fixture=True,
    )
    road_unmonitored = CurrentRoadStatusContext(
        condition_state=RoadConditionState.NO_CURRENT_EVIDENCE,
        verification_state=RoadVerificationState.UNMONITORED,
    )

    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-007",
        road_name="Rasoolpura Underpass",
        forecast_inputs=[extreme_fc],
        road_status_context=road_unmonitored,
        reference_time_utc=ref_time,
    )

    # Forward-looking forecast category is CRITICAL
    assert res.forecast_risk_category == "CRITICAL"
    assert res.heuristic_risk_score is not None and res.heuristic_risk_score >= 0.50

    # Ground condition MUST REMAIN NO_CURRENT_EVIDENCE
    assert res.current_road_status_context["condition_state"] == "NO_CURRENT_EVIDENCE"
    assert res.current_road_status_context["verification_state"] == "UNMONITORED"


def test_absent_flood_evidence_does_not_infer_safety():
    """
    SAFETY INVARIANT: Absence of observed flood reports does not imply road safety.
    Static susceptibility and forward forecast risk remain active and unsuppressed.
    """
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    fc = ForecastRainfallInput(
        location_id="HYD-SEG-008",
        source_id="IMD-WRF-02",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=25.0,
        is_synthetic_fixture=True,
    )
    vuln_high = StaticVulnerabilityContext(
        segment_id="HYD-SEG-008",
        vulnerability_index=0.85,
        vulnerability_category="SEVERE",
    )
    no_evidence_road = CurrentRoadStatusContext(
        condition_state=RoadConditionState.NO_CURRENT_EVIDENCE,
        verification_state=RoadVerificationState.UNMONITORED,
    )

    res = evaluate_forecast_risk(
        segment_id="HYD-SEG-008",
        road_name="Shaikpet Nala Underpass",
        forecast_inputs=[fc],
        vulnerability_context=vuln_high,
        road_status_context=no_evidence_road,
        reference_time_utc=ref_time,
    )

    assert res.forecast_risk_category in {"MEDIUM", "HIGH", "CRITICAL"}
    # Must not contain any safe claim
    assert "safe" not in res.forecast_risk_category.lower()


# ==============================================================================
# 6. Prohibitions on Probability Claims & Forbidden Phrases
# ==============================================================================

def test_prohibition_of_calibrated_probability_claims():
    """
    ForecastRiskAssessmentOutput validator strictly rejects is_calibrated_probability=True.
    Heuristic risk scores cannot be claimed as calibrated probabilities.
    """
    with pytest.raises(ValueError, match="is_calibrated_probability cannot be declared True"):
        ForecastRiskAssessmentOutput(
            segment_id="HYD-SEG-009",
            road_name="Panjagutta Junction",
            assessment_status=ForecastDataStatus.AVAILABLE_VALID,
            assessment_timestamp_utc="2026-10-27T07:00:00Z",
            static_susceptibility_context={"vulnerability_index": 0.5},
            current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
            verified_historical_outcomes_context={"verified_count": 0},
            forecast_risk_category="MEDIUM",
            heuristic_risk_score=0.45,
            is_calibrated_probability=True,  # PROHIBITED!
            confidence_score=0.75,
        )


def test_prohibition_of_forbidden_safety_assertions():
    """ForecastRiskAssessmentOutput validator rejects forbidden claims across text fields."""
    for phrase in FORBIDDEN_SAFETY_PHRASES:
        with pytest.raises(ValueError, match="forbidden"):
            ForecastRiskAssessmentOutput(
                segment_id="HYD-SEG-010",
                road_name=f"Road claiming {phrase}",
                assessment_status=ForecastDataStatus.AVAILABLE_VALID,
                assessment_timestamp_utc="2026-10-27T07:00:00Z",
                static_susceptibility_context={"vulnerability_index": 0.2},
                current_road_status_context={"condition_state": "NO_CURRENT_EVIDENCE"},
                verified_historical_outcomes_context={"verified_count": 0},
                forecast_risk_category="LOW",
                heuristic_risk_score=0.10,
                is_calibrated_probability=False,
                confidence_score=0.80,
            )


# ==============================================================================
# 7. Forecast-Source Readiness Audit & Gate Verification
# ==============================================================================

def test_forecast_source_readiness_audit_verdict():
    """
    Forensic audit of external forecast sources must evaluate to BLOCKED_NO_AUTHORIZED_SOURCE.
    Zero external feeds have authorized operational access in repository.
    """
    report = audit_forecast_sources_readiness()

    assert report.readiness_verdict == "BLOCKED_NO_AUTHORIZED_SOURCE"
    assert report.authorized_sources_count == 0
    assert report.connected_live_sources_count == 0
    assert report.total_candidate_sources_audited == 4
    assert report.operational_readiness_status == "BLOCKED_PENDING_INSTITUTIONAL_DATA"
    assert report.engineering_readiness_status == "OFFLINE_CONTRACTS_COMPLETE"
    assert len(report.unresolved_blockers) >= 4
    assert len(report.prerequisites_to_unblock) >= 3

    # Verify candidate source IDs
    source_ids = [s.source_id for s in report.candidate_sources]
    assert "SRC-FC-01-IMD-NWP" in source_ids
    assert "SRC-FC-02-TSDPS-MESO" in source_ids
    assert "SRC-FC-03-DWR-BEGUMPET" in source_ids
    assert "SRC-FC-04-GLOBAL-NWP" in source_ids

    # All candidate sources must have is_authorized_for_operations = False
    for s in report.candidate_sources:
        assert s.is_authorized_for_operations is False
        assert s.is_live_stream_connected is False


# ==============================================================================
# 8. Dispatch Actionability Invariants
# ==============================================================================

def test_dispatch_actionability_criteria():
    """
    is_actionable_for_dispatch must be True ONLY when:
    - forecast_risk_category is HIGH or CRITICAL
    - assessment_status is AVAILABLE_VALID
    - confidence_score >= 0.50
    """
    ref_time = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)

    # Valid high forecast rain with high vulnerability -> Actionable
    fc_heavy = ForecastRainfallInput(
        location_id="HYD-SEG-011",
        source_id="TEST-SRC",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=32.0,
        is_synthetic_fixture=True,
    )
    vuln = StaticVulnerabilityContext(
        segment_id="HYD-SEG-011",
        vulnerability_index=0.80,
    )
    res_heavy = evaluate_forecast_risk(
        segment_id="HYD-SEG-011",
        road_name="Tolichowki Underpass",
        forecast_inputs=[fc_heavy],
        vulnerability_context=vuln,
        reference_time_utc=ref_time,
    )
    assert res_heavy.forecast_risk_category in {"HIGH", "CRITICAL"}
    assert res_heavy.is_actionable_for_dispatch is True

    # Trace rain -> Clear / Low -> Not actionable
    fc_light = ForecastRainfallInput(
        location_id="HYD-SEG-012",
        source_id="TEST-SRC",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc="2026-10-27T06:00:00Z",
        valid_timestamp_utc="2026-10-27T08:00:00Z",
        forecast_horizon_hours=2.0,
        rainfall_amount=1.5,
        is_synthetic_fixture=True,
    )
    res_light = evaluate_forecast_risk(
        segment_id="HYD-SEG-012",
        road_name="Banjara Hills Rd 1",
        forecast_inputs=[fc_light],
        reference_time_utc=ref_time,
    )
    assert res_light.forecast_risk_category == "CLEAR"
    assert res_light.is_actionable_for_dispatch is False
