"""
Sahaay AI - Phase 13.2 Formal Contracts & Mock Adapter Test Suite
Verifies:
1. IMDRainfallObservation strict contract validation (bounds, timezone, non-negativity, consistency).
2. Safe cumulative counter conversion (monotonic deltas, rollover math, daily resets, spike rejection).
3. Hardened rainfall engine (negative input rejection, missing cumulative window tracking).
4. Deterministic MockIMDRainfallAdapter (outage handling, zero vs missing distinction, staleness, deduplication).
5. Cross-phase safety preservation (Phase 12 decision contracts).
"""

import math
from datetime import datetime, time, timedelta, timezone
from typing import Optional

import pytest

from sahaay.adapters.base import FeedAuthorizationStatus
from sahaay.adapters.mock_imd_adapter import MockIMDRainfallAdapter
from sahaay.decision.contracts import AlertLevel, DecisionInput, evaluate_decision
from sahaay.hyderabad_risk.counter_conversion import (
    DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    CounterConversionResult,
    convert_consecutive_gauge_observations,
    convert_cumulative_counter_to_interval,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
    RainfallRiskResult,
)


# ==============================================================================
# 1. IMDRainfallObservation Pydantic Contract Validation Tests
# ==============================================================================

def test_observation_contract_valid_payload():
    """Verify clean instantiation of IMDRainfallObservation with valid telemetry."""
    now_utc = datetime.now(timezone.utc)
    obs = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK",
        station_id="SYNTH_HYD_01",
        station_name="Synthetic Hyderabad Central AWS",
        station_type=IMDStationType.AWS,
        latitude=17.3850,
        longitude=78.4867,
        observation_time_utc=now_utc,
        ingestion_time_utc=now_utc,
        interval_minutes=60,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
        raw_counter_value_mm=124.5,
        interval_rainfall_mm=12.5,
        qc_flag=ObservationQCFlag.VALID,
        is_valid=True,
    )
    assert obs.station_id == "SYNTH_HYD_01"
    assert obs.interval_rainfall_mm == 12.5
    assert obs.is_valid is True


def test_observation_contract_rejects_naive_timestamp():
    """SAFETY RULE: Naive datetimes without timezone must be rejected."""
    naive_dt = datetime(2026, 10, 26, 12, 0, 0)  # No tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        IMDRainfallObservation(
            provider="MOCK_SYNTHETIC_BENCHMARK",
            station_id="SYNTH_HYD_01",
            station_name="Synthetic Hyderabad Central AWS",
            latitude=17.3850,
            longitude=78.4867,
            observation_time_utc=naive_dt,
            ingestion_time_utc=datetime.now(timezone.utc),
            measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
            interval_rainfall_mm=5.0,
            is_valid=True,
        )


@pytest.mark.parametrize("lat,lon", [
    (14.99, 78.4867),   # Lat too low (< 15.0)
    (20.51, 78.4867),   # Lat too high (> 20.5)
    (17.3850, 76.49),   # Lon too low (< 76.5)
    (17.3850, 82.51),   # Lon too high (> 82.5)
    (float("nan"), 78.4867),
    (17.3850, float("inf")),
])
def test_observation_contract_rejects_out_of_bounds_or_non_finite_coords(lat, lon):
    """Coordinates outside regional project bounds or non-finite must raise ValidationError."""
    now_utc = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        IMDRainfallObservation(
            provider="MOCK_SYNTHETIC_BENCHMARK",
            station_id="SYNTH_HYD_01",
            station_name="Synthetic Hyderabad Central AWS",
            latitude=lat,
            longitude=lon,
            observation_time_utc=now_utc,
            ingestion_time_utc=now_utc,
            measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
            interval_rainfall_mm=0.0,
            is_valid=True,
        )


def test_observation_contract_rejects_negative_rainfall():
    """Negative rainfall values presented as valid readings must be rejected."""
    now_utc = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="greater than or equal to 0|cannot be negative"):
        IMDRainfallObservation(
            provider="MOCK_SYNTHETIC_BENCHMARK",
            station_id="SYNTH_HYD_01",
            station_name="Synthetic Hyderabad Central AWS",
            latitude=17.3850,
            longitude=78.4867,
            observation_time_utc=now_utc,
            ingestion_time_utc=now_utc,
            measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
            interval_rainfall_mm=-12.5,
            is_valid=True,
        )


def test_observation_contract_cross_field_consistency():
    """An observation marked is_valid=True cannot have an error QC flag."""
    now_utc = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="cannot have error QC flag"):
        IMDRainfallObservation(
            provider="MOCK_SYNTHETIC_BENCHMARK",
            station_id="SYNTH_HYD_01",
            station_name="Synthetic Hyderabad Central AWS",
            latitude=17.3850,
            longitude=78.4867,
            observation_time_utc=now_utc,
            ingestion_time_utc=now_utc,
            measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
            interval_rainfall_mm=10.0,
            qc_flag=ObservationQCFlag.QC_NEGATIVE_DELTA,
            is_valid=True,  # Inconsistent with QC_NEGATIVE_DELTA
        )


# ==============================================================================
# 2. Cumulative Counter Conversion & QC Tests
# ==============================================================================

def test_normal_monotonic_counter_conversion():
    """Test Case 1: Normal non-decreasing counter readings produce correct interval delta."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    res = convert_cumulative_counter_to_interval(
        current_counter_mm=65.5,
        current_time_utc=t1,
        previous_counter_mm=50.0,
        previous_time_utc=t0,
    )
    assert res.is_valid is True
    assert res.interval_rainfall_mm == 15.5
    assert res.qc_flag == ObservationQCFlag.VALID
    assert res.elapsed_minutes == 60.0
    assert res.effective_rate_mm_per_hr == 15.5


def test_verified_configured_counter_rollover():
    """Test Case 2: Configured counter rollover at device capacity (e.g. 1000mm) is correctly computed."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    # Gauge rolls over at 1000.0mm: previous reading was 990.0, current is 15.0
    # Expected delta: (1000.0 - 990.0) + 15.0 = 25.0 mm
    res = convert_cumulative_counter_to_interval(
        current_counter_mm=15.0,
        current_time_utc=t1,
        previous_counter_mm=990.0,
        previous_time_utc=t0,
        counter_max_mm=1000.0,
    )
    assert res.is_valid is True
    assert res.interval_rainfall_mm == 25.0
    assert res.qc_flag == ObservationQCFlag.QC_COUNTER_ROLLOVER
    assert "Verified hardware counter rollover" in res.qc_reason


def test_counter_decrease_unknown_cause():
    """Test Case 3: Counter decrease with unknown cause is withheld without clamping to 0.0mm."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    res = convert_cumulative_counter_to_interval(
        current_counter_mm=70.0,
        current_time_utc=t1,
        previous_counter_mm=85.0,
        previous_time_utc=t0,
        counter_max_mm=None,  # No rollover capacity configured
    )
    assert res.is_valid is False
    assert res.interval_rainfall_mm is None  # NEVER clamped to 0.0
    assert res.qc_flag == ObservationQCFlag.QC_NEGATIVE_DELTA
    assert "Unexplained counter decrease" in res.qc_reason


def test_source_documented_daily_reset():
    """Test Case 4: Documented source daily reset (03:00 UTC / 08:30 IST) is flagged without fabricating zero."""
    t0 = datetime(2026, 10, 26, 2, 30, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 26, 3, 0, 0, tzinfo=timezone.utc)  # Exact 03:00 UTC reset
    res = convert_cumulative_counter_to_interval(
        current_counter_mm=2.0,
        current_time_utc=t1,
        previous_counter_mm=140.0,
        previous_time_utc=t0,
        configured_daily_reset_utc=time(3, 0),
        reset_tolerance_minutes=15,
    )
    assert res.is_valid is False
    assert res.interval_rainfall_mm is None
    assert res.qc_flag == ObservationQCFlag.QC_GAUGE_RESET
    assert "daily reset window" in res.qc_reason


def test_unphysical_rainfall_delta():
    """Test Case 5: Delta exceeding project physical threshold (>250mm/hr) is rejected as unphysical spike."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    res = convert_cumulative_counter_to_interval(
        current_counter_mm=310.0,
        current_time_utc=t1,
        previous_counter_mm=10.0,
        previous_time_utc=t0,  # 300mm in 1 hour > 250mm/hr limit
    )
    assert res.is_valid is False
    assert res.interval_rainfall_mm is None
    assert res.qc_flag == ObservationQCFlag.QC_UNPHYSICAL_SPIKE
    assert "exceeds project QC threshold" in res.qc_reason


def test_missing_current_or_previous_reading():
    """Test Case 6: Missing counter or timestamp yields QC_MISSING_VALUE."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    res1 = convert_cumulative_counter_to_interval(
        current_counter_mm=None,
        current_time_utc=t0,
        previous_counter_mm=50.0,
        previous_time_utc=t0,
    )
    assert res1.is_valid is False
    assert res1.qc_flag == ObservationQCFlag.QC_MISSING_VALUE

    res2 = convert_cumulative_counter_to_interval(
        current_counter_mm=50.0,
        current_time_utc=None,
        previous_counter_mm=40.0,
        previous_time_utc=t0,
    )
    assert res2.is_valid is False
    assert res2.qc_flag == ObservationQCFlag.QC_MISSING_VALUE


def test_zero_or_negative_elapsed_time():
    """Test Case 7: Identical or out-of-order timestamps yield QC_TIMESTAMP_ANOMALY."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    # Zero elapsed time
    res_zero = convert_cumulative_counter_to_interval(
        current_counter_mm=55.0,
        current_time_utc=t0,
        previous_counter_mm=50.0,
        previous_time_utc=t0,
    )
    assert res_zero.is_valid is False
    assert res_zero.qc_flag == ObservationQCFlag.QC_TIMESTAMP_ANOMALY
    assert "Zero elapsed time" in res_zero.qc_reason

    # Negative elapsed time (t_curr precedes t_prev)
    t1 = t0 - timedelta(minutes=15)
    res_neg = convert_cumulative_counter_to_interval(
        current_counter_mm=55.0,
        current_time_utc=t1,
        previous_counter_mm=50.0,
        previous_time_utc=t0,
    )
    assert res_neg.is_valid is False
    assert res_neg.qc_flag == ObservationQCFlag.QC_TIMESTAMP_ANOMALY
    assert "Negative elapsed time" in res_neg.qc_reason


def test_convert_consecutive_gauge_observations_station_mismatch():
    """Station mismatch between consecutive observation records is rejected."""
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    obs1 = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK",
        station_id="STATION_A",
        station_name="Station Alpha",
        latitude=17.385,
        longitude=78.486,
        observation_time_utc=t0,
        ingestion_time_utc=t0,
        measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER,
        raw_counter_value_mm=50.0,
        is_valid=True,
    )
    obs2 = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK",
        station_id="STATION_B",
        station_name="Station Beta",
        latitude=17.400,
        longitude=78.500,
        observation_time_utc=t1,
        ingestion_time_utc=t1,
        measurement_mode=MeasurementMode.CUMULATIVE_GAUGE_COUNTER,
        raw_counter_value_mm=60.0,
        is_valid=True,
    )
    res = convert_consecutive_gauge_observations(obs2, obs1)
    assert res.is_valid is False
    assert res.qc_flag == ObservationQCFlag.QC_TIMESTAMP_ANOMALY
    assert "Station mismatch" in res.qc_reason


# ==============================================================================
# 3. Hardened Rainfall Risk Engine Tests
# ==============================================================================

def test_negative_rainfall_input_triggers_unknown_never_clamped():
    """Test Case 13: Negative sensor reading must NEVER be clamped to 0.0mm or evaluate as LOW."""
    res = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=-25.0,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert res.risk_category == "UNKNOWN"
    assert res.risk_score == 0.0
    assert res.confidence == 0.10
    assert "INVALID_SENSOR_READING" in res.reason_codes
    assert "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes
    assert any("negative or non-finite" in w for w in res.warnings)


def test_non_finite_rainfall_input_triggers_unknown():
    """Non-finite (NaN or Inf) hourly rainfall reading triggers UNKNOWN."""
    res_nan = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=float("nan"),
    )
    assert res_nan.risk_category == "UNKNOWN"
    assert "INVALID_SENSOR_READING" in res_nan.reason_codes

    res_inf = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=float("inf"),
    )
    assert res_inf.risk_category == "UNKNOWN"
    assert "INVALID_SENSOR_READING" in res_inf.reason_codes


def test_missing_rolling_windows_not_imputed_as_zero():
    """Test Case 12: Missing 3h/24h windows are tracked in missing_inputs and not imputed as zero."""
    res = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=0.0,
        rain_3h_mm=None,
        rain_6h_mm=None,
        rain_24h_mm=None,
        station_dist_km=2.0,
        data_freshness_hours=0.5,
    )
    assert "rain_3h_mm" in res.missing_inputs
    assert "rain_24h_mm" in res.missing_inputs
    assert "CUMULATIVE_WINDOWS_UNAVAILABLE" in res.reason_codes
    assert any("antecedent saturation is unobserved" in w for w in res.warnings)
    # Confidence is penalized for missing windows
    assert res.confidence < 1.0


# ==============================================================================
# 4. Deterministic Mock Adapter Tests
# ==============================================================================

def test_mock_adapter_valid_measured_zero_vs_missing_telemetry():
    """Test Case 11: Valid measured zero rainfall (0.0mm) is clearly distinguished from missing telemetry."""
    adapter = MockIMDRainfallAdapter()
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Query with no observations loaded -> missing data
    reading_missing = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading_missing.data_available is False
    assert reading_missing.value is None
    assert "NO_TELEMETRY_AVAILABLE" in reading_missing.quality_flags
    assert reading_missing.fallback_applied is False

    # 2. Query with valid measured zero observation loaded
    obs_zero = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK",
        station_id="SYNTH_HYD_01",
        station_name="Synthetic Hyderabad Central AWS",
        station_type=IMDStationType.AWS,
        latitude=17.3850,
        longitude=78.4867,
        observation_time_utc=t_now,
        ingestion_time_utc=t_now,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
        interval_rainfall_mm=0.0,
        is_valid=True,
    )
    adapter.load_observations("CORRIDOR-01", [obs_zero])

    reading_zero = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading_zero.data_available is True
    assert reading_zero.value is not None
    assert reading_zero.value["rainfall_1h_mm"] == 0.0
    assert "VALID_MEASURED_ZERO" in reading_zero.quality_flags


def test_mock_adapter_stale_observation():
    """Test Case 8: Observation older than 3 hours is flagged as stale."""
    adapter = MockIMDRainfallAdapter(stale_threshold_hours=3.0)
    t_obs = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)
    t_query = datetime(2026, 10, 26, 10, 30, 0, tzinfo=timezone.utc)  # 4.5h later

    obs = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK",
        station_id="SYNTH_HYD_01",
        station_name="Synthetic Hyderabad Central AWS",
        latitude=17.3850,
        longitude=78.4867,
        observation_time_utc=t_obs,
        ingestion_time_utc=t_obs,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION,
        interval_rainfall_mm=14.0,
        is_valid=True,
    )
    adapter.load_observations("CORRIDOR-01", [obs])

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_query)
    assert reading.is_stale is True
    assert reading.freshness_seconds == 4.5 * 3600.0
    assert "TELEMETRY_STALE" in reading.quality_flags


def test_mock_adapter_out_of_order_and_chronological_selection():
    """Test Case 9: Adapter sorts out-of-order records chronologically and picks the latest eligible reading."""
    adapter = MockIMDRainfallAdapter()
    t1 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Ingest in out-of-order sequence: t3, then t1, then t2
    obs3 = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t3, ingestion_time_utc=t3,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=30.0, is_valid=True,
    )
    obs1 = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t1, ingestion_time_utc=t1,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=10.0, is_valid=True,
    )
    obs2 = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t2, ingestion_time_utc=t2,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=20.0, is_valid=True,
    )
    adapter.load_observations("CORRIDOR-01", [obs3, obs1, obs2])

    # Query at 11:30 should get obs2 (20.0mm at 11:00)
    reading = adapter.fetch_latest("CORRIDOR-01", query_time=datetime(2026, 10, 26, 11, 30, 0, tzinfo=timezone.utc))
    assert reading.data_available is True
    assert reading.value["rainfall_1h_mm"] == 20.0


def test_mock_adapter_deduplicates_identical_records():
    """Test Case 10: Duplicate station/time records are deduplicated without double-counting."""
    adapter = MockIMDRainfallAdapter()
    t1 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)

    obs_first = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t1, ingestion_time_utc=t1,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=15.0, is_valid=True,
    )
    obs_duplicate = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t1, ingestion_time_utc=t1,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=15.0, is_valid=True,
    )
    adapter.load_observations("CORRIDOR-01", [obs_first, obs_duplicate])

    records = adapter._records_by_location["CORRIDOR-01"]
    assert len(records) == 1  # Deduplicated to exactly 1 record


def test_mock_adapter_outage_never_emits_dry_baseline():
    """Test Case 14: Mock provider outage must NEVER manufacture 0.0mm dry baseline fallback."""
    adapter = MockIMDRainfallAdapter()
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Load a record, then trigger simulated outage
    obs = IMDRainfallObservation(
        provider="MOCK_SYNTHETIC_BENCHMARK", station_id="S1", station_name="S1",
        latitude=17.385, longitude=78.486, observation_time_utc=t_now, ingestion_time_utc=t_now,
        measurement_mode=MeasurementMode.INTERVAL_ACCUMULATION, interval_rainfall_mm=15.0, is_valid=True,
    )
    adapter.load_observations("CORRIDOR-01", [obs])
    adapter.set_simulated_outage(True)

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading.data_available is False
    assert reading.value is None  # CRITICAL: not {"rainfall_1h_mm": 0.0}
    assert reading.fallback_applied is False
    assert "PROVIDER_OUTAGE_SIMULATED" in reading.quality_flags


# ==============================================================================
# 5. Cross-Phase Safety Integration Tests (Phase 12 Compatibility)
# ==============================================================================

def test_phase12_unknown_rainfall_preservation_in_decision_synthesis():
    """Test Case 15: Hardened rainfall result integrates with Phase 12 decision contracts safely."""
    # When rainfall engine produces UNKNOWN (e.g. from negative sensor glitch)
    rainfall_result = evaluate_rainfall_risk_engine(
        location_id="CORRIDOR-01",
        rain_1h_mm=-5.0,  # Negative input yields UNKNOWN
    )
    assert rainfall_result.risk_category == "UNKNOWN"

    decision_input = DecisionInput.from_rainfall_result(
        location_id="CORRIDOR-01",
        road_name="Test Corridor",
        rainfall_result=rainfall_result,
    )
    assert decision_input.rainfall_risk_category == "UNKNOWN"

    # Evaluate decision: UNKNOWN rainfall must require human verification and not clear route
    output = evaluate_decision(decision_input)
    assert output.requires_human_verification is True
    assert output.decision_status.value == "INSUFFICIENT_DATA"
    assert output.alert_level != AlertLevel.EMERGENCY  # Does not trigger emergency without vision evidence
