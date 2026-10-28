"""
Sahaay AI - Phase E: Emergency Destination & Safe Routing Schemas
(src/sahaay/emergency_destinations/schemas.py)

Codifies strict data contracts for:
1. Verified emergency destination registry records with explicit provenance and unknown indicators.
2. Transparent candidate destination ranking and suitability assessment.
3. Separation of geographic proximity from topological route feasibility.
4. Non-fabrication boundaries and disarmed operational action enforcement.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.decision.contracts import CurrentFloodEvidenceStatus
from sahaay.routing.contracts import (
    EmergencyDestination,
    EmergencyDestinationType,
    FacilityOperationalStatus,
    VehicleType,
    MANDATORY_SAFETY_DISCLAIMER,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RiskAwareRouteAssessment,
    RouteAssessmentOutcome,
    FORBIDDEN_SAFETY_PHRASES,
)


class DestinationFeasibilityTier(str, Enum):
    """
    Topological network feasibility classification between origin and facility.
    Distinguishes continuous graph path existence from disconnected or cut topology.
    """
    CONNECTED_AND_TRAVERSABLE = "CONNECTED_AND_TRAVERSABLE"   # Route exists with zero impassable cuts
    BLOCKED_IMPASSABLE_ACCESS = "BLOCKED_IMPASSABLE_ACCESS"   # Graph path is blocked by verified floodwaters
    DISCONNECTED_TOPOLOGY = "DISCONNECTED_TOPOLOGY"           # Origin and destination reside in disconnected graph components
    UNSUPPORTED_LOCATION = "UNSUPPORTED_LOCATION"             # Origin or destination node not registered in road graph


class DestinationSuitabilityTier(str, Enum):
    """
    Operational suitability tier of an emergency destination facility.
    Never infers operational suitability merely because a facility exists in registry.
    """
    SUITABLE_VERIFIED_OPERATIONAL = "SUITABLE_VERIFIED_OPERATIONAL" # Verified open, verified traversable path, essential capabilities present
    DEGRADED_UNVERIFIED_STATUS = "DEGRADED_UNVERIFIED_STATUS"       # Traversable path exists, but operational status is UNVERIFIED
    CONSTRAINED_CAPACITY = "CONSTRAINED_CAPACITY"                   # Facility verified operational but capacity constrained
    RESTRICTED_ACCESS_INUNDATED = "RESTRICTED_ACCESS_INUNDATED"     # Facility grounds or access bay inundated
    UNSUITABLE_UNREACHABLE = "UNSUITABLE_UNREACHABLE"               # Path is blocked or disconnected; facility unreachable


class EmergencyDestinationRecord(EmergencyDestination):
    """
    Authoritative emergency destination record (Hospital, Municipal Shelter, Relief Center).
    Explicitly tracks location provenance, operational status freshness, verified capabilities,
    and unknown fields. Clearly marks synthetic demonstration fixtures.
    """
    # Location Provenance & Graph Topology
    location_provenance: str = Field(
        "GHMC_OFFICIAL_GIS_REGISTRY",
        description="Source authority for physical coordinates"
    )
    nearest_graph_node_id: Optional[str] = Field(
        None,
        description="Closest validated RoadGraph node ID for topological routing"
    )
    zone: Optional[str] = None
    address_sanitized: Optional[str] = None

    # Source & Verification Provenance
    source_authority: str = Field(
        "GHMC_DISASTER_MANAGEMENT_CELL",
        description="Administrative authority maintaining record"
    )
    verification_timestamp_utc: Optional[str] = Field(
        None,
        description="ISO-8601 UTC timestamp of last official field or administrative verification"
    )

    # Operational Status Evidence & Freshness
    status_freshness_category: str = Field(
        "UNKNOWN",
        description="FRESH (<=60m), AGING (60-180m), STALE (>180m), or UNKNOWN"
    )
    status_evidence_summary: Optional[str] = Field(
        None,
        description="Audit summary of how operational status was verified"
    )
    status_evidence_age_minutes: Optional[float] = None

    # Verified Service Capabilities (Only populated where verified; None = UNKNOWN)
    has_emergency_department: Optional[bool] = None
    has_icu_beds: Optional[bool] = None
    has_trauma_care: Optional[bool] = None
    has_backup_power: Optional[bool] = None
    bed_capacity_total: Optional[int] = Field(None, ge=0)
    bed_capacity_available: Optional[int] = Field(None, ge=0)

    # Fixture Disclosure & Missing Field Indicators
    is_synthetic_fixture: bool = Field(
        False,
        description="Must be True if facility is a demonstration fixture rather than verified operational asset"
    )
    fixture_warning: Optional[str] = Field(
        None,
        description="Warning label explicitly identifying synthetic demonstration status"
    )
    unknown_fields: List[str] = Field(
        default_factory=list,
        description="Audit list of required operational fields that are unknown/unverified"
    )
    data_quality_flags: List[str] = Field(
        default_factory=list,
        description="Quality flags (e.g. UNVERIFIED_OPERATIONAL_STATUS, STALE_CAPACITY_DATA)"
    )

    @model_validator(mode="after")
    def validate_destination_safety_invariants(self) -> "EmergencyDestinationRecord":
        # 1. Prohibit claiming facility is verified operational if status is UNVERIFIED
        if self.operational_status == FacilityOperationalStatus.UNVERIFIED:
            if "operational_status" not in self.unknown_fields:
                self.unknown_fields.append("operational_status")
            if "UNVERIFIED_OPERATIONAL_STATUS" not in self.data_quality_flags:
                self.data_quality_flags.append("UNVERIFIED_OPERATIONAL_STATUS")

        # 2. If synthetic fixture, ensure fixture warning is explicit
        if self.is_synthetic_fixture and not self.fixture_warning:
            self.fixture_warning = (
                "DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY: Synthetic record for pipeline verification only. "
                "Do NOT use for actual emergency dispatch or evacuation."
            )

        # 3. Prohibit forbidden safety phrases in descriptions/names
        all_text = " ".join([
            self.name,
            self.status_evidence_summary or "",
            " ".join(self.data_quality_flags),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Destination record contains forbidden safety phrase: '{phrase}'")

        return self


class CandidateDestinationAssessment(BaseModel):
    """
    Detailed evaluation of a candidate emergency destination relative to a specific origin.
    Separates straight-line geographic proximity from topological route feasibility.
    """
    facility: EmergencyDestinationRecord
    feasibility_tier: DestinationFeasibilityTier
    suitability_tier: DestinationSuitabilityTier

    # Proximity vs Route Metrics
    straight_line_distance_meters: float = Field(..., ge=0.0)
    route_distance_meters: Optional[float] = Field(None, ge=0.0)
    route_duration_seconds: Optional[float] = Field(None, ge=0.0)

    # Feasibility Indicators
    is_topologically_connected: bool = False
    is_access_passable: bool = False
    is_operationally_suitable: bool = False

    # Transparent Ranking
    ranking_score: float = Field(
        ...,
        description="Transparent composite score: 0.0 (unreachable/unsuitable) to 1.0 (optimal verified)"
    )
    ranking_rationale: str = Field(
        ...,
        description="Documented criteria explaining assigned ranking tier"
    )
    selection_or_rejection_explanation: str = Field(
        ...,
        description="Explicit reasoning for why destination was recommended, deprioritized, or rejected"
    )

    # Associated Route Assessment (if computed)
    route_assessment: Optional[RiskAwareRouteAssessment] = None

    # Audit & Uncertainty Disclosures
    warnings: List[str] = Field(default_factory=list)
    unknown_suitability_fields: List[str] = Field(default_factory=list)


class DestinationSuitabilityRequest(BaseModel):
    """
    Request payload to evaluate and rank candidate emergency destinations.
    """
    origin_node_id: Optional[str] = Field(None, description="Starting RoadGraph node ID")
    origin_latitude: Optional[float] = Field(None, ge=17.0, le=17.8)
    origin_longitude: Optional[float] = Field(None, ge=78.1, le=78.8)
    destination_type: Optional[EmergencyDestinationType] = Field(
        None,
        description="Filter by destination type (e.g., HOSPITAL or OFFICIAL_SHELTER)"
    )
    vehicle_type: VehicleType = Field(
        VehicleType.LIGHT_MOTOR_VEHICLE,
        description="Vehicle classification for clearance and speed evaluation"
    )
    require_verified_operational: bool = Field(
        False,
        description="If True, strictly filters out unverified facilities"
    )
    max_candidates: int = Field(5, ge=1, le=20)
    caller_role: Optional[str] = Field(
        None,
        description="Unauthenticated client-supplied role token; rejected by security gate"
    )
    request_emergency_dispatch: bool = Field(
        False,
        description="Privileged autonomous dispatch request; rejected by security gate"
    )


class DestinationSuitabilityResponse(BaseModel):
    """
    Response payload ranking candidate emergency destinations with full transparency.
    """
    assessment_timestamp_utc: str
    origin_node_id: Optional[str] = None
    origin_coordinates: Optional[Dict[str, float]] = None
    vehicle_type: VehicleType
    candidates_ranked: List[CandidateDestinationAssessment] = Field(default_factory=list)
    total_registered_facilities: int = 0
    connected_facilities_count: int = 0
    suitable_facilities_count: int = 0
    ranking_criteria_summary: str = (
        "1. Topological graph connectivity (continuous road network path). "
        "2. Ground corridor passability (exclusion of verified impassable segments). "
        "3. Verified operational status (OPERATIONAL_VERIFIED > CONSTRAINED > UNVERIFIED). "
        "4. Risk-penalized travel distance. Geographic proximity alone never determines suitability."
    )
    coverage_warning: str = (
        "SPARSE_SEED_CATALOG_WARNING: Road network contains ~22 seed segments. "
        "Topological routing is unsupported for origins/destinations outside monitored components. "
        "Do not interpret missing road paths as safe or passable."
    )
    safety_disclaimer: str = (
        "ADVISORY EMERGENCY ROUTING ONLY: Sahaay AI does not guarantee hospital admission, "
        "bed availability, or flood-free transit. Conditions change rapidly. "
        "Comply with police and emergency service directives on ground. "
        "Autonomous dispatch and road closures are strictly disabled."
    )
    operational_action_authorized: bool = Field(
        False,
        description="Autonomous dispatch and emergency service activation remain strictly disabled"
    )
