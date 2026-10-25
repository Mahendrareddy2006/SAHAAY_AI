"""
Sahaay AI - Rainfall Risk AI Component Contracts
Defines data structures, schemas, and transparent baseline scoring for rainfall-induced waterlogging risk.
"""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class RainfallObservationInput(BaseModel):
    location_id: str = Field(..., description="Road segment or zone identifier")
    observed_rain_1h_mm: float = Field(..., ge=0.0, description="Observed rainfall accumulation over last 1 hour in mm")
    observed_rain_3h_mm: float = Field(0.0, ge=0.0, description="Observed rainfall accumulation over last 3 hours in mm")
    observed_rain_24h_mm: float = Field(0.0, ge=0.0, description="Observed rainfall accumulation over last 24 hours in mm")
    forecast_rain_1h_mm: float = Field(0.0, ge=0.0, description="Forecast rainfall accumulation over next 1 hour in mm")
    forecast_rain_3h_mm: float = Field(0.0, ge=0.0, description="Forecast rainfall accumulation over next 3 hours in mm")
    soil_saturation_index: Optional[float] = Field(None, ge=0.0, le=1.0, description="Soil saturation index (0.0 dry to 1.0 saturated)")
    data_timestamp: str = Field(..., description="ISO 8601 timestamp of rainfall data")

class RainfallRiskOutput(BaseModel):
    location_id: str
    risk_category: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Estimated waterlogging risk score")
    prediction_horizon_hours: int = Field(1, description="Forecast horizon in hours")
    contributing_factors: List[str] = Field(default_factory=list)
    model_version: str = "rainfall_heuristic_v1.0"
    created_at: str
    warnings: List[str] = Field(default_factory=list)

def estimate_rainfall_risk(data: RainfallObservationInput) -> RainfallRiskOutput:
    """
    Transparent, explainable baseline for rainfall risk estimation.
    Prevents temporal leakage by strictly separating past observations from future predictions.
    """
    import time
    
    factors = []
    # Weighted accumulation formula for Hyderabad urban conditions:
    # Heavy threshold: >30mm/hr causes immediate waterlogging in low-lying Hyderabad catchments
    immediate_intensity = data.observed_rain_1h_mm + (0.8 * data.forecast_rain_1h_mm)
    sustained_accumulation = data.observed_rain_3h_mm * 0.4
    
    score = min(1.0, (immediate_intensity * 0.02) + (sustained_accumulation * 0.01))
    
    if data.observed_rain_1h_mm >= 35.0:
        factors.append(f"Cloudburst-level intensity: {data.observed_rain_1h_mm:.1f} mm in past hour")
    elif data.observed_rain_1h_mm >= 15.0:
        factors.append(f"Moderate-to-heavy rainfall: {data.observed_rain_1h_mm:.1f} mm in past hour")
        
    if data.forecast_rain_1h_mm >= 20.0:
        factors.append(f"Imminent heavy downpour forecast: {data.forecast_rain_1h_mm:.1f} mm next hour")
        
    if score >= 0.70:
        category = "CRITICAL"
    elif score >= 0.45:
        category = "HIGH"
    elif score >= 0.20:
        category = "MEDIUM"
    else:
        category = "LOW"
        
    return RainfallRiskOutput(
        location_id=data.location_id,
        risk_category=category,
        risk_score=round(score, 3),
        prediction_horizon_hours=1,
        contributing_factors=factors or ["Rainfall within normal seasonal drainage absorption capacity"],
        model_version="rainfall_heuristic_v1.0",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        warnings=["Preliminary rainfall risk baseline: Heuristic model pending tabular ML training on historical radar logs."]
    )
