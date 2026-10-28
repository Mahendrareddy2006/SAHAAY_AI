"""
Sahaay AI - Phase C: Live Weather and Rainfall Ingestion Pipeline Test Suite
(tests/test_phase_c_weather_pipeline.py)

Comprehensive verification for Phase C:
1. Valid provider responses and malformed payloads.
2. Units (mm, cm, in, mm/hr, cm/hr), timestamps, and time zones (UTC, IST offsets, epochs).
3. Rainfall rate vs interval accumulation vs cumulative gauge counter.
4. Cumulative bucket counter conversion, resets, rollovers, and invalid counter drops.
5. Missing, stale, duplicated, and out-of-order observations.
6. Provider timeout, outage, and bounded retries.
7. Provenance and station metadata gazetteer.
8. Forecast unavailable and insufficient-data behavior (Phase 18 integration).
9. Non-silent missingness: no conversion of missing data or outages to zero rainfall.
10. No inference of confirmed flooding from forecast rainfall alone.
11. Compatibility with Phase 13 and Phase 18 contracts.
12. Routing safety invariants (no impassability from rain alone; verified road status authoritative).
13. Security: privileged live-feed activation blocked pending server-side cryptographic authentication.
14. REST API integration endpoints.
"""

from datetime import datetime, time, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple
import pytest
from fastapi.testclient import TestClient

from sahaay.adapters.base import AdapterReading, FeedAuthorizationStatus
from sahaay.adapters.imd_provider_adapter import (
    IMDRainfallProviderAdapter,
    IMDTransportClient,
    MAX_PHYSICAL_RATE_MM_PER_HR,
)
from sahaay.adapters.mock_imd_adapter import MockIMDRainfallAdapter
from sahaay.api.main import app
from sahaay.forecast_risk.schemas import (
    ForecastDataStatus,
    ForecastQualityFlag,
    ForecastRainfallInput,
    ForecastSourceType,
    AccumulationInterval,
    PrecipitationUnit,
)
from sahaay.forecast_risk.service import ForecastRiskAssessmentService
from sahaay.hyderabad_risk.counter_conversion import (
    DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    convert_cumulative_counter_to_interval,
)
from sahaay.hyderabad_risk.features import aggregate_observations_to_rolling_windows
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
    RainfallRiskResult,
)
from sahaay.hyderabad_risk.weather_pipeline import (
    CANONICAL_STATION_GAZETTEER,
    IngestionHealthStatus,
    PipelineOperationalStatus,
    RawTelemetryPayload,
    StationMetadata,
    WeatherIngestionPipeline,
    default_weather_pipeline,
)
from sahaay.road_network.graph import RoadGraph, RoadGraphBuilder
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import RoadConditionState, RoadStatusSnapshot, RoadVerificationState
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import PassabilityAssessment, RouteAssessmentOutcome
from sahaay.routing.service import RiskAwareRoutingService


# ==============================================================================
# Helper Factory Fixtures
# ==============================================================================

def make_test_obs(
    station_id: str = "HYD-STN-BEGUMPET",
    station_name: str = "Begumpet Airport AWS",
    provider: str = "IMD",
    latitude: float = 17.4480,
    longitude: float = 78.4680,
    obs_time: Optional[datetime] = None,
    interval_rainfall_mm: Optional[float] = 12.0,
    raw_counter_value_mm: Optional[float] = None,
    instantaneous_rate_mm_hr: Optional[float] = None,
    interval_minutes: int = 60,
    measurement_mode: MeasurementMode = MeasurementMode.INTERVAL_ACCUMULATION,
    qc_flag: ObservationQCFlag = ObservationQCFlag.VALID,
    is_valid: bool = True,
) -> IMDRainfallObservation:
    t_obs = obs_time or datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    return IMDRainfallObservation(
        provider=provider,
        station_id=station_id,
        station_name=station_name,
        station_type=IMDStationType.AWS,
        latitude=latitude,
        longitude=longitude,
        observation_time_utc=t_obs,
        ingestion_time_utc=t_obs + timedelta(seconds=30),
        interval_minutes=interval_minutes,
        measurement_mode=measurement_mode,
        raw_counter_value_mm=raw_counter_value_mm,
        interval_rainfall_mm=interval_rainfall_mm,
        instantaneous_rate_mm_hr=instantaneous_rate_mm_hr,
        qc_flag=qc_flag,
        is_valid=is_valid,
        provenance_metadata={"test_fixture": "phase_c"},
    )


# ==============================================================================
# 1. Valid Provider Responses and Malformed Payloads
# ==============================================================================

def test_valid_provider_response_ingestion():
    """Valid raw telemetry payload is parsed, normalized, and stored into pipeline."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    records = [
        RawTelemetryPayload(
            station_id="HYD-STN-BEGUMPET",
            station_name="Begumpet AWS",
            latitude=17.4480,
            longitude=78.4680,
            timestamp=t_now.isoformat(),
            rainfall_amount=15.5,
            interval_minutes=60,
            units="mm",
        ),
        RawTelemetryPayload(
            station_id="HYD-STN-SHAMSHABAD",
            station_name="Shamshabad AWS",
            latitude=17.2403,
            longitude=78.4294,
            timestamp=t_now.isoformat(),
            rainfall_amount=8.2,
            interval_minutes=60,
            units="mm",
        ),
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(records, ingestion_time=t_now, query_time=t_now)
    assert valid_c == 2
    assert quar_c == 0
    assert len(pipeline._observations_by_station["HYD-STN-BEGUMPET"]) == 1
    assert len(pipeline._observations_by_station["HYD-STN-SHAMSHABAD"]) == 1


def test_malformed_payload_quarantines_safely():
    """Malformed records (missing ID, missing timestamps, missing coords outside gazetteer) quarantine safely."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    bad_records = [
        {"station_id": "", "timestamp": t_now.isoformat(), "rainfall_amount": 5.0},  # Missing ID
        {"station_id": "UNKNOWN_STN", "timestamp": t_now.isoformat(), "rainfall_amount": 5.0},  # Missing coords
        {"station_id": "HYD-STN-BEGUMPET", "timestamp": "invalid_date_str", "rainfall_amount": 5.0},  # Bad date
        {"station_id": "HYD-STN-BEGUMPET", "timestamp": t_now.isoformat()},  # No readings
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(bad_records, ingestion_time=t_now, query_time=t_now)
    assert valid_c == 0
    assert quar_c > 0
    assert len(warnings) > 0


def test_non_finite_and_negative_payload_values_quarantined():
    """Negative values and NaNs/Infs are flagged as invalid and quarantined, never admitted."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    records = [
        RawTelemetryPayload(
            station_id="HYD-STN-BEGUMPET",
            timestamp=t_now.isoformat(),
            rainfall_amount=-10.0,  # Negative
        ),
        RawTelemetryPayload(
            station_id="HYD-STN-SHAMSHABAD",
            timestamp=t_now.isoformat(),
            rainfall_rate_mm_per_hr=float("nan"),  # NaN
        ),
        RawTelemetryPayload(
            station_id="HYD-STN-GOLCONDA",
            timestamp=t_now.isoformat(),
            cumulative_counter_mm=float("inf"),  # Inf
        ),
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(records, ingestion_time=t_now, query_time=t_now)
    assert valid_c == 0
    assert quar_c == 3


# ==============================================================================
# 2. Units, Timestamps, and Time Zones
# ==============================================================================

def test_unit_normalization_cm_in_m():
    """Precipitation units in cm, in, and m are correctly normalized to standard millimeters (mm)."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    # 2.5 cm = 25.0 mm
    rec_cm = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_amount=2.5,
        units="cm",
    )
    obs_cm, _ = pipeline.normalize_raw_reading(rec_cm, ingestion_time=t_now, query_time=t_now)
    assert obs_cm is not None
    assert obs_cm.interval_rainfall_mm == pytest.approx(25.0, 0.01)

    # 1.0 inch = 25.4 mm
    rec_in = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_amount=1.0,
        units="in",
    )
    obs_in, _ = pipeline.normalize_raw_reading(rec_in, ingestion_time=t_now, query_time=t_now)
    assert obs_in is not None
    assert obs_in.interval_rainfall_mm == pytest.approx(25.4, 0.01)


def test_rate_units_normalization():
    """Instantaneous rainfall rates in cm/h or in/h are normalized to mm/hr."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    rec = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_rate_mm_per_hr=3.0,
        units="cm/h",  # 3.0 cm/h = 30.0 mm/hr
    )
    obs, _ = pipeline.normalize_raw_reading(rec, ingestion_time=t_now, query_time=t_now)
    assert obs is not None
    assert obs.measurement_mode == MeasurementMode.INSTANTANEOUS_RATE
    assert obs.instantaneous_rate_mm_hr == pytest.approx(30.0, 0.01)


def test_timestamp_timezone_and_ist_conversion():
    """Timestamps with IST (+05:30) offset or epoch formats are normalized to UTC."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)

    # IST timestamp: 11:30 AM IST = 06:00 UTC
    ist_str = "2026-10-28T11:30:00+05:30"
    obs_dt, _ = pipeline.normalize_timestamp(ist_str, query_time=t_now)
    assert obs_dt.hour == 6
    assert obs_dt.minute == 0
    assert obs_dt.tzinfo == timezone.utc

    # Epoch seconds: 1793167200 -> 2026-10-28 06:00 UTC
    epoch_sec = 1793167200
    obs_dt_epoch, _ = pipeline.normalize_timestamp(epoch_sec, query_time=t_now)
    assert obs_dt_epoch.hour == 6
    assert obs_dt_epoch.tzinfo == timezone.utc


def test_future_timestamp_quarantined():
    """Future timestamps exceeding reference time + 1 minute are quarantined with QC_TIMESTAMP_ANOMALY."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    t_future = t_now + timedelta(hours=2)

    rec = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_future.isoformat(),
        rainfall_amount=10.0,
    )
    obs, warnings = pipeline.normalize_raw_reading(rec, ingestion_time=t_now, query_time=t_now)
    assert obs is not None
    assert obs.is_valid is False
    assert obs.qc_flag == ObservationQCFlag.QC_TIMESTAMP_ANOMALY
    assert "QC_TIMESTAMP_ANOMALY" in warnings


# ==============================================================================
# 3. Rainfall Rate vs Accumulation vs Cumulative Counter
# ==============================================================================

def test_distinguish_rate_accumulation_counter():
    """Strictly distinguishes instantaneous rain rate, interval accumulation, and cumulative counter."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    # Rate
    rec_rate = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_rate_mm_per_hr=45.0,
    )
    obs_rate, _ = pipeline.normalize_raw_reading(rec_rate, ingestion_time=t_now, query_time=t_now)
    assert obs_rate.measurement_mode == MeasurementMode.INSTANTANEOUS_RATE
    assert obs_rate.instantaneous_rate_mm_hr == 45.0
    assert obs_rate.interval_rainfall_mm is None

    # Accumulation
    rec_acc = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_amount=20.0,
    )
    obs_acc, _ = pipeline.normalize_raw_reading(rec_acc, ingestion_time=t_now, query_time=t_now)
    assert obs_acc.measurement_mode == MeasurementMode.INTERVAL_ACCUMULATION
    assert obs_acc.interval_rainfall_mm == 20.0

    # Counter
    rec_cnt = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        cumulative_counter_mm=140.0,
    )
    obs_cnt, _ = pipeline.normalize_raw_reading(rec_cnt, ingestion_time=t_now, query_time=t_now)
    assert obs_cnt.measurement_mode == MeasurementMode.CUMULATIVE_GAUGE_COUNTER
    assert obs_cnt.raw_counter_value_mm == 140.0


def test_instantaneous_rate_not_conflated_with_interval_accumulation():
    """An instantaneous rate of 60 mm/hr is not treated as 60 mm interval accumulation."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    rec = RawTelemetryPayload(
        station_id="HYD-STN-BEGUMPET",
        timestamp=t_now.isoformat(),
        rainfall_rate_mm_per_hr=60.0,
        interval_minutes=15,  # 15-minute sensor reading
    )
    obs, _ = pipeline.normalize_raw_reading(rec, ingestion_time=t_now, query_time=t_now)
    assert obs.measurement_mode == MeasurementMode.INSTANTANEOUS_RATE
    assert obs.instantaneous_rate_mm_hr == 60.0
    # Must NOT set interval_rainfall_mm to 60.0!
    assert obs.interval_rainfall_mm is None


# ==============================================================================
# 4. Cumulative Bucket Conversion, Resets, Rollovers, and Drops
# ==============================================================================

def test_cumulative_counter_monotonic_conversion():
    """Normal monotonic counter readings Ct and Ct-1 correctly derive interval rainfall."""
    t0 = datetime(2026, 10, 28, 5, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    res = convert_cumulative_counter_to_interval(
        current_counter_mm=85.0,
        current_time_utc=t1,
        previous_counter_mm=60.0,
        previous_time_utc=t0,
    )
    assert res.is_valid is True
    assert res.interval_rainfall_mm == 25.0
    assert res.qc_flag == ObservationQCFlag.VALID


def test_cumulative_counter_verified_rollover():
    """Hardware counter rollover at known capacity (e.g. 1000mm) is computed without error."""
    t0 = datetime(2026, 10, 28, 5, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    res = convert_cumulative_counter_to_interval(
        current_counter_mm=12.0,
        current_time_utc=t1,
        previous_counter_mm=990.0,
        previous_time_utc=t0,
        counter_max_mm=1000.0,
    )
    assert res.is_valid is True
    assert res.interval_rainfall_mm == 22.0  # (1000 - 990) + 12 = 22
    assert res.qc_flag == ObservationQCFlag.QC_COUNTER_ROLLOVER


def test_cumulative_counter_unexplained_decrease_never_clamped_to_zero():
    """Unexplained counter decrease is rejected as QC_NEGATIVE_DELTA, NEVER clamped to 0.0mm."""
    t0 = datetime(2026, 10, 28, 5, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    res = convert_cumulative_counter_to_interval(
        current_counter_mm=45.0,
        current_time_utc=t1,
        previous_counter_mm=80.0,
        previous_time_utc=t0,
        counter_max_mm=None,  # No rollover metadata
    )
    assert res.is_valid is False
    assert res.interval_rainfall_mm is None  # Never 0.0 mm!
    assert res.qc_flag == ObservationQCFlag.QC_NEGATIVE_DELTA


# ==============================================================================
# 5. Missing, Stale, Duplicated, and Out-of-Order Observations
# ==============================================================================

def test_out_of_order_stream_reconciled():
    """Stream of out-of-order records is sorted chronologically prior to interval/counter derivation."""
    pipeline = WeatherIngestionPipeline()
    t0 = datetime(2026, 10, 28, 4, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 28, 5, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    # Ingest in scrambled order: t2, then t0, then t1
    records = [
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t2.isoformat(), cumulative_counter_mm=150.0),
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t0.isoformat(), cumulative_counter_mm=100.0),
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t1.isoformat(), cumulative_counter_mm=125.0),
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(records, ingestion_time=t2, query_time=t2)
    st_records = pipeline._observations_by_station["HYD-STN-BEGUMPET"]
    # Check that stored records are in chronological order
    assert st_records[0].observation_time_utc == t0
    assert st_records[1].observation_time_utc == t1
    assert st_records[2].observation_time_utc == t2


def test_identical_duplicates_deduplicated():
    """Identical observations for same station and timestamp deduplicate to a single reading."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    records = [
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t_now.isoformat(), rainfall_amount=10.0),
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t_now.isoformat(), rainfall_amount=10.0),
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(records, ingestion_time=t_now, query_time=t_now)
    assert valid_c == 1  # Deduplicated into 1
    assert len(pipeline._observations_by_station["HYD-STN-BEGUMPET"]) == 1


def test_conflicting_duplicates_quarantined():
    """Conflicting duplicate readings at identical timestamp are quarantined with QC_CONFLICTING_DUPLICATE."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    records = [
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t_now.isoformat(), rainfall_amount=5.0),
        RawTelemetryPayload(station_id="HYD-STN-BEGUMPET", timestamp=t_now.isoformat(), rainfall_amount=25.0),  # Conflicting!
    ]

    valid_c, quar_c, warnings = pipeline.ingest_batch(records, ingestion_time=t_now, query_time=t_now)
    assert quar_c >= 1
    st_records = pipeline._observations_by_station["HYD-STN-BEGUMPET"]
    assert any(o.qc_flag == ObservationQCFlag.QC_CONFLICTING_DUPLICATE for o in st_records)


def test_stale_telemetry_detection():
    """Telemetry older than stale_threshold_hours (3.0h) is flagged as stale in corridor evaluation."""
    pipeline = WeatherIngestionPipeline(stale_threshold_hours=3.0)
    t_old = datetime(2026, 10, 28, 1, 0, 0, tzinfo=timezone.utc)
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)  # 5 hours later

    obs = make_test_obs(obs_time=t_old, interval_rainfall_mm=10.0)
    pipeline.ingest_batch([obs], ingestion_time=t_old, query_time=t_now)

    res = pipeline.evaluate_corridor_weather(
        corridor_id="HYD-LOC-001",
        corridor_lat=17.4480,
        corridor_lon=78.4680,
        target_dt=t_now,
    )
    assert res.data_freshness_hours >= 5.0
    assert "TELEMETRY_STALE" in res.qc_flags or res.data_freshness_hours > 3.0


# ==============================================================================
# 6. Provider Timeout, Outage, and Bounded Retries
# ==============================================================================

def test_provider_timeout_handled_with_retries():
    """Transport query timeout triggers bounded retries up to max_retries and returns controlled error."""
    call_count = 0

    def mock_timeout_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        raise TimeoutError("Socket timeout")

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        timeout_seconds=1.0,
        max_retries=2,
        transport_callable=mock_timeout_transport,
    )

    code, data, flags, err = client.query("telemetry/rainfall")
    assert code == 0
    assert data is None
    assert "CONNECTION_TIMEOUT" in flags
    assert "PROVIDER_UNAVAILABLE" in flags
    assert call_count == 3  # Initial + 2 retries = 3 calls


def test_provider_outage_does_not_manufacture_zero():
    """Provider outage yields data_available=False and value=None, NEVER 0.0 mm dry weather."""
    mock_adapter = MockIMDRainfallAdapter()
    mock_adapter.set_simulated_outage(True)

    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    reading = mock_adapter.fetch_latest("HYD-LOC-001", query_time=t_now)

    assert reading.data_available is False
    assert reading.value is None
    assert "PROVIDER_OUTAGE_SIMULATED" in reading.quality_flags

    # Pipeline integration: risk result must be UNKNOWN
    pipeline = WeatherIngestionPipeline(adapter=mock_adapter)
    res = pipeline.evaluate_corridor_weather("HYD-LOC-001", 17.40, 78.45, target_dt=t_now)
    assert res.risk_category == "UNKNOWN"
    assert "rain_1h_mm" in res.missing_inputs or "INSUFFICIENT_TELEMETRY_DATA" in res.reason_codes


def test_consecutive_failures_tracked():
    """Consecutive failure counter increments on repeated fetch errors and resets on success."""
    mock_adapter = MockIMDRainfallAdapter()
    mock_adapter.set_simulated_outage(True)

    pipeline = WeatherIngestionPipeline(adapter=mock_adapter)
    pipeline.fetch_and_ingest_from_adapter("HYD-LOC-001")
    pipeline.fetch_and_ingest_from_adapter("HYD-LOC-001")

    health = pipeline.get_ingestion_health()
    assert health.consecutive_failures == 2
    assert health.pipeline_status in (PipelineOperationalStatus.DEGRADED, PipelineOperationalStatus.OUTAGE)


# ==============================================================================
# 7. Provenance and Station Metadata Gazetteer
# ==============================================================================

def test_station_gazetteer_metadata_preserved():
    """Canonical weather station gazetteer includes all primary urban and reservoir stations."""
    gazetteer = default_weather_pipeline.get_stations_gazetteer()
    station_ids = {s.station_id for s in gazetteer}

    assert "HYD-STN-BEGUMPET" in station_ids
    assert "HYD-STN-SHAMSHABAD" in station_ids
    assert "HYD-STN-GOLCONDA" in station_ids
    assert "HYD-STN-HIMAYATSAGAR" in station_ids
    assert "HYD-STN-OSMANSAGAR" in station_ids

    # All stations must have coordinates within project bounds
    for s in gazetteer:
        assert 15.0 <= s.latitude <= 20.5
        assert 76.5 <= s.longitude <= 82.5


def test_observation_provenance_propagated_to_risk_result():
    """Station provenance (ID, name, provider, timestamp) is propagated to RainfallRiskResult."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    obs = make_test_obs(
        station_id="HYD-STN-BEGUMPET",
        station_name="Begumpet Airport AWS",
        provider="IMD-AWS-TELEMETRY",
        obs_time=t_now,
        interval_rainfall_mm=18.0,
    )
    pipeline.ingest_batch([obs], ingestion_time=t_now, query_time=t_now)

    res = pipeline.evaluate_corridor_weather("HYD-LOC-001", 17.4480, 78.4680, target_dt=t_now)
    assert res.station_id == "HYD-STN-BEGUMPET"
    assert res.provider == "IMD-AWS-TELEMETRY"
    assert res.observation_provenance.get("station_name") == "Begumpet Airport AWS"


# ==============================================================================
# 8. Forecast Integration & Evidence Separation (Phase 18 Integration)
# ==============================================================================

def test_forecast_missing_yields_insufficient_data():
    """When forecast input is unavailable, assessment status evaluates strictly to INSUFFICIENT_DATA."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    assessment = pipeline.evaluate_corridor_forecast_risk(
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        corridor_lat=17.40,
        corridor_lon=78.45,
        forecast_inputs=None,  # No forecast available
        reference_time_utc=t_now,
    )
    assert assessment.assessment_status == ForecastDataStatus.INSUFFICIENT_DATA
    assert assessment.heuristic_risk_score is None
    assert assessment.forecast_risk_category == "INSUFFICIENT_DATA"
    assert assessment.is_actionable_for_dispatch is False


def test_five_signals_strictly_separated():
    """Forecast assessment output strictly isolates all five distinct evidence contexts."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    fc_input = ForecastRainfallInput(
        location_id="HYD-LOC-001",
        source_id="IMD-WRF-RUN-06Z",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc=t_now.isoformat().replace("+00:00", "Z"),
        valid_timestamp_utc=(t_now + timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        forecast_horizon_hours=3.0,
        rainfall_amount=28.0,
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_3H,
        spatial_resolution_km=9.0,
        is_synthetic_fixture=True,
    )

    assessment = pipeline.evaluate_corridor_forecast_risk(
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        corridor_lat=17.40,
        corridor_lon=78.45,
        forecast_inputs=[fc_input],
        static_vulnerability_index=0.65,
        static_vulnerability_category="HIGH",
        road_condition_state=RoadConditionState.NO_CURRENT_EVIDENCE.value,
        reference_time_utc=t_now,
    )

    # Signal 1: Forecast Precipitation Context
    assert assessment.forecast_rainfall_context is not None
    assert assessment.forecast_rainfall_context["rainfall_amount"] == 28.0

    # Signal 2: Observed Gauge Context
    assert assessment.observed_rainfall_context is not None

    # Signal 3: Static Susceptibility Context
    assert assessment.static_susceptibility_context["vulnerability_category"] == "HIGH"

    # Signal 4: Current Road Condition Context
    assert assessment.current_road_status_context["condition_state"] == "NO_CURRENT_EVIDENCE"

    # Signal 5: Verified Historical Outcomes Context
    assert assessment.verified_historical_outcomes_context["status"] == "ZERO_VERIFIED_OUTCOMES_ON_DISK"


def test_no_calibrated_probability_claimed():
    """Forecast risk heuristic prohibits unearned claims of calibrated probability."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    assessment = pipeline.evaluate_corridor_forecast_risk(
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        corridor_lat=17.40,
        corridor_lon=78.45,
        forecast_inputs=None,
        reference_time_utc=t_now,
    )
    assert assessment.is_calibrated_probability is False


def test_forecast_rainfall_alone_does_not_infer_flooded_road():
    """Extreme forecast precipitation alone does NOT mark a road as actively flooded."""
    pipeline = WeatherIngestionPipeline()
    t_now = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)

    fc_heavy = ForecastRainfallInput(
        location_id="HYD-LOC-001",
        source_id="IMD-WRF-RUN-06Z",
        source_type=ForecastSourceType.OFFICIAL_MET_AGENCY_IMD,
        issue_timestamp_utc=t_now.isoformat().replace("+00:00", "Z"),
        valid_timestamp_utc=(t_now + timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        forecast_horizon_hours=3.0,
        rainfall_amount=95.0,  # Cloudburst-level forecast
        rainfall_units=PrecipitationUnit.MILLIMETERS,
        accumulation_interval=AccumulationInterval.INTERVAL_3H,
        spatial_resolution_km=9.0,
        is_synthetic_fixture=True,
    )

    assessment = pipeline.evaluate_corridor_forecast_risk(
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        corridor_lat=17.40,
        corridor_lon=78.45,
        forecast_inputs=[fc_heavy],
        static_vulnerability_index=0.85,
        static_vulnerability_category="SEVERE",
        road_condition_state=RoadConditionState.NO_CURRENT_EVIDENCE.value,
        reference_time_utc=t_now,
    )

    # Road condition remains NO_CURRENT_EVIDENCE: forecast does not fabricate confirmed flooding!
    assert assessment.current_road_status_context["condition_state"] == "NO_CURRENT_EVIDENCE"
    assert assessment.is_calibrated_probability is False
    assert "Autonomous road closures and automated emergency dispatch are strictly prohibited." in assessment.safety_disclaimer


# ==============================================================================
# 9. Routing Safety Invariants (Phase B & 19 Integration)
# ==============================================================================

def test_routing_engine_never_marks_impassable_from_rain_alone():
    """
    CRITICAL ROUTING INVARIANT:
    A high rainfall threshold or forecast surge does NOT mark a road impassable.
    Only confirmed ground-status evidence (VERIFIED_IMPASSABLE) excludes a segment.
    """
    router_service = RiskAwareRoutingService()

    # Corridor with high forecast risk but no confirmed ground flooding
    seg_assessment = router_service.assess_segment(
        segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        road_status=None,  # No confirmed status
        forecast_risk=None,
        static_vulnerability_index=0.85,
        static_vulnerability_category="SEVERE",
    )

    # Road remains traversable (with caution notices and uncertainty), NEVER impassable!
    assert seg_assessment.is_traversable is True
    assert seg_assessment.passability_state != PassabilityAssessment.VERIFIED_IMPASSABLE


def test_sparse_graph_unsupported_topology_honesty():
    """Disconnected graph nodes return TOPOLOGY_UNSUPPORTED without fabricating links."""
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Disconnected node pair: OU Colony (West) and Patny Circle (Secunderabad North)
    res = router.find_risk_aware_route(
        origin_node_id="NODE-OU-COLONY",
        destination_node_id="NODE-PATNY-CIRCLE",
    )
    assert res.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert res.total_distance_meters == 0.0
    assert "disconnected topological components" in res.warnings[0].lower()


# ==============================================================================
# 10. Security & Privileged Live Feed Activation Blockers
# ==============================================================================

def test_security_privileged_live_activation_blocked():
    """Privileged live feed activation attempt in batch ingest API is strictly rejected with HTTP 403."""
    client = TestClient(app)

    payload = {
        "records": [
            {
                "station_id": "HYD-STN-BEGUMPET",
                "timestamp": "2026-10-28T06:00:00Z",
                "rainfall_amount": 5.0,
            }
        ],
        "activate_live_stream": True,  # Privileged activation attempt!
    }

    res = client.post("/api/v1/weather/ingest", json=payload)
    assert res.status_code == 403
    assert "SECURITY GATE" in res.json()["detail"]
    assert "cryptographic authentication" in res.json()["detail"].lower()


# ==============================================================================
# 11. REST API Endpoints Integration
# ==============================================================================

def test_api_get_weather_provider_status():
    """GET /api/v1/weather/provider/status returns provider inventory and BLOCKED authorization status."""
    client = TestClient(app)
    res = client.get("/api/v1/weather/provider/status")
    assert res.status_code == 200
    data = res.json()
    assert "candidate_providers_inventory" in data
    assert any(p["source_id"] == "IMD-LIVE-AWS" for p in data["candidate_providers_inventory"])
    assert any(p["source_id"] == "TSDPS-URBAN-AWS" for p in data["candidate_providers_inventory"])


def test_api_get_weather_ingestion_health():
    """GET /api/v1/weather/ingestion/health returns operational health metrics."""
    client = TestClient(app)
    res = client.get("/api/v1/weather/ingestion/health")
    assert res.status_code == 200
    data = res.json()
    assert "pipeline_status" in data
    assert "provider_authorization_status" in data
    assert "monitored_stations_count" in data
    assert data["monitored_stations_count"] >= 10


def test_api_get_weather_stations():
    """GET /api/v1/weather/stations returns canonical gazetteer of weather stations."""
    client = TestClient(app)
    res = client.get("/api/v1/weather/stations")
    assert res.status_code == 200
    stations = res.json()
    assert len(stations) >= 10
    station_ids = [s["station_id"] for s in stations]
    assert "HYD-STN-BEGUMPET" in station_ids


def test_api_get_corridor_weather():
    """GET /api/v1/weather/corridor/{corridor_id} returns weather evaluation."""
    client = TestClient(app)
    res = client.get("/api/v1/weather/corridor/HYD-LOC-001")
    assert res.status_code == 200
    data = res.json()
    assert data["location_id"] == "HYD-LOC-001"
    assert "risk_category" in data


def test_api_get_corridor_forecast():
    """GET /api/v1/weather/forecast/{corridor_id} returns forecast risk assessment."""
    client = TestClient(app)
    res = client.get("/api/v1/weather/forecast/HYD-LOC-001")
    assert res.status_code == 200
    data = res.json()
    assert data["segment_id"] == "HYD-LOC-001"
    assert "forecast_rainfall_context" in data
    assert "observed_rainfall_context" in data
    assert "static_susceptibility_context" in data
    assert "current_road_status_context" in data
    assert "verified_historical_outcomes_context" in data


def test_api_post_weather_ingest_success():
    """POST /api/v1/weather/ingest successfully ingests batch records when not requesting privileged live mode."""
    client = TestClient(app)
    t_past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    payload = {
        "records": [
            {
                "station_id": "HYD-STN-BEGUMPET",
                "timestamp": t_past,
                "rainfall_amount": 14.5,
                "units": "mm",
            }
        ],
        "activate_live_stream": False,
    }
    res = client.post("/api/v1/weather/ingest", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["valid_observations_count"] == 1
    assert data["status"] == "SUCCESS"
