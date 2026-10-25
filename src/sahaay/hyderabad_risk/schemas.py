"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Schemas
Defines strict Pydantic data contracts for spatial hotspots, drains, waterbodies, telemetry, and features.
"""

from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field


class FloodingHotspot(BaseModel):
    hotspot_id: str
    name: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    source: str = "TRAC_GHMC_OpenCity"


class DrainLine(BaseModel):
    drain_id: str
    name: str
    coordinates: List[Tuple[float, float]] = Field(..., description="List of (latitude, longitude) tuples")
    point_count: int


class WaterBody(BaseModel):
    waterbody_id: str
    name: str
    centroid_lat: float = Field(..., ge=-90.0, le=90.0)
    centroid_lon: float = Field(..., ge=-180.0, le=180.0)
    area_sq_m: float = Field(0.0, ge=0.0)


class TelemetryRainfallRecord(BaseModel):
    station_id: str
    district: str
    latitude: float
    longitude: float
    timestamp: str
    rainfall_mm: float
    is_valid: bool = True
    qc_flag: str = "VALID"


class GeospatialRiskFeatureVector(BaseModel):
    """
    Unified multi-source geospatial and hydrological feature vector for a road corridor.
    """
    location_id: str
    road_name: str
    latitude: float
    longitude: float
    
    # Proximity features (meters/km)
    dist_to_flood_hotspot_m: float = Field(..., ge=0.0)
    nearest_hotspot_name: str
    dist_to_nearest_drain_m: float = Field(..., ge=0.0)
    dist_to_nearest_waterbody_m: float = Field(..., ge=0.0)
    nearest_waterbody_name: str
    
    # Telemetry proximity & freshness
    nearest_station_id: str
    nearest_station_dist_km: float = Field(..., ge=0.0)
    telemetry_freshness_hours: Optional[float] = None
    
    # Dynamic accumulations (mm)
    rain_1h_mm: Optional[float] = None
    rain_3h_mm: Optional[float] = None
    rain_6h_mm: Optional[float] = None
    rain_24h_mm: Optional[float] = None
    
    # Climatological baseline (mm)
    historical_month_mean_mm: float
    historical_month_p90_mm: float
    
    # Component Outputs
    vulnerability_index: float = Field(..., ge=0.0, le=1.0)
    vulnerability_category: str
    rainfall_risk_score: float = Field(..., ge=0.0, le=1.0)
    rainfall_risk_category: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    generated_at_utc: str


class RainfallRiskResult(BaseModel):
    location_id: str
    risk_category: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    data_timestamp: str
    data_freshness_hours: float
    reason_codes: List[str]
    missing_inputs: List[str]
    model_version: str = "hyderabad_rainfall_risk_v1.0"
    warnings: List[str]


class RoadVulnerabilityResult(BaseModel):
    location_id: str
    road_name: str
    vulnerability_index: float = Field(..., ge=0.0, le=1.0)
    vulnerability_category: str = Field(..., description="LOW, MODERATE, HIGH, SEVERE")
    contributing_features: Dict[str, Any]
    missing_data: List[str]
    spatial_resolution: str
    last_update_time: str
    model_version: str = "hyderabad_road_vulnerability_v1.0"
    warnings: List[str]
