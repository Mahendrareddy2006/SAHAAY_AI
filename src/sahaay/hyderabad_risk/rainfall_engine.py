"""
Sahaay AI - Hyderabad Rainfall Risk Baseline Engine
Implements an explainable, traceable rainfall risk evaluation engine calibrated against
India Meteorological Department (IMD) precipitation intensity standards.
"""

import logging
import math
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional, Tuple

from sahaay.hyderabad_risk.schemas import IMDRainfallObservation, RainfallRiskResult

logger = logging.getLogger(__name__)

# Traceable IMD Intensity Classification Thresholds (provisional operational rules)
# Ref: India Meteorological Department (IMD) Standard Operating Procedure for Weather Forecasting
IMD_THRESHOLDS = {
    "light_max_mm_per_hr": 7.5,
    "moderate_max_mm_per_hr": 15.0,
    "heavy_max_mm_per_hr": 35.0,
    "cloudburst_min_mm_per_hr": 100.0,
    "rolling_3h_warning_mm": 40.0,
    "rolling_6h_warning_mm": 70.0,
    "rolling_24h_heavy_mm": 64.5,
    "rolling_24h_very_heavy_mm": 115.5,
}


def evaluate_rainfall_risk_engine(
    location_id: str,
    rain_1h_mm: Optional[float],
    rain_3h_mm: Optional[float] = None,
    rain_6h_mm: Optional[float] = None,
    rain_24h_mm: Optional[float] = None,
    station_dist_km: Optional[float] = None,
    data_freshness_hours: float = 0.0,
    data_timestamp: Optional[str] = None,
    historical_month_p90_mm: Optional[float] = None,
    provider: Optional[str] = None,
    station_id: Optional[str] = None,
    qc_flags: Optional[List[str]] = None,
    observation_provenance: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
) -> RainfallRiskResult:
    """
    Evaluates explainable rainfall risk for a specific road corridor.
    Calculates risk score (0.0 to 1.0), category (LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN),
    and confidence based on station distance, observation freshness, and missing accumulation windows.
    Preserves provider, station identity, proximity tier, and observation provenance.
    """
    if data_timestamp is None:
        data_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    reason_codes: List[str] = []
    missing_inputs: List[str] = []
    warnings: List[str] = list(warnings) if warnings is not None else []

    # Proximity tier classification (local urban vs peri-urban vs regional catchment vs unknown)
    if station_dist_km is None:
        proximity_tier = "UNKNOWN"
        reason_codes.append("STATION_PROXIMITY_UNKNOWN")
        warnings.append(
            "Station distance or coordinates not provided; proximity tier is UNKNOWN. "
            "Telemetry cannot be treated as verified local urban evidence."
        )
    elif station_dist_km > 35.0:
        proximity_tier = "REGIONAL_CATCHMENT"
        reason_codes.append("REGIONAL_CATCHMENT_TELEMETRY")
        warnings.append(
            f"Telemetry station is distant regional catchment ({round(station_dist_km, 1)}km > 35km); "
            "represents dam/reservoir watershed, NOT hyper-local road corridor precipitation."
        )
    elif station_dist_km > 15.0:
        proximity_tier = "PERI_URBAN"
    else:
        proximity_tier = "LOCAL_URBAN"

    # Check for missing inputs
    if rain_1h_mm is None:
        missing_inputs.append("rain_1h_mm")
    if rain_3h_mm is None:
        missing_inputs.append("rain_3h_mm")
    if rain_6h_mm is None:
        missing_inputs.append("rain_6h_mm")
    if rain_24h_mm is None:
        missing_inputs.append("rain_24h_mm")

    # If primary 1h rain is missing, we must NOT assume 0.0 mm
    if rain_1h_mm is None:
        warnings.append("Hourly rainfall observation missing; cannot determine instantaneous intensity.")
        reason_codes.append("INSUFFICIENT_TELEMETRY_DATA")
        return RainfallRiskResult(
            location_id=location_id,
            risk_category="UNKNOWN",
            risk_score=0.0,
            confidence=0.1,
            data_timestamp=data_timestamp,
            data_freshness_hours=data_freshness_hours,
            reason_codes=reason_codes,
            missing_inputs=missing_inputs,
            model_version="hyderabad_rainfall_risk_v1.0",
            warnings=warnings,
            station_id=station_id,
            provider=provider,
            station_dist_km=round(station_dist_km, 2) if station_dist_km is not None else None,
            station_proximity_tier=proximity_tier,
            observation_provenance=observation_provenance or {},
            qc_flags=qc_flags or [],
        )

    # 1. Input Sanity: Reject negative or non-finite readings (DO NOT CLAMP TO 0.0)
    if math.isnan(rain_1h_mm) or math.isinf(rain_1h_mm) or rain_1h_mm < 0.0:
        warnings.append(f"Invalid hourly rainfall observation ({rain_1h_mm} mm); negative or non-finite reading.")
        reason_codes.append("INVALID_SENSOR_READING")
        reason_codes.append("INSUFFICIENT_TELEMETRY_DATA")
        return RainfallRiskResult(
            location_id=location_id,
            risk_category="UNKNOWN",
            risk_score=0.0,
            confidence=0.10,
            data_timestamp=data_timestamp,
            data_freshness_hours=data_freshness_hours,
            reason_codes=reason_codes,
            missing_inputs=missing_inputs,
            model_version="hyderabad_rainfall_risk_v1.0",
            warnings=warnings,
            station_id=station_id,
            provider=provider,
            station_dist_km=round(station_dist_km, 2) if station_dist_km is not None else None,
            station_proximity_tier=proximity_tier,
            observation_provenance=observation_provenance or {},
            qc_flags=qc_flags or [],
        )

    # Sanitize rolling windows (discard negative/non-finite values as invalid/missing)
    valid_3h = rain_3h_mm if (rain_3h_mm is not None and not (math.isnan(rain_3h_mm) or math.isinf(rain_3h_mm) or rain_3h_mm < 0.0)) else None
    if rain_3h_mm is not None and valid_3h is None:
        warnings.append(f"Invalid rolling 3h rainfall ({rain_3h_mm} mm) discarded as unphysical.")
        reason_codes.append("INVALID_ROLLING_WINDOW_DATA")
        if "rain_3h_mm" not in missing_inputs:
            missing_inputs.append("rain_3h_mm")

    valid_6h = rain_6h_mm if (rain_6h_mm is not None and not (math.isnan(rain_6h_mm) or math.isinf(rain_6h_mm) or rain_6h_mm < 0.0)) else None
    if rain_6h_mm is not None and valid_6h is None:
        warnings.append(f"Invalid rolling 6h rainfall ({rain_6h_mm} mm) discarded as unphysical.")
        reason_codes.append("INVALID_ROLLING_WINDOW_DATA")
        if "rain_6h_mm" not in missing_inputs:
            missing_inputs.append("rain_6h_mm")

    valid_24h = rain_24h_mm if (rain_24h_mm is not None and not (math.isnan(rain_24h_mm) or math.isinf(rain_24h_mm) or rain_24h_mm < 0.0)) else None
    if rain_24h_mm is not None and valid_24h is None:
        warnings.append(f"Invalid rolling 24h rainfall ({rain_24h_mm} mm) discarded as unphysical.")
        reason_codes.append("INVALID_ROLLING_WINDOW_DATA")
        if "rain_24h_mm" not in missing_inputs:
            missing_inputs.append("rain_24h_mm")

    # 2. Base Intensity Evaluation
    r1 = rain_1h_mm
    base_score = 0.0
    category = "LOW"

    if r1 >= IMD_THRESHOLDS["heavy_max_mm_per_hr"]:
        category = "CRITICAL"
        base_score = min(1.0, 0.80 + (r1 - 35.0) / 100.0)
        reason_codes.append("IMD_VERY_HEAVY_INTENSITY_EXCEEDED")
    elif r1 >= IMD_THRESHOLDS["moderate_max_mm_per_hr"]:
        category = "HIGH"
        base_score = 0.60 + 0.20 * ((r1 - 15.0) / (35.0 - 15.0))
        reason_codes.append("IMD_HEAVY_INTENSITY_EXCEEDED")
    elif r1 >= IMD_THRESHOLDS["light_max_mm_per_hr"]:
        category = "MEDIUM"
        base_score = 0.30 + 0.30 * ((r1 - 7.5) / (15.0 - 7.5))
        reason_codes.append("IMD_MODERATE_INTENSITY")
    elif r1 > 0.0:
        category = "LOW"
        base_score = 0.10 + 0.20 * (r1 / 7.5)
        reason_codes.append("IMD_LIGHT_INTENSITY")
    else:
        category = "LOW"
        base_score = 0.02
        reason_codes.append("NORMAL_DRY_CONDITIONS")
        if valid_3h is None and valid_24h is None:
            warnings.append("Cumulative accumulation windows (3h/24h) are missing; antecedent saturation is unobserved.")
            reason_codes.append("CUMULATIVE_WINDOWS_UNAVAILABLE")

    # 3. Multi-window rolling accumulation amplification
    if valid_3h is not None and valid_3h >= IMD_THRESHOLDS["rolling_3h_warning_mm"]:
        if base_score < 0.70:
            base_score = max(base_score, 0.70)
            category = "HIGH"
        reason_codes.append("ROLLING_3H_FLASH_SURGE")

    if valid_24h is not None:
        if valid_24h >= IMD_THRESHOLDS["rolling_24h_very_heavy_mm"]:
            base_score = max(base_score, 0.85)
            category = "CRITICAL"
            reason_codes.append("ROLLING_24H_EXTREME_SATURATION")
        elif valid_24h >= IMD_THRESHOLDS["rolling_24h_heavy_mm"]:
            base_score = max(base_score, 0.65)
            if category == "LOW" or category == "MEDIUM":
                category = "HIGH"
            reason_codes.append("ROLLING_24H_HEAVY_SATURATION")

    # 4. Climatological Context
    if historical_month_p90_mm and valid_24h and valid_24h > (historical_month_p90_mm * 0.5):
        reason_codes.append("EXCEEDS_50PCT_MONTHLY_P90_IN_24H")

    # 5. Confidence Discounting
    # Base confidence is 1.0, decayed by station distance, data age, and missing windows
    confidence = 1.0

    # Distance penalty: stations beyond 15km lose confidence (0.01 per km beyond 15km, max 0.35)
    if station_dist_km is not None:
        if station_dist_km > 15.0:
            dist_penalty = min(0.35, (station_dist_km - 15.0) * 0.01)
            confidence -= dist_penalty
            reason_codes.append(f"STATION_DISTANCE_DISCOUNTED_{round(station_dist_km)}KM")
    else:
        confidence -= 0.15
        reason_codes.append("STATION_PROXIMITY_UNKNOWN_DISCOUNTED")

    # Freshness penalty: telemetry older than 1.5h loses confidence (0.08 per hour, max 0.40)
    if data_freshness_hours > 1.5:
        fresh_penalty = min(0.40, (data_freshness_hours - 1.5) * 0.08)
        confidence -= fresh_penalty
        warnings.append(f"Telemetry observation is {round(data_freshness_hours, 1)} hours stale.")
        reason_codes.append("TELEMETRY_DATA_STALE")

    # Missing windows penalty: 0.08 per missing rolling window
    if missing_inputs:
        confidence -= len(missing_inputs) * 0.08
        reason_codes.append(f"MISSING_{len(missing_inputs)}_ROLLING_WINDOWS")

    confidence = round(max(0.10, min(1.0, confidence)), 2)
    risk_score = round(max(0.0, min(1.0, base_score)), 2)

    return RainfallRiskResult(
        location_id=location_id,
        risk_category=category,
        risk_score=risk_score,
        confidence=confidence,
        data_timestamp=data_timestamp,
        data_freshness_hours=round(data_freshness_hours, 1),
        reason_codes=reason_codes,
        missing_inputs=missing_inputs,
        model_version="hyderabad_rainfall_risk_v1.0",
        warnings=warnings,
        station_id=station_id,
        provider=provider,
        station_dist_km=round(station_dist_km, 2) if station_dist_km is not None else None,
        station_proximity_tier=proximity_tier,
        observation_provenance=observation_provenance or {},
        qc_flags=qc_flags or [],
    )


def evaluate_rainfall_risk_from_observations(
    location_id: str,
    observations: List[IMDRainfallObservation],
    corridor_lat: float,
    corridor_lon: float,
    target_dt: Optional[datetime] = None,
    historical_month_p90_mm: Optional[float] = None,
    counter_max_mm: Optional[float] = None,
    configured_daily_reset_utc: Optional[time] = None,
) -> RainfallRiskResult:
    """
    End-to-end integration entry point:
    Consumes a stream of validated IMDRainfallObservation records, normalizes and deduplicates them,
    identifies the nearest station to the corridor, aggregates rolling accumulation windows,
    and executes the hardened rainfall risk engine with complete provenance propagation.
    """
    from sahaay.hyderabad_risk.features import (
        aggregate_observations_to_rolling_windows,
        haversine_distance_m,
        normalize_and_deduplicate_observations,
    )

    if target_dt is None:
        target_dt = datetime.now(timezone.utc)
    elif target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    if not observations:
        return evaluate_rainfall_risk_engine(
            location_id=location_id,
            rain_1h_mm=None,
            data_freshness_hours=0.0,
            data_timestamp=target_dt.isoformat().replace("+00:00", "Z"),
            historical_month_p90_mm=historical_month_p90_mm,
        )

    # Normalize, deduplicate, and convert cumulative counters
    normalized_obs, norm_warnings = normalize_and_deduplicate_observations(
        observations=observations,
        counter_max_mm=counter_max_mm,
        configured_daily_reset_utc=configured_daily_reset_utc,
    )

    # Identify nearest station to the corridor
    station_positions: Dict[str, Tuple[float, float, str]] = {}
    for o in observations:
        station_positions[o.station_id] = (o.latitude, o.longitude, o.provider)

    nearest_station_id = None
    min_dist_km = float("inf")
    nearest_provider = None

    for st_id, (s_lat, s_lon, prov) in station_positions.items():
        dist_m = haversine_distance_m(corridor_lat, corridor_lon, s_lat, s_lon)
        dist_km = dist_m / 1000.0
        if dist_km < min_dist_km:
            min_dist_km = dist_km
            nearest_station_id = st_id
            nearest_provider = prov

    if nearest_station_id is None:
        nearest_station_id = observations[0].station_id
        nearest_provider = observations[0].provider
        min_dist_km = 0.0

    # Aggregate rolling accumulation windows for the nearest station
    agg = aggregate_observations_to_rolling_windows(
        observations=normalized_obs,
        station_id=nearest_station_id,
        target_dt=target_dt,
    )

    rain_1h = agg["rain_1h_mm"]
    rain_3h = agg["rain_3h_mm"]
    rain_6h = agg["rain_6h_mm"]
    rain_24h = agg["rain_24h_mm"]
    freshness_hours = agg["freshness_hours"] if agg["freshness_hours"] is not None else 99.0
    latest_obs = agg["latest_obs"]

    # Gather QC flags and provenance from latest valid observation
    qc_flags: List[str] = []
    provenance: Dict[str, Any] = {}
    if latest_obs is not None:
        qc_flags.append(latest_obs.qc_flag.value)
        provenance = {
            "station_name": latest_obs.station_name,
            "station_type": latest_obs.station_type.value,
            "observation_time_utc": latest_obs.observation_time_utc.isoformat(),
            "ingestion_time_utc": latest_obs.ingestion_time_utc.isoformat(),
            "interval_minutes": latest_obs.interval_minutes,
            "metadata": latest_obs.provenance_metadata,
        }
    else:
        qc_flags.append("QC_MISSING_VALUE")

    # Evaluate risk engine
    result = evaluate_rainfall_risk_engine(
        location_id=location_id,
        rain_1h_mm=rain_1h,
        rain_3h_mm=rain_3h,
        rain_6h_mm=rain_6h,
        rain_24h_mm=rain_24h,
        station_dist_km=min_dist_km,
        data_freshness_hours=freshness_hours,
        data_timestamp=target_dt.isoformat().replace("+00:00", "Z"),
        historical_month_p90_mm=historical_month_p90_mm,
        provider=nearest_provider,
        station_id=nearest_station_id,
        qc_flags=qc_flags,
        observation_provenance=provenance,
    )

    # Append pipeline normalization and coverage warnings
    combined_warnings = list(dict.fromkeys(result.warnings + norm_warnings + agg["warnings"]))
    result.warnings = combined_warnings

    return result


def evaluate_rainfall_risk_from_adapter(
    location_id: str,
    adapter: Any,
    corridor_lat: float,
    corridor_lon: float,
    target_dt: Optional[datetime] = None,
    historical_month_p90_mm: Optional[float] = None,
) -> RainfallRiskResult:
    """
    Consumes telemetry directly from an adapter boundary (e.g. MockIMDRainfallAdapter),
    integrating latest observations into the rainfall risk engine or propagating outages/malformed payloads as UNKNOWN.
    """
    from sahaay.hyderabad_risk.features import haversine_distance_m

    if target_dt is None:
        target_dt = datetime.now(timezone.utc)
    elif target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    reading = adapter.fetch_latest(location_id=location_id, query_time=target_dt)

    # 1. Outage or None reading
    if not reading.data_available or reading.value is None:
        reasons = list(reading.quality_flags)
        if "INSUFFICIENT_TELEMETRY_DATA" not in reasons:
            reasons.append("INSUFFICIENT_TELEMETRY_DATA")
        warn_msg = reading.error_message or "Adapter reported telemetry unavailable (outage or offline)."
        return evaluate_rainfall_risk_engine(
            location_id=location_id,
            rain_1h_mm=None,
            data_freshness_hours=99.0,
            data_timestamp=target_dt.isoformat().replace("+00:00", "Z"),
            historical_month_p90_mm=historical_month_p90_mm,
            provider=getattr(adapter, "source_id", "UNKNOWN"),
            qc_flags=reading.quality_flags,
            warnings=[warn_msg],
        )

    # 2. Validate payload type: must be a dictionary
    val_data = reading.value
    if not isinstance(val_data, dict):
        warn_msg = (
            f"Adapter '{getattr(adapter, 'source_id', 'UNKNOWN')}' returned malformed payload: "
            f"expected dictionary, got {type(val_data).__name__} ({repr(val_data)[:50]}). "
            "Telemetry quarantined as UNKNOWN."
        )
        return evaluate_rainfall_risk_engine(
            location_id=location_id,
            rain_1h_mm=None,
            data_freshness_hours=99.0,
            data_timestamp=target_dt.isoformat().replace("+00:00", "Z"),
            historical_month_p90_mm=historical_month_p90_mm,
            provider=getattr(adapter, "source_id", "UNKNOWN"),
            qc_flags=reading.quality_flags + ["MALFORMED_ADAPTER_PAYLOAD"],
            warnings=[warn_msg],
        )

    # 3. Valid reading dictionary present
    rain_1h = val_data.get("rainfall_1h_mm")
    rain_3h = val_data.get("rainfall_3h_mm")
    rain_6h = val_data.get("rainfall_6h_mm")
    rain_24h = val_data.get("rainfall_24h_mm")
    station_id = val_data.get("station_id")
    provider = val_data.get("provider", getattr(adapter, "source_id", "UNKNOWN"))

    # Compute distance if station coordinates provided
    s_lat = val_data.get("latitude")
    s_lon = val_data.get("longitude")
    dist_km = None
    if s_lat is not None and s_lon is not None and corridor_lat is not None and corridor_lon is not None:
        try:
            dist_km = haversine_distance_m(corridor_lat, corridor_lon, float(s_lat), float(s_lon)) / 1000.0
        except (ValueError, TypeError):
            dist_km = val_data.get("station_dist_km", None)
    else:
        dist_km = val_data.get("station_dist_km", None)

    freshness_hours = (reading.freshness_seconds / 3600.0) if reading.freshness_seconds is not None else 0.0
    if reading.freshness_seconds is None and reading.observation_timestamp_utc:
        try:
            obs_dt = datetime.fromisoformat(reading.observation_timestamp_utc.replace("Z", "+00:00"))
            freshness_hours = max(0.0, (target_dt - obs_dt).total_seconds() / 3600.0)
        except Exception:
            freshness_hours = 0.0

    return evaluate_rainfall_risk_engine(
        location_id=location_id,
        rain_1h_mm=rain_1h,
        rain_3h_mm=rain_3h,
        rain_6h_mm=rain_6h,
        rain_24h_mm=rain_24h,
        station_dist_km=dist_km,
        data_freshness_hours=freshness_hours,
        data_timestamp=reading.observation_timestamp_utc or target_dt.isoformat().replace("+00:00", "Z"),
        historical_month_p90_mm=historical_month_p90_mm,
        provider=provider,
        station_id=station_id,
        qc_flags=reading.quality_flags,
        observation_provenance={
            "source_name": reading.source_name,
            "retrieval_timestamp_utc": reading.retrieval_timestamp_utc,
            "units": reading.units,
        },
    )

