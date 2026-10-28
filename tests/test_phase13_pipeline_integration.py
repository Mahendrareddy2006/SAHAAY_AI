"""
Sahaay AI - Phase 13.3 Rainfall Engine & Pipeline Integration Test Suite
Verifies:
1. End-to-end integration of validated IMDRainfallObservation streams into the rainfall risk engine.
2. Safe conversion and rolling accumulation calculation across multiple temporal windows (1h, 3h, 6h, 24h).
3. Deduplication of identical records and quarantine of conflicting duplicates.
4. Out-of-order record handling without rolling window corruption.
5. Strict non-silent missingness: missing windows are not imputed as zero.
6. Preservation of station and provider provenance, distance penalty, and regional catchment tiering.
7. Safe adapter boundary integration (outages yield UNKNOWN, never dry weather).
8. Preservation of Phase 12 decision contracts and vision abstention boundaries [0.35, 0.65].
"""

import math
from datetime import datetime, time, timedelta, timezone
from typing import List

import pytest

from sahaay.adapters.base import AdapterReading, FeedAuthorizationStatus
from sahaay.adapters.mock_imd_adapter import MockIMDRainfallAdapter
from sahaay.decision.contracts import (
    AlertLevel,
    CurrentFloodEvidenceStatus,
    DecisionInput,
    DecisionStatus,
    evaluate_decision,
)
from sahaay.vision.policy import map_vision_probabilities_to_decision
from sahaay.hyderabad_risk.features import (
    aggregate_observations_to_rolling_windows,
    normalize_and_deduplicate_observations,
)
from sahaay.hyderabad_risk.rainfall_engine import (
    evaluate_rainfall_risk_engine,
    evaluate_rainfall_risk_from_adapter,
    evaluate_rainfall_risk_from_observations,
)
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
    RainfallRiskResult,
)


# ==============================================================================
# Helper fixture creators
# ==============================================================================

def create_synthetic_obs(
    station_id: str = "SYNTH_URBAN_01",
    station_name: str = "Synthetic Urban Begumpet AWS",
    provider: str = "MOCK_SYNTHETIC_BENCHMARK",
    latitude: float = 17.4450,
    longitude: float = 78.4700,
    obs_time: datetime = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc),
    interval_rainfall_mm: float = 10.0,
    interval_minutes: int = 60,
    measurement_mode: MeasurementMode = MeasurementMode.INTERVAL_ACCUMULATION,
    raw_counter_value_mm: float = None,
    is_valid: bool = True,
    qc_flag: ObservationQCFlag = ObservationQCFlag.VALID,
) -> IMDRainfallObservation:
    """Creates an explicit synthetic observation for testing."""
    return IMDRainfallObservation(
        provider=provider,
        station_id=station_id,
        station_name=station_name,
        station_type=IMDStationType.AWS,
        latitude=latitude,
        longitude=longitude,
        observation_time_utc=obs_time,
        ingestion_time_utc=obs_time + timedelta(seconds=45),
        interval_minutes=interval_minutes,
        measurement_mode=measurement_mode,
        raw_counter_value_mm=raw_counter_value_mm,
        interval_rainfall_mm=interval_rainfall_mm,
        qc_flag=qc_flag,
        is_valid=is_valid,
        provenance_metadata={"benchmark": "phase13_test_suite"},
    )


# ==============================================================================
# 1. Valid Interval Accumulation Flow
# ==============================================================================

def test_valid_interval_accumulation_flows_to_risk_engine():
    """Test 1: Valid interval accumulation flows into rolling windows and risk engine."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    obs = create_synthetic_obs(
        obs_time=t_now,
        interval_rainfall_mm=22.0,  # IMD Heavy (> 15.0 mm/hr)
        latitude=17.4450,
        longitude=78.4700,
    )
    # Corridor right next to station (~0 km)
    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-BEGUMPET",
        observations=[obs],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res.risk_category == "HIGH"
    assert res.risk_score >= 0.60
    assert "IMD_HEAVY_INTENSITY_EXCEEDED" in res.reason_codes
    assert res.station_id == "SYNTH_URBAN_01"
    assert res.station_proximity_tier == "LOCAL_URBAN"
    assert res.provider == "MOCK_SYNTHETIC_BENCHMARK"


# ==============================================================================
# 2. Cumulative Counter Conversion Integration
# ==============================================================================

def test_cumulative_counter_series_converts_and_integrates():
    """Test 2: A series of cumulative counter readings converts into interval rain and triggers surge."""
    t0 = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)  # 10:00
    t2 = t0 + timedelta(hours=2)  # 11:00
    t3 = t0 + timedelta(hours=3)  # 12:00

    # Counter progression: 100 -> 115 (+15mm) -> 135 (+20mm) -> 155 (+20mm)
    # Total in 3h = 55.0 mm >= 40.0 mm (rolling 3h flash surge)
    obs_list = [
        create_synthetic_obs(obs_time=t0, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=100.0, interval_rainfall_mm=None),
        create_synthetic_obs(obs_time=t1, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=115.0, interval_rainfall_mm=None),
        create_synthetic_obs(obs_time=t2, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=135.0, interval_rainfall_mm=None),
        create_synthetic_obs(obs_time=t3, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=155.0, interval_rainfall_mm=None),
    ]

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=obs_list,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t3,
    )
    assert res.risk_category in ("HIGH", "CRITICAL")
    assert "ROLLING_3H_FLASH_SURGE" in res.reason_codes
    assert res.station_id == "SYNTH_URBAN_01"


# ==============================================================================
# 3. Invalid Counter Decrease Does Not Become Zero
# ==============================================================================

def test_invalid_counter_decrease_does_not_become_zero():
    """Test 3: Counter drop with unverified cause is withheld and does NOT become zero rainfall."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    obs_list = [
        create_synthetic_obs(obs_time=t0, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=100.0, interval_rainfall_mm=None),
        create_synthetic_obs(obs_time=t1, measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER, raw_counter_value_mm=75.0, interval_rainfall_mm=None),
    ]

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=obs_list,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t1,
    )
    # The second reading was invalid (negative delta withheld); hence 1h rainfall is missing!
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes
    assert any("Counter conversion" in w for w in res.warnings)


# ==============================================================================
# 4. Valid Measured Zero vs Missing Telemetry
# ==============================================================================

def test_valid_measured_zero_vs_missing_telemetry():
    """Test 4: Measured zero is evaluated as LOW risk, distinct from UNKNOWN missing telemetry."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Valid measured zero
    obs_zero = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=0.0)
    res_zero = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[obs_zero],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res_zero.risk_category == "LOW"
    assert "NORMAL_DRY_CONDITIONS" in res_zero.reason_codes

    # Missing telemetry (no observations)
    res_missing = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res_missing.risk_category == "UNKNOWN"
    assert res_missing.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res_missing.reason_codes


# ==============================================================================
# 5. Missing 1h Rainfall Produces UNKNOWN
# ==============================================================================

def test_missing_1h_rainfall_produces_unknown():
    """Test 5: If the primary 1h window has no valid observations, risk is strictly UNKNOWN."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    # Observation is 2 hours old (at 10:00); 1h window (11:00 - 12:00) has NO data
    obs_old = create_synthetic_obs(obs_time=t_now - timedelta(hours=2), interval_rainfall_mm=10.0)

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[obs_old],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res.risk_category == "UNKNOWN"
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes


# ==============================================================================
# 6. Missing Accumulation Windows Not Imputed as Zero
# ==============================================================================

def test_missing_rolling_windows_not_imputed_as_zero():
    """Test 6: Missing 3h/6h/24h windows are retained as None and not assumed dry."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    # Exactly 1 observation in 1h window
    obs = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=0.0)

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[obs],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert "rain_3h_mm" in res.missing_inputs
    assert "rain_6h_mm" in res.missing_inputs
    assert "rain_24h_mm" in res.missing_inputs
    assert "CUMULATIVE_WINDOWS_UNAVAILABLE" in res.reason_codes
    assert res.confidence < 1.0


# ==============================================================================
# 7. Stale Observations Flagged
# ==============================================================================

def test_stale_observations_flagged():
    """Test 7: Observations older than 3 hours trigger staleness warnings."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    t_stale = t_now - timedelta(hours=4)  # 4 hours old

    obs = create_synthetic_obs(obs_time=t_stale, interval_rainfall_mm=5.0)
    norm_obs, _ = normalize_and_deduplicate_observations([obs])
    agg = aggregate_observations_to_rolling_windows(norm_obs, station_id=obs.station_id, target_dt=t_now)

    assert agg["freshness_hours"] == 4.0
    assert any("stale" in w.lower() for w in agg["warnings"])


# ==============================================================================
# 8. Out-of-Order Observations Handled
# ==============================================================================

def test_out_of_order_observations_do_not_corrupt_windows():
    """Test 8: Telemetry supplied in scrambled time order is sorted and aggregated without corruption."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Provide in scrambled order: t2, then t0, then t1
    obs2 = create_synthetic_obs(obs_time=t2, interval_rainfall_mm=10.0)
    obs0 = create_synthetic_obs(obs_time=t0, interval_rainfall_mm=5.0)
    obs1 = create_synthetic_obs(obs_time=t1, interval_rainfall_mm=8.0)

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[obs2, obs0, obs1],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t2,
    )
    # 1h rain is t2 (10.0mm -> MEDIUM)
    # 3h rain is 10 + 8 + 5 = 23.0mm
    assert res.risk_category == "MEDIUM"
    assert res.data_freshness_hours == 0.0


# ==============================================================================
# 9. Duplicate Station/Time Records Not Double-Counted
# ==============================================================================

def test_duplicate_records_not_double_counted():
    """Test 9: Exact duplicate records for same station and time are deduplicated idempotently."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    obs1 = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=10.0)
    obs2 = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=10.0)

    norm_obs, _ = normalize_and_deduplicate_observations([obs1, obs2])
    assert len(norm_obs) == 1
    assert norm_obs[0].interval_rainfall_mm == 10.0


# ==============================================================================
# 10. Conflicting Duplicates Quarantined
# ==============================================================================

def test_conflicting_duplicates_quarantined():
    """Test 10: Conflicting duplicate records (disagreeing values) are quarantined with QC_CONFLICTING_DUPLICATE."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    obs1 = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=5.0)
    obs2 = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=35.0)  # Severe conflict

    norm_obs, warnings = normalize_and_deduplicate_observations([obs1, obs2])
    assert len(norm_obs) == 1
    quarantined = norm_obs[0]
    assert quarantined.is_valid is False
    assert quarantined.interval_rainfall_mm is None
    assert quarantined.qc_flag == ObservationQCFlag.QC_CONFLICTING_DUPLICATE
    assert any("Conflicting duplicate" in w for w in warnings)


# ==============================================================================
# 11. Distant Regional Telemetry Provenance and Penalty
# ==============================================================================

def test_distant_regional_telemetry_penalized():
    """Test 11: Regional dam gauge situated 60km away is categorized as REGIONAL_CATCHMENT and penalized."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    # Station ~60km away
    obs_distant = create_synthetic_obs(
        station_id="NWIC_DAM_SINGUR_01",
        station_name="Singur Dam Catchment Gauge",
        latitude=17.7500,
        longitude=78.0000,
        obs_time=t_now,
        interval_rainfall_mm=20.0,
    )

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-HYD-CENTER",
        observations=[obs_distant],
        corridor_lat=17.3850,
        corridor_lon=78.4867,
        target_dt=t_now,
    )
    assert res.station_proximity_tier == "REGIONAL_CATCHMENT"
    assert "REGIONAL_CATCHMENT_TELEMETRY" in res.reason_codes
    assert res.confidence <= 0.65  # Distance penalty applied
    assert res.station_dist_km > 35.0


# ==============================================================================
# 12. Mock Adapter Outage Safety
# ==============================================================================

def test_mock_adapter_outage_does_not_emit_dry_readings():
    """Test 12: Mock adapter outage returns UNKNOWN risk, not fabricated 0.0mm dry weather."""
    adapter = MockIMDRainfallAdapter()
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Load valid observation, then simulate outage
    obs = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=25.0)
    adapter.load_observations("CORRIDOR-01", [obs])
    adapter.set_simulated_outage(True)

    res = evaluate_rainfall_risk_from_adapter(
        location_id="CORRIDOR-01",
        adapter=adapter,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes


# ==============================================================================
# 13. Invalid Input Rejection
# ==============================================================================

@pytest.mark.parametrize("invalid_val", [-10.0, float("nan"), float("inf")])
def test_invalid_rainfall_inputs_rejected_by_engine(invalid_val):
    """Test 13: Non-finite and negative inputs strictly yield UNKNOWN."""
    res = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=invalid_val,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "INVALID_SENSOR_READING" in res.reason_codes


# ==============================================================================
# 14. DecisionInput from RainfallResult Preserves UNKNOWN
# ==============================================================================

def test_decision_input_preserves_unknown_semantics():
    """Test 14: DecisionInput.from_rainfall_result propagates UNKNOWN into DecisionOutput."""
    rainfall_result = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=None,  # Missing input
    )
    assert rainfall_result.risk_category == "UNKNOWN"

    dec_in = DecisionInput.from_rainfall_result(
        location_id="CORRIDOR-01",
        road_name="Khairatabad Flyover",
        rainfall_result=rainfall_result,
    )
    assert dec_in.rainfall_risk_category == "UNKNOWN"

    dec_out = evaluate_decision(dec_in)
    assert dec_out.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert dec_out.current_flood_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
    assert dec_out.requires_human_verification is True
    assert dec_out.alert_level != AlertLevel.EMERGENCY


# ==============================================================================
# 15. Phase 12 Vision Abstention Band Invariance [0.35, 0.65]
# ==============================================================================

@pytest.mark.parametrize("prob,expected_status,expected_ambiguous", [
    (0.349, CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE, False),
    (0.350, CurrentFloodEvidenceStatus.INCONCLUSIVE, True),   # Inclusive lower boundary
    (0.500, CurrentFloodEvidenceStatus.INCONCLUSIVE, True),   # Inside abstention band
    (0.650, CurrentFloodEvidenceStatus.INCONCLUSIVE, True),   # Inclusive upper boundary
    (0.651, CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE, False),
])
def test_phase12_vision_abstention_band_preserved(prob, expected_status, expected_ambiguous):
    """Test 15: Vision abstention band remains exactly inclusive at [0.35, 0.65]."""
    cls_name, conf, is_ambig, is_inconcl, reasons = map_vision_probabilities_to_decision(float(prob))
    assert is_ambig == expected_ambiguous
    if is_ambig:
        assert cls_name == "inconclusive"
        assert is_inconcl is True


# ==============================================================================
# 16. Existing Valid-Measurement Threshold Boundaries
# ==============================================================================

@pytest.mark.parametrize("rain_mm,expected_cat", [
    (0.0, "LOW"),
    (5.0, "LOW"),
    (7.5, "MEDIUM"),
    (15.0, "HIGH"),
    (35.0, "CRITICAL"),
])
def test_valid_measurement_threshold_boundaries_preserved(rain_mm, expected_cat):
    """Test 16: Operational IMD threshold step functions remain intact for valid inputs."""
    res = evaluate_rainfall_risk_engine(
        location_id="TEST-LOC",
        rain_1h_mm=rain_mm,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res.risk_category == expected_cat


# ==============================================================================
# 17. Regional Catchment Telemetry Decision Layer Propagation
# ==============================================================================

def test_regional_catchment_cannot_trigger_actionable_watch():
    """
    Test 17: Telemetry from a distant regional catchment (~80 km) with heavy rain (50 mm/hr)
    on a chronically vulnerable urban road MUST NOT produce an actionable local-road WATCH alert.
    Must produce qualified, non-actionable ADVISORY with REGIONAL_CATCHMENT_TELEMETRY_DISCOUNTED.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    # Station ~80km away from corridor
    obs_distant = create_synthetic_obs(
        station_id="NWIC_DAM_NIZAMSAGAR_01",
        station_name="Nizamsagar Reservoir Watershed Gauge",
        latitude=18.1500,
        longitude=77.9000,
        obs_time=t_now,
        interval_rainfall_mm=50.0,  # Extreme regional rain
    )

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-HYD-CENTER",
        observations=[obs_distant],
        corridor_lat=17.3850,
        corridor_lon=78.4867,
        target_dt=t_now,
    )
    assert res.station_proximity_tier == "REGIONAL_CATCHMENT"
    assert res.station_dist_km > 35.0

    # Pass to DecisionInput for a chronically vulnerable road segment
    d_in = DecisionInput.from_rainfall_result(
        location_id="CORRIDOR-HYD-CENTER",
        road_name="Begumpet Chronic Hotspot",
        rainfall_result=res,
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
    )
    assert d_in.rainfall_proximity_tier == "REGIONAL_CATCHMENT"
    assert d_in.rainfall_risk_category == "CRITICAL"

    # Evaluate decision
    d_out = evaluate_decision(d_in)
    assert d_out.alert_level == AlertLevel.ADVISORY
    assert d_out.alert_level != AlertLevel.WATCH
    assert d_out.is_actionable_for_crews is False
    assert d_out.rainfall_proximity_tier == "REGIONAL_CATCHMENT"
    assert d_out.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert "REGIONAL_CATCHMENT_TELEMETRY_DISCOUNTED" in d_out.reason_codes
    assert d_out.confidence <= 0.40

    # Ensure serialized representation preserves proximity tier
    dumped = d_out.model_dump()
    assert dumped["rainfall_proximity_tier"] == "REGIONAL_CATCHMENT"
    assert dumped["is_actionable_for_crews"] is False


def test_regional_telemetry_does_not_suppress_independent_local_evidence():
    """
    Test 18: Distant regional catchment rainfall does NOT suppress independently supplied
    fresh local visual flood evidence or responder inspection.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    obs_distant = create_synthetic_obs(
        station_id="NWIC_DAM_NIZAMSAGAR_01",
        latitude=18.1500,
        longitude=77.9000,
        obs_time=t_now,
        interval_rainfall_mm=50.0,
    )
    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-HYD-CENTER",
        observations=[obs_distant],
        corridor_lat=17.3850,
        corridor_lon=78.4867,
        target_dt=t_now,
    )

    # Supply local visual flood evidence
    d_in = DecisionInput.from_rainfall_result(
        location_id="CORRIDOR-HYD-CENTER",
        road_name="Begumpet Chronic Hotspot",
        rainfall_result=res,
        vision_predicted_class="flooded",
        vision_confidence=0.88,
        vulnerability_category="HIGH",
    )
    d_out = evaluate_decision(d_in)
    # Local flood evidence is verified and fresh -> Must trigger WARNING with actionable crew dispatch
    assert d_out.alert_level == AlertLevel.WARNING
    assert d_out.is_actionable_for_crews is True
    assert d_out.current_flood_evidence_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE


# ==============================================================================
# 19. Temporal Coverage & Sub-Hourly Accumulation Safety
# ==============================================================================

def test_single_sub_hourly_observation_withheld_for_1h_window():
    """
    Test 19: A single 15-minute or 5-minute observation in a 1-hour window has insufficient
    temporal coverage (< 45 min) and excessive uncovered gap (> 20 min); rain_1h_mm is withheld as None.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Single 15-minute observation with 2.0mm
    obs_15m = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=2.0, interval_minutes=15)
    agg_15m = aggregate_observations_to_rolling_windows([obs_15m], station_id="SYNTH_URBAN_01", target_dt=t_now)
    assert agg_15m["rain_1h_mm"] is None
    assert any("insufficient temporal coverage" in w for w in agg_15m["warnings"])

    # 2. Single 5-minute observation with 1.0mm
    obs_5m = create_synthetic_obs(obs_time=t_now, interval_rainfall_mm=1.0, interval_minutes=5)
    agg_5m = aggregate_observations_to_rolling_windows([obs_5m], station_id="SYNTH_URBAN_01", target_dt=t_now)
    assert agg_5m["rain_1h_mm"] is None
    assert any("insufficient temporal coverage" in w for w in agg_5m["warnings"])


def test_fully_covered_sub_hourly_1h_window():
    """
    Test 20: Four consecutive 15-minute observations covering the entire hour (11:00-12:00)
    aggregate to a valid 1-hour accumulation.
    """
    t0 = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)
    t2 = t0 + timedelta(minutes=30)
    t3 = t0 + timedelta(minutes=45)
    t4 = t0 + timedelta(minutes=60)

    obs_list = [
        create_synthetic_obs(obs_time=t1, interval_rainfall_mm=2.0, interval_minutes=15),
        create_synthetic_obs(obs_time=t2, interval_rainfall_mm=3.0, interval_minutes=15),
        create_synthetic_obs(obs_time=t3, interval_rainfall_mm=4.0, interval_minutes=15),
        create_synthetic_obs(obs_time=t4, interval_rainfall_mm=5.0, interval_minutes=15),
    ]

    agg = aggregate_observations_to_rolling_windows(obs_list, station_id="SYNTH_URBAN_01", target_dt=t4)
    assert agg["rain_1h_mm"] == 14.0  # 2 + 3 + 4 + 5 = 14.0mm
    assert agg["freshness_hours"] == 0.0


def test_gapped_sub_hourly_observations_withheld():
    """
    Test 21: Sub-hourly observations with an uncovered gap > 20 min are withheld as None.
    """
    t0 = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)  # 11:00 to 11:15
    t4 = t0 + timedelta(minutes=60)  # 11:45 to 12:00 (Gap of 30 min from 11:15 to 11:45)

    obs_list = [
        create_synthetic_obs(obs_time=t1, interval_rainfall_mm=2.0, interval_minutes=15),
        create_synthetic_obs(obs_time=t4, interval_rainfall_mm=2.0, interval_minutes=15),
    ]
    agg = aggregate_observations_to_rolling_windows(obs_list, station_id="SYNTH_URBAN_01", target_dt=t4)
    assert agg["rain_1h_mm"] is None
    assert any("insufficient temporal coverage" in w for w in agg["warnings"])


# ==============================================================================
# 20. Overlapping Intervals Withholding
# ==============================================================================

def test_overlapping_intervals_withheld_to_prevent_double_counting():
    """
    Test 22: Two 60-minute interval observations that overlap in time (e.g. 10:30-11:30 and 11:00-12:00)
    are detected and withheld to prevent double-counting.
    """
    t1 = datetime(2026, 10, 26, 11, 30, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    obs1 = create_synthetic_obs(obs_time=t1, interval_rainfall_mm=15.0, interval_minutes=60)
    obs2 = create_synthetic_obs(obs_time=t2, interval_rainfall_mm=20.0, interval_minutes=60)

    agg = aggregate_observations_to_rolling_windows([obs1, obs2], station_id="SYNTH_URBAN_01", target_dt=t2)
    assert agg["rain_1h_mm"] is None
    assert any("overlapping measurement intervals" in w for w in agg["warnings"])


def test_adjacent_non_overlapping_intervals_aggregated_cleanly():
    """
    Test 23: Adjacent non-overlapping 60-minute intervals (10:00-11:00 and 11:00-12:00)
    are aggregated without overlapping interval warnings.
    """
    t1 = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    obs1 = create_synthetic_obs(obs_time=t1, interval_rainfall_mm=10.0, interval_minutes=60)
    obs2 = create_synthetic_obs(obs_time=t2, interval_rainfall_mm=15.0, interval_minutes=60)

    agg = aggregate_observations_to_rolling_windows([obs1, obs2], station_id="SYNTH_URBAN_01", target_dt=t2)
    assert agg["rain_1h_mm"] == 15.0  # Only t2 is in the 1h window (11:00, 12:00]
    assert not any("overlapping measurement intervals" in w for w in agg["warnings"])


# ==============================================================================
# 21. Freshness Measured from Latest Valid Observation
# ==============================================================================

def test_freshness_measured_from_latest_valid_not_corrupt_record():
    """
    Test 24: When an invalid record arrives at target_dt, telemetry freshness is measured
    from the latest VALID observation (4 hours old), NOT masked as 0.0h fresh.
    """
    t_target = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    t_valid = t_target - timedelta(hours=4)

    obs_valid = create_synthetic_obs(obs_time=t_valid, interval_rainfall_mm=10.0)
    obs_corrupt = create_synthetic_obs(
        obs_time=t_target,
        interval_rainfall_mm=None,
        raw_counter_value_mm=None,
        is_valid=False,
        qc_flag=ObservationQCFlag.QC_MISSING_VALUE,
    )

    agg = aggregate_observations_to_rolling_windows([obs_valid, obs_corrupt], station_id="SYNTH_URBAN_01", target_dt=t_target)
    assert agg["freshness_hours"] == 4.0
    assert any("was invalid" in w for w in agg["warnings"])
    assert any("stale" in w for w in agg["warnings"])


def test_freshness_when_no_valid_observations_exist():
    """
    Test 25: When all available observations are invalid/quarantined, freshness is None
    and risk engine safely yields UNKNOWN with INSUFFICIENT_TELEMETRY_DATA.
    """
    t_target = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    obs_corrupt = create_synthetic_obs(
        obs_time=t_target,
        interval_rainfall_mm=None,
        is_valid=False,
        qc_flag=ObservationQCFlag.QC_NEGATIVE_VALUE,
    )

    res = evaluate_rainfall_risk_from_observations(
        location_id="CORRIDOR-01",
        observations=[obs_corrupt],
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_target,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes


# ==============================================================================
# 22. Adapter Payload Hardening
# ==============================================================================

class GenericMockAdapter:
    def __init__(self, reading):
        self.source_id = "GENERIC_ADAPTER_TEST"
        self._reading = reading

    def fetch_latest(self, location_id: str, query_time: datetime):
        return self._reading


@pytest.mark.parametrize("bad_val,expected_flag", [
    (15.5, "MALFORMED_ADAPTER_PAYLOAD"),
    ("15.5mm", "MALFORMED_ADAPTER_PAYLOAD"),
    ([10.0, 20.0], "MALFORMED_ADAPTER_PAYLOAD"),
])
def test_adapter_hardened_against_non_dict_payloads(bad_val, expected_flag):
    """Test 26: Non-dict adapter payloads are safely quarantined as UNKNOWN without crashing."""
    reading = AdapterReading(
        source_id="GENERIC_ADAPTER_TEST",
        source_name="Generic Test Adapter",
        authorization_status=FeedAuthorizationStatus.AUTHORIZED_LIVE,
        data_available=True,
        retrieval_timestamp_utc="2026-10-26T12:00:00Z",
        value=bad_val,
        units="mm",
    )
    adapter = GenericMockAdapter(reading)
    res = evaluate_rainfall_risk_from_adapter(
        location_id="CORRIDOR-01",
        adapter=adapter,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert expected_flag in res.qc_flags
    assert any("malformed payload" in w for w in res.warnings)


def test_adapter_hardened_against_empty_dict():
    """Test 27: Empty dict payload safely yields UNKNOWN without crashing."""
    reading = AdapterReading(
        source_id="GENERIC_ADAPTER_TEST",
        source_name="Generic Test Adapter",
        authorization_status=FeedAuthorizationStatus.AUTHORIZED_LIVE,
        data_available=True,
        retrieval_timestamp_utc="2026-10-26T12:00:00Z",
        value={},
        units="mm",
    )
    adapter = GenericMockAdapter(reading)
    res = evaluate_rainfall_risk_from_adapter(
        location_id="CORRIDOR-01",
        adapter=adapter,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes


# ==============================================================================
# 23. Measured Zero Confidence Accounting & Antecedent Penalties
# ==============================================================================

def test_measured_zero_confidence_accounting():
    """
    Test 28: Valid measured zero rainfall has confidence 1.0 ONLY when antecedent rolling
    windows (3h, 6h, 24h) are present and valid. When antecedent windows are unobserved,
    confidence is properly discounted by missing window penalties.
    """
    # 1. Measured zero with all windows present
    res_full = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=0.0,
        rain_3h_mm=0.0,
        rain_6h_mm=0.0,
        rain_24h_mm=0.0,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res_full.risk_category == "LOW"
    assert res_full.risk_score == 0.02
    assert res_full.confidence == 1.0  # Full confidence justified only with full antecedent coverage

    # 2. Measured zero with missing antecedent windows (3h/6h/24h unobserved)
    res_discounted = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=0.0,
        rain_3h_mm=None,
        rain_6h_mm=None,
        rain_24h_mm=None,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res_discounted.risk_category == "LOW"
    assert res_discounted.risk_score == 0.02
    # 1.0 - (3 * 0.08) = 0.76 confidence! Never falsely claimed as full 1.0 confidence!
    assert res_discounted.confidence == 0.76
    assert "CUMULATIVE_WINDOWS_UNAVAILABLE" in res_discounted.reason_codes


# ==============================================================================
# 24. Proximity Metadata: Elimination of Unsafe LOCAL_URBAN Defaults
# ==============================================================================

def test_rainfall_engine_without_station_dist_defaults_to_unknown_never_local_urban():
    """
    CRITICAL SAFETY REQUIREMENT:
    Calling evaluate_rainfall_risk_engine without station_dist_km must NEVER
    default to 0.0 or LOCAL_URBAN. Proximity tier must be explicitly UNKNOWN.
    """
    res = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-PROX-01",
        rain_1h_mm=45.0,  # Critical intensity
        # station_dist_km omitted!
        data_freshness_hours=0.5,
    )
    assert res.station_proximity_tier == "UNKNOWN"
    assert res.station_proximity_tier != "LOCAL_URBAN"
    assert res.station_dist_km is None
    assert "STATION_PROXIMITY_UNKNOWN" in res.reason_codes
    assert any("proximity tier is UNKNOWN" in w for w in res.warnings)


def test_decision_input_defaults_to_unknown_proximity():
    """
    DecisionInput constructed without proximity metadata must default to UNKNOWN,
    never LOCAL_URBAN.
    """
    inp = DecisionInput(
        location_id="CORRIDOR-PROX-02",
        road_name="Panjagutta Main Rd",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.90,
        # rainfall_proximity_tier omitted!
        vulnerability_category="SEVERE",
        vulnerability_index=0.85,
    )
    assert inp.rainfall_proximity_tier == "UNKNOWN"
    assert inp.rainfall_proximity_tier != "LOCAL_URBAN"


def test_from_rainfall_result_missing_proximity_becomes_unknown():
    """
    A rainfall result lacking proximity metadata must NOT become LOCAL_URBAN
    when passed into DecisionInput.from_rainfall_result.
    """
    class LegacyRainfallResult:
        risk_category = "CRITICAL"
        risk_score = 0.88
        missing_inputs = []
        warnings = []
        station_id = "LEGACY_ST_01"

    legacy_res = LegacyRainfallResult()
    inp = DecisionInput.from_rainfall_result(
        location_id="CORRIDOR-PROX-03",
        road_name="Banjara Hills Rd 12",
        rainfall_result=legacy_res,
        vulnerability_category="HIGH",
        vulnerability_index=0.75,
    )
    assert inp.rainfall_proximity_tier == "UNKNOWN"
    assert inp.rainfall_proximity_tier != "LOCAL_URBAN"


def test_unknown_proximity_heavy_rain_withholds_actionable_watch():
    """
    High rainfall risk + SEVERE road vulnerability + UNKNOWN station proximity
    must NOT trigger an actionable crew alert (WATCH) based on rainfall alone.
    It must yield a qualified ADVISORY with is_actionable_for_crews=False.
    """
    inp = DecisionInput(
        location_id="CORRIDOR-PROX-04",
        road_name="Tolichowki Chronic Junction",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        rainfall_proximity_tier="UNKNOWN",
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
    )
    out = evaluate_decision(inp)
    assert out.alert_level == AlertLevel.ADVISORY
    assert out.alert_level != AlertLevel.WATCH
    assert out.is_actionable_for_crews is False
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    assert "UNKNOWN_PROXIMITY_TELEMETRY_DISCOUNTED" in out.reason_codes
    assert any("UNKNOWN proximity tier" in w for w in out.warnings)


def test_verified_local_physical_evidence_escalates_despite_unknown_or_regional_proximity():
    """
    SAFETY INVARIANT:
    Verified local physical evidence (e.g. field responder verification or observed
    ground flood) must escalate independently of UNKNOWN or REGIONAL rainfall proximity.
    """
    # 1. Unknown proximity rainfall + on-site responder confirmation -> WARNING
    inp_responder = DecisionInput(
        location_id="CORRIDOR-PROX-05",
        road_name="Tolichowki Chronic Junction",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        rainfall_proximity_tier="UNKNOWN",
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
        is_field_verified=True,  # Ground responder on site
    )
    out_responder = evaluate_decision(inp_responder)
    assert out_responder.alert_level == AlertLevel.WARNING
    assert out_responder.is_actionable_for_crews is True
    assert out_responder.current_flood_evidence_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
    assert "FIELD_RESPONDER_INSPECTION_CONFIRMED" in out_responder.reason_codes

    # 2. Corroborated ground responder + visual flood upload -> EMERGENCY
    inp_emergency = DecisionInput(
        location_id="CORRIDOR-PROX-05",
        road_name="Tolichowki Chronic Junction",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        rainfall_proximity_tier="UNKNOWN",
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
        vision_predicted_class="flooded",
        vision_confidence=0.90,
        is_field_verified=True,  # Dual visual + responder confirmation
    )
    out_emergency = evaluate_decision(inp_emergency)
    assert out_emergency.alert_level == AlertLevel.EMERGENCY
    assert out_emergency.is_actionable_for_crews is True
    assert out_emergency.current_flood_evidence_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
    assert "EMERGENCY_DEEP_INUNDATION_CONFIRMED" in out_emergency.reason_codes

    # 3. Regional catchment rainfall + observed street flooding -> WARNING
    inp_visual = DecisionInput(
        location_id="CORRIDOR-PROX-05",
        road_name="Tolichowki Chronic Junction",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        rainfall_proximity_tier="REGIONAL_CATCHMENT",
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
        vision_predicted_class="flooded",
        vision_confidence=0.85,
    )
    out_visual = evaluate_decision(inp_visual)
    assert out_visual.alert_level == AlertLevel.WARNING
    assert out_visual.is_actionable_for_crews is True
    assert out_visual.current_flood_evidence_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE


def test_explicit_verified_local_proximity_triggers_watch():
    """
    Explicit, verified local proximity (LOCAL_URBAN) on chronically vulnerable corridor
    correctly triggers actionable WATCH as designed.
    """
    inp_local = DecisionInput(
        location_id="CORRIDOR-PROX-06",
        road_name="Begumpet Railway Bridge",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.92,
        rainfall_proximity_tier="LOCAL_URBAN",
        vulnerability_category="SEVERE",
        vulnerability_index=0.88,
    )
    out_local = evaluate_decision(inp_local)
    assert out_local.alert_level == AlertLevel.WATCH
    assert out_local.is_actionable_for_crews is True
    assert out_local.current_flood_evidence_status == CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
    assert "PREDICTED_WATERLOGGING_SURGE_ANTICIPATED" in out_local.reason_codes


def test_existing_regional_catchment_discounting_remains_intact():
    """
    Existing Phase 13.3 regional catchment discounting (>35km) remains strictly intact.
    """
    inp_regional = DecisionInput(
        location_id="CORRIDOR-PROX-07",
        road_name="Moosarambagh Bridge",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        rainfall_proximity_tier="REGIONAL_CATCHMENT",
        rainfall_station_id="OSMAN_SAGAR_DAM_AWS",
        vulnerability_category="SEVERE",
        vulnerability_index=0.90,
    )
    out_regional = evaluate_decision(inp_regional)
    assert out_regional.alert_level == AlertLevel.ADVISORY
    assert out_regional.is_actionable_for_crews is False
    assert "REGIONAL_CATCHMENT_TELEMETRY_DISCOUNTED" in out_regional.reason_codes
    assert out_regional.rainfall_proximity_tier == "REGIONAL_CATCHMENT"


