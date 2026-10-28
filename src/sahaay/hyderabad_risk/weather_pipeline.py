"""
Sahaay AI - Operational Weather & Rainfall Ingestion Pipeline
(src/sahaay/hyderabad_risk/weather_pipeline.py)

Implements an operational, safety-first meteorological telemetry ingestion pipeline.
Enforces strict contracts:
1. Strict schema validation, unit normalization (mm, cm, in, mm/h), and timestamp normalization (UTC, IST offsets, epochs).
2. Explicit distinction between instantaneous rain rates (mm/hr), interval accumulations (mm/interval), and cumulative bucket counters (Ct).
3. Monotonic counter conversion with verified rollovers and daily resets; negative counter drops with unknown cause are NEVER clamped to 0.0mm.
4. Non-silent missingness: missing data, provider outages, and quarantined readings evaluate strictly to UNKNOWN / INSUFFICIENT_DATA; dry weather (0.0mm) is NEVER fabricated.
5. Deduplication of identical observations and quarantine of conflicting duplicates.
6. Out-of-order stream reconciliation preserving chronological sequence.
7. Continuous operational health tracking: last successful retrieval, data age, consecutive failures, and error logging.
8. Five-signal forecast evidence separation reusing Phase 18 ForecastRiskAssessmentService.
9. Security governance: privileged live feed activation remains BLOCKED pending server-side cryptographic authentication.
"""

from datetime import datetime, time, timedelta, timezone
from enum import Enum
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.adapters.base import AdapterReading, FeedAuthorizationStatus
from sahaay.adapters.imd_provider_adapter import (
    IMDRainfallProviderAdapter,
    IMDTransportClient,
    TELANGANA_LAT_MIN,
    TELANGANA_LAT_MAX,
    TELANGANA_LON_MIN,
    TELANGANA_LON_MAX,
    MAX_PHYSICAL_RATE_MM_PER_HR,
)
from sahaay.adapters.mock_imd_adapter import MockIMDRainfallAdapter
from sahaay.hyderabad_risk.counter_conversion import (
    DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    convert_cumulative_counter_to_interval,
    convert_consecutive_gauge_observations,
)
from sahaay.hyderabad_risk.features import (
    aggregate_observations_to_rolling_windows,
    haversine_distance_m,
    normalize_and_deduplicate_observations,
)
from sahaay.hyderabad_risk.rainfall_engine import evaluate_rainfall_risk_engine
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    IMDStationType,
    MeasurementMode,
    ObservationQCFlag,
    RainfallRiskResult,
)
from sahaay.forecast_risk.schemas import (
    ForecastDataStatus,
    ForecastRainfallInput,
    ForecastRiskAssessmentOutput,
    ObservedRainfallContext,
    StaticVulnerabilityContext,
    CurrentRoadStatusContext,
)
from sahaay.forecast_risk.service import ForecastRiskAssessmentService

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Pipeline Schemas & Health Contracts
# ==============================================================================

class PipelineOperationalStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OUTAGE = "OUTAGE"
    UNCONFIGURED = "UNCONFIGURED"


class StationMetadata(BaseModel):
    station_id: str
    station_name: str
    station_type: IMDStationType = IMDStationType.AWS
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    elevation_m: Optional[float] = None
    locality: str = "Greater Hyderabad"
    basin_type: str = "URBAN_CATCHMENT"  # URBAN_CATCHMENT or RESERVOIR_BASIN
    is_active: bool = True
    last_observation_utc: Optional[str] = None
    last_observation_val_mm: Optional[float] = None
    is_stale: bool = False


class IngestionHealthStatus(BaseModel):
    pipeline_status: PipelineOperationalStatus
    provider_authorization_status: FeedAuthorizationStatus
    is_live_stream_connected: bool
    configured_endpoint: str
    has_credentials: bool
    last_successful_retrieval_utc: Optional[str] = None
    last_retrieval_attempt_utc: Optional[str] = None
    data_age_seconds: Optional[float] = None
    consecutive_failures: int = 0
    last_error_message: Optional[str] = None
    active_quality_flags: List[str] = Field(default_factory=list)
    total_observations_ingested: int = 0
    valid_observations_count: int = 0
    quarantined_observations_count: int = 0
    monitored_stations_count: int = 0
    active_stations_count: int = 0
    security_authorization_mode: str = "SERVER_AUTHENTICATION_BLOCKED"


class RawTelemetryPayload(BaseModel):
    """Flexible schema for raw inbound telemetry before normalization."""
    station_id: str = Field(..., min_length=1)
    station_name: Optional[str] = None
    provider: Optional[str] = "IMD"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Union[str, int, float, datetime]
    interval_minutes: int = 60
    measurement_mode: Optional[str] = None  # RATE, ACCUMULATION, COUNTER
    rainfall_amount: Optional[float] = None
    rainfall_rate_mm_per_hr: Optional[float] = None
    cumulative_counter_mm: Optional[float] = None
    units: Optional[str] = "mm"  # mm, cm, in, mm/h, cm/h, in/h
    counter_max_mm: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Canonical Hyderabad meteorological station gazetteer
CANONICAL_STATION_GAZETTEER: Dict[str, StationMetadata] = {
    "HYD-STN-BEGUMPET": StationMetadata(
        station_id="HYD-STN-BEGUMPET",
        station_name="Begumpet Airport Observatory (IMD AWS)",
        station_type=IMDStationType.AWS,
        latitude=17.4480,
        longitude=78.4680,
        elevation_m=531.0,
        locality="Secunderabad / Begumpet",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-SHAMSHABAD": StationMetadata(
        station_id="HYD-STN-SHAMSHABAD",
        station_name="RGIA Shamshabad Met Office (IMD AWS)",
        station_type=IMDStationType.AWS,
        latitude=17.2403,
        longitude=78.4294,
        elevation_m=615.0,
        locality="Shamshabad South",
        basin_type="PERI_URBAN",
    ),
    "HYD-STN-GOLCONDA": StationMetadata(
        station_id="HYD-STN-GOLCONDA",
        station_name="Golconda / Shaikpet Urban Rain Gauge (ARG)",
        station_type=IMDStationType.ARG,
        latitude=17.3833,
        longitude=78.4011,
        elevation_m=520.0,
        locality="West Zone / Shaikpet",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-JUBILEE-HILLS": StationMetadata(
        station_id="HYD-STN-JUBILEE-HILLS",
        station_name="Jubilee Hills Urban AWS",
        station_type=IMDStationType.AWS,
        latitude=17.4325,
        longitude=78.4072,
        elevation_m=560.0,
        locality="West Zone / Jubilee Hills",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-KHAIRATABAD": StationMetadata(
        station_id="HYD-STN-KHAIRATABAD",
        station_name="Khairatabad / Somajiguda Urban AWS",
        station_type=IMDStationType.AWS,
        latitude=17.4125,
        longitude=78.4590,
        elevation_m=515.0,
        locality="Central Zone / Khairatabad",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-CHARMINAR": StationMetadata(
        station_id="HYD-STN-CHARMINAR",
        station_name="Charminar / Old City Rain Gauge (ARG)",
        station_type=IMDStationType.ARG,
        latitude=17.3616,
        longitude=78.4747,
        elevation_m=490.0,
        locality="South Zone / Charminar",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-MALKAJGIRI": StationMetadata(
        station_id="HYD-STN-MALKAJGIRI",
        station_name="Malkajgiri / Alwal Northern AWS",
        station_type=IMDStationType.AWS,
        latitude=17.4520,
        longitude=78.5310,
        elevation_m=545.0,
        locality="North Zone / Malkajgiri",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-HAYATHNAGAR": StationMetadata(
        station_id="HYD-STN-HAYATHNAGAR",
        station_name="Hayathnagar Eastern Observatory (AWS)",
        station_type=IMDStationType.AWS,
        latitude=17.3270,
        longitude=78.6040,
        elevation_m=498.0,
        locality="East Zone / Hayathnagar",
        basin_type="PERI_URBAN",
    ),
    "HYD-STN-LINGAMPALLY": StationMetadata(
        station_id="HYD-STN-LINGAMPALLY",
        station_name="Serilingampally / Hitec City AWS",
        station_type=IMDStationType.AWS,
        latitude=17.4850,
        longitude=78.3200,
        elevation_m=585.0,
        locality="West Zone / Cyberabad",
        basin_type="URBAN_CATCHMENT",
    ),
    "HYD-STN-HIMAYATSAGAR": StationMetadata(
        station_id="HYD-STN-HIMAYATSAGAR",
        station_name="Himayatsagar Dam Catchment Gauge",
        station_type=IMDStationType.ARG,
        latitude=17.3150,
        longitude=78.3620,
        elevation_m=540.0,
        locality="Musi River Upstream Catchment",
        basin_type="RESERVOIR_BASIN",
    ),
    "HYD-STN-OSMANSAGAR": StationMetadata(
        station_id="HYD-STN-OSMANSAGAR",
        station_name="Osmansagar / Gandipet Catchment Gauge",
        station_type=IMDStationType.ARG,
        latitude=17.3750,
        longitude=78.2980,
        elevation_m=545.0,
        locality="Musi River Upstream Catchment",
        basin_type="RESERVOIR_BASIN",
    ),
}


# ==============================================================================
# 2. Weather Ingestion Pipeline Class
# ==============================================================================

class WeatherIngestionPipeline:
    """
    Operational Ingestion Pipeline orchestrating meteorological telemetry intake,
    normalization, anomaly detection, counter conversions, and rolling accumulations.
    """

    def __init__(
        self,
        adapter: Optional[Any] = None,
        stale_threshold_hours: float = 3.0,
        max_physical_rate_mm_per_hr: float = DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
        daily_reset_time_utc: Optional[time] = time(3, 0),  # 03:00 UTC = 08:30 IST
        forecast_service: Optional[ForecastRiskAssessmentService] = None,
        stations_gazetteer: Optional[Dict[str, StationMetadata]] = None,
    ):
        self.adapter = adapter or IMDRainfallProviderAdapter()
        self.stale_threshold_seconds = stale_threshold_hours * 3600.0
        self.stale_threshold_hours = stale_threshold_hours
        self.max_physical_rate_mm_per_hr = max_physical_rate_mm_per_hr
        self.daily_reset_time_utc = daily_reset_time_utc
        self.forecast_service = forecast_service or ForecastRiskAssessmentService()

        # Station gazetteer metadata
        self._stations: Dict[str, StationMetadata] = dict(stations_gazetteer or CANONICAL_STATION_GAZETTEER)

        # In-memory historical telemetry store: station_id -> list of IMDRainfallObservation
        self._observations_by_station: Dict[str, List[IMDRainfallObservation]] = {}

        # Pipeline health and operational accounting
        self._last_successful_retrieval_utc: Optional[str] = None
        self._last_attempt_utc: Optional[str] = None
        self._consecutive_failures: int = 0
        self._last_error_message: Optional[str] = None
        self._total_ingested_count: int = 0
        self._valid_observations_count: int = 0
        self._quarantined_observations_count: int = 0
        self._active_quality_flags: List[str] = []

    # --------------------------------------------------------------------------
    # Telemetry Normalization & Quality Control
    # --------------------------------------------------------------------------

    def normalize_timestamp(
        self,
        raw_ts: Union[str, int, float, datetime],
        query_time: Optional[datetime] = None,
    ) -> Tuple[Optional[datetime], List[str]]:
        """
        Parses and standardizes timestamps into timezone-aware UTC datetime.
        Detects naive datetimes, parses ISO-8601 with timezone, epoch ms/sec,
        and enforces future-timestamp bounds.
        """
        warnings: List[str] = []
        obs_dt: Optional[datetime] = None

        if isinstance(raw_ts, datetime):
            obs_dt = raw_ts if raw_ts.tzinfo is not None else raw_ts.replace(tzinfo=timezone.utc)
        elif isinstance(raw_ts, (int, float)):
            try:
                val = float(raw_ts)
                if val > 1e11:  # Epoch milliseconds
                    val /= 1000.0
                obs_dt = datetime.fromtimestamp(val, tz=timezone.utc)
            except Exception as e:
                return None, [f"Unparseable epoch timestamp '{raw_ts}': {str(e)}"]
        elif isinstance(raw_ts, str):
            clean_ts = raw_ts.strip()
            # Standardize Z to +00:00
            if clean_ts.endswith("Z"):
                clean_ts = clean_ts[:-1] + "+00:00"
            try:
                obs_dt = datetime.fromisoformat(clean_ts)
                if obs_dt.tzinfo is None:
                    # Naive datetime: strictly tag warning and assume UTC
                    obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                    warnings.append("Observation timestamp was timezone-naive; standardized to UTC.")
            except Exception:
                try:
                    # Handle common formats
                    obs_dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except Exception as e:
                    return None, [f"Unparseable ISO timestamp '{raw_ts}': {str(e)}"]

        if obs_dt is None:
            return None, ["Timestamp is None or could not be parsed."]

        # Ensure converted to UTC timezone
        obs_dt = obs_dt.astimezone(timezone.utc)

        # Future timestamp detection (> query_time + 1 minute)
        now_utc = query_time or datetime.now(timezone.utc)
        if obs_dt > now_utc + timedelta(minutes=1):
            warnings.append(f"Observation timestamp ({obs_dt.isoformat()}) is in the future; quarantined.")
            return obs_dt, warnings + ["QC_TIMESTAMP_ANOMALY"]

        return obs_dt, warnings

    def normalize_units(
        self,
        val: Optional[float],
        units: str,
        is_rate: bool = False,
    ) -> Optional[float]:
        """
        Normalizes measurement values to canonical millimeters (mm) or mm/hr.
        Supports mm, cm, in, mm/h, cm/h, in/h.
        """
        if val is None:
            return None
        if math.isnan(val) or math.isinf(val):
            return None

        u = (units or "mm").strip().lower()
        if u in ("mm", "mm/h", "mm/hr"):
            return float(val)
        elif u in ("cm", "cm/h", "cm/hr", "centimeter", "centimeters"):
            return float(val) * 10.0
        elif u in ("in", "inch", "inches", "in/h", "in/hr"):
            return float(val) * 25.4
        elif u in ("m", "meter", "meters"):
            return float(val) * 1000.0
        return float(val)

    def normalize_raw_reading(
        self,
        raw: Union[RawTelemetryPayload, Dict[str, Any]],
        ingestion_time: Optional[datetime] = None,
        query_time: Optional[datetime] = None,
    ) -> Tuple[Optional[IMDRainfallObservation], List[str]]:
        """
        Normalizes a single raw observation into an IMDRainfallObservation contract.
        Performs unit normalization, coordinate verification, timestamp parsing,
        mode classification, and physical validity checks.
        """
        warnings: List[str] = []
        ingestion_dt = ingestion_time or datetime.now(timezone.utc)

        data = raw.model_dump() if isinstance(raw, RawTelemetryPayload) else dict(raw)

        station_id = str(data.get("station_id") or data.get("stationId") or data.get("id") or "").strip()
        if not station_id:
            return None, ["MISSING_STATION_ID"]

        # Coordinates resolution (from payload or gazetteer fallback)
        lat = data.get("latitude") if data.get("latitude") is not None else data.get("lat")
        lon = data.get("longitude") if data.get("longitude") is not None else data.get("lon")

        if (lat is None or lon is None) and station_id in self._stations:
            gazetteer_meta = self._stations[station_id]
            lat = gazetteer_meta.latitude
            lon = gazetteer_meta.longitude

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None, [f"Station {station_id} missing valid numerical coordinates; quarantined."]

        # Coordinate bounds verification (Telangana / Greater Hyderabad)
        if not (TELANGANA_LAT_MIN <= lat <= TELANGANA_LAT_MAX and TELANGANA_LON_MIN <= lon <= TELANGANA_LON_MAX):
            return None, [f"Station {station_id} coordinates ({lat}, {lon}) outside regional project bounds; quarantined."]

        # Station name and provider
        station_name = str(data.get("station_name") or data.get("name") or station_id).strip()
        provider_name = str(data.get("provider") or "IMD").strip()

        # Timestamp normalization
        raw_ts = data.get("timestamp") or data.get("observation_time_utc") or data.get("time")
        if raw_ts is None:
            return None, [f"Station {station_id} missing observation timestamp; quarantined."]

        obs_dt, ts_warnings = self.normalize_timestamp(raw_ts, query_time=query_time)
        warnings.extend(ts_warnings)
        if obs_dt is None:
            return None, warnings

        is_future = "QC_TIMESTAMP_ANOMALY" in ts_warnings

        # Interval minutes
        try:
            interval_mins = int(data.get("interval_minutes", 60))
        except (ValueError, TypeError):
            interval_mins = 60

        units_str = str(data.get("units") or "mm")

        # Values extraction
        raw_interval = data.get("rainfall_amount") if data.get("rainfall_amount") is not None else (
            data.get("interval_rainfall_mm") if data.get("interval_rainfall_mm") is not None else data.get("rainfall_mm")
        )
        raw_rate = data.get("rainfall_rate_mm_per_hr") if data.get("rainfall_rate_mm_per_hr") is not None else (
            data.get("rate_mm_h") if data.get("rate_mm_h") is not None else data.get("instantaneous_rate_mm_hr")
        )
        raw_counter = data.get("cumulative_counter_mm") if data.get("cumulative_counter_mm") is not None else (
            data.get("raw_counter_value_mm") if data.get("raw_counter_value_mm") is not None else data.get("counter_mm")
        )

        norm_interval = self.normalize_units(raw_interval, units_str, is_rate=False)
        norm_rate = self.normalize_units(raw_rate, units_str, is_rate=True)
        norm_counter = self.normalize_units(raw_counter, units_str, is_rate=False)

        # Measurement Mode Determination
        mode = MeasurementMode.INTERVAL_ACCUMULATION
        if norm_rate is not None and norm_interval is None and norm_counter is None:
            mode = MeasurementMode.INSTANTANEOUS_RATE
        elif norm_counter is not None and norm_interval is None and norm_rate is None:
            mode = MeasurementMode.CUMULATIVE_GAUGE_COUNTER
        elif norm_interval is not None:
            mode = MeasurementMode.INTERVAL_ACCUMULATION

        # Physical Validity Checks
        qc_flag = ObservationQCFlag.VALID
        is_valid = True

        if is_future:
            qc_flag = ObservationQCFlag.QC_TIMESTAMP_ANOMALY
            is_valid = False

        # Negative checks
        if norm_interval is not None and norm_interval < 0.0:
            qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
            is_valid = False
            norm_interval = None
            warnings.append(f"Station {station_id} reported negative interval rainfall; quarantined.")

        if norm_rate is not None and norm_rate < 0.0:
            qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
            is_valid = False
            norm_rate = None
            warnings.append(f"Station {station_id} reported negative rainfall rate; quarantined.")

        if norm_counter is not None and norm_counter < 0.0:
            qc_flag = ObservationQCFlag.QC_NEGATIVE_VALUE
            is_valid = False
            norm_counter = None
            warnings.append(f"Station {station_id} reported negative cumulative counter; quarantined.")

        # Physical spike checks (world record ~305 mm/hr, calibrated QC 250 mm/hr)
        if norm_interval is not None:
            effective_rate = (norm_interval / (interval_mins / 60.0)) if interval_mins > 0 else norm_interval
            if effective_rate > self.max_physical_rate_mm_per_hr:
                qc_flag = ObservationQCFlag.QC_UNPHYSICAL_SPIKE
                is_valid = False
                warnings.append(f"Station {station_id} interval rainfall exceeds physical spike threshold ({effective_rate:.1f} mm/h > {self.max_physical_rate_mm_per_hr} mm/h); flagged invalid.")

        if norm_rate is not None and norm_rate > self.max_physical_rate_mm_per_hr:
            qc_flag = ObservationQCFlag.QC_UNPHYSICAL_SPIKE
            is_valid = False
            warnings.append(f"Station {station_id} rainfall rate exceeds physical threshold ({norm_rate:.1f} mm/h); flagged invalid.")

        # Require at least one reading value
        if norm_interval is None and norm_counter is None and norm_rate is None:
            qc_flag = ObservationQCFlag.QC_MISSING_VALUE
            is_valid = False
            warnings.append(f"Station {station_id} contains no valid numerical measurement reading.")

        station_type = IMDStationType.AWS
        if station_id in self._stations:
            station_type = self._stations[station_id].station_type

        try:
            obs = IMDRainfallObservation(
                provider=provider_name,
                station_id=station_id,
                station_name=station_name,
                station_type=station_type,
                latitude=lat,
                longitude=lon,
                observation_time_utc=obs_dt,
                ingestion_time_utc=ingestion_dt,
                interval_minutes=interval_mins,
                measurement_mode=mode,
                raw_counter_value_mm=norm_counter,
                interval_rainfall_mm=norm_interval,
                instantaneous_rate_mm_hr=norm_rate,
                qc_flag=qc_flag,
                is_valid=is_valid,
                provenance_metadata=data.get("metadata", {}),
            )
            return obs, warnings
        except Exception as e:
            return None, warnings + [f"Failed to create IMDRainfallObservation: {str(e)}"]

    # --------------------------------------------------------------------------
    # Ingestion Batch Processing
    # --------------------------------------------------------------------------

    def ingest_batch(
        self,
        telemetry_records: List[Union[RawTelemetryPayload, Dict[str, Any], IMDRainfallObservation]],
        ingestion_time: Optional[datetime] = None,
        query_time: Optional[datetime] = None,
        counter_max_mm: Optional[float] = 1000.0,
    ) -> Tuple[int, int, List[str]]:
        """
        Ingests a batch of telemetry records with strict deduplication, chronological
        ordering, counter conversion, and station gazetteer synchronization.
        Returns: (valid_count, quarantined_count, warnings_list)
        """
        now_dt = ingestion_time or datetime.now(timezone.utc)
        self._last_attempt_utc = now_dt.isoformat().replace("+00:00", "Z")

        parsed_observations: List[IMDRainfallObservation] = []
        all_warnings: List[str] = []

        for rec in telemetry_records:
            self._total_ingested_count += 1
            if isinstance(rec, IMDRainfallObservation):
                parsed_observations.append(rec)
            else:
                obs, w = self.normalize_raw_reading(rec, ingestion_time=now_dt, query_time=query_time)
                all_warnings.extend(w)
                if obs:
                    parsed_observations.append(obs)
                else:
                    self._quarantined_observations_count += 1

        if not parsed_observations:
            self._last_error_message = "No parseable observations in batch."
            return 0, self._quarantined_observations_count, all_warnings

        # Deduplicate, sort chronologically, and execute counter conversions
        normalized, norm_warnings = normalize_and_deduplicate_observations(
            observations=parsed_observations,
            counter_max_mm=counter_max_mm,
            max_physical_rate_mm_per_hr=self.max_physical_rate_mm_per_hr,
            configured_daily_reset_utc=self.daily_reset_time_utc,
        )
        all_warnings.extend(norm_warnings)

        valid_batch_count = 0
        quarantined_batch_count = 0

        # Store into station histories and update station metadata
        for obs in normalized:
            st_id = obs.station_id
            self._observations_by_station.setdefault(st_id, []).append(obs)

            if obs.is_valid:
                valid_batch_count += 1
                self._valid_observations_count += 1
            else:
                quarantined_batch_count += 1
                self._quarantined_observations_count += 1

            # Update gazetteer status if tracked
            if st_id in self._stations:
                meta = self._stations[st_id]
                meta.last_observation_utc = obs.observation_time_utc.isoformat().replace("+00:00", "Z")
                meta.last_observation_val_mm = obs.interval_rainfall_mm if obs.interval_rainfall_mm is not None else obs.instantaneous_rate_mm_hr
                meta.is_stale = False

        # Sort each station history chronologically and retain up to 72 hours
        for st_id, records in self._observations_by_station.items():
            records.sort(key=lambda o: (o.observation_time_utc, o.ingestion_time_utc))
            # Retention limit: keep latest 200 records per station
            if len(records) > 200:
                self._observations_by_station[st_id] = records[-200:]

        if valid_batch_count > 0:
            self._last_successful_retrieval_utc = now_dt.isoformat().replace("+00:00", "Z")
            self._consecutive_failures = 0
            self._last_error_message = None

        return valid_batch_count, quarantined_batch_count, all_warnings

    # --------------------------------------------------------------------------
    # Adapter Ingestion & Resilient Querying
    # --------------------------------------------------------------------------

    def fetch_and_ingest_from_adapter(
        self,
        location_id: str = "CORRIDOR-ALL",
        query_time: Optional[datetime] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Queries the configured boundary adapter, ingests returned observations,
        and safely handles outages or missing credentials without synthetic dry fallback.
        """
        now_dt = query_time or datetime.now(timezone.utc)
        self._last_attempt_utc = now_dt.isoformat().replace("+00:00", "Z")

        # 1. Check if adapter has fetch_observations method (IMDRainfallProviderAdapter)
        if hasattr(self.adapter, "fetch_observations"):
            observations, warnings = self.adapter.fetch_observations(location_id=location_id, query_time=now_dt)
            if not observations:
                self._consecutive_failures += 1
                self._last_error_message = f"Adapter returned 0 observations for corridor '{location_id}'."
                self._active_quality_flags = list(set(self._active_quality_flags + warnings))
                return False, warnings

            valid_c, quar_c, norm_w = self.ingest_batch(observations, ingestion_time=now_dt, query_time=now_dt)
            return valid_c > 0, warnings + norm_w

        # 2. Standard BaseLiveAdapter fetch_latest
        reading: AdapterReading = self.adapter.fetch_latest(location_id=location_id, query_time=now_dt)
        if not reading.data_available or reading.value is None:
            self._consecutive_failures += 1
            self._last_error_message = reading.error_message or "Adapter reported telemetry unavailable."
            self._active_quality_flags = list(set(self._active_quality_flags + reading.quality_flags))
            return False, reading.quality_flags + ([reading.error_message] if reading.error_message else [])

        # Process valid reading value
        val_data = reading.value
        if isinstance(val_data, dict):
            raw_payload = RawTelemetryPayload(
                station_id=str(val_data.get("station_id") or "ADAPTER-FEED"),
                station_name=val_data.get("station_name"),
                provider=val_data.get("provider", self.adapter.source_id),
                latitude=val_data.get("latitude"),
                longitude=val_data.get("longitude"),
                timestamp=reading.observation_timestamp_utc or reading.retrieval_timestamp_utc,
                interval_minutes=int(val_data.get("interval_minutes", 60)),
                rainfall_amount=val_data.get("rainfall_1h_mm"),
                units=reading.units,
            )
            valid_c, quar_c, norm_w = self.ingest_batch([raw_payload], ingestion_time=now_dt, query_time=now_dt)
            return valid_c > 0, reading.quality_flags + norm_w

        return False, ["Adapter returned non-dict payload value."]

    # --------------------------------------------------------------------------
    # Corridor Weather & Risk Evaluation
    # --------------------------------------------------------------------------

    def evaluate_corridor_weather(
        self,
        corridor_id: str,
        corridor_lat: float,
        corridor_lon: float,
        target_dt: Optional[datetime] = None,
        historical_month_p90_mm: Optional[float] = None,
    ) -> RainfallRiskResult:
        """
        Evaluates real-time weather status for a monitored road corridor against
        the nearest station's normalized telemetry observations.
        Preserves non-silent missingness (never assumes 0.0mm dry weather on missing data).
        """
        now_dt = target_dt or datetime.now(timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)

        target_iso = now_dt.isoformat().replace("+00:00", "Z")

        # Gather all valid observations up to target_dt across all stations
        all_eligible_obs: List[IMDRainfallObservation] = []
        for records in self._observations_by_station.values():
            all_eligible_obs.extend([o for o in records if o.observation_time_utc <= now_dt])

        if not all_eligible_obs:
            # Check if adapter has fallback reading
            if self.adapter:
                return self._evaluate_from_adapter_fallback(
                    corridor_id=corridor_id,
                    corridor_lat=corridor_lat,
                    corridor_lon=corridor_lon,
                    target_dt=now_dt,
                    historical_month_p90_mm=historical_month_p90_mm,
                )

            return evaluate_rainfall_risk_engine(
                location_id=corridor_id,
                rain_1h_mm=None,
                station_dist_km=None,
                data_freshness_hours=99.0,
                data_timestamp=target_iso,
                historical_month_p90_mm=historical_month_p90_mm,
                warnings=["No telemetry observations ingested for any station prior to query timestamp."],
            )

        # Find nearest station with eligible observations
        nearest_st_id = None
        min_dist_km = float("inf")
        nearest_provider = None

        station_coords: Dict[str, Tuple[float, float, str]] = {}
        for o in all_eligible_obs:
            station_coords[o.station_id] = (o.latitude, o.longitude, o.provider)

        for st_id, (s_lat, s_lon, prov) in station_coords.items():
            dist_km = haversine_distance_m(corridor_lat, corridor_lon, s_lat, s_lon) / 1000.0
            if dist_km < min_dist_km:
                min_dist_km = dist_km
                nearest_st_id = st_id
                nearest_provider = prov

        if nearest_st_id is None:
            nearest_st_id = all_eligible_obs[0].station_id
            nearest_provider = all_eligible_obs[0].provider
            min_dist_km = 0.0

        # Calculate rolling accumulations for nearest station
        agg = aggregate_observations_to_rolling_windows(
            observations=all_eligible_obs,
            station_id=nearest_st_id,
            target_dt=now_dt,
        )

        rain_1h = agg["rain_1h_mm"]
        rain_3h = agg["rain_3h_mm"]
        rain_6h = agg["rain_6h_mm"]
        rain_24h = agg["rain_24h_mm"]
        freshness_h = agg["freshness_hours"] if agg["freshness_hours"] is not None else 99.0
        latest_obs = agg["latest_obs"]

        qc_flags = [latest_obs.qc_flag.value] if latest_obs else ["QC_MISSING_VALUE"]
        if rain_1h == 0.0:
            qc_flags.append("VALID_MEASURED_ZERO")

        provenance = {
            "station_id": nearest_st_id,
            "station_name": latest_obs.station_name if latest_obs else nearest_st_id,
            "provider": nearest_provider,
            "observation_time_utc": latest_obs.observation_time_utc.isoformat() if latest_obs else None,
            "retrieval_timestamp_utc": target_iso,
            "freshness_hours": round(freshness_h, 2),
        }

        result = evaluate_rainfall_risk_engine(
            location_id=corridor_id,
            rain_1h_mm=rain_1h,
            rain_3h_mm=rain_3h,
            rain_6h_mm=rain_6h,
            rain_24h_mm=rain_24h,
            station_dist_km=min_dist_km,
            data_freshness_hours=freshness_h,
            data_timestamp=target_iso,
            historical_month_p90_mm=historical_month_p90_mm,
            provider=nearest_provider,
            station_id=nearest_st_id,
            qc_flags=qc_flags,
            observation_provenance=provenance,
            warnings=agg["warnings"],
        )
        return result

    def _evaluate_from_adapter_fallback(
        self,
        corridor_id: str,
        corridor_lat: float,
        corridor_lon: float,
        target_dt: datetime,
        historical_month_p90_mm: Optional[float] = None,
    ) -> RainfallRiskResult:
        """Invokes evaluate_rainfall_risk_from_adapter if no observations are in memory."""
        reading = self.adapter.fetch_latest(corridor_id, query_time=target_dt)
        if not reading.data_available or reading.value is None:
            return evaluate_rainfall_risk_engine(
                location_id=corridor_id,
                rain_1h_mm=None,
                station_dist_km=None,
                data_freshness_hours=99.0,
                data_timestamp=target_dt.isoformat().replace("+00:00", "Z"),
                historical_month_p90_mm=historical_month_p90_mm,
                provider=self.adapter.source_id,
                qc_flags=reading.quality_flags,
                warnings=[reading.error_message or "Adapter reported telemetry unavailable."],
            )

        val_data = reading.value
        rain_1h = val_data.get("rainfall_1h_mm")
        st_dist = val_data.get("station_dist_km")
        if st_dist is None and val_data.get("latitude") and val_data.get("longitude"):
            st_dist = haversine_distance_m(corridor_lat, corridor_lon, float(val_data["latitude"]), float(val_data["longitude"])) / 1000.0

        freshness_h = (reading.freshness_seconds / 3600.0) if reading.freshness_seconds is not None else 0.0
        return evaluate_rainfall_risk_engine(
            location_id=corridor_id,
            rain_1h_mm=rain_1h,
            rain_3h_mm=val_data.get("rainfall_3h_mm"),
            station_dist_km=st_dist,
            data_freshness_hours=freshness_h,
            data_timestamp=reading.observation_timestamp_utc or target_dt.isoformat().replace("+00:00", "Z"),
            historical_month_p90_mm=historical_month_p90_mm,
            provider=val_data.get("provider", self.adapter.source_id),
            station_id=val_data.get("station_id"),
            qc_flags=reading.quality_flags,
        )

    # --------------------------------------------------------------------------
    # Forecast Evaluation with Strict Five-Signal Evidence Isolation
    # --------------------------------------------------------------------------

    def evaluate_corridor_forecast_risk(
        self,
        corridor_id: str,
        road_name: str,
        corridor_lat: float,
        corridor_lon: float,
        forecast_inputs: Optional[List[ForecastRainfallInput]] = None,
        static_vulnerability_index: Optional[float] = None,
        static_vulnerability_category: Optional[str] = None,
        road_condition_state: Optional[str] = None,
        reference_time_utc: Optional[datetime] = None,
    ) -> ForecastRiskAssessmentOutput:
        """
        Integrates weather telemetry with Phase 18 ForecastRiskAssessmentService.
        Preserves strict separation across 5 distinct signals:
        1. Forecast precipitation context (F)
        2. Observed gauge rainfall (R)
        3. Static flood susceptibility (V)
        4. Current road condition (O)
        5. Verified historical flood outcomes (H)
        """
        now_dt = reference_time_utc or datetime.now(timezone.utc)

        # 1. Evaluate current observed gauge context
        obs_res = self.evaluate_corridor_weather(
            corridor_id=corridor_id,
            corridor_lat=corridor_lat,
            corridor_lon=corridor_lon,
            target_dt=now_dt,
        )

        obs_context = ObservedRainfallContext(
            observed_1h_mm=obs_res.rain_1h_mm if hasattr(obs_res, "rain_1h_mm") else None,
            observed_3h_mm=obs_res.rain_3h_mm if hasattr(obs_res, "rain_3h_mm") else None,
            telemetry_source_id=obs_res.station_id,
            telemetry_distance_km=obs_res.station_dist_km,
            telemetry_freshness_hours=obs_res.data_freshness_hours,
        )

        # 2. Static vulnerability context
        v_idx = static_vulnerability_index if static_vulnerability_index is not None else 0.50
        v_cat = static_vulnerability_category or "UNKNOWN"
        vuln_context = StaticVulnerabilityContext(
            segment_id=corridor_id,
            vulnerability_index=v_idx,
            vulnerability_category=v_cat,
        )

        # 3. Current road status context
        road_context = CurrentRoadStatusContext(
            segment_id=corridor_id,
            condition_state=road_condition_state or "NO_CURRENT_EVIDENCE",
            verification_state="UNMONITORED",
        )

        # 4. Execute Phase 18 forecast assessment
        return self.forecast_service.evaluate_forecast_risk(
            segment_id=corridor_id,
            road_name=road_name,
            forecast_inputs=forecast_inputs,
            observed_context=obs_context,
            vulnerability_context=vuln_context,
            road_status_context=road_context,
            reference_time_utc=now_dt,
        )

    # --------------------------------------------------------------------------
    # Operational Health & Status Reporting
    # --------------------------------------------------------------------------

    def get_ingestion_health(self) -> IngestionHealthStatus:
        """
        Generates an auditable operational health report covering data age,
        consecutive failures, adapter authorization, and station availability.
        """
        now_utc = datetime.now(timezone.utc)
        data_age = None
        if self._last_successful_retrieval_utc:
            try:
                last_dt = datetime.fromisoformat(self._last_successful_retrieval_utc.replace("Z", "+00:00"))
                data_age = round(max(0.0, (now_utc - last_dt).total_seconds()), 1)
            except Exception:
                pass

        # Pipeline operational status determination
        if self._consecutive_failures >= 3:
            pipe_status = PipelineOperationalStatus.OUTAGE
        elif self._consecutive_failures > 0 or (data_age is not None and data_age > self.stale_threshold_seconds):
            pipe_status = PipelineOperationalStatus.DEGRADED
        elif self._valid_observations_count > 0:
            pipe_status = PipelineOperationalStatus.HEALTHY
        else:
            pipe_status = PipelineOperationalStatus.UNCONFIGURED

        adapter_auth = getattr(self.adapter, "auth_status", FeedAuthorizationStatus.PENDING_APPROVAL)
        configured_ep = "NOT_CONFIGURED"
        has_creds = False
        if hasattr(self.adapter, "base_url") and self.adapter.base_url:
            configured_ep = IMDTransportClient._mask_url(self.adapter.base_url)
            has_creds = bool(getattr(self.adapter, "api_key", None))

        active_stns = sum(1 for m in self._stations.values() if m.last_observation_utc is not None and not m.is_stale)

        return IngestionHealthStatus(
            pipeline_status=pipe_status,
            provider_authorization_status=adapter_auth,
            is_live_stream_connected=(adapter_auth == FeedAuthorizationStatus.AUTHORIZED_LIVE and self._consecutive_failures == 0),
            configured_endpoint=configured_ep,
            has_credentials=has_creds,
            last_successful_retrieval_utc=self._last_successful_retrieval_utc,
            last_retrieval_attempt_utc=self._last_attempt_utc,
            data_age_seconds=data_age,
            consecutive_failures=self._consecutive_failures,
            last_error_message=self._last_error_message,
            active_quality_flags=list(set(self._active_quality_flags)),
            total_observations_ingested=self._total_ingested_count,
            valid_observations_count=self._valid_observations_count,
            quarantined_observations_count=self._quarantined_observations_count,
            monitored_stations_count=len(self._stations),
            active_stations_count=active_stns,
            security_authorization_mode="SERVER_AUTHENTICATION_BLOCKED",
        )

    def get_stations_gazetteer(self) -> List[StationMetadata]:
        """Returns the list of monitored meteorological stations."""
        return list(self._stations.values())


# Global default weather pipeline instance
default_weather_pipeline = WeatherIngestionPipeline()
