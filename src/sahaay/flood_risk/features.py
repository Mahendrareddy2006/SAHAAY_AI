"""
Sahaay AI - Phase 17: Local Flood-Risk Feature Engineering Pipeline
(src/sahaay/flood_risk/features.py)

Builds reproducible, leakage-free feature vectors for localized flood risk assessment.
Enforces non-silent missingness semantics, spatial coordinate validation,
and physical precipitation bounds.
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sahaay.hyderabad_risk.features import (
    haversine_distance_m,
    point_to_segment_distance_m,
    compute_hotspot_proximity,
    compute_drain_proximity,
    compute_waterbody_proximity,
)
from sahaay.flood_risk.schemas import LocalFloodRiskInput

logger = logging.getLogger(__name__)

# Hyderabad Metropolitan Area Bounding Box
HYDERABAD_METRO_BOUNDS = {
    "min_lat": 17.15,
    "max_lat": 17.65,
    "min_lon": 78.15,
    "max_lon": 78.70,
}

# Physical bounds for hourly precipitation rate in Hyderabad
MAX_PHYSICAL_HOURLY_RAIN_MM = 250.0


class LocalFloodRiskFeaturePipeline:
    """
    Reproducible feature construction pipeline for localized road flood risk.
    """

    def __init__(self):
        pass

    def validate_spatial_bounds(self, lat: Optional[float], lon: Optional[float]) -> Tuple[bool, List[str]]:
        """Validates that coordinates lie within the authorized Hyderabad bounding box."""
        reasons = []
        if lat is None or lon is None:
            return True, reasons  # Optional coordinates
        
        in_bounds = (
            HYDERABAD_METRO_BOUNDS["min_lat"] <= lat <= HYDERABAD_METRO_BOUNDS["max_lat"]
            and HYDERABAD_METRO_BOUNDS["min_lon"] <= lon <= HYDERABAD_METRO_BOUNDS["max_lon"]
        )
        if not in_bounds:
            reasons.append("COORDINATES_OUT_OF_METRO_BOUNDING_BOX")
            return False, reasons
        return True, reasons

    def validate_precipitation_bounds(
        self,
        rain_1h: Optional[float],
        rain_3h: Optional[float],
        forecast_1h: Optional[float],
    ) -> Tuple[bool, List[str]]:
        """Validates physical precipitation rate bounds and non-negativity."""
        reasons = []
        for val, name in [(rain_1h, "rain_1h_mm"), (rain_3h, "rain_3h_mm"), (forecast_1h, "rain_forecast_1h_mm")]:
            if val is not None:
                if math.isnan(val) or math.isinf(val):
                    reasons.append(f"NON_FINITE_VALUE_IN_{name.upper()}")
                    return False, reasons
                if val < 0.0:
                    reasons.append(f"NEGATIVE_VALUE_IN_{name.upper()}")
                    return False, reasons
                if val > MAX_PHYSICAL_HOURLY_RAIN_MM:
                    reasons.append(f"EXCESSIVE_RATE_IN_{name.upper()}")
                    return False, reasons
        return True, reasons

    def construct_features(
        self,
        segment_id: str,
        road_name: str,
        corridor_zone: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        forecast_horizon_hours: int = 1,
        rainfall_1h_mm: Optional[float] = None,
        rainfall_3h_mm: Optional[float] = None,
        rainfall_forecast_1h_mm: Optional[float] = None,
        rainfall_forecast_3h_mm: Optional[float] = None,
        telemetry_station_dist_km: Optional[float] = None,
        telemetry_freshness_hours: Optional[float] = None,
        vulnerability_index: Optional[float] = None,
        vulnerability_category: Optional[str] = "UNKNOWN",
        current_road_condition: Optional[Any] = None,
        current_road_freshness: Optional[Any] = None,
        evaluation_timestamp_utc: Optional[str] = None,
    ) -> Tuple[LocalFloodRiskInput, List[str]]:
        """
        Constructs and validates a LocalFloodRiskInput feature vector.
        Missing telemetry remains strictly None/UNKNOWN (non-silent missingness).
        """
        warnings = []
        missing_inputs = []

        # Validate spatial coordinates
        valid_spatial, spatial_errs = self.validate_spatial_bounds(latitude, longitude)
        if not valid_spatial:
            warnings.extend(spatial_errs)

        # Validate precipitation telemetry
        valid_precip, precip_errs = self.validate_precipitation_bounds(
            rainfall_1h_mm, rainfall_3h_mm, rainfall_forecast_1h_mm
        )
        if not valid_precip:
            warnings.extend(precip_errs)
            # Quarantine corrupted inputs
            rainfall_1h_mm = None
            rainfall_forecast_1h_mm = None

        # Track missingness
        if rainfall_1h_mm is None and rainfall_forecast_1h_mm is None:
            missing_inputs.append("rainfall_telemetry")
        if vulnerability_index is None:
            missing_inputs.append("vulnerability_index")

        # Temporal timestamp
        now_utc = datetime.now(timezone.utc)
        eval_iso = evaluation_timestamp_utc or now_utc.isoformat().replace("+00:00", "Z")

        feat = LocalFloodRiskInput(
            segment_id=segment_id,
            road_name=road_name,
            corridor_zone=corridor_zone,
            latitude=latitude,
            longitude=longitude,
            forecast_horizon_hours=forecast_horizon_hours,
            rainfall_1h_mm=rainfall_1h_mm,
            rainfall_3h_mm=rainfall_3h_mm,
            rainfall_forecast_1h_mm=rainfall_forecast_1h_mm,
            rainfall_forecast_3h_mm=rainfall_forecast_3h_mm,
            telemetry_station_dist_km=telemetry_station_dist_km,
            telemetry_freshness_hours=telemetry_freshness_hours,
            vulnerability_index=vulnerability_index,
            vulnerability_category=vulnerability_category,
            current_road_condition=current_road_condition,
            current_road_freshness=current_road_freshness,
            evaluation_timestamp_utc=eval_iso,
        )
        return feat, warnings
