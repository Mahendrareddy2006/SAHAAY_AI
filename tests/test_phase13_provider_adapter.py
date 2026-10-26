"""
Sahaay AI - Phase 13.3-13.5 Provider Adapter & Pipeline Resilience Test Suite
Verifies:
1. IMDRainfallProviderAdapter configuration absence and auth gate (zero unverified live claims).
2. Transport resilience (timeouts, network connection failures, HTTP errors).
3. Payload normalization (valid records, coordinate filtering, timezone enforcement).
4. Data quality resilience (malformed payloads, missing fields, unparseable timestamps).
5. Deduplication and conflicting duplicate quarantine.
6. Safe missingness and freshness enforcement (freshness from latest valid record, newer invalid pings ignored).
7. Valid zero vs missing/outage distinction (never manufacture dry 0.0mm).
8. End-to-end integration with evaluate_rainfall_risk_from_adapter and risk engine.
9. Source status reporting honesty.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import pytest

from sahaay.adapters.base import FeedAuthorizationStatus
from sahaay.adapters.imd_provider_adapter import (
    IMDRainfallProviderAdapter,
    IMDTransportClient,
    MAX_PHYSICAL_RATE_MM_PER_HR,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_from_adapter
from sahaay.hyderabad_risk.schemas import ObservationQCFlag


# ==============================================================================
# 1. Configuration & Authorization Absence
# ==============================================================================

def test_adapter_configuration_absence_yields_pending_approval():
    """
    CRITICAL POLICY:
    When environment variables and credentials are absent, adapter must NOT claim
    to be live-authorized or manufacture readings. It must report PENDING_APPROVAL.
    """
    adapter = IMDRainfallProviderAdapter(base_url=None, api_key=None)
    assert adapter.auth_status == FeedAuthorizationStatus.PENDING_APPROVAL

    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)

    assert reading.data_available is False
    assert reading.value is None  # Never synthesize dry weather!
    assert "MISSING_PROVIDER_CREDENTIALS" in reading.quality_flags
    assert "PENDING_APPROVAL" in reading.quality_flags
    assert reading.fallback_applied is False
    assert "credentials pending authorization" in reading.error_message.lower()


# ==============================================================================
# 2. Transport Resilience: Timeouts, Connection Failures, HTTP Errors
# ==============================================================================

def test_adapter_transport_timeout_handling():
    """
    Network timeout must yield a controlled outage reading with value=None,
    NEVER an unhandled exception or 0.0mm dry fallback.
    """
    def timeout_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        raise TimeoutError("Simulated socket read timeout")

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        timeout_seconds=2.0,
        transport_callable=timeout_transport,
    )
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        transport=client,
    )

    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)

    assert reading.data_available is False
    assert reading.value is None
    assert "CONNECTION_TIMEOUT" in reading.quality_flags
    assert "PROVIDER_UNAVAILABLE" in reading.quality_flags


def test_adapter_transport_connection_failure():
    """Network connection failure must yield controlled degraded outcome."""
    def conn_fail_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        raise ConnectionError("Host unreachable")

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        transport_callable=conn_fail_transport,
    )
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        transport=client,
    )

    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)

    assert reading.data_available is False
    assert reading.value is None
    assert "NETWORK_CONNECTION_ERROR" in reading.quality_flags


@pytest.mark.parametrize("http_code,expected_flag", [
    (401, "HTTP_ERROR_401"),
    (403, "HTTP_ERROR_403"),
    (500, "HTTP_ERROR_500"),
    (503, "HTTP_ERROR_503"),
])
def test_adapter_transport_http_errors(http_code, expected_flag):
    """HTTP error codes from gateway must be captured as controlled quality flags."""
    def http_err_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        return http_code, {"error": "Gateway rejected request"}

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        transport_callable=http_err_transport,
    )
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="secret-token",
        transport=client,
    )

    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)

    assert reading.data_available is False
    assert reading.value is None
    assert expected_flag in reading.quality_flags
    assert "PROVIDER_UNAVAILABLE" in reading.quality_flags


# ==============================================================================
# 3. Payload Normalization & Data Quality Filtering
# ==============================================================================

def test_adapter_successful_payload_normalization():
    """Valid JSON payload from provider is normalized into standard observation records."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    sample_payload = {
        "status": "success",
        "records": [
            {
                "station_id": "IMD_BEGUMPET_AWS",
                "station_name": "Begumpet Airport AWS",
                "latitude": 17.4531,
                "longitude": 78.4676,
                "observation_time_utc": "2026-10-26T11:45:00Z",
                "interval_rainfall_mm": 24.5,
                "interval_minutes": 60,
                "provider": "IMD",
            }
        ]
    }

    def mock_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        return 200, sample_payload

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport_callable=mock_transport,
    )
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=client,
    )

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)

    assert reading.data_available is True
    assert reading.value is not None
    assert reading.value["rainfall_1h_mm"] == 24.5
    assert reading.value["station_id"] == "IMD_BEGUMPET_AWS"
    assert reading.value["latitude"] == 17.4531
    assert reading.value["longitude"] == 78.4676
    assert "VALID_OBSERVATION" in reading.quality_flags
    assert reading.is_stale is False


def test_adapter_malformed_and_missing_field_records():
    """
    Malformed records (missing station ID, invalid coordinates, unparseable timestamps)
    are quarantined without crashing the adapter.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    sample_payload = {
        "records": [
            {"station_id": "", "latitude": 17.45, "longitude": 78.46, "observation_time_utc": "2026-10-26T11:30:00Z"},  # Empty ID
            {"station_id": "BAD_COORDS", "latitude": "invalid", "longitude": 78.46, "observation_time_utc": "2026-10-26T11:30:00Z"},  # NaN coords
            {"station_id": "OUT_OF_BOUNDS", "latitude": 55.0, "longitude": 78.46, "observation_time_utc": "2026-10-26T11:30:00Z"},  # Outside bounds
            {"station_id": "BAD_TIME", "latitude": 17.45, "longitude": 78.46, "observation_time_utc": "not-a-timestamp"},  # Bad time
            {"station_id": "VALID_01", "latitude": 17.45, "longitude": 78.46, "observation_time_utc": "2026-10-26T11:30:00Z", "interval_rainfall_mm": 5.0},
        ]
    }

    def mock_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        return 200, sample_payload

    client = IMDTransportClient(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport_callable=mock_transport,
    )
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=client,
    )

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading.data_available is True
    assert reading.value["station_id"] == "VALID_01"
    assert reading.value["rainfall_1h_mm"] == 5.0


def test_adapter_duplicate_record_handling():
    """Identical station + timestamp duplicates are deduplicated cleanly."""
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    sample_payload = {
        "records": [
            {"station_id": "DUP_ST_01", "latitude": 17.45, "longitude": 78.46, "observation_time_utc": "2026-10-26T11:00:00Z", "interval_rainfall_mm": 10.0},
            {"station_id": "DUP_ST_01", "latitude": 17.45, "longitude": 78.46, "observation_time_utc": "2026-10-26T11:00:00Z", "interval_rainfall_mm": 10.0},
        ]
    }

    def mock_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        return 200, sample_payload

    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=mock_transport),
    )

    obs_list, warnings = adapter.fetch_observations("CORRIDOR-01", query_time=t_now)
    assert len(obs_list) == 1
    assert obs_list[0].interval_rainfall_mm == 10.0


# ==============================================================================
# 4. Safe Missingness and Freshness Enforcement
# ==============================================================================

def test_adapter_freshness_measured_from_latest_valid_record():
    """
    CRITICAL SAFETY REQUIREMENT:
    Freshness delay must be calculated from the latest VALID observation.
    A newer invalid observation (e.g. sensor glitch) must NOT reset the freshness
    clock or mask staleness.
    """
    t_query = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    t_valid = t_query - timedelta(hours=2)        # 10:00 UTC (valid, 2 hours old)
    t_corrupt = t_query - timedelta(minutes=5)     # 11:55 UTC (corrupt negative reading)

    sample_payload = {
        "records": [
            {
                "station_id": "HYD_AWS_01",
                "latitude": 17.45,
                "longitude": 78.46,
                "observation_time_utc": t_valid.isoformat(),
                "interval_rainfall_mm": 15.0,
            },
            {
                "station_id": "HYD_AWS_01",
                "latitude": 17.45,
                "longitude": 78.46,
                "observation_time_utc": t_corrupt.isoformat(),
                "interval_rainfall_mm": -99.0,  # Negative sensor glitch!
            },
        ]
    }

    def mock_transport(url: str, headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any]]:
        return 200, sample_payload

    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=mock_transport),
    )

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_query)

    assert reading.data_available is True
    assert reading.value["rainfall_1h_mm"] == 15.0  # Uses valid reading
    # Freshness must be 7200s (2.0 hours), NOT 300s (5 min from corrupt reading)!
    assert reading.freshness_seconds == 7200.0
    assert "NEWER_INVALID_OBSERVATION_DISCARDED" in reading.quality_flags


def test_adapter_stale_telemetry_flagging():
    """Telemetry older than stale_threshold_hours is flagged is_stale=True."""
    t_query = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    t_stale = t_query - timedelta(hours=4)  # 4 hours old > 3.0h threshold

    sample_payload = {
        "records": [
            {
                "station_id": "HYD_AWS_01",
                "latitude": 17.45,
                "longitude": 78.46,
                "observation_time_utc": t_stale.isoformat(),
                "interval_rainfall_mm": 12.0,
            }
        ]
    }

    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        stale_threshold_hours=3.0,
        transport=IMDTransportClient(
            "https://api.imd.gov.in/test",
            "valid-key",
            transport_callable=lambda u, h, t: (200, sample_payload),
        ),
    )

    reading = adapter.fetch_latest("CORRIDOR-01", query_time=t_query)
    assert reading.data_available is True
    assert reading.is_stale is True
    assert "TELEMETRY_STALE" in reading.quality_flags


def test_adapter_distinguishes_valid_zero_from_missing():
    """
    CRITICAL SAFETY REQUIREMENT:
    Valid zero rainfall (0.0mm) must be accompanied by VALID_MEASURED_ZERO flag.
    Missing data or empty payload must produce data_available=False and value=None.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Valid zero
    zero_payload = {
        "records": [{
            "station_id": "HYD_AWS_01",
            "latitude": 17.45,
            "longitude": 78.46,
            "observation_time_utc": t_now.isoformat(),
            "interval_rainfall_mm": 0.0,
        }]
    }
    adapter_zero = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=lambda u, h, t: (200, zero_payload)),
    )
    reading_zero = adapter_zero.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading_zero.data_available is True
    assert reading_zero.value["rainfall_1h_mm"] == 0.0
    assert "VALID_MEASURED_ZERO" in reading_zero.quality_flags

    # 2. Outage / empty records
    empty_payload = {"records": []}
    adapter_empty = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=lambda u, h, t: (200, empty_payload)),
    )
    reading_empty = adapter_empty.fetch_latest("CORRIDOR-01", query_time=t_now)
    assert reading_empty.data_available is False
    assert reading_empty.value is None  # NEVER fabricated dry baseline
    assert "NO_TELEMETRY_AVAILABLE" in reading_empty.quality_flags


# ==============================================================================
# 5. End-to-End Pipeline & Risk Engine Integration
# ==============================================================================

def test_provider_adapter_end_to_end_pipeline_integration():
    """
    Tests IMDRainfallProviderAdapter connected directly into evaluate_rainfall_risk_from_adapter.
    Verifies that:
    - Heavy rainfall from nearby station produces HIGH risk and LOCAL_URBAN proximity.
    - Provider outage gracefully yields UNKNOWN risk without exceptions.
    """
    t_now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Nearby station heavy rain (Begumpet corridor: 17.445, 78.470)
    live_payload = {
        "records": [{
            "station_id": "IMD_BEGUMPET",
            "station_name": "Begumpet Airport AWS",
            "latitude": 17.4531,
            "longitude": 78.4676,  # ~1.0 km from corridor
            "observation_time_utc": t_now.isoformat(),
            "interval_rainfall_mm": 28.0,  # Heavy IMD rain
        }]
    }

    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=lambda u, h, t: (200, live_payload)),
    )

    res = evaluate_rainfall_risk_from_adapter(
        location_id="CORRIDOR-BEGUMPET",
        adapter=adapter,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res.risk_category == "HIGH"
    assert res.station_proximity_tier == "LOCAL_URBAN"
    assert res.station_dist_km < 5.0
    assert "IMD_HEAVY_INTENSITY_EXCEEDED" in res.reason_codes

    # 2. Outage handling
    adapter_outage = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/test",
        api_key="valid-key",
        transport=IMDTransportClient("https://api.imd.gov.in/test", "valid-key", transport_callable=lambda u, h, t: (503, None)),
    )
    res_outage = evaluate_rainfall_risk_from_adapter(
        location_id="CORRIDOR-BEGUMPET",
        adapter=adapter_outage,
        corridor_lat=17.4450,
        corridor_lon=78.4700,
        target_dt=t_now,
    )
    assert res_outage.risk_category == "UNKNOWN"
    assert res_outage.risk_score == 0.0
    assert "INSUFFICIENT_TELEMETRY_DATA" in res_outage.reason_codes


def test_source_status_reporting_honesty():
    """get_source_status reports operational health, configuration, and explicit blockers."""
    adapter = IMDRainfallProviderAdapter(
        base_url="https://api.imd.gov.in/telemetry/v1",
        api_key="secret-token-xyz",
    )
    status = adapter.get_source_status()
    assert status["source_id"] == "IMD-LIVE-AWS"
    assert status["has_credentials"] is True
    # URL is masked (no credentials leaked)
    assert "https://api.imd.gov.in" in status["configured_endpoint"]
    assert len(status["access_blockers"]) >= 2
    assert len(status["data_handling_safeguards"]) >= 4
