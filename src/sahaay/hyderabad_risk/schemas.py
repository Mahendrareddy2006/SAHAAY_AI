"""
Sahaay AI - Hyderabad Geospatial & Rainfall Risk AI Schemas
Defines strict Pydantic data contracts for spatial hotspots, drains, waterbodies, telemetry, and features.
"""

import math
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field, field_validator, model_validator


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
    risk_category: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN")
    risk_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    data_timestamp: str
    data_freshness_hours: float
    reason_codes: List[str]
    missing_inputs: List[str]
    model_version: str = "hyderabad_rainfall_risk_v1.0"
    warnings: List[str]
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    provider: Optional[str] = None
    station_dist_km: Optional[float] = None
    station_proximity_tier: Optional[str] = None
    rain_1h_mm: Optional[float] = None
    rain_3h_mm: Optional[float] = None
    rain_6h_mm: Optional[float] = None
    rain_24h_mm: Optional[float] = None
    instantaneous_rate_mm_hr: Optional[float] = None
    observation_provenance: Dict[str, Any] = Field(default_factory=dict)
    qc_flags: List[str] = Field(default_factory=list)


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


# ==============================================================================
# Phase 13: Formal Rainfall Observation Data Contracts (IMD / Telemetry)
# ==============================================================================

class IMDStationType(str, Enum):
    AWS = "AWS"                               # Automatic Weather Station (multi-sensor)
    ARG = "ARG"                               # Automatic Rain Gauge (tipping bucket)
    MANUAL_OBSERVATORY = "MANUAL_OBSERVATORY" # Standard manned surface observatory
    COMMUNITY_GAUGE = "COMMUNITY_GAUGE"       # Civic / third-party / local sensor
    UNKNOWN = "UNKNOWN"                       # Unspecified / unverified station type


class MeasurementMode(str, Enum):
    INTERVAL_ACCUMULATION = "INTERVAL_ACCUMULATION"        # Direct interval rainfall (e.g., mm in 15m or 1h)
    CUMULATIVE_GAUGE_COUNTER = "CUMULATIVE_GAUGE_COUNTER"  # Monotonic gauge counter register (Ct)
    INSTANTANEOUS_RATE = "INSTANTANEOUS_RATE"              # Instantaneous rain rate (mm/hr)


class ObservationQCFlag(str, Enum):
    VALID = "VALID"
    QC_UNPHYSICAL_SPIKE = "QC_UNPHYSICAL_SPIKE"
    QC_NEGATIVE_VALUE = "QC_NEGATIVE_VALUE"
    QC_NEGATIVE_DELTA = "QC_NEGATIVE_DELTA"
    QC_COUNTER_ROLLOVER = "QC_COUNTER_ROLLOVER"
    QC_GAUGE_RESET = "QC_GAUGE_RESET"
    QC_STALE_VALUE = "QC_STALE_VALUE"
    QC_TIMESTAMP_ANOMALY = "QC_TIMESTAMP_ANOMALY"
    QC_MISSING_VALUE = "QC_MISSING_VALUE"
    QC_CONFLICTING_DUPLICATE = "QC_CONFLICTING_DUPLICATE"


class IMDRainfallObservation(BaseModel):
    """
    Validated rainfall observation data contract compatible with IMD / state telemetry standards.
    Supports direct interval accumulations, raw cumulative gauge counters, and instantaneous rain rates.
    Enforces timezone awareness, coordinate bounds, and physical validity.
    """
    # 1. Provenance & Identification
    provider: str = Field(..., min_length=1, description="Telemetry source authority (e.g. 'IMD', 'TSDPS', 'MOCK_SYNTHETIC')")
    station_id: str = Field(..., min_length=1, description="Station alphanumeric identifier")
    station_name: str = Field(..., min_length=1, description="Human-readable station or locality name")
    station_type: IMDStationType = Field(default=IMDStationType.UNKNOWN, description="Station classification")

    # 2. Geospatial Coordinates (Telangana & Greater Hyderabad regional bounds: 15.0-20.5°N, 76.5-82.5°E)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (WGS84)")

    # 3. Timestamps (Strictly timezone-aware UTC)
    observation_time_utc: datetime = Field(..., description="Nominal measurement timestamp in UTC")
    ingestion_time_utc: datetime = Field(..., description="Timestamp when record was ingested by Sahaay in UTC")
    interval_minutes: int = Field(default=60, gt=0, le=1440, description="Measurement or accumulation period in minutes")

    # 4. Measurement Representation
    measurement_mode: MeasurementMode = Field(..., description="Measurement representation mode")
    raw_counter_value_mm: Optional[float] = Field(None, ge=0.0, description="Raw cumulative gauge counter Ct (mm)")
    interval_rainfall_mm: Optional[float] = Field(None, ge=0.0, description="Derived or reported interval rainfall (mm)")
    instantaneous_rate_mm_hr: Optional[float] = Field(None, ge=0.0, description="Instantaneous rainfall rate (mm/hr)")

    # 5. Quality & Validity
    qc_flag: ObservationQCFlag = Field(default=ObservationQCFlag.VALID, description="Quality control classification")
    is_valid: bool = Field(default=True, description="True only if verified and safe for risk evaluation")
    provenance_metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific telemetry metadata")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Latitude cannot be NaN or Inf.")
        # Regional project bounds: Telangana, Greater Hyderabad & bordering catchments (15.0°N to 20.5°N)
        if not (15.0 <= v <= 20.5):
            raise ValueError(f"Latitude {v} is outside regional project bounds [15.0, 20.5].")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Longitude cannot be NaN or Inf.")
        # Regional project bounds: Telangana, Greater Hyderabad & bordering catchments (76.5°E to 82.5°E)
        if not (76.5 <= v <= 82.5):
            raise ValueError(f"Longitude {v} is outside regional project bounds [76.5, 82.5].")
        return v

    @field_validator("observation_time_utc", "ingestion_time_utc")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware (UTC). Naive datetimes are strictly rejected.")
        return v

    @field_validator("raw_counter_value_mm", "interval_rainfall_mm", "instantaneous_rate_mm_hr")
    @classmethod
    def validate_finite_and_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if math.isnan(v) or math.isinf(v):
                raise ValueError("Rainfall values cannot be NaN or Inf.")
            if v < 0.0:
                raise ValueError(f"Rainfall value ({v} mm) cannot be negative.")
        return v

    @model_validator(mode="after")
    def validate_consistency(self) -> "IMDRainfallObservation":
        # At least one reading must be present
        if self.raw_counter_value_mm is None and self.interval_rainfall_mm is None and self.instantaneous_rate_mm_hr is None:
            if self.is_valid:
                raise ValueError("An observation marked is_valid=True must supply raw_counter_value_mm or interval_rainfall_mm.")

        # If marked is_valid=True, QC flag cannot be an error flag
        invalid_flags = {
            ObservationQCFlag.QC_NEGATIVE_VALUE,
            ObservationQCFlag.QC_NEGATIVE_DELTA,
            ObservationQCFlag.QC_UNPHYSICAL_SPIKE,
            ObservationQCFlag.QC_TIMESTAMP_ANOMALY,
            ObservationQCFlag.QC_MISSING_VALUE,
            ObservationQCFlag.QC_STALE_VALUE,
            ObservationQCFlag.QC_GAUGE_RESET,
            ObservationQCFlag.QC_CONFLICTING_DUPLICATE,
        }
        if self.is_valid and self.qc_flag in invalid_flags:
            raise ValueError(f"Observation marked is_valid=True cannot have error QC flag {self.qc_flag.value}.")

        return self

