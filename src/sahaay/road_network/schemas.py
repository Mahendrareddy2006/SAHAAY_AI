"""
Sahaay AI - Phase A: Road Network & Geospatial Map Data Contracts
(src/sahaay/road_network/schemas.py)

Canonical schemas for:
- Static road network topology, corridors, and directed segments.
- GeoJSON-compliant geometric representations (EPSG:4326 / WGS84).
- Decoupling of immutable infrastructure attributes from dynamic flood observations.
- Provenance, licensing (ODbL 1.0), and verification status.
"""

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    RoadStatusSnapshot,
    MANDATORY_ROAD_SAFETY_NOTICE,
    FORBIDDEN_SAFETY_PHRASES,
)


class RoadClassification(str, Enum):
    """Categorical road classification derived from OpenStreetMap / Municipal GIS standards."""
    MOTORWAY = "motorway"
    TRUNK = "trunk"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    RESIDENTIAL = "residential"
    UNCLASSIFIED = "unclassified"
    SERVICE = "service"


class RoadMonitoringStatus(str, Enum):
    """Monitoring and surveillance tier for a road corridor or segment."""
    MONITORED_CORRIDOR = "MONITORED_CORRIDOR"           # Active hotspot with historical vulnerability index
    UNMONITORED_NETWORK = "UNMONITORED_NETWORK"         # Standard road network segment without active telemetry
    SURVEILLANCE_ACTIVE = "SURVEILLANCE_ACTIVE"         # Monitored via physical telemetry or camera
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"             # Mapped segment but condition unknown


class GeoJSONGeometryType(str, Enum):
    """Supported GeoJSON geometry primitives."""
    POINT = "Point"
    LINESTRING = "LineString"
    MULTILINESTRING = "MultiLineString"


# Hyderabad Metropolitan Geographic Bounding Box (WGS84 EPSG:4326)
HYDERABAD_MIN_LAT = 17.0
HYDERABAD_MAX_LAT = 17.8
HYDERABAD_MIN_LON = 78.1
HYDERABAD_MAX_LON = 78.8

MANDATORY_MAP_DATA_DISCLAIMER = (
    "MAP ADVISORY NOTICE: Sahaay AI road geometries and condition markers are advisory indicators. "
    "Absence of reported waterlogging on a corridor DOES NOT imply safe passage or dry pavement. "
    "Drivers must exercise discretion and comply with on-ground Hyderabad Traffic Police directives."
)


def validate_wgs84_coordinate(lon: float, lat: float) -> Tuple[float, float]:
    """Validates that a coordinate pair lies within Hyderabad metropolitan bounds."""
    if not (HYDERABAD_MIN_LON <= lon <= HYDERABAD_MAX_LON):
        raise ValueError(
            f"Longitude {lon} is outside Hyderabad bounds [{HYDERABAD_MIN_LON}, {HYDERABAD_MAX_LON}]"
        )
    if not (HYDERABAD_MIN_LAT <= lat <= HYDERABAD_MAX_LAT):
        raise ValueError(
            f"Latitude {lat} is outside Hyderabad bounds [{HYDERABAD_MIN_LAT}, {HYDERABAD_MAX_LAT}]"
        )
    return lon, lat


class RoadGeometry(BaseModel):
    """
    GeoJSON-compliant geometry representation in WGS84 (EPSG:4326).
    Coordinates format:
    - Point: [lon, lat]
    - LineString: [[lon1, lat1], [lon2, lat2], ...]
    - MultiLineString: [[[lon, lat], ...], ...]
    """
    type: GeoJSONGeometryType
    coordinates: Union[List[float], List[List[float]], List[List[List[float]]]]

    @model_validator(mode="after")
    def validate_geometry_coordinates(self) -> "RoadGeometry":
        geom_type = self.type
        coords = self.coordinates

        if geom_type == GeoJSONGeometryType.POINT:
            if not isinstance(coords, list) or len(coords) < 2:
                raise ValueError("Point coordinates must contain at least [longitude, latitude]")
            validate_wgs84_coordinate(float(coords[0]), float(coords[1]))

        elif geom_type == GeoJSONGeometryType.LINESTRING:
            if not isinstance(coords, list) or len(coords) < 2:
                raise ValueError("LineString must contain at least 2 coordinate pairs [[lon, lat], ...]")
            for pair in coords:
                if not isinstance(pair, list) or len(pair) < 2:
                    raise ValueError(f"Invalid coordinate pair in LineString: {pair}")
                validate_wgs84_coordinate(float(pair[0]), float(pair[1]))

        elif geom_type == GeoJSONGeometryType.MULTILINESTRING:
            if not isinstance(coords, list) or len(coords) < 1:
                raise ValueError("MultiLineString must contain at least one LineString coordinate array")
            for line in coords:
                if not isinstance(line, list) or len(line) < 2:
                    raise ValueError("Each line in MultiLineString must contain at least 2 coordinate pairs")
                for pair in line:
                    if not isinstance(pair, list) or len(pair) < 2:
                        raise ValueError(f"Invalid coordinate pair in MultiLineString: {pair}")
                    validate_wgs84_coordinate(float(pair[0]), float(pair[1]))

        return self


class RoadSegment(BaseModel):
    """
    Canonical static road network segment model.
    Decoupled from dynamic weather/flood observations.
    Represents permanent physical infrastructure.
    """
    segment_id: str = Field(..., min_length=3, max_length=64, description="Unique segment identifier e.g. HYD-LOC-001 or OSM-WAY-10293")
    road_name: str = Field(..., min_length=2, max_length=150, description="Common or official road name")
    corridor_id: Optional[str] = Field(None, description="Associated corridor ID e.g. HYD-LOC-001")
    zone: Optional[str] = Field(None, description="Municipal zone e.g. West Zone, Central Zone")
    road_class: RoadClassification = RoadClassification.PRIMARY
    geometry: RoadGeometry

    # Directionality & Connectivity
    is_one_way: bool = False
    from_node_id: Optional[str] = None
    to_node_id: Optional[str] = None
    connected_segment_ids: List[str] = Field(default_factory=list)
    length_meters: Optional[float] = Field(None, ge=1.0, le=100000.0)
    speed_limit_kph: Optional[int] = Field(None, ge=10, le=140)
    lanes_count: Optional[int] = Field(None, ge=1, le=12)

    # Static Topographic / Drainage Vulnerability (Baseline Infrastructure)
    static_vulnerability_index: Optional[float] = Field(None, ge=0.0, le=1.0)
    static_vulnerability_category: Optional[str] = Field(None, description="LOW, MODERATE, HIGH, SEVERE")
    elevation_min_m: Optional[float] = None
    elevation_max_m: Optional[float] = None

    # Monitoring & Provenance
    monitoring_status: RoadMonitoringStatus = RoadMonitoringStatus.MONITORED_CORRIDOR
    source_provider: str = Field("SAHAAY_BASE_CORRIDOR_CATALOG", description="OpenStreetMap, GHMC GIS, or Base Catalog")
    source_license: str = Field("ODbL-1.0", description="Open Database License 1.0 or municipal attribution")
    source_attribution: str = Field("© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project")
    retrieval_timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    provenance_hash: Optional[str] = None

    # Validation
    is_valid_geometry: bool = True
    validation_notes: List[str] = Field(default_factory=list)

    @field_validator("road_name")
    @classmethod
    def validate_safety_language(cls, v: str) -> str:
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v.lower():
                raise ValueError(f"Road name cannot contain misleading safety claim: '{phrase}'")
        return v


class RoadSegmentMapProperties(BaseModel):
    """
    Combined map feature properties fusing static road metadata
    with current live road status snapshot for map rendering.
    """
    segment_id: str
    corridor_id: Optional[str] = None
    road_name: str
    zone: Optional[str] = None
    road_class: str
    is_one_way: bool = False
    length_meters: Optional[float] = None
    monitoring_status: str

    # Static Susceptibility (Physical Baseline)
    static_vulnerability_index: Optional[float] = None
    static_vulnerability_category: Optional[str] = None

    # Dynamic Road Status (Live Observation)
    condition_state: RoadConditionState = RoadConditionState.UNKNOWN
    evidence_type: RoadEvidenceType = RoadEvidenceType.NO_EVIDENCE
    freshness_category: RoadFreshnessCategory = RoadFreshnessCategory.UNKNOWN
    verification_state: RoadVerificationState = RoadVerificationState.UNMONITORED
    uncertainty_level: UncertaintyLevel = UncertaintyLevel.HIGH
    confidence_score: float = 0.0

    # Flood specifics
    measured_water_depth_cm: Optional[float] = None
    has_conflicting_evidence: bool = False
    last_status_update_utc: Optional[str] = None
    evidence_age_minutes: Optional[float] = None

    # Map Symbology Styling Directives
    marker_color: str = "#64748b"        # Hex color code for UI
    stroke_style: str = "dashed"         # solid, dashed, pulse
    stroke_weight: int = 4               # line width in px
    alert_badge: str = "UNKNOWN"

    # Mandatory Disclaimers
    safety_notice: str = MANDATORY_ROAD_SAFETY_NOTICE
    disclaimer: str = MANDATORY_MAP_DATA_DISCLAIMER

    # Phase D: Canonical Corridor Evidence Integration
    evidence_state: Optional[str] = None
    evidence_explanation: Optional[str] = None
    evidence_sufficiency: Optional[str] = None
    has_unresolved_conflicts: bool = False
    observed_rainfall_1h_mm: Optional[float] = None
    forecast_precipitation_band: Optional[str] = None
    vision_state: Optional[str] = None
    vision_confidence: Optional[float] = None
    vision_is_provisional: bool = True
    coverage_warning: str = "SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE"


class RoadSegmentMapFeature(BaseModel):
    """GeoJSON Feature representing a single road segment with fused map properties."""
    type: str = "Feature"
    id: str
    geometry: RoadGeometry
    properties: RoadSegmentMapProperties


class RoadNetworkFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection representing all road network segments and overlays."""
    type: str = "FeatureCollection"
    features: List[RoadSegmentMapFeature]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MapCoverageReport(BaseModel):
    """Summary of geospatial map coverage, monitored corridors, and licensing."""
    generated_at_utc: str
    total_segments_mapped: int
    monitored_corridors_count: int
    unmonitored_segments_count: int
    total_centerline_length_km: float
    bounding_box: Dict[str, float]
    source_attribution: str
    source_license: str
    coverage_status: str
    data_freshness_summary: Dict[str, int]
    condition_state_summary: Dict[str, int]
    disclaimer: str = MANDATORY_MAP_DATA_DISCLAIMER
