"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Feature Engineering Module
Derives explainable spatial proximity, rolling hydrological accumulations,
climatological baselines, and data-quality indicators for road corridors.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from sahaay.hyderabad_risk.schemas import (
    DrainLine,
    FloodingHotspot,
    GeospatialRiskFeatureVector,
    WaterBody,
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
