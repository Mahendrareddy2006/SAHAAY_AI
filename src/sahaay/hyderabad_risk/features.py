"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Feature Engineering Module
Derives explainable spatial proximity, rolling hydrological accumulations,
climatological baselines, and data-quality indicators for road corridors.
"""

import logging
import math
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

from sahaay.hyderabad_risk.schemas import (
    DrainLine,
    FloodingHotspot,
    GeospatialRiskFeatureVector,
    IMDRainfallObservation,
    MeasurementMode,
    ObservationQCFlag,
    WaterBody,
)
from sahaay.hyderabad_risk.counter_conversion import (
    DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    CounterConversionResult,
    convert_consecutive_gauge_observations,
    convert_cumulative_counter_to_interval,
)

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two points in meters using Haversine formula.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def point_to_segment_distance_m(
    p_lat: float, p_lon: float,
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float
) -> float:
    """
    Computes orthogonal distance from point P to line segment AB in meters.
    Approximates locally on equirectangular projection centered at P.
    """
    # Convert lat/lon degrees to local meters around p_lat
    lat_scale = 111320.0
    lon_scale = 111320.0 * math.cos(math.radians(p_lat))

    px, py = 0.0, 0.0
    ax = (a_lon - p_lon) * lon_scale
    ay = (a_lat - p_lat) * lat_scale
    bx = (b_lon - p_lon) * lon_scale
    by = (b_lat - p_lat) * lat_scale

    abx = bx - ax
    aby = by - ay
    seg_len_sq = abx * abx + aby * aby

    if seg_len_sq == 0.0:
        return math.sqrt(ax * ax + ay * ay)

    # Project point onto segment: t = dot(P-A, B-A) / |B-A|^2
    t = ((-ax) * abx + (-ay) * aby) / seg_len_sq
    t = max(0.0, min(1.0, t))

    proj_x = ax + t * abx
    proj_y = ay + t * aby

    return math.sqrt(proj_x * proj_x + proj_y * proj_y)


def compute_hotspot_proximity(
    lat: float, lon: float, hotspots: List[FloodingHotspot]
) -> Tuple[float, str]:
    """
    Computes distance to nearest known historical waterlogging hotspot in meters.
    """
    if not hotspots:
        return 99999.0, "UNKNOWN"

    min_dist = float("inf")
    nearest_name = "UNKNOWN"

    for h in hotspots:
        d = haversine_distance_m(lat, lon, h.latitude, h.longitude)
        if d < min_dist:
            min_dist = d
            nearest_name = h.name

    return round(min_dist, 1), nearest_name


def compute_drain_proximity(
    lat: float, lon: float, drains: List[DrainLine]
) -> float:
    """
    Computes minimum distance to mapped open drainage / nala network in meters.
    """
    if not drains:
        return 99999.0

    min_dist = float("inf")

    for drain in drains:
        coords = drain.coordinates
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            dist = point_to_segment_distance_m(lat, lon, p1[0], p1[1], p2[0], p2[1])
            if dist < min_dist:
                min_dist = dist
                if min_dist < 5.0:  # Early exit if virtually touching
                    return round(min_dist, 1)

    return round(min_dist, 1)


def compute_waterbody_proximity(
    lat: float, lon: float, waterbodies: List[WaterBody]
) -> Tuple[float, str]:
    """
    Computes distance to nearest lake/tank waterbody centroid in meters.
    """
    if not waterbodies:
        return 99999.0, "UNKNOWN"

    min_dist = float("inf")
    nearest_name = "UNKNOWN"

    for wb in waterbodies:
        d = haversine_distance_m(lat, lon, wb.centroid_lat, wb.centroid_lon)
        if d < min_dist:
            min_dist = d
            nearest_name = wb.name

    return round(min_dist, 1), nearest_name


def find_nearest_telemetry_station(
    lat: float, lon: float, stations_df: pd.DataFrame
) -> Tuple[str, float]:
    """
    Identifies the nearest weather telemetry station and distance in km.
    """
    min_dist_km = float("inf")
    nearest_station = "UNKNOWN"

    for _, row in stations_df.iterrows():
        dist_m = haversine_distance_m(lat, lon, row["Latitude"], row["Longitude"])
        dist_km = dist_m / 1000.0
        if dist_km < min_dist_km:
            min_dist_km = dist_km
            nearest_station = str(row["Station"])

    return nearest_station, round(min_dist_km, 2)


def compute_rolling_rainfall(
    station_id: str,
    target_dt: datetime,
    telemetry_clean_df: pd.DataFrame,
    windows: List[int] = [1, 3, 6, 24]
) -> Dict[str, Optional[float]]:
    """
    Calculates rolling rainfall accumulations (1h, 3h, 6h, 24h) from telemetry.
    Strict non-silent missingness: If data is missing or stale, returns None or records gaps.
    """
    res: Dict[str, Optional[float]] = {f"rain_{w}h_mm": None for w in windows}
    res["freshness_hours"] = None

    station_data = telemetry_clean_df[
        (telemetry_clean_df["Station"] == station_id)
        & (telemetry_clean_df["qc_flag"] == "VALID")
    ].copy()

    if station_data.empty:
        return res

    station_data = station_data.sort_values("parsed_timestamp")
    latest_ts = station_data["parsed_timestamp"].max()
    
    # Calculate freshness relative to target_dt
    diff_sec = (target_dt - latest_ts).total_seconds()
    freshness_h = max(0.0, diff_sec / 3600.0)
    res["freshness_hours"] = round(freshness_h, 1)

    # Accumulate valid readings within time window [target_dt - W, target_dt]
    val_col = "Telemetry Hourly Rainfall (mm)"
    for w in windows:
        start_w = target_dt - timedelta(hours=w)
        sub = station_data[
            (station_data["parsed_timestamp"] >= start_w)
            & (station_data["parsed_timestamp"] <= target_dt)
        ]
        if not sub.empty:
            # Check expected hourly count vs observed count
            observed_hours = len(sub)
            if observed_hours >= max(1, w // 2):  # Require at least 50% coverage
                res[f"rain_{w}h_mm"] = round(float(sub[val_col].sum()), 2)
            else:
                res[f"rain_{w}h_mm"] = None  # Severe missingness: do NOT assume zero!
        else:
            res[f"rain_{w}h_mm"] = None

    return res


def get_climatological_baseline(
    month: int, monthly_df: pd.DataFrame
) -> Tuple[float, float]:
    """
    Looks up 121-year historical monthly mean and 90th percentile from IMD series.
    """
    month_names = ["Jan", "Feb", "Mar", "April", "May", "June", "July", "Aug", "Sept", "Oct", "Nov", "Dec"]
    if 1 <= month <= 12:
        col = month_names[month - 1]
    else:
        col = "July"

    if col in monthly_df.columns:
        mean_val = float(monthly_df[col].mean())
        p90_val = float(np.percentile(monthly_df[col].dropna(), 90))
        return round(mean_val, 1), round(p90_val, 1)
    
    return 150.0, 250.0


# ==============================================================================
# Phase 13.3: Rainfall Observation Stream Normalization & Rolling Aggregation
# ==============================================================================

def normalize_and_deduplicate_observations(
    observations: List[IMDRainfallObservation],
    counter_max_mm: Optional[float] = None,
    max_physical_rate_mm_per_hr: float = DEFAULT_MAX_PHYSICAL_RATE_MM_PER_HR,
    configured_daily_reset_utc: Optional[time] = None,
    reset_tolerance_minutes: int = 15,
) -> Tuple[List[IMDRainfallObservation], List[str]]:
    """
    Normalizes, deduplicates, and validates a stream of rainfall observations.
    
    Processing Steps:
    1. Groups observations by station_id.
    2. Sorts each station's stream chronologically by observation_time_utc.
    3. Detects repeated records for the same station at the identical observation timestamp:
       - Identical values: Deduplicated to a single observation without double counting.
       - Disagreeing values: Flagged as QC_CONFLICTING_DUPLICATE, quarantined (is_valid=False,
         interval_rainfall_mm=None), and an explicit warning is recorded.
    4. For cumulative gauge counter series, converts consecutive readings into interval rainfall
       using convert_consecutive_gauge_observations.
    5. Preserves all provenance metadata and observation timestamps.
    """
    warnings: List[str] = []
    if not observations:
        return [], warnings

    # Group by station_id
    by_station: Dict[str, List[IMDRainfallObservation]] = {}
    for obs in observations:
        by_station.setdefault(obs.station_id, []).append(obs)

    processed_all: List[IMDRainfallObservation] = []

    for station_id, st_records in by_station.items():
        # Sort chronologically by observation_time_utc, then ingestion_time_utc
        sorted_records = sorted(
            st_records,
            key=lambda o: (o.observation_time_utc, o.ingestion_time_utc)
        )

        # Step 1: Detect duplicates at the same timestamp
        deduped_series: List[IMDRainfallObservation] = []
        i = 0
        n = len(sorted_records)
        while i < n:
            curr = sorted_records[i]
            group = [curr]
            j = i + 1
            while j < n and sorted_records[j].observation_time_utc == curr.observation_time_utc:
                group.append(sorted_records[j])
                j += 1

            if len(group) == 1:
                deduped_series.append(curr)
            else:
                # Multiple records for same station at same timestamp
                # Compare reported values to detect conflict
                if curr.measurement_mode == MeasurementMode.INTERVAL_ACCUMULATION:
                    vals = [r.interval_rainfall_mm for r in group if r.interval_rainfall_mm is not None]
                else:
                    vals = [r.raw_counter_value_mm for r in group if r.raw_counter_value_mm is not None]

                has_conflict = False
                if len(vals) > 1:
                    min_v, max_v = min(vals), max(vals)
                    if abs(max_v - min_v) > 0.001:
                        has_conflict = True

                if has_conflict:
                    warn_msg = (
                        f"Conflicting duplicate telemetry for station '{station_id}' at "
                        f"{curr.observation_time_utc.isoformat()}: reported values {vals} conflict. "
                        f"Observation quarantined with QC_CONFLICTING_DUPLICATE."
                    )
                    warnings.append(warn_msg)
                    logger.warning(warn_msg)
                    quarantined = curr.model_copy(update={
                        "interval_rainfall_mm": None,
                        "raw_counter_value_mm": None,
                        "is_valid": False,
                        "qc_flag": ObservationQCFlag.QC_CONFLICTING_DUPLICATE,
                    })
                    deduped_series.append(quarantined)
                else:
                    # Identical values: deduplicate safely to single record
                    deduped_series.append(group[-1])

            i = j

        # Step 2: Convert cumulative counters for consecutive records
        station_normalized: List[IMDRainfallObservation] = []
        prev_obs: Optional[IMDRainfallObservation] = None

        for obs in deduped_series:
            if obs.measurement_mode == MeasurementMode.CUMULATIVE_GAUGE_COUNTER:
                if obs.interval_rainfall_mm is None and obs.raw_counter_value_mm is not None:
                    if prev_obs is not None and prev_obs.raw_counter_value_mm is not None:
                        conv = convert_consecutive_gauge_observations(
                            current_obs=obs,
                            previous_obs=prev_obs,
                            counter_max_mm=counter_max_mm,
                            max_physical_rate_mm_per_hr=max_physical_rate_mm_per_hr,
                            configured_daily_reset_utc=configured_daily_reset_utc,
                            reset_tolerance_minutes=reset_tolerance_minutes,
                        )
                        if conv.is_valid:
                            obs = obs.model_copy(update={
                                "interval_rainfall_mm": conv.interval_rainfall_mm,
                                "interval_minutes": int(round(conv.elapsed_minutes or obs.interval_minutes)),
                                "qc_flag": conv.qc_flag,
                                "is_valid": True,
                            })
                        else:
                            obs = obs.model_copy(update={
                                "interval_rainfall_mm": None,
                                "qc_flag": conv.qc_flag,
                                "is_valid": False,
                            })
                            warnings.append(f"Counter conversion for station '{station_id}' rejected: {conv.qc_reason}")
                    else:
                        # Initial reading in cumulative series has no prior baseline
                        obs = obs.model_copy(update={
                            "interval_rainfall_mm": None,
                            "qc_flag": ObservationQCFlag.QC_MISSING_VALUE,
                            "is_valid": False,
                        })
                        warnings.append(f"Initial cumulative reading for station '{station_id}' lacks prior baseline reading to differentiate.")

            station_normalized.append(obs)
            if (
                obs.raw_counter_value_mm is not None
                and not math.isnan(obs.raw_counter_value_mm)
                and not math.isinf(obs.raw_counter_value_mm)
                and obs.raw_counter_value_mm >= 0.0
                and obs.qc_flag != ObservationQCFlag.QC_CONFLICTING_DUPLICATE
            ):
                prev_obs = obs

        processed_all.extend(station_normalized)

    # Sort all processed records across all stations by observation_time_utc
    processed_all.sort(key=lambda o: o.observation_time_utc)
    return processed_all, warnings


def aggregate_observations_to_rolling_windows(
    observations: List[IMDRainfallObservation],
    station_id: str,
    target_dt: datetime,
    windows: List[int] = [1, 3, 6, 24],
) -> Dict[str, Any]:
    """
    Calculates rolling rainfall accumulations (1h, 3h, 6h, 24h) from eligible observations.
    
    Temporal Coverage & Non-Silent Missingness Invariants:
    1. Only observations with is_valid=True and interval_rainfall_mm is not None are aggregated.
    2. Observations strictly <= target_dt are eligible.
    3. Freshness is measured from target_dt to the latest VALID observation.
       Invalid or corrupted pings never mask telemetry staleness.
    4. For 1h window, requires at least 45 minutes of unique temporal coverage (75%)
       and max uncovered gap <= 20 minutes. A single 5- or 15-minute observation is never
       treated as a complete 1-hour accumulation.
    5. Multi-hour windows (W > 1) enforce defensible minimum coverage and maximum gap limits:
       - 3h window: >= 120 minutes coverage, max gap <= 75 minutes.
       - 6h window: >= 180 minutes coverage, max gap <= 150 minutes.
       - 24h window: >= 720 minutes coverage, max gap <= 360 minutes.
    6. Overlapping measurement intervals are detected; accumulation is withheld to prevent double-counting.
    7. Valid 0.0mm readings are aggregated as legitimate zero rainfall.
    8. Incomplete coverage returns None (strictly non-silent missingness, never imputed as zero).
    """
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    res: Dict[str, Any] = {f"rain_{w}h_mm": None for w in windows}
    res["freshness_hours"] = None
    res["latest_obs"] = None
    res["warnings"] = []

    st_obs = [
        o for o in observations
        if o.station_id == station_id and o.observation_time_utc <= target_dt
    ]

    if not st_obs:
        res["warnings"].append(f"No observations found for station '{station_id}' prior to {target_dt.isoformat()}.")
        return res

    # Sort chronologically
    st_obs.sort(key=lambda o: o.observation_time_utc)

    # Filter strictly valid observations with non-None interval rainfall
    valid_obs = [
        o for o in st_obs
        if o.is_valid and o.interval_rainfall_mm is not None
    ]

    if not valid_obs:
        res["warnings"].append(
            f"No valid observations found for station '{station_id}' prior to {target_dt.isoformat()} "
            f"({len(st_obs)} raw records were invalid or quarantined)."
        )
        return res

    valid_obs.sort(key=lambda o: o.observation_time_utc)
    latest_valid_obs = valid_obs[-1]
    res["latest_obs"] = latest_valid_obs

    diff_sec = (target_dt - latest_valid_obs.observation_time_utc).total_seconds()
    freshness_hours = round(max(0.0, diff_sec / 3600.0), 2)
    res["freshness_hours"] = freshness_hours

    if freshness_hours > 3.0:
        res["warnings"].append(
            f"Latest valid telemetry observation is {freshness_hours} hours stale (> 3.0h threshold)."
        )

    # If the latest overall record was invalid, surface that freshness was measured from the last valid observation
    if st_obs[-1].observation_time_utc > latest_valid_obs.observation_time_utc:
        res["warnings"].append(
            f"Most recent record at {st_obs[-1].observation_time_utc.isoformat()} was invalid ({st_obs[-1].qc_flag.value}); "
            f"freshness measured from latest valid observation ({freshness_hours}h ago)."
        )

    for w in windows:
        start_w = target_dt - timedelta(hours=w)

        # Observations intersecting window (start_w, target_dt]
        w_obs: List[IMDRainfallObservation] = []
        for o in valid_obs:
            o_end = o.observation_time_utc
            o_start = o_end - timedelta(minutes=o.interval_minutes)
            if o_end > start_w and o_end <= target_dt:
                w_obs.append(o)

        if not w_obs:
            res[f"rain_{w}h_mm"] = None
            continue

        # Sort intersecting observations by start, then end
        w_obs.sort(key=lambda o: (o.observation_time_utc - timedelta(minutes=o.interval_minutes), o.observation_time_utc))

        # 1. Overlapping Interval Check
        has_overlap = False
        for idx in range(len(w_obs) - 1):
            curr_end = w_obs[idx].observation_time_utc
            next_start = w_obs[idx + 1].observation_time_utc - timedelta(minutes=w_obs[idx + 1].interval_minutes)
            # Check overlap exceeding a 30-second clock tolerance
            if next_start < curr_end - timedelta(seconds=30):
                has_overlap = True
                break

        if has_overlap:
            res[f"rain_{w}h_mm"] = None
            res["warnings"].append(
                f"Window {w}h contains overlapping measurement intervals for station '{station_id}'; "
                "accumulation withheld to prevent double-counting."
            )
            continue

        # 2. Compute Union Coverage & Max Gap
        clipped_intervals: List[Tuple[datetime, datetime]] = []
        for o in w_obs:
            o_end = o.observation_time_utc
            o_start = o_end - timedelta(minutes=o.interval_minutes)
            clip_start = max(o_start, start_w)
            clip_end = min(o_end, target_dt)
            if clip_start < clip_end:
                clipped_intervals.append((clip_start, clip_end))

        if not clipped_intervals:
            res[f"rain_{w}h_mm"] = None
            continue

        # Merge adjacent or intersecting intervals
        clipped_intervals.sort(key=lambda x: (x[0], x[1]))
        merged: List[Tuple[datetime, datetime]] = []
        for c_start, c_end in clipped_intervals:
            if not merged:
                merged.append((c_start, c_end))
            else:
                m_start, m_end = merged[-1]
                if c_start <= m_end:
                    merged[-1] = (m_start, max(m_end, c_end))
                else:
                    merged.append((c_start, c_end))

        covered_minutes = sum((m_end - m_start).total_seconds() / 60.0 for m_start, m_end in merged)

        # Calculate gaps
        gaps: List[float] = []
        gaps.append((merged[0][0] - start_w).total_seconds() / 60.0)
        for idx in range(len(merged) - 1):
            gaps.append((merged[idx + 1][0] - merged[idx][1]).total_seconds() / 60.0)
        gaps.append((target_dt - merged[-1][1]).total_seconds() / 60.0)
        max_gap_minutes = max(gaps) if gaps else 0.0

        # Coverage Thresholds
        if w == 1:
            min_required_minutes = 45.0  # 75% coverage
            max_allowed_gap_minutes = 20.0
        elif w == 3:
            min_required_minutes = 120.0  # 66.7% coverage (2 of 3 hours)
            max_allowed_gap_minutes = 75.0
        elif w == 6:
            min_required_minutes = 180.0  # 50% coverage
            max_allowed_gap_minutes = 150.0
        elif w == 24:
            min_required_minutes = 720.0  # 50% coverage
            max_allowed_gap_minutes = 360.0  # 6 hours
        else:
            min_required_minutes = (w * 60.0) * 0.50
            max_allowed_gap_minutes = (w * 60.0) * 0.40

        if covered_minutes >= min_required_minutes and max_gap_minutes <= max_allowed_gap_minutes:
            res[f"rain_{w}h_mm"] = round(float(sum(o.interval_rainfall_mm for o in w_obs)), 2)
        else:
            res[f"rain_{w}h_mm"] = None
            res["warnings"].append(
                f"Window {w}h has insufficient temporal coverage ({round(covered_minutes, 1)} min < {min_required_minutes} min required, "
                f"or max gap {round(max_gap_minutes, 1)} min > {max_allowed_gap_minutes} min allowed); accumulation withheld."
            )

    return res

