"""
Sahaay AI - IMD Live Weather Telemetry Provider Adapter
Boundary adapter connecting Sahaay AI to external India Meteorological Department (IMD)
and regional weather telemetry gateways.

Enforces zero-leakage credential management, strict network resilience (timeouts, retries,
outage handling), observation normalization, and safe missingness/freshness invariants.
"""

from datetime import datetime, timezone, timedelta
import json
import logging
import math
import os
import socket
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from sahaay.adapters.base import AdapterReading, BaseLiveAdapter, FeedAuthorizationStatus
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
)

logger = logging.getLogger(__name__)

# Regional geospatial coordinate bounds (Telangana & Greater Hyderabad)
TELANGANA_LAT_MIN = 15.0
TELANGANA_LAT_MAX = 20.5
TELANGANA_LON_MIN = 76.5
TELANGANA_LON_MAX = 82.5

# Physical rate limit (world record ~305 mm/hr, Shangdi 1975)
MAX_PHYSICAL_RATE_MM_PER_HR = 305.0


class IMDTransportClient:
    """
    Decoupled HTTP transport client for external weather telemetry providers.
    Supports dependency-free execution via urllib.request and injectable mock transports
    for deterministic unit testing.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 1,
        transport_callable: Optional[Callable[[str, Dict[str, str], float], Tuple[int, Dict[str, Any]]]] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self._transport_callable = transport_callable

    def query(
        self,
        endpoint_path: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]], List[str], Optional[str]]:
        """
        Executes an HTTP GET query against the provider gateway.
        Returns: (http_status_code, payload_dict, quality_flags, error_message)
        """
        if not self.base_url:
            return 0, None, ["MISSING_PROVIDER_ENDPOINT"], "Provider base URL is not configured."

        if not self.api_key:
            return 0, None, ["MISSING_PROVIDER_CREDENTIALS"], "Provider API credentials are not configured."

        query_params = dict(params or {})
        full_url = f"{self.base_url}/{endpoint_path.lstrip('/')}"
        if query_params:
            full_url = f"{full_url}?{urllib.parse.urlencode(query_params)}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "SahaayAI-TelemetryAdapter/1.0 (Public Safety Hydrological Ingestion)",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Use injected mock transport if provided
        if self._transport_callable is not None:
            attempts = 0
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    status_code, data = self._transport_callable(full_url, headers, self.timeout_seconds)
                    if status_code != 200:
                        q_flags = [f"HTTP_ERROR_{status_code}", "PROVIDER_UNAVAILABLE"]
                        if status_code in (401, 403):
                            q_flags.append("AUTHENTICATION_FAILED")
                        return status_code, None, q_flags, f"Provider HTTP error {status_code}"
                    return status_code, data, [], None
                except TimeoutError:
                    if attempts > self.max_retries:
                        return 0, None, ["CONNECTION_TIMEOUT", "PROVIDER_UNAVAILABLE"], f"Query to {self._mask_url(full_url)} timed out ({self.timeout_seconds}s)."
                except ConnectionError as e:
                    if attempts > self.max_retries:
                        return 0, None, ["NETWORK_CONNECTION_ERROR", "PROVIDER_UNAVAILABLE"], f"Connection failed: {str(e)}"
                except Exception as e:
                    if attempts > self.max_retries:
                        return 0, None, ["TRANSPORT_EXCEPTION", "PROVIDER_UNAVAILABLE"], f"Transport error: {str(e)}"

        # Default standard library urllib transport
        attempts = 0
        last_error = ""
        while attempts <= self.max_retries:
            attempts += 1
            try:
                req = urllib.request.Request(full_url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    status_code = resp.status
                    raw_bytes = resp.read()
                    try:
                        data = json.loads(raw_bytes.decode("utf-8"))
                        if not isinstance(data, dict) and not isinstance(data, list):
                            return status_code, None, ["MALFORMED_PROVIDER_PAYLOAD", "PROVIDER_UNAVAILABLE"], "Provider returned non-JSON-container payload."
                        if isinstance(data, list):
                            data = {"records": data}
                        return status_code, data, [], None
                    except json.JSONDecodeError as jde:
                        return status_code, None, ["MALFORMED_PROVIDER_PAYLOAD", "PROVIDER_UNAVAILABLE"], f"Failed to parse provider JSON: {str(jde)}"

            except urllib.error.HTTPError as he:
                status_code = he.code
                err_msg = f"Provider HTTP error {status_code}: {he.reason}"
                q_flags = [f"HTTP_ERROR_{status_code}", "PROVIDER_UNAVAILABLE"]
                if status_code in (401, 403):
                    q_flags.append("AUTHENTICATION_FAILED")
                return status_code, None, q_flags, err_msg

            except (urllib.error.URLError, socket.timeout, TimeoutError) as ue:
                reason = getattr(ue, "reason", str(ue))
                if isinstance(reason, socket.timeout) or "timed out" in str(reason).lower():
                    last_error = f"Connection timed out after {self.timeout_seconds}s."
                    if attempts > self.max_retries:
                        return 0, None, ["CONNECTION_TIMEOUT", "PROVIDER_UNAVAILABLE"], last_error
                else:
                    last_error = f"Network connection failed: {reason}"
                    if attempts > self.max_retries:
                        return 0, None, ["NETWORK_CONNECTION_ERROR", "PROVIDER_UNAVAILABLE"], last_error

            except Exception as e:
                last_error = f"Unexpected network failure: {str(e)}"
                if attempts > self.max_retries:
                    return 0, None, ["NETWORK_EXCEPTION", "PROVIDER_UNAVAILABLE"], last_error

        return 0, None, ["PROVIDER_UNAVAILABLE"], last_error

    @staticmethod
    def _mask_url(url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


class IMDRainfallProviderAdapter(BaseLiveAdapter):
    """
    Production-ready boundary adapter for IMD and state meteorological feeds.

    Operational Policy:
    1. Zero secret leakage: Credentials sourced strictly from environment variables.
    2. Zero synthetic zeros: Missingness and provider outages yield controlled UNKNOWN outcomes.
    3. Freshness integrity: Freshness computed exclusively from the latest valid observation.
    4. Boundary isolation: Network errors, timeouts, and malformed payloads never crash the pipeline.
    """

    def __init__(
        self,
        source_id: str = "IMD-LIVE-AWS",
        source_name: str = "India Meteorological Department (IMD) AWS Telemetry Feed",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        stale_threshold_hours: Optional[float] = None,
        transport: Optional[IMDTransportClient] = None,
    ):
        # Resolve configuration from explicit args or environment variables
        resolved_base_url = base_url or os.environ.get("SAHAAY_IMD_API_BASE_URL", "").strip()
        resolved_api_key = api_key or os.environ.get("SAHAAY_IMD_API_KEY") or os.environ.get("SAHAAY_IMD_AUTH_TOKEN")
        
        raw_timeout = timeout_seconds if timeout_seconds is not None else os.environ.get("SAHAAY_IMD_TIMEOUT_SECONDS", "5.0")
        try:
            resolved_timeout = float(raw_timeout)
        except (ValueError, TypeError):
            resolved_timeout = 5.0

        raw_stale = stale_threshold_hours if stale_threshold_hours is not None else os.environ.get("SAHAAY_IMD_STALE_THRESHOLD_HOURS", "3.0")
        try:
            resolved_stale = float(raw_stale)
        except (ValueError, TypeError):
            resolved_stale = 3.0

        has_creds = bool(resolved_base_url and resolved_api_key)
        auth_status = FeedAuthorizationStatus.AUTHORIZED_LIVE if has_creds else FeedAuthorizationStatus.PENDING_APPROVAL

        super().__init__(
            source_id=source_id,
            source_name=source_name,
            auth_status=auth_status,
        )

        self.base_url = resolved_base_url
        self.api_key = resolved_api_key
        self.timeout_seconds = resolved_timeout
        self.stale_threshold_seconds = resolved_stale * 3600.0

        self.transport = transport or IMDTransportClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
        )

        self._last_query_timestamp: Optional[str] = None
        self._last_fetch_successful: bool = False
        self._last_successful_retrieval_utc: Optional[str] = None
        self._consecutive_failures: int = 0
        self._last_error_message: Optional[str] = None

    def parse_provider_payload(
        self,
        payload: Any,
        ingestion_time: datetime,
        query_time: Optional[datetime] = None,
    ) -> Tuple[List[IMDRainfallObservation], List[str]]:
        """
        Normalizes arbitrary provider JSON payloads into validated IMDRainfallObservation records.
        Preserves strict QC flag attribution, bounds verification, and deduplication.
        """
        warnings: List[str] = []
        if not payload:
            return [], ["EMPTY_PAYLOAD"]

        raw_records = []
        if isinstance(payload, list):
            raw_records = payload
        elif isinstance(payload, dict):
            if "records" in payload and isinstance(payload["records"], list):
                raw_records = payload["records"]
            elif "observations" in payload and isinstance(payload["observations"], list):
                raw_records = payload["observations"]
            elif "data" in payload and isinstance(payload["data"], list):
                raw_records = payload["data"]
            else:
                # Single record container
                raw_records = [payload]
        else:
            return [], ["UNRECOGNIZED_PAYLOAD_STRUCTURE"]

        parsed_obs: List[IMDRainfallObservation] = []
        seen_keys: Dict[Tuple[str, str], IMDRainfallObservation] = {}

        for idx, rec in enumerate(raw_records):
            if not isinstance(rec, dict):
                warnings.append(f"Record #{idx} is not a dictionary; discarded.")
                continue

            station_id = str(rec.get("station_id") or rec.get("stationId") or rec.get("id") or "").strip()
            station_name = str(rec.get("station_name") or rec.get("stationName") or rec.get("name") or station_id or "IMD AWS").strip()
            provider_name = str(rec.get("provider") or "IMD").strip()

            if not station_id:
                warnings.append(f"Record #{idx} missing mandatory station_id; quarantined.")
                continue

            # Coordinates
            try:
                lat = float(rec.get("latitude") if rec.get("latitude") is not None else rec.get("lat"))
                lon = float(rec.get("longitude") if rec.get("longitude") is not None else rec.get("lon"))
            except (ValueError, TypeError):
                warnings.append(f"Station {station_id} missing valid numerical coordinates; quarantined.")
                continue

            # Coordinate bounds verification
            coords_valid = (TELANGANA_LAT_MIN <= lat <= TELANGANA_LAT_MAX) and (TELANGANA_LON_MIN <= lon <= TELANGANA_LON_MAX)
            if not coords_valid:
                warnings.append(f"Station {station_id} coordinates ({lat}, {lon}) outside regional project bounds; quarantined.")
                continue

            # Timestamp parsing
            raw_ts = rec.get("observation_time_utc") or rec.get("timestamp") or rec.get("time")
            if not raw_ts:
                warnings.append(f"Station {station_id} missing observation timestamp; quarantined.")
                continue

            obs_dt = None
            if isinstance(raw_ts, datetime):
                obs_dt = raw_ts if raw_ts.tzinfo is not None else raw_ts.replace(tzinfo=timezone.utc)
            elif isinstance(raw_ts, str):
                try:
                    clean_ts = raw_ts.replace("Z", "+00:00")
                    obs_dt = datetime.fromisoformat(clean_ts)
                    if obs_dt.tzinfo is None:
                        obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    warnings.append(f"Station {station_id} has unparseable timestamp '{raw_ts}'; quarantined.")
                    continue
            elif isinstance(raw_ts, (int, float)):
                try:
                    # Epoch seconds or milliseconds
                    ts_val = float(raw_ts)
                    if ts_val > 1e11:
                        ts_val /= 1000.0
                    obs_dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                except Exception:
                    warnings.append(f"Station {station_id} has invalid epoch timestamp '{raw_ts}'; quarantined.")
                    continue

            if obs_dt is None:
                continue

            # Future-timestamp quarantine
            now_boundary = (query_time or ingestion_time) + timedelta(minutes=1)
            is_future = obs_dt > now_boundary
            if is_future:
                warnings.append(f"Station {station_id} observation timestamp ({obs_dt.isoformat()}) is future-dated; quarantined.")
                qc_flag = ObservationQCFlag.QC_TIMESTAMP_ANOMALY
                is_valid = False
            else:
                qc_flag = ObservationQCFlag.VALID
                is_valid = True

            # Units conversion factor
            units_factor = 1.0
            raw_units = str(rec.get("units") or "mm").strip().lower()
            if raw_units in ("cm", "centimeters"):
                units_factor = 10.0
            elif raw_units in ("in", "inch", "inches"):
                units_factor = 25.4
            elif raw_units in ("m", "meter", "meters"):
                units_factor = 1000.0

            # Rainfall values
            interval_mm = rec.get("interval_rainfall_mm") if rec.get("interval_rainfall_mm") is not None else rec.get("rainfall_mm")
            raw_counter = rec.get("raw_counter_value_mm") if rec.get("raw_counter_value_mm") is not None else rec.get("cumulative_counter_mm")
            raw_rate = rec.get("rainfall_rate_mm_per_hr") if rec.get("rainfall_rate_mm_per_hr") is not None else (
                rec.get("rate_mm_h") if rec.get("rate_mm_h") is not None else rec.get("instantaneous_rate_mm_hr")
            )

            parsed_interval: Optional[float] = None
            if interval_mm is not None:
                try:
                    parsed_interval = float(interval_mm) * units_factor
                except (ValueError, TypeError):
                    parsed_interval = None

            parsed_counter: Optional[float] = None
            if raw_counter is not None:
                try:
                    parsed_counter = float(raw_counter) * units_factor
                except (ValueError, TypeError):
                    parsed_counter = None

            parsed_rate: Optional[float] = None
            if raw_rate is not None:
                try:
                    parsed_rate = float(raw_rate) * units_factor
                except (ValueError, TypeError):
                    parsed_rate = None

            # Physical validity checks
            if parsed_interval is not None:
                if math.isnan(parsed_interval) or math.isinf(parsed_interval) or parsed_interval < 0.0:
                    qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
                    is_valid = False
                    warnings.append(f"Station {station_id} has negative/non-finite rainfall ({parsed_interval} mm); flagged invalid.")
                    parsed_interval = None  # None to allow valid Pydantic model construction
                elif parsed_interval > MAX_PHYSICAL_RATE_MM_PER_HR:
                    qc_flag = ObservationQCFlag.QC_UNPHYSICAL_SPIKE
                    is_valid = False
                    warnings.append(f"Station {station_id} exceeds physical rainfall limit ({parsed_interval} mm); flagged invalid.")

            if parsed_rate is not None:
                if math.isnan(parsed_rate) or math.isinf(parsed_rate) or parsed_rate < 0.0:
                    qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
                    is_valid = False
                    warnings.append(f"Station {station_id} has negative/non-finite rate ({parsed_rate}); flagged invalid.")
                    parsed_rate = None
                elif parsed_rate > MAX_PHYSICAL_RATE_MM_PER_HR:
                    qc_flag = ObservationQCFlag.QC_UNPHYSICAL_SPIKE
                    is_valid = False
                    warnings.append(f"Station {station_id} exceeds physical rainfall limit ({parsed_rate} mm/h); flagged invalid.")

            if parsed_counter is not None:
                if math.isnan(parsed_counter) or math.isinf(parsed_counter) or parsed_counter < 0.0:
                    qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
                    is_valid = False
                    warnings.append(f"Station {station_id} has negative/non-finite counter ({parsed_counter} mm); flagged invalid.")
                    parsed_counter = None

            # Measurement mode
            mode = MeasurementMode.INTERVAL_ACCUMULATION
            if parsed_counter is not None and parsed_interval is None and parsed_rate is None:
                mode = MeasurementMode.CUMULATIVE_GAUGE_COUNTER
            elif parsed_rate is not None and parsed_interval is None and parsed_counter is None:
                mode = MeasurementMode.INSTANTANEOUS_RATE

            # Deduplication key: (station_id, observation_time_utc)
            dedup_key = (station_id, obs_dt.isoformat())
            if dedup_key in seen_keys:
                existing = seen_keys[dedup_key]
                # Check for conflicting duplicates
                if existing.interval_rainfall_mm != parsed_interval or existing.raw_counter_value_mm != parsed_counter:
                    existing.qc_flag = ObservationQCFlag.QC_CONFLICTING_DUPLICATE
                    existing.is_valid = False
                    warnings.append(f"Conflicting duplicate reading for {station_id} at {obs_dt.isoformat()}; quarantined.")
                continue

            try:
                obs = IMDRainfallObservation(
                    provider=provider_name,
                    station_id=station_id,
                    station_name=station_name,
                    station_type=IMDStationType.AWS,
                    latitude=lat,
                    longitude=lon,
                    observation_time_utc=obs_dt,
                    ingestion_time_utc=ingestion_time,
                    interval_minutes=int(rec.get("interval_minutes", 60)),
                    measurement_mode=mode,
                    raw_counter_value_mm=parsed_counter,
                    interval_rainfall_mm=parsed_interval,
                    instantaneous_rate_mm_hr=parsed_rate,
                    qc_flag=qc_flag,
                    is_valid=is_valid,
                    provenance_metadata=rec.get("metadata", {}),
                )
                seen_keys[dedup_key] = obs
                parsed_obs.append(obs)
            except Exception as e:
                warnings.append(f"Validation error creating observation for {station_id}: {str(e)}")

        return parsed_obs, warnings

    def fetch_observations(
        self,
        location_id: str,
        query_time: Optional[datetime] = None,
    ) -> Tuple[List[IMDRainfallObservation], List[str]]:
        """
        Fetches and normalizes a sequence of IMDRainfallObservation records from the provider gateway.
        Returns: (observations_list, warning_messages)
        """
        now_dt = datetime.now(timezone.utc)
        if query_time is None:
            query_time = now_dt
        elif query_time.tzinfo is None:
            query_time = query_time.replace(tzinfo=timezone.utc)

        self._last_query_timestamp = now_dt.isoformat().replace("+00:00", "Z")

        # Query transport
        params = {"location_id": location_id, "query_time": query_time.isoformat()}
        code, data, flags, err = self.transport.query(endpoint_path="telemetry/rainfall", params=params)

        if code != 200 or data is None:
            self._last_fetch_successful = False
            self._consecutive_failures += 1
            self._last_error_message = err or f"HTTP error {code}"
            return [], flags + ([err] if err else [])

        self._last_fetch_successful = True
        self._last_successful_retrieval_utc = now_dt.isoformat().replace("+00:00", "Z")
        self._consecutive_failures = 0
        self._last_error_message = None
        observations, norm_warnings = self.parse_provider_payload(
            payload=data,
            ingestion_time=now_dt,
            query_time=query_time,
        )
        return observations, flags + norm_warnings

    def fetch_latest(
        self,
        location_id: str,
        query_time: Optional[datetime] = None,
    ) -> AdapterReading:
        """
        Standard BaseLiveAdapter boundary method returning an AdapterReading.
        Enforces:
        - Non-silent missingness (outage / error returns value=None, NEVER 0.0mm dry baseline)
        - Freshness calculated strictly from the latest valid observation
        - Clear distinction between valid zero, stale data, and missing data
        """
        now_dt = datetime.now(timezone.utc)
        if query_time is None:
            query_time = now_dt
        elif query_time.tzinfo is None:
            query_time = query_time.replace(tzinfo=timezone.utc)

        retrieval_iso = query_time.isoformat().replace("+00:00", "Z")

        # 1. Check Configuration & Authorization
        if not self.base_url or not self.api_key:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,  # Never synthesize dry weather
                units="mm/hr",
                quality_flags=["MISSING_PROVIDER_CREDENTIALS", "PENDING_APPROVAL"],
                fallback_applied=False,
                error_message="Live IMD API gateway credentials pending authorization. Live feed is disabled.",
            )

        # 2. Query Transport & Fetch Observations
        observations, warnings = self.fetch_observations(location_id, query_time)

        if not observations:
            q_flags = ["NO_TELEMETRY_AVAILABLE"]
            if not self._last_fetch_successful:
                q_flags.append("PROVIDER_OUTAGE")
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,  # Explicit None: zero rainfall is NEVER manufactured
                units="mm/hr",
                quality_flags=q_flags + warnings,
                fallback_applied=False,
                error_message=f"No telemetry observations available from provider for corridor '{location_id}'.",
            )

        # 3. Filter to eligible observations up to query_time
        eligible = [o for o in observations if o.observation_time_utc <= query_time]
        if not eligible:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,
                units="mm/hr",
                quality_flags=["NO_PRIOR_TELEMETRY"],
                fallback_applied=False,
                error_message=f"No observations prior to query time {retrieval_iso}.",
            )

        # 4. Enforce Freshness Invariant: Must use the latest VALID, eligible observation
        valid_obs = [o for o in eligible if o.is_valid and o.qc_flag == ObservationQCFlag.VALID]

        if not valid_obs:
            # All observations failed QC or are invalid
            latest_raw = eligible[-1]
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=latest_raw.observation_time_utc.isoformat().replace("+00:00", "Z"),
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=round(max(0.0, (query_time - latest_raw.observation_time_utc).total_seconds()), 1),
                is_stale=False,
                value=None,  # Invalid observations never become 0.0mm
                units="mm/hr",
                quality_flags=["ALL_OBSERVATIONS_INVALID", latest_raw.qc_flag.value],
                fallback_applied=False,
                error_message=f"All {len(eligible)} observations for corridor failed QC validation.",
            )

        latest_valid = valid_obs[-1]
        freshness_sec = max(0.0, (query_time - latest_valid.observation_time_utc).total_seconds())
        is_stale = freshness_sec > self.stale_threshold_seconds
        obs_iso = latest_valid.observation_time_utc.isoformat().replace("+00:00", "Z")

        quality_flags = ["VALID_OBSERVATION"]
        if is_stale:
            quality_flags.append("TELEMETRY_STALE")

        # Flag if a newer invalid observation was discarded
        latest_raw = eligible[-1]
        if latest_raw.observation_time_utc > latest_valid.observation_time_utc:
            quality_flags.append("NEWER_INVALID_OBSERVATION_DISCARDED")

        val_mm = latest_valid.interval_rainfall_mm
        if val_mm == 0.0:
            quality_flags.append("VALID_MEASURED_ZERO")

        return AdapterReading(
            source_id=self.source_id,
            source_name=self.source_name,
            authorization_status=self.auth_status,
            is_live_stream=False,
            data_available=True,
            observation_timestamp_utc=obs_iso,
            retrieval_timestamp_utc=retrieval_iso,
            freshness_seconds=round(freshness_sec, 1),
            is_stale=is_stale,
            value={
                "rainfall_1h_mm": val_mm,
                "station_id": latest_valid.station_id,
                "station_name": latest_valid.station_name,
                "provider": latest_valid.provider,
                "station_type": latest_valid.station_type.value,
                "latitude": latest_valid.latitude,
                "longitude": latest_valid.longitude,
                "interval_minutes": latest_valid.interval_minutes,
                "qc_flag": latest_valid.qc_flag.value,
            },
            units="mm/hr",
            quality_flags=quality_flags,
            fallback_applied=False,
        )

    def get_source_status(self) -> Dict[str, Any]:
        """
        Reports operational health, authentication state, and known live-activation limitations.
        """
        masked_endpoint = "NOT_CONFIGURED"
        if self.base_url:
            masked_endpoint = IMDTransportClient._mask_url(self.base_url)

        data_age = None
        if self._last_successful_retrieval_utc:
            try:
                last_dt = datetime.fromisoformat(self._last_successful_retrieval_utc.replace("Z", "+00:00"))
                data_age = round(max(0.0, (datetime.now(timezone.utc) - last_dt).total_seconds()), 1)
            except Exception:
                pass

        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "authorization_status": self.auth_status.value,
            "is_live_connected": (self.auth_status == FeedAuthorizationStatus.AUTHORIZED_LIVE and self._last_fetch_successful),
            "configured_endpoint": masked_endpoint,
            "has_credentials": bool(self.api_key),
            "primary_access_method": "HTTPS REST API (IMD / MoES Weather Telemetry Gateway)",
            "last_successful_retrieval_utc": self._last_successful_retrieval_utc,
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error_message,
            "data_age_seconds": data_age,
            "access_blockers": [
                "Official provider API base URL and token must be configured in environment (SAHAAY_IMD_API_BASE_URL, SAHAAY_IMD_API_KEY).",
                "Formal institutional data-sharing MOU required with IMD/GHMC for live operational dispatch.",
                "Verified AWS/ARG station gazetteer coordinates required for hyper-local urban corridor attribution."
            ],
            "data_handling_safeguards": [
                "Zero credentials in source code or git history.",
                "Strict boundary timeouts and connection resilience (no hung HTTP requests).",
                "Zero synthetic zero rainfall during outages, HTTP errors, or missing data.",
                "Freshness calculated strictly against latest valid observation; invalid pings cannot mask staleness.",
                "Outage, invalid, or stale data produces controlled UNKNOWN / degraded state."
            ],
            "fallback_strategy": "Controlled degraded state with data_available=False and explicit UNKNOWN risk; dry weather is NEVER fabricated."
        }
