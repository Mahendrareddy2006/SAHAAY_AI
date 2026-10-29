"""
Sahaay AI - Phase A: Road Network Store & Map Feature Generator
(src/sahaay/road_network/store.py)

Manages road network segment catalog, coordinates, connectivity graph,
and synthesizes GeoJSON feature collections for live map visualization.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import threading

from sahaay.road_network.schemas import (
    RoadClassification,
    RoadMonitoringStatus,
    GeoJSONGeometryType,
    RoadGeometry,
    RoadSegment,
    RoadSegmentMapProperties,
    RoadSegmentMapFeature,
    RoadNetworkFeatureCollection,
    MapCoverageReport,
    HYDERABAD_MIN_LAT,
    HYDERABAD_MAX_LAT,
    HYDERABAD_MIN_LON,
    HYDERABAD_MAX_LON,
    MANDATORY_MAP_DATA_DISCLAIMER,
)
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    RoadStatusSnapshot,
    MANDATORY_ROAD_SAFETY_NOTICE,
)
from sahaay.road_status.service import default_road_status_service


def calculate_symbology(
    condition_state: RoadConditionState,
    freshness: RoadFreshnessCategory,
    verification: RoadVerificationState,
    monitoring_status: RoadMonitoringStatus,
) -> Dict[str, Any]:
    """
    Computes visual map styling based on strict safety hierarchy:
    - Never renders unknown/unmonitored roads in the same style as verified passable roads.
    - Accentuates verified impassable segments with high-visibility crimson red.
    - Explicitly distinguishes unverified reports with dashed amber styling.
    - Visualizes stale/expired conditions with muted warning styling.
    """
    if condition_state == RoadConditionState.VERIFIED_IMPASSABLE:
        return {
            "marker_color": "#e11d48",       # Crimson Red
            "stroke_style": "solid",
            "stroke_weight": 6,
            "alert_badge": "IMPASSABLE"
        }
    elif condition_state == RoadConditionState.VERIFIED_WATERLOGGED:
        return {
            "marker_color": "#f97316",       # Deep Orange
            "stroke_style": "solid",
            "stroke_weight": 5,
            "alert_badge": "WATERLOGGED"
        }
    elif condition_state == RoadConditionState.VERIFIED_PASSABLE:
        return {
            "marker_color": "#10b981",       # Emerald Green
            "stroke_style": "solid",
            "stroke_weight": 4,
            "alert_badge": "PASSABLE"
        }
    elif condition_state == RoadConditionState.CONFLICTING:
        return {
            "marker_color": "#a855f7",       # Purple / Magenta
            "stroke_style": "dashed",
            "stroke_weight": 4,
            "alert_badge": "CONFLICTING"
        }
    elif condition_state == RoadConditionState.CORROBORATED:
        return {
            "marker_color": "#f97316",       # Orange
            "stroke_style": "dashed",
            "stroke_weight": 4,
            "alert_badge": "CORROBORATED"
        }
    elif condition_state == RoadConditionState.UNVERIFIED:
        return {
            "marker_color": "#f59e0b",       # Amber
            "stroke_style": "dashed",
            "stroke_weight": 3,
            "alert_badge": "UNVERIFIED"
        }
    elif freshness in {RoadFreshnessCategory.STALE, RoadFreshnessCategory.EXPIRED} or condition_state in {RoadConditionState.STALE, RoadConditionState.EXPIRED}:
        return {
            "marker_color": "#78716c",       # Muted Stone/Brown
            "stroke_style": "dashed",
            "stroke_weight": 3,
            "alert_badge": "STALE_DATA"
        }
    else:
        # UNKNOWN or NO_CURRENT_EVIDENCE or UNMONITORED
        return {
            "marker_color": "#64748b",       # Slate Gray (Neutral Unknown)
            "stroke_style": "dashed",
            "stroke_weight": 3,
            "alert_badge": "UNKNOWN"
        }


class RoadNetworkStore:
    """Thread-safe store of road network segments, geometry vectors, and map overlays."""

    def __init__(self, populate_defaults: bool = True):
        self._lock = threading.Lock()
        self._segments: Dict[str, RoadSegment] = {}
        if populate_defaults:
            self._initialize_canonical_corridors()

    def clear(self) -> None:
        """Clears all stored segments for testing empty/unavailable state."""
        with self._lock:
            self._segments.clear()

    def _initialize_canonical_corridors(self):
        """
        Pre-populates the 20 primary Hyderabad monitored corridors with canonical
        LineString geometries along real street vectors, plus representative unmonitored links.
        """
        raw_corridors = [
            # 1. Tolichowki Flyover Underpass
            {
                "segment_id": "HYD-LOC-001",
                "road_name": "Tolichowki Flyover Underpass (Old Mumbai Hwy)",
                "corridor_id": "HYD-LOC-001",
                "zone": "West Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4060, 17.3995], [78.4112, 17.4023], [78.4165, 17.4050]],
                "from_node_id": "NODE-RETHIBOWLI",
                "to_node_id": "NODE-SHAIKPET-ENTRY",
                "length_meters": 1280.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.532,
                "vulnerability_category": "HIGH",
            },
            # 2. Shaikpet Nala Road
            {
                "segment_id": "HYD-LOC-002",
                "road_name": "Shaikpet Nala Road",
                "corridor_id": "HYD-LOC-002",
                "zone": "West Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.3940, 17.4060], [78.3986, 17.4095], [78.4030, 17.4130]],
                "from_node_id": "NODE-SHAIKPET-ENTRY",
                "to_node_id": "NODE-OU-COLONY",
                "length_meters": 1150.0,
                "speed_limit_kph": 50,
                "lanes_count": 4,
                "vulnerability_index": 0.371,
                "vulnerability_category": "MODERATE",
            },
            # 3. Begumpet Rasoolpura Underpass
            {
                "segment_id": "HYD-LOC-003",
                "road_name": "Begumpet Rasoolpura Underpass (SP Road)",
                "corridor_id": "HYD-LOC-003",
                "zone": "North Zone",
                "road_class": RoadClassification.TRUNK,
                "coordinates": [[78.4670, 17.4390], [78.4728, 17.4419], [78.4785, 17.4450]],
                "from_node_id": "NODE-BEGUMPET-STN",
                "to_node_id": "NODE-RASOOLPURA-X",
                "length_meters": 1340.0,
                "speed_limit_kph": 60,
                "lanes_count": 6,
                "vulnerability_index": 0.0,
                "vulnerability_category": "LOW",
            },
            # 4. Khairatabad Flyover Junction
            {
                "segment_id": "HYD-LOC-004",
                "road_name": "Khairatabad Flyover Junction (Raj Bhavan Rd)",
                "corridor_id": "HYD-LOC-004",
                "zone": "Central Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4560, 17.4080], [78.4611, 17.4116], [78.4660, 17.4150]],
                "from_node_id": "NODE-LAKDIKAPUL-N",
                "to_node_id": "NODE-RAJBHAVAN-S",
                "length_meters": 1220.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.328,
                "vulnerability_category": "MODERATE",
            },
            # 5. Malakpet Railway Underbridge
            {
                "segment_id": "HYD-LOC-005",
                "road_name": "Malakpet Railway Underbridge (RUB)",
                "corridor_id": "HYD-LOC-005",
                "zone": "South Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4920, 17.3735], [78.4975, 17.3768], [78.5030, 17.3800]],
                "from_node_id": "NODE-CHADERGHAT",
                "to_node_id": "NODE-MALAKPET-GUNJ",
                "length_meters": 1180.0,
                "speed_limit_kph": 40,
                "lanes_count": 4,
                "vulnerability_index": 0.379,
                "vulnerability_category": "MODERATE",
            },
            # 6. Panjagutta Underpass & Nagarjuna Circle
            {
                "segment_id": "HYD-LOC-006",
                "road_name": "Panjagutta Underpass & Nagarjuna Circle",
                "corridor_id": "HYD-LOC-006",
                "zone": "Central Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4470, 17.4230], [78.4518, 17.4262], [78.4565, 17.4295]],
                "from_node_id": "NODE-BANJARA-HILLS-RD1",
                "to_node_id": "NODE-AMEERPET-S",
                "length_meters": 1100.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.412,
                "vulnerability_category": "MODERATE",
            },
            # 7. Gachibowli Bio-Diversity Junction
            {
                "segment_id": "HYD-LOC-007",
                "road_name": "Gachibowli Bio-Diversity Flyover Underpass",
                "corridor_id": "HYD-LOC-007",
                "zone": "West Zone",
                "road_class": RoadClassification.TRUNK,
                "coordinates": [[78.3600, 17.4395], [78.3654, 17.4428], [78.3710, 17.4460]],
                "from_node_id": "NODE-GACHIBOWLI-ORR",
                "to_node_id": "NODE-RAIDURGAM",
                "length_meters": 1320.0,
                "speed_limit_kph": 60,
                "lanes_count": 6,
                "vulnerability_index": 0.205,
                "vulnerability_category": "MODERATE",
            },
            # 8. Lakdikapul Junction & Railway Bridge
            {
                "segment_id": "HYD-LOC-008",
                "road_name": "Lakdikapul Junction & Railway Bridge",
                "corridor_id": "HYD-LOC-008",
                "zone": "Central Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4600, 17.4010], [78.4651, 17.4042], [78.4700, 17.4075]],
                "from_node_id": "NODE-MEHDIPATNAM-N",
                "to_node_id": "NODE-SECRETARIAT-W",
                "length_meters": 1160.0,
                "speed_limit_kph": 40,
                "lanes_count": 6,
                "vulnerability_index": 0.392,
                "vulnerability_category": "MODERATE",
            },
            # 9. Secunderabad Clock Tower Subway
            {
                "segment_id": "HYD-LOC-009",
                "road_name": "Secunderabad Clock Tower Subway",
                "corridor_id": "HYD-LOC-009",
                "zone": "North Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4950, 17.4400], [78.4998, 17.4431], [78.5045, 17.4465]],
                "from_node_id": "NODE-SECUNDERABAD-STN",
                "to_node_id": "NODE-PATNY-CIRCLE",
                "length_meters": 1120.0,
                "speed_limit_kph": 40,
                "lanes_count": 4,
                "vulnerability_index": 0.0,
                "vulnerability_category": "LOW",
            },
            # 10. Musarambagh Bridge Causeway
            {
                "segment_id": "HYD-LOC-010",
                "road_name": "Musarambagh Bridge Causeway (Musi River)",
                "corridor_id": "HYD-LOC-010",
                "zone": "East Zone",
                "road_class": RoadClassification.SECONDARY,
                "coordinates": [[78.5040, 17.3680], [78.5085, 17.3712], [78.5130, 17.3745]],
                "from_node_id": "NODE-AMBERPET-S",
                "to_node_id": "NODE-MALAKPET-E",
                "length_meters": 1050.0,
                "speed_limit_kph": 40,
                "lanes_count": 2,
                "vulnerability_index": 0.158,
                "vulnerability_category": "LOW",
            },
            # 11. Madhapur Cyber Towers Corridor
            {
                "segment_id": "HYD-LOC-011",
                "road_name": "Madhapur Cyber Towers Hitec City Main Rd",
                "corridor_id": "HYD-LOC-011",
                "zone": "West Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.3760, 17.4470], [78.3808, 17.4504], [78.3860, 17.4540]],
                "from_node_id": "NODE-HITEC-STN",
                "to_node_id": "NODE-JUBILEE-CHECKPOST",
                "length_meters": 1250.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.035,
                "vulnerability_category": "LOW",
            },
            # 12. Dilsukhnagar Bus Depot Main Road
            {
                "segment_id": "HYD-LOC-012",
                "road_name": "Dilsukhnagar Bus Depot Main Road (NH 65)",
                "corridor_id": "HYD-LOC-012",
                "zone": "East Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.5195, 17.3650], [78.5247, 17.3688], [78.5300, 17.3725]],
                "from_node_id": "NODE-MALAKPET-E",
                "to_node_id": "NODE-CHAITANYAPURI",
                "length_meters": 1200.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.155,
                "vulnerability_category": "LOW",
            },
            # 13. Ameerpet Metro Junction
            {
                "segment_id": "HYD-LOC-013",
                "road_name": "Ameerpet Metro Junction Underpass",
                "corridor_id": "HYD-LOC-013",
                "zone": "Central Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4430, 17.4340], [78.4482, 17.4375], [78.4530, 17.4410]],
                "from_node_id": "NODE-PANJAGUTTA-N",
                "to_node_id": "NODE-SR-NAGAR",
                "length_meters": 1150.0,
                "speed_limit_kph": 40,
                "lanes_count": 6,
                "vulnerability_index": 0.284,
                "vulnerability_category": "MODERATE",
            },
            # 14. Moosarambagh to Amberpet Nala Link
            {
                "segment_id": "HYD-LOC-014",
                "road_name": "Moosarambagh to Amberpet Nala Link",
                "corridor_id": "HYD-LOC-014",
                "zone": "Central Zone",
                "road_class": RoadClassification.SECONDARY,
                "coordinates": [[78.5090, 17.3780], [78.5142, 17.3821], [78.5190, 17.3860]],
                "from_node_id": "NODE-MUSARAMBAGH-N",
                "to_node_id": "NODE-AMBERPET-MAIN",
                "length_meters": 1140.0,
                "speed_limit_kph": 40,
                "lanes_count": 4,
                "vulnerability_index": 0.033,
                "vulnerability_category": "LOW",
            },
            # 15. Miyapur Allwyn Junction
            {
                "segment_id": "HYD-LOC-015",
                "road_name": "Miyapur Allwyn Junction (NH 65)",
                "corridor_id": "HYD-LOC-015",
                "zone": "West Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.3495, 17.4930], [78.3548, 17.4965], [78.3600, 17.5000]],
                "from_node_id": "NODE-CHANDANAGAR",
                "to_node_id": "NODE-MIYAPUR-METRO",
                "length_meters": 1220.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.368,
                "vulnerability_category": "MODERATE",
            },
            # 16. Uppal Ring Road Junction
            {
                "segment_id": "HYD-LOC-016",
                "road_name": "Uppal Ring Road Inner Junction",
                "corridor_id": "HYD-LOC-016",
                "zone": "East Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.5550, 17.3980], [78.5602, 17.4018], [78.5655, 17.4055]],
                "from_node_id": "NODE-RAMANTHAPUR",
                "to_node_id": "NODE-UPPAL-METRO",
                "length_meters": 1280.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.072,
                "vulnerability_category": "LOW",
            },
            # 17. Bowenpally Check Post
            {
                "segment_id": "HYD-LOC-017",
                "road_name": "Bowenpally Check Post (NH 44)",
                "corridor_id": "HYD-LOC-017",
                "zone": "North Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4710, 17.4685], [78.4764, 17.4725], [78.4815, 17.4765]],
                "from_node_id": "NODE-TADBUND",
                "to_node_id": "NODE-MEDCHAL-HWY",
                "length_meters": 1200.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.054,
                "vulnerability_category": "LOW",
            },
            # 18. Mehdipatnam Rythu Bazaar Road
            {
                "segment_id": "HYD-LOC-018",
                "road_name": "Mehdipatnam Rythu Bazaar Road",
                "corridor_id": "HYD-LOC-018",
                "zone": "Central Zone",
                "road_class": RoadClassification.SECONDARY,
                "coordinates": [[78.4350, 17.3880], [78.4402, 17.3916], [78.4455, 17.3950]],
                "from_node_id": "NODE-RETHIBOWLI",
                "to_node_id": "NODE-MASAB-TANK",
                "length_meters": 1170.0,
                "speed_limit_kph": 40,
                "lanes_count": 4,
                "vulnerability_index": 0.052,
                "vulnerability_category": "LOW",
            },
            # 19. Balanagar Narasapur Cross Road
            {
                "segment_id": "HYD-LOC-019",
                "road_name": "Balanagar Narasapur Cross Road",
                "corridor_id": "HYD-LOC-019",
                "zone": "North Zone",
                "road_class": RoadClassification.PRIMARY,
                "coordinates": [[78.4415, 17.4650], [78.4468, 17.4691], [78.4520, 17.4730]],
                "from_node_id": "NODE-FATEH-NAGAR",
                "to_node_id": "NODE-JEEDIMETLA",
                "length_meters": 1210.0,
                "speed_limit_kph": 50,
                "lanes_count": 6,
                "vulnerability_index": 0.0,
                "vulnerability_category": "LOW",
            },
            # 20. Alwal Rythu Bazaar Low-Lying Area
            {
                "segment_id": "HYD-LOC-020",
                "road_name": "Alwal Rythu Bazaar Low-Lying Area",
                "corridor_id": "HYD-LOC-020",
                "zone": "North Zone",
                "road_class": RoadClassification.SECONDARY,
                "coordinates": [[78.4980, 17.4985], [78.5031, 17.5024], [78.5080, 17.5060]],
                "from_node_id": "NODE-LOTHKUNTA",
                "to_node_id": "NODE-ALWAL-HILLS",
                "length_meters": 1130.0,
                "speed_limit_kph": 40,
                "lanes_count": 2,
                "vulnerability_index": 0.369,
                "vulnerability_category": "MODERATE",
            },
            # Unmonitored Residential / Connecting Segments (Testing boundary between monitored corridors and general road grid)
            {
                "segment_id": "HYD-SEG-UNMON-01",
                "road_name": "Rethibowli to Gudimalkapur Connecting Lane",
                "corridor_id": None,
                "zone": "Central Zone",
                "road_class": RoadClassification.RESIDENTIAL,
                "coordinates": [[78.4350, 17.3880], [78.4310, 17.3850], [78.4280, 17.3820]],
                "from_node_id": "NODE-RETHIBOWLI",
                "to_node_id": "NODE-GUDIMALKAPUR",
                "length_meters": 950.0,
                "speed_limit_kph": 30,
                "lanes_count": 2,
                "vulnerability_index": None,
                "vulnerability_category": None,
                "monitoring_status": RoadMonitoringStatus.UNMONITORED_NETWORK,
            },
            {
                "segment_id": "HYD-SEG-UNMON-02",
                "road_name": "Banjara Hills Road No 12 Interior Colony Link",
                "corridor_id": None,
                "zone": "Central Zone",
                "road_class": RoadClassification.RESIDENTIAL,
                "coordinates": [[78.4410, 17.4120], [78.4380, 17.4150], [78.4350, 17.4180]],
                "from_node_id": "NODE-BANJARA-RD12",
                "to_node_id": "NODE-FILMNAGAR",
                "length_meters": 820.0,
                "speed_limit_kph": 30,
                "lanes_count": 2,
                "vulnerability_index": None,
                "vulnerability_category": None,
                "monitoring_status": RoadMonitoringStatus.UNMONITORED_NETWORK,
            },
        ]

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        for item in raw_corridors:
            geom = RoadGeometry(
                type=GeoJSONGeometryType.LINESTRING,
                coordinates=item["coordinates"],
            )
            seg = RoadSegment(
                segment_id=item["segment_id"],
                road_name=item["road_name"],
                corridor_id=item.get("corridor_id"),
                zone=item.get("zone"),
                road_class=item.get("road_class", RoadClassification.PRIMARY),
                geometry=geom,
                from_node_id=item.get("from_node_id"),
                to_node_id=item.get("to_node_id"),
                length_meters=item.get("length_meters"),
                speed_limit_kph=item.get("speed_limit_kph"),
                lanes_count=item.get("lanes_count"),
                static_vulnerability_index=item.get("vulnerability_index"),
                static_vulnerability_category=item.get("vulnerability_category"),
                monitoring_status=item.get("monitoring_status", RoadMonitoringStatus.MONITORED_CORRIDOR),
                source_provider="SAHAAY_BASE_CORRIDOR_CATALOG",
                source_license="ODbL-1.0",
                source_attribution="© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project",
                retrieval_timestamp_utc=now_iso,
                is_valid_geometry=True,
                validation_notes=["Canonical Hyderabad baseline geometry verified"],
            )
            self._segments[seg.segment_id] = seg

    def get_segment(self, segment_id: str) -> Optional[RoadSegment]:
        with self._lock:
            return self._segments.get(segment_id)

    def list_segments(
        self,
        zone: Optional[str] = None,
        road_class: Optional[RoadClassification] = None,
        monitoring_status: Optional[RoadMonitoringStatus] = None,
    ) -> List[RoadSegment]:
        with self._lock:
            res = list(self._segments.values())
            if zone:
                res = [s for s in res if s.zone and s.zone.lower() == zone.lower()]
            if road_class:
                res = [s for s in res if s.road_class == road_class]
            if monitoring_status:
                res = [s for s in res if s.monitoring_status == monitoring_status]
            return res

    def find_nearest_segment_to_coords(
        self,
        lat: float,
        lon: float,
        max_distance_meters: float = 3000.0,
        ambiguity_threshold_meters: float = 10.0,
        return_metadata: bool = False,
    ) -> Any:
        """
        Finds the nearest road segment in the store catalog to the given coordinate.
        Validates coordinate bounds and physical validity.
        Returns None (or (None, inf, False) if return_metadata=True) if no segment is within max_distance_meters
        or if coordinates are invalid.
        """
        import math
        if lat is None or lon is None:
            return (None, float("inf"), False) if return_metadata else None
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (ValueError, TypeError):
            return (None, float("inf"), False) if return_metadata else None

        if math.isnan(lat_f) or math.isnan(lon_f) or math.isinf(lat_f) or math.isinf(lon_f):
            return (None, float("inf"), False) if return_metadata else None

        if not (-90.0 <= lat_f <= 90.0) or not (-180.0 <= lon_f <= 180.0):
            return (None, float("inf"), False) if return_metadata else None

        nearest_seg = None
        min_dist = float("inf")
        second_min_dist = float("inf")

        with self._lock:
            all_segs = list(self._segments.values())

        for seg in all_segs:
            coords = getattr(seg.geometry, "coordinates", []) or []
            seg_min_dist = float("inf")
            for pt in coords:
                if len(pt) >= 2:
                    p_lon, p_lat = pt[0], pt[1]
                    phi1 = math.radians(lat_f)
                    phi2 = math.radians(p_lat)
                    dphi = math.radians(p_lat - lat_f)
                    dlambda = math.radians(p_lon - lon_f)
                    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
                    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
                    dist_m = 6371000.0 * c
                    if dist_m < seg_min_dist:
                        seg_min_dist = dist_m

            if seg_min_dist < min_dist:
                second_min_dist = min_dist
                min_dist = seg_min_dist
                nearest_seg = seg
            elif seg_min_dist < second_min_dist:
                second_min_dist = seg_min_dist

        if min_dist <= max_distance_meters:
            is_ambiguous = (second_min_dist - min_dist) <= ambiguity_threshold_meters
            if return_metadata:
                return (nearest_seg, min_dist, is_ambiguous)
            return nearest_seg

        if return_metadata:
            return (None, min_dist, False)
        return None

    def add_segment(self, segment: RoadSegment) -> bool:
        """Adds or updates a validated road segment."""
        with self._lock:
            self._segments[segment.segment_id] = segment
            return True

    def build_map_feature(
        self,
        segment: RoadSegment,
        status_snapshot: Optional[RoadStatusSnapshot] = None,
        corridor_evidence: Optional[Any] = None,
    ) -> RoadSegmentMapFeature:
        """
        Synthesizes a GeoJSON Feature by combining static infrastructure
        metadata with an active RoadStatusSnapshot.
        """
        if status_snapshot is None:
            # Query Phase 16 service for corridor or return unknown default
            if segment.corridor_id:
                try:
                    status_snapshot = default_road_status_service.get_corridor_status(segment.corridor_id)
                except Exception:
                    status_snapshot = None

        if status_snapshot is not None:
            cond_state = status_snapshot.condition_state
            ev_type = status_snapshot.evidence_type
            freshness = status_snapshot.freshness_category
            ver_state = status_snapshot.verification_state
            uncertainty = status_snapshot.uncertainty_level
            conf = status_snapshot.confidence_score
            water_depth = status_snapshot.measured_water_depth_cm
            has_conflict = status_snapshot.has_conflicting_evidence
            last_update = status_snapshot.last_status_update_utc
            evidence_age = status_snapshot.evidence_age_minutes
        else:
            cond_state = RoadConditionState.UNKNOWN
            ev_type = RoadEvidenceType.NO_EVIDENCE
            freshness = RoadFreshnessCategory.UNKNOWN
            ver_state = RoadVerificationState.UNMONITORED
            uncertainty = UncertaintyLevel.HIGH
            conf = 0.0
            water_depth = None
            has_conflict = False
            last_update = None
            evidence_age = None

        # Phase D: Canonical Corridor Evidence Integration
        evidence_state = None
        evidence_expl = None
        evidence_suff = None
        unresolved_conflicts = has_conflict
        obs_rain_1h = None
        fc_band = None
        vis_state = None
        vis_conf = None
        vis_prov = True

        if corridor_evidence is not None:
            evidence_state = corridor_evidence.evidence_state.value if hasattr(corridor_evidence.evidence_state, "value") else str(corridor_evidence.evidence_state)
            evidence_expl = corridor_evidence.compact_explanation
            evidence_suff = corridor_evidence.evidence_sufficiency.value if hasattr(corridor_evidence.evidence_sufficiency, "value") else str(corridor_evidence.evidence_sufficiency)
            unresolved_conflicts = corridor_evidence.has_unresolved_conflicts
            obs_rain_1h = corridor_evidence.observed_rainfall.rainfall_1h_mm
            fc_band = corridor_evidence.forecast_rainfall.precipitation_band
            vis_state = corridor_evidence.vision_evidence.predicted_class
            vis_conf = corridor_evidence.vision_evidence.calibrated_confidence
            vis_prov = True
        elif segment.corridor_id:
            try:
                from sahaay.corridor_evidence.service import default_corridor_evidence_service
                cev = default_corridor_evidence_service.assess_corridor(
                    corridor_id=segment.corridor_id,
                    road_segment=segment,
                    road_status_snapshot=status_snapshot,
                )
                evidence_state = cev.evidence_state.value
                evidence_expl = cev.compact_explanation
                evidence_suff = cev.evidence_sufficiency.value
                unresolved_conflicts = cev.has_unresolved_conflicts
                obs_rain_1h = cev.observed_rainfall.rainfall_1h_mm
                fc_band = cev.forecast_rainfall.precipitation_band
                vis_state = cev.vision_evidence.predicted_class
                vis_conf = cev.vision_evidence.calibrated_confidence
                vis_prov = True
            except Exception:
                pass

        symbology = calculate_symbology(
            condition_state=cond_state,
            freshness=freshness,
            verification=ver_state,
            monitoring_status=segment.monitoring_status,
        )

        props = RoadSegmentMapProperties(
            segment_id=segment.segment_id,
            corridor_id=segment.corridor_id,
            road_name=segment.road_name,
            zone=segment.zone,
            road_class=segment.road_class.value,
            is_one_way=segment.is_one_way,
            length_meters=segment.length_meters,
            monitoring_status=segment.monitoring_status.value,
            static_vulnerability_index=segment.static_vulnerability_index,
            static_vulnerability_category=segment.static_vulnerability_category,
            condition_state=cond_state,
            evidence_type=ev_type,
            freshness_category=freshness,
            verification_state=ver_state,
            uncertainty_level=uncertainty,
            confidence_score=conf,
            measured_water_depth_cm=water_depth,
            has_conflicting_evidence=unresolved_conflicts,
            last_status_update_utc=last_update,
            evidence_age_minutes=evidence_age,
            marker_color=symbology["marker_color"],
            stroke_style=symbology["stroke_style"],
            stroke_weight=symbology["stroke_weight"],
            alert_badge=symbology["alert_badge"],
            evidence_state=evidence_state,
            evidence_explanation=evidence_expl,
            evidence_sufficiency=evidence_suff,
            has_unresolved_conflicts=unresolved_conflicts,
            observed_rainfall_1h_mm=obs_rain_1h,
            forecast_precipitation_band=fc_band,
            vision_state=vis_state,
            vision_confidence=vis_conf,
            vision_is_provisional=vis_prov,
        )

        return RoadSegmentMapFeature(
            type="Feature",
            id=segment.segment_id,
            geometry=segment.geometry,
            properties=props,
        )

    def to_geojson_feature_collection(self) -> RoadNetworkFeatureCollection:
        """Exports the full network as a valid GeoJSON FeatureCollection."""
        features: List[RoadSegmentMapFeature] = []
        with self._lock:
            all_segs = list(self._segments.values())

        for seg in all_segs:
            features.append(self.build_map_feature(seg))

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        metadata = {
            "title": "Sahaay AI — Hyderabad Live Map & Road Network Overlays",
            "generated_at_utc": now_iso,
            "total_features": len(features),
            "crs": "EPSG:4326 (WGS84)",
            "source_license": "ODbL-1.0",
            "source_attribution": "© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project",
            "disclaimer": MANDATORY_MAP_DATA_DISCLAIMER,
        }

        return RoadNetworkFeatureCollection(
            type="FeatureCollection",
            features=features,
            metadata=metadata,
        )

    def get_coverage_report(self) -> MapCoverageReport:
        """Computes network coverage metrics, total kilometers, and condition summary."""
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            all_segs = list(self._segments.values())

        total_km = sum((s.length_meters or 0.0) for s in all_segs) / 1000.0
        monitored = sum(1 for s in all_segs if s.monitoring_status == RoadMonitoringStatus.MONITORED_CORRIDOR)
        unmonitored = len(all_segs) - monitored

        freshness_counts: Dict[str, int] = {}
        condition_counts: Dict[str, int] = {}

        for s in all_segs:
            feat = self.build_map_feature(s)
            c = feat.properties.condition_state.value
            f = feat.properties.freshness_category.value
            condition_counts[c] = condition_counts.get(c, 0) + 1
            freshness_counts[f] = freshness_counts.get(f, 0) + 1

        coverage_status = "EMPTY_OR_UNAVAILABLE" if not all_segs else "BASELINE_CANDIDATE_CORRIDORS_MAPPED"
        return MapCoverageReport(
            generated_at_utc=now_iso,
            total_segments_mapped=len(all_segs),
            monitored_corridors_count=monitored,
            unmonitored_segments_count=unmonitored,
            total_centerline_length_km=round(total_km, 2),
            bounding_box={
                "min_lat": HYDERABAD_MIN_LAT,
                "max_lat": HYDERABAD_MAX_LAT,
                "min_lon": HYDERABAD_MIN_LON,
                "max_lon": HYDERABAD_MAX_LON,
            },
            source_attribution="© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project",
            source_license="ODbL-1.0",
            coverage_status=coverage_status,
            data_freshness_summary=freshness_counts,
            condition_state_summary=condition_counts,
            disclaimer=MANDATORY_MAP_DATA_DISCLAIMER,
        )

    def get_road_graph(self) -> Any:
        """
        Builds and returns the directed topological RoadGraph from stored road segments.
        Does not fabricate connections: disjoint segments remain separate components.
        """
        from sahaay.road_network.graph import RoadGraphBuilder
        with self._lock:
            builder = RoadGraphBuilder()
            graph, _ = builder.build_from_segments(list(self._segments.values()))
            return graph


# Global default store instance
default_road_network_store = RoadNetworkStore()
