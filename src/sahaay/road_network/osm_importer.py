"""
Sahaay AI - Phase A: OpenStreetMap Road Network Importer & Normalizer
(src/sahaay/road_network/osm_importer.py)

Provides a validated, auditable ingestion path for OpenStreetMap (OSM)
and municipal vector road network data:
- Geometry validity checks (WGS84 EPSG:4326 bounding box, minimum vertex count).
- OSM highway tag mapping to canonical RoadClassification.
- Directionality, one-way enforcement, and node connectivity.
- Duplicate identifier detection and rejection.
- Mandatory ODbL 1.0 license and attribution tracking.
- Decouples static network geometry from dynamic flood closures.
"""

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from sahaay.road_network.schemas import (
    RoadClassification,
    RoadMonitoringStatus,
    GeoJSONGeometryType,
    RoadGeometry,
    RoadSegment,
    HYDERABAD_MIN_LAT,
    HYDERABAD_MAX_LAT,
    HYDERABAD_MIN_LON,
    HYDERABAD_MAX_LON,
    validate_wgs84_coordinate,
)


# Standard OSM highway tag mapping
OSM_HIGHWAY_MAPPING: Dict[str, RoadClassification] = {
    "motorway": RoadClassification.MOTORWAY,
    "motorway_link": RoadClassification.MOTORWAY,
    "trunk": RoadClassification.TRUNK,
    "trunk_link": RoadClassification.TRUNK,
    "primary": RoadClassification.PRIMARY,
    "primary_link": RoadClassification.PRIMARY,
    "secondary": RoadClassification.SECONDARY,
    "secondary_link": RoadClassification.SECONDARY,
    "tertiary": RoadClassification.TERTIARY,
    "tertiary_link": RoadClassification.TERTIARY,
    "residential": RoadClassification.RESIDENTIAL,
    "living_street": RoadClassification.RESIDENTIAL,
    "unclassified": RoadClassification.UNCLASSIFIED,
    "service": RoadClassification.SERVICE,
}


class OSMImportValidationIssue(BaseModel):
    """Auditable log of validation errors or warnings during normalization."""
    element_id: str
    issue_type: str  # ERROR, WARNING
    code: str
    message: str


class OSMImportResult(BaseModel):
    """Summary of an OSM or municipal road network import batch."""
    import_timestamp_utc: str
    source_name: str
    source_license: str
    source_attribution: str
    total_records_processed: int
    valid_segments_imported: int
    invalid_records_rejected: int
    imported_segments: List[RoadSegment] = Field(default_factory=list)
    validation_issues: List[OSMImportValidationIssue] = Field(default_factory=list)
    bounding_box_observed: Optional[Dict[str, float]] = None


class OSMNetworkImporter:
    """Normalizes and imports OpenStreetMap road data into canonical RoadSegment models."""

    def __init__(self, default_zone: str = "Central Zone"):
        self.default_zone = default_zone
        self.attribution = "© OpenStreetMap contributors, ODbL 1.0"
        self.license = "ODbL-1.0"

    def normalize_osm_feature(
        self,
        raw_feature: Dict[str, Any],
        seen_ids: set,
    ) -> Tuple[Optional[RoadSegment], List[OSMImportValidationIssue]]:
        """
        Normalizes a single GeoJSON Feature or OSM way record into a canonical RoadSegment.
        Enforces coordinate validation, duplicate rejection, and connectivity extraction.
        """
        issues: List[OSMImportValidationIssue] = []

        # 1. Identifier extraction
        elem_id = str(
            raw_feature.get("id")
            or raw_feature.get("properties", {}).get("osm_id")
            or raw_feature.get("properties", {}).get("segment_id")
            or ""
        ).strip()

        if not elem_id:
            issues.append(
                OSMImportValidationIssue(
                    element_id="UNKNOWN",
                    issue_type="ERROR",
                    code="MISSING_IDENTIFIER",
                    message="Road feature missing unique identifier (id or osm_id)",
                )
            )
            return None, issues

        if elem_id in seen_ids:
            issues.append(
                OSMImportValidationIssue(
                    element_id=elem_id,
                    issue_type="ERROR",
                    code="DUPLICATE_IDENTIFIER",
                    message=f"Duplicate segment ID '{elem_id}' detected; rejecting to preserve topology",
                )
            )
            return None, issues

        # 2. Geometry parsing and validation
        geom_raw = raw_feature.get("geometry", {})
        geom_type_str = geom_raw.get("type", "")
        raw_coords = geom_raw.get("coordinates", [])

        if geom_type_str not in ["LineString", "MultiLineString"]:
            issues.append(
                OSMImportValidationIssue(
                    element_id=elem_id,
                    issue_type="ERROR",
                    code="UNSUPPORTED_GEOMETRY_TYPE",
                    message=f"Road segments must be LineString or MultiLineString, got '{geom_type_str}'",
                )
            )
            return None, issues

        validated_coords = []
        try:
            if geom_type_str == "LineString":
                if len(raw_coords) < 2:
                    raise ValueError(f"LineString requires >= 2 points, found {len(raw_coords)}")
                for pt in raw_coords:
                    lon, lat = validate_wgs84_coordinate(float(pt[0]), float(pt[1]))
                    validated_coords.append([lon, lat])
                geom = RoadGeometry(type=GeoJSONGeometryType.LINESTRING, coordinates=validated_coords)

            elif geom_type_str == "MultiLineString":
                multi_coords = []
                for line in raw_coords:
                    if len(line) < 2:
                        continue
                    line_pts = []
                    for pt in line:
                        lon, lat = validate_wgs84_coordinate(float(pt[0]), float(pt[1]))
                        line_pts.append([lon, lat])
                    multi_coords.append(line_pts)
                if not multi_coords:
                    raise ValueError("MultiLineString has no valid lines")
                geom = RoadGeometry(type=GeoJSONGeometryType.MULTILINESTRING, coordinates=multi_coords)

        except Exception as e:
            issues.append(
                OSMImportValidationIssue(
                    element_id=elem_id,
                    issue_type="ERROR",
                    code="INVALID_GEOMETRY_COORDINATES",
                    message=f"Coordinate validation failed: {str(e)}",
                )
            )
            return None, issues

        # 3. Tags & Properties extraction
        props = raw_feature.get("properties", {})
        road_name = str(props.get("name") or props.get("road_name") or f"Unnamed Road ({elem_id})").strip()

        # Highway classification
        highway_tag = str(props.get("highway") or "unclassified").lower()
        road_class = OSM_HIGHWAY_MAPPING.get(highway_tag, RoadClassification.UNCLASSIFIED)

        # Directionality
        oneway_val = str(props.get("oneway", "no")).lower()
        is_one_way = oneway_val in ["yes", "1", "true"]

        from_node = props.get("from_node_id") or props.get("from_node")
        to_node = props.get("to_node_id") or props.get("to_node")

        # Speed limit & lanes
        speed_limit = None
        maxspeed_val = props.get("maxspeed")
        if maxspeed_val:
            try:
                speed_limit = int(str(maxspeed_val).replace("km/h", "").replace("kph", "").strip())
            except ValueError:
                issues.append(
                    OSMImportValidationIssue(
                        element_id=elem_id,
                        issue_type="WARNING",
                        code="UNPARSED_MAXSPEED",
                        message=f"Could not parse maxspeed: {maxspeed_val}",
                    )
                )

        lanes = None
        lanes_val = props.get("lanes")
        if lanes_val:
            try:
                lanes = int(lanes_val)
            except ValueError:
                pass

        # Estimate length in meters using equirectangular approximation
        length_meters = 0.0
        if geom_type_str == "LineString":
            for i in range(len(validated_coords) - 1):
                p1 = validated_coords[i]
                p2 = validated_coords[i + 1]
                # dLat, dLon in radians
                lat1_rad, lat2_rad = math.radians(p1[1]), math.radians(p2[1])
                d_lat = math.radians(p2[1] - p1[1])
                d_lon = math.radians(p2[0] - p1[0])
                # Equirectangular approximation around 17.4 degrees
                x = d_lon * math.cos((lat1_rad + lat2_rad) / 2.0)
                y = d_lat
                length_meters += 6371000.0 * math.sqrt(x * x + y * y)

        length_meters = round(length_meters, 1) if length_meters > 0 else 100.0

        # Provenance hash
        prov_str = f"{elem_id}_{road_name}_{geom_type_str}_{len(raw_coords)}"
        prov_hash = hashlib.sha256(prov_str.encode("utf-8")).hexdigest()

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Check monitoring status (defaults to unmonitored general network)
        monitoring_status = (
            RoadMonitoringStatus.MONITORED_CORRIDOR
            if props.get("corridor_id") or elem_id.startswith("HYD-LOC-")
            else RoadMonitoringStatus.UNMONITORED_NETWORK
        )

        segment = RoadSegment(
            segment_id=elem_id,
            road_name=road_name,
            corridor_id=props.get("corridor_id"),
            zone=props.get("zone", self.default_zone),
            road_class=road_class,
            geometry=geom,
            is_one_way=is_one_way,
            from_node_id=str(from_node) if from_node else None,
            to_node_id=str(to_node) if to_node else None,
            length_meters=length_meters,
            speed_limit_kph=speed_limit,
            lanes_count=lanes,
            monitoring_status=monitoring_status,
            source_provider="OpenStreetMap Contributors (via Sahaay Normalizer)",
            source_license=self.license,
            source_attribution=self.attribution,
            retrieval_timestamp_utc=now_iso,
            provenance_hash=prov_hash,
            is_valid_geometry=True,
            validation_notes=[f"OSM tag: highway={highway_tag}"] if highway_tag else [],
        )

        return segment, issues

    def import_geojson_features(
        self,
        geojson_data: Dict[str, Any],
        source_name: str = "OpenStreetMap_Extract_Hyderabad",
    ) -> OSMImportResult:
        """
        Parses and validates a GeoJSON FeatureCollection of road segments.
        Ensures atomic validation, error tracking, and attribution enforcement.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        features = geojson_data.get("features", [])

        imported: List[RoadSegment] = []
        all_issues: List[OSMImportValidationIssue] = []
        seen_ids: set = set()

        lons, lats = [], []

        for feat in features:
            seg, issues = self.normalize_osm_feature(feat, seen_ids)
            all_issues.extend(issues)
            if seg is not None:
                seen_ids.add(seg.segment_id)
                imported.append(seg)
                # track bbox
                if seg.geometry.type == GeoJSONGeometryType.LINESTRING:
                    for pt in seg.geometry.coordinates:
                        lons.append(pt[0])
                        lats.append(pt[1])

        bbox_observed = None
        if lons and lats:
            bbox_observed = {
                "min_lon": min(lons),
                "max_lon": max(lons),
                "min_lat": min(lats),
                "max_lat": max(lats),
            }

        return OSMImportResult(
            import_timestamp_utc=now_iso,
            source_name=source_name,
            source_license=self.license,
            source_attribution=self.attribution,
            total_records_processed=len(features),
            valid_segments_imported=len(imported),
            invalid_records_rejected=len(features) - len(imported),
            imported_segments=imported,
            validation_issues=all_issues,
            bounding_box_observed=bbox_observed,
        )
