"""
Sahaay AI - Hyderabad Rainfall Risk Baseline Engine
Implements an explainable, traceable rainfall risk evaluation engine calibrated against
India Meteorological Department (IMD) precipitation intensity standards.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sahaay.hyderabad_risk.schemas import RainfallRiskResult

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
    station_dist_km: float = 0.0,
    data_freshness_hours: float = 0.0,
    data_timestamp: Optional[str] = None,
    historical_month_p90_mm: Optional[float] = None,
) -> RainfallRiskResult:
    """
    Evaluates explainable rainfall risk for a specific road corridor.
    Calculates risk score (0.0 to 1.0), category (LOW, MEDIUM, HIGH, CRITICAL),
    and confidence based on station distance and observation freshness.
    """
    if data_timestamp is None:
        data_timestamp = datetime.utcnow().isoformat() + "Z"

    reason_codes: List[str] = []
    missing_inputs: List[str] = []
    warnings: List[str] = []

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
        )

    # 1. Base Intensity Evaluation
    r1 = max(0.0, rain_1h_mm)
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

    # 2. Multi-window rolling accumulation amplification
    if rain_3h_mm is not None and rain_3h_mm >= IMD_THRESHOLDS["rolling_3h_warning_mm"]:
        if base_score < 0.70:
            base_score = max(base_score, 0.70)
            category = "HIGH"
        reason_codes.append("ROLLING_3H_FLASH_SURGE")

    if rain_24h_mm is not None:
        if rain_24h_mm >= IMD_THRESHOLDS["rolling_24h_very_heavy_mm"]:
            base_score = max(base_score, 0.85)
            category = "CRITICAL"
            reason_codes.append("ROLLING_24H_EXTREME_SATURATION")
        elif rain_24h_mm >= IMD_THRESHOLDS["rolling_24h_heavy_mm"]:
            base_score = max(base_score, 0.65)
            if category == "LOW" or category == "MEDIUM":
                category = "HIGH"
            reason_codes.append("ROLLING_24H_HEAVY_SATURATION")

    # 3. Climatological Context
    if historical_month_p90_mm and rain_24h_mm and rain_24h_mm > (historical_month_p90_mm * 0.5):
        reason_codes.append("EXCEEDS_50PCT_MONTHLY_P90_IN_24H")

    # 4. Confidence Discounting
    # Base confidence is 1.0, decayed by station distance, data age, and missing windows
    confidence = 1.0

    # Distance penalty: stations beyond 15km lose confidence (0.01 per km beyond 15km, max 0.35)
    if station_dist_km > 15.0:
        dist_penalty = min(0.35, (station_dist_km - 15.0) * 0.01)
        confidence -= dist_penalty
        reason_codes.append(f"STATION_DISTANCE_DISCOUNTED_{round(station_dist_km)}KM")

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
    )
