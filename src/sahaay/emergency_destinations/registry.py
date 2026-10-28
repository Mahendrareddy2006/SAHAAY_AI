"""
Sahaay AI - Phase E: Emergency Destination Registry
(src/sahaay/emergency_destinations/registry.py)

Thread-safe registry of verified emergency destinations (Hospitals, Official Municipal Shelters).
Maintains exact location provenance, operational status evidence, and data quality indicators.
Explicitly labels demonstration fixtures and prevents unsupported claims of operational readiness.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional

from sahaay.decision.contracts import CurrentFloodEvidenceStatus
from sahaay.emergency_destinations.schemas import (
    EmergencyDestinationRecord,
    EmergencyDestinationType,
    FacilityOperationalStatus,
)

logger = logging.getLogger(__name__)


class EmergencyDestinationRegistry:
    """
    Thread-safe registry of emergency destination facilities.
    Maintains provenance, unknown fields, and data quality flags.
    Integrates with RoadGraph nodes for topological route feasibility checking.
    """

    def __init__(self, populate_seed_fixtures: bool = True):
        self._lock = threading.Lock()
        self._destinations: Dict[str, EmergencyDestinationRecord] = {}
        if populate_seed_fixtures:
            self._initialize_seed_catalog()

    def clear(self) -> None:
        """Clears all registered destinations (used for outage/empty testing)."""
        with self._lock:
            self._destinations.clear()

    def register_destination(self, destination: EmergencyDestinationRecord) -> bool:
        """Adds or updates a destination record."""
        with self._lock:
            self._destinations[destination.facility_id] = destination
            return True

    def get_destination(self, facility_id: str) -> Optional[EmergencyDestinationRecord]:
        """Retrieves a destination record by its unique identifier."""
        with self._lock:
            return self._destinations.get(facility_id)

    def list_destinations(self) -> List[EmergencyDestinationRecord]:
        """Returns all currently registered destinations."""
        with self._lock:
            return list(self._destinations.values())

    def filter_destinations(
        self,
        destination_type: Optional[EmergencyDestinationType] = None,
        operational_status: Optional[FacilityOperationalStatus] = None,
        zone: Optional[str] = None,
        only_connected: bool = False,
    ) -> List[EmergencyDestinationRecord]:
        """Filters registered destinations based on specific criteria."""
        with self._lock:
            results = list(self._destinations.values())

        if destination_type:
            results = [d for d in results if d.destination_type == destination_type]
        if operational_status:
            results = [d for d in results if d.operational_status == operational_status]
        if zone:
            results = [d for d in results if d.zone == zone]
        if only_connected:
            results = [d for d in results if d.nearest_graph_node_id is not None]

        return results

    def _initialize_seed_catalog(self) -> None:
        """
        Populates baseline demonstration fixtures mapped to known seed road network nodes.
        Strictly labels fixtures as synthetic demonstration records where real-time feeds are unintegrated.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        seed_facilities = [
            # 1. Osmania General Hospital (South Zone, near Chaderghat)
            EmergencyDestinationRecord(
                facility_id="HOSP-OSMANIA-01",
                name="Osmania General Hospital",
                destination_type=EmergencyDestinationType.HOSPITAL,
                latitude=17.3750,
                longitude=78.4820,
                location_provenance="TS_HEALTH_DIRECTORATE_GIS_CATALOG",
                nearest_graph_node_id="NODE-CHADERGHAT",
                zone="South Zone",
                address_sanitized="Afzal Gunj, Hyderabad, Telangana 500012",
                source_authority="GHMC_EMERGENCY_MANAGEMENT_CELL",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
                status_freshness_category="FRESH",
                status_evidence_summary="Verified operational by district health liaison desk; 24x7 emergency active.",
                status_evidence_age_minutes=25.0,
                has_emergency_department=True,
                has_icu_beds=True,
                has_trauma_care=True,
                has_backup_power=True,
                has_dedicated_emergency_bay=True,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-2460XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Baseline demonstration profile with synthetic telemetry.",
                unknown_fields=["live_available_icu_beds", "blood_bank_units"],
                data_quality_flags=["DEMONSTRATION_FIXTURE"],
            ),
            # 2. Nizam's Institute of Medical Sciences (Punjagutta)
            EmergencyDestinationRecord(
                facility_id="HOSP-NIMS-01",
                name="Nizam's Institute of Medical Sciences (NIMS)",
                destination_type=EmergencyDestinationType.HOSPITAL,
                latitude=17.4225,
                longitude=78.4520,
                location_provenance="TS_HEALTH_DIRECTORATE_GIS_CATALOG",
                nearest_graph_node_id="NODE-AMEERPET-S",
                zone="Central Zone",
                address_sanitized="Punjagutta, Hyderabad, Telangana 500082",
                source_authority="GHMC_EMERGENCY_MANAGEMENT_CELL",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
                status_freshness_category="FRESH",
                status_evidence_summary="Verified tertiary care trauma facility active.",
                status_evidence_age_minutes=40.0,
                has_emergency_department=True,
                has_icu_beds=True,
                has_trauma_care=True,
                has_backup_power=True,
                has_dedicated_emergency_bay=True,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-2348XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Baseline demonstration profile with synthetic telemetry.",
                unknown_fields=["live_bed_census"],
                data_quality_flags=["DEMONSTRATION_FIXTURE"],
            ),
            # 3. Care Hospital Banjara Hills
            EmergencyDestinationRecord(
                facility_id="HOSP-CARE-BANJARA-01",
                name="Care Hospital Banjara Hills",
                destination_type=EmergencyDestinationType.HOSPITAL,
                latitude=17.4140,
                longitude=78.4400,
                location_provenance="TS_HEALTH_DIRECTORATE_GIS_CATALOG",
                nearest_graph_node_id="NODE-BANJARA-RD12",
                zone="Central Zone",
                address_sanitized="Road No 1, Banjara Hills, Hyderabad 500034",
                source_authority="GHMC_EMERGENCY_MANAGEMENT_CELL",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.UNVERIFIED,
                status_freshness_category="UNKNOWN",
                status_evidence_summary="Hospital registered in civic directory; live monsoon operational status UNVERIFIED.",
                status_evidence_age_minutes=None,
                has_emergency_department=True,
                has_icu_beds=None,  # Unknown
                has_trauma_care=None,
                has_backup_power=None,
                has_dedicated_emergency_bay=True,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-6165XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Status unverified; requires field confirmation.",
                unknown_fields=["operational_status", "has_icu_beds", "has_backup_power"],
                data_quality_flags=["UNVERIFIED_OPERATIONAL_STATUS", "DEMONSTRATION_FIXTURE"],
            ),
            # 4. GHMC Tolichowki Municipal Relief Shelter
            EmergencyDestinationRecord(
                facility_id="SHELTER-TOLICHOWKI-01",
                name="GHMC Community Hall Flood Relief Shelter (Tolichowki)",
                destination_type=EmergencyDestinationType.OFFICIAL_SHELTER,
                latitude=17.4045,
                longitude=78.4120,
                location_provenance="GHMC_DISASTER_MANAGEMENT_RECORDS",
                nearest_graph_node_id="NODE-SHAIKPET-ENTRY",
                zone="West Zone",
                address_sanitized="Near Tolichowki X Roads, Hyderabad 500008",
                source_authority="GHMC_URBAN_COMMUNITY_DEVELOPMENT",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
                status_freshness_category="FRESH",
                status_evidence_summary="Designated high-ground municipal shelter activated by zonal commissioner.",
                status_evidence_age_minutes=15.0,
                has_emergency_department=False,
                has_icu_beds=False,
                has_trauma_care=False,
                has_backup_power=True,
                has_dedicated_emergency_bay=False,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-2111XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Designated shelter site in demonstration mode.",
                unknown_fields=["live_cot_count", "food_packet_reserve"],
                data_quality_flags=["DEMONSTRATION_FIXTURE"],
            ),
            # 5. Khairatabad Municipal Relief Shelter
            EmergencyDestinationRecord(
                facility_id="SHELTER-KHAIRATABAD-01",
                name="Khairatabad Government High School Relief Shelter",
                destination_type=EmergencyDestinationType.OFFICIAL_SHELTER,
                latitude=17.4125,
                longitude=78.4620,
                location_provenance="GHMC_DISASTER_MANAGEMENT_RECORDS",
                nearest_graph_node_id="NODE-RAJBHAVAN-S",
                zone="Central Zone",
                address_sanitized="Khairatabad Anand Nagar, Hyderabad 500004",
                source_authority="GHMC_URBAN_COMMUNITY_DEVELOPMENT",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.OPERATIONAL_CAPACITY_CONSTRAINED,
                status_freshness_category="AGING",
                status_evidence_summary="Shelter operating at 90% capacity; priority given to vulnerable citizens.",
                status_evidence_age_minutes=95.0,
                has_emergency_department=False,
                has_icu_beds=False,
                has_trauma_care=False,
                has_backup_power=False,
                has_dedicated_emergency_bay=False,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-2333XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Capacity constrained demonstration fixture.",
                unknown_fields=["potable_water_liters"],
                data_quality_flags=["CONSTRAINED_CAPACITY", "DEMONSTRATION_FIXTURE"],
            ),
            # 6. Inundated / Access-Restricted Facility Fixture (For safety testing)
            EmergencyDestinationRecord(
                facility_id="HOSP-INUNDATED-DEMO-01",
                name="Musarambagh Community Health Center",
                destination_type=EmergencyDestinationType.HOSPITAL,
                latitude=17.3710,
                longitude=78.5080,
                location_provenance="TS_HEALTH_DIRECTORATE_GIS_CATALOG",
                nearest_graph_node_id="NODE-MALAKPET-GUNJ",
                zone="South Zone",
                address_sanitized="Musarambagh Cause-way Link, Hyderabad 500036",
                source_authority="GHMC_EMERGENCY_MANAGEMENT_CELL",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
                status_freshness_category="FRESH",
                status_evidence_summary="Ground floor waterlogged (45cm); vehicular access bay completely submerged.",
                status_evidence_age_minutes=10.0,
                has_emergency_department=True,
                has_icu_beds=False,
                has_trauma_care=False,
                has_backup_power=False,
                has_dedicated_emergency_bay=True,
                verified_access_road_status=CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE,
                emergency_contact_masked="040-2455XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Safety fixture representing inundated facility.",
                unknown_fields=[],
                data_quality_flags=["INUNDATED_ACCESS_RESTRICTED", "DEMONSTRATION_FIXTURE"],
            ),
            # 7. Disconnected Topology Facility Fixture (For topology safety testing)
            EmergencyDestinationRecord(
                facility_id="HOSP-ISOLATED-DEMO-01",
                name="Uppal Regional Isolation Clinic",
                destination_type=EmergencyDestinationType.HOSPITAL,
                latitude=17.4010,
                longitude=78.5600,
                location_provenance="TS_HEALTH_DIRECTORATE_GIS_CATALOG",
                nearest_graph_node_id="NODE-ISOLATED-2",
                zone="East Zone",
                address_sanitized="Uppal Ring Road Bypass, Hyderabad 500039",
                source_authority="GHMC_EMERGENCY_MANAGEMENT_CELL",
                verification_timestamp_utc=now_iso,
                operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
                status_freshness_category="FRESH",
                status_evidence_summary="Facility fully operational, but road connection is in a disconnected graph component.",
                status_evidence_age_minutes=30.0,
                has_emergency_department=True,
                has_icu_beds=True,
                has_trauma_care=False,
                has_backup_power=True,
                has_dedicated_emergency_bay=True,
                verified_access_road_status=CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
                emergency_contact_masked="040-2720XXXX",
                is_synthetic_fixture=True,
                fixture_warning="DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Disconnected component demonstration fixture.",
                unknown_fields=[],
                data_quality_flags=["DISCONNECTED_TOPOLOGY", "DEMONSTRATION_FIXTURE"],
            ),
        ]

        for fac in seed_facilities:
            self._destinations[fac.facility_id] = fac

    def to_geojson_feature_collection(self) -> Dict[str, Any]:
        """
        Exports all registered destinations as a valid GeoJSON FeatureCollection
        suitable for live map rendering.
        """
        features = []
        with self._lock:
            for fac in self._destinations.values():
                # Color coding based on operational status
                if fac.operational_status == FacilityOperationalStatus.OPERATIONAL_VERIFIED:
                    marker_color = "#10b981"  # Emerald Green
                    status_badge = "OPERATIONAL"
                elif fac.operational_status == FacilityOperationalStatus.OPERATIONAL_CAPACITY_CONSTRAINED:
                    marker_color = "#f59e0b"  # Amber
                    status_badge = "CONSTRAINED"
                elif fac.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED:
                    marker_color = "#e11d48"  # Crimson Red
                    status_badge = "INUNDATED_RESTRICTED"
                else:
                    marker_color = "#64748b"  # Slate Gray (Unverified)
                    status_badge = "UNVERIFIED"

                feature = {
                    "type": "Feature",
                    "id": fac.facility_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [fac.longitude, fac.latitude],
                    },
                    "properties": {
                        "facility_id": fac.facility_id,
                        "name": fac.name,
                        "destination_type": fac.destination_type.value,
                        "operational_status": fac.operational_status.value,
                        "status_badge": status_badge,
                        "marker_color": marker_color,
                        "nearest_graph_node_id": fac.nearest_graph_node_id,
                        "zone": fac.zone,
                        "is_synthetic_fixture": fac.is_synthetic_fixture,
                        "fixture_warning": fac.fixture_warning,
                        "has_emergency_department": fac.has_emergency_department,
                        "has_icu_beds": fac.has_icu_beds,
                        "data_quality_flags": fac.data_quality_flags,
                        "unknown_fields": fac.unknown_fields,
                    },
                }
                features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "total_destinations": len(features),
                "catalog_type": "EMERGENCY_DESTINATION_REGISTRY",
                "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "disclaimer": (
                    "DEMONSTRATION REGISTRY ONLY: Facilities are seed fixtures for system validation. "
                    "Do NOT use for actual emergency dispatch or evacuation."
                ),
            },
        }


# Global default destination registry instance
default_destination_registry = EmergencyDestinationRegistry()
