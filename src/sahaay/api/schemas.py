"""
Sahaay AI - API Schemas (Pydantic V2)
Strict data contracts for HTTP request/response payloads.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class LocationCoords(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)

class ClassScores(BaseModel):
    not_flooded: float = Field(..., ge=0.0, le=1.0)
    flooded: float = Field(..., ge=0.0, le=1.0)

class VisionPredictionResponse(BaseModel):
    prediction_id: str
    predicted_class: str
    confidence: float
    class_scores: ClassScores
    is_ambiguous: bool
    is_inconclusive: Optional[bool] = False
    inconclusive_reasons: Optional[List[str]] = None
    quality_metrics: Optional[Dict[str, Any]] = None
    model_name: str
    model_version: str
    device: str
    inference_latency_ms: float
    created_at: str
    report_id: Optional[str] = None
    location: Optional[LocationCoords] = None
    warnings: List[str] = Field(default_factory=list)

class VisionHealthResponse(BaseModel):
    status: str
    model_name: str
    model_version: str
    checkpoint_loaded: bool
    device: str

class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: str


class RainfallEstimateRequest(BaseModel):
    location_id: str
    rain_1h_mm: Optional[float] = None
    rain_3h_mm: Optional[float] = None
    rain_6h_mm: Optional[float] = None
    rain_24h_mm: Optional[float] = None
    station_dist_km: Optional[float] = Field(None, ge=0.0)
    data_freshness_hours: float = Field(0.0, ge=0.0)
    data_timestamp: Optional[str] = None
    historical_month_p90_mm: Optional[float] = None


class RoadVulnerabilityRequest(BaseModel):
    location_id: str
    road_name: str
    dist_to_hotspot_m: float = Field(..., ge=0.0)
    nearest_hotspot_name: str
    dist_to_drain_m: float = Field(..., ge=0.0)
    dist_to_waterbody_m: float = Field(..., ge=0.0)
    nearest_waterbody_name: str
    road_elevation_m: Optional[float] = None
    drainage_capacity_cusecs: Optional[float] = None

