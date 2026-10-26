"""
Sahaay AI - Risk-Aware Routing & Emergency Destination Integration Contracts
Defines formal schemas for advisory route planning, hospital/shelter access,
and mandatory safety invariants.

STATUS: INTEGRATION SPECIFICATION & CONTRACT DEFINITION ONLY.
The routing engine, graph traversals, and live road closures are NOT_IMPLEMENTED.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.decision.contracts import AlertLevel, CurrentFloodEvidenceStatus


class VehicleType(str, Enum):
    TWO_WHEELER = "TWO_WHEELER"
    THREE_WHEELER_AUTO = "THREE_WHEELER_AUTO"
    LIGHT_MOTOR_VEHICLE = "LIGHT_MOTOR_VEHICLE"       # Cars, Sedans, Small Hatchbacks
    HIGH_CLEARANCE_SUV = "HIGH_CLEARANCE_SUV"         # SUVs, Ambulances
    HEAVY_COMMERCIAL = "HEAVY_COMMERCIAL"             # Buses, Trucks, Rescue Tenders


class EmergencyDestinationType(str, Enum):
    HOSPITAL = "HOSPITAL"
    OFFICIAL_SHELTER = "OFFICIAL_SHELTER"


class FacilityOperationalStatus(str, Enum):
    OPERATIONAL_VERIFIED = "OPERATIONAL_VERIFIED"
    OPERATIONAL_CAPACITY_CONSTRAINED = "OPERATIONAL_CAPACITY_CONSTRAINED"
    INUNDATED_ACCESS_RESTRICTED = "INUNDATED_ACCESS_RESTRICTED"
    UNVERIFIED = "UNVERIFIED"


class EmergencyDestination(BaseModel):
    """
    Verified emergency destination record (Hospital or Municipal Relief Shelter).
    """
    facility_id: str = Field(..., pattern=r"^(HOSP|SHELTER)-[A-Z0-9\-]{3,25}$")
    name: str = Field(..., min_length=3, max_length=150)
    destination_type: EmergencyDestinationType
    latitude: float = Field(..., ge=17.0, le=17.8)
    longitude: float = Field(..., ge=78.1, le=78.8)
    operational_status: FacilityOperationalStatus = FacilityOperationalStatus.UNVERIFIED
    has_dedicated_emergency_bay: bool = False
    verified_access_road_status: CurrentFloodEvidenceStatus = CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE
    emergency_contact_masked: str = Field(..., description="Masked/verified official helpline number")
    last_verified_utc: Optional[str] = None


class RouteRequest(BaseModel):
    """
    Inbound request for advisory risk-aware routing.
    """
    origin_latitude: float = Field(..., ge=17.0, le=17.8)
    origin_longitude: float = Field(..., ge=78.1, le=78.8)
    destination_latitude: float = Field(..., ge=17.0, le=17.8)
    destination_longitude: float = Field(..., ge=78.1, le=78.8)
    vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE
    target_facility_id: Optional[str] = None
    departure_time_utc: Optional[str] = None
    avoid_high_susceptibility: bool = True


class RouteSegmentRisk(BaseModel):
    """
    Segment-level risk evaluation along an advisory route.
    """
    segment_id: str
    road_name: str
    length_meters: float = Field(..., ge=0.0)
    current_alert_level: AlertLevel
    current_evidence_status: CurrentFloodEvidenceStatus
    rainfall_risk_category: str
    vulnerability_category: str
    segment_risk_score: float = Field(..., ge=0.0, le=1.0)
    is_passable_for_vehicle: bool = True
    advisory_notice: Optional[str] = None


MANDATORY_SAFETY_DISCLAIMER = (
    "ADVISORY ROUTING ONLY: Sahaay AI does not guarantee safe passage. "
    "Waterlogging conditions change rapidly during severe monsoon downpours. "
    "Exercise driver discretion and comply with on-ground traffic police directives. "
    "Autonomous road closure or emergency dispatch is strictly prohibited."
)


class RouteResponse(BaseModel):
    """
    Advisory route response payload.
    Enforces mandatory safety invariants:
    - Never claim a route is guaranteed safe.
    - Explicitly surfaces unmonitored segments with UNKNOWN risk.
    - Embeds mandatory non-autonomous advisory disclaimer.
    """
    route_id: str
    origin: Dict[str, float]
    destination: Dict[str, float]
    vehicle_type: VehicleType
    target_facility: Optional[EmergencyDestination] = None
    total_distance_meters: float = Field(..., ge=0.0)
    estimated_duration_seconds: float = Field(..., ge=0.0)
    aggregate_risk_score: float = Field(..., ge=0.0, le=1.0)
    segments: List[RouteSegmentRisk] = Field(default_factory=list)
    has_unmonitored_segments: bool = False
    unmonitored_segments_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    safety_disclaimer: str = MANDATORY_SAFETY_DISCLAIMER
    engine_status: str = "SPECIFICATION_CONTRACT_ONLY_NOT_IMPLEMENTED"

    @field_validator("safety_disclaimer")
    @classmethod
    def validate_safety_disclaimer(cls, v: str) -> str:
        if not v or "does not guarantee safe passage" not in v:
            raise ValueError(
                "Mandatory safety disclaimer must explicitly state that the route is NOT guaranteed safe."
            )
        return v

    @model_validator(mode="after")
    def verify_safety_and_cross_field_invariants(self) -> "RouteResponse":
        # 1. Check for misleading guaranteed-safety phrasing across warnings and segment notices
        # NOTE: Heuristic phrase matching mitigates overt misleading safety declarations,
        # but cannot detect every possible linguistically subtle claim of guaranteed safety.
        prohibited_safety_phrases = [
            "guaranteed safe",
            "100% safe",
            "completely safe",
            "passable with zero risk",
            "zero risk route",
            "flood-free route",
            "certified safe passage",
        ]
        
        for w in self.warnings:
            w_lower = w.lower()
            for phrase in prohibited_safety_phrases:
                if phrase in w_lower:
                    raise ValueError(f"Routing response must NEVER claim a route is guaranteed safe (found: '{phrase}').")

        for seg in self.segments:
            if seg.advisory_notice:
                notice_lower = seg.advisory_notice.lower()
                for phrase in prohibited_safety_phrases:
                    if phrase in notice_lower:
                        raise ValueError(f"Segment advisory notice must NEVER claim guaranteed safety (found: '{phrase}').")

        # 2. Cross-field unmonitored segments consistency
        unmonitored = [
            s for s in self.segments
            if s.current_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
            or s.rainfall_risk_category == "UNKNOWN"
        ]
        if unmonitored and not self.has_unmonitored_segments:
            raise ValueError(
                "has_unmonitored_segments must be True when route contains segments with UNKNOWN or stale evidence."
            )
        if len(unmonitored) != self.unmonitored_segments_count:
            if self.unmonitored_segments_count == 0 and unmonitored:
                raise ValueError(
                    f"unmonitored_segments_count must match count of unmonitored segments ({len(unmonitored)})."
                )

        # 3. Cross-field emergency / impassable segment consistency
        has_emergency_segment = any(
            s.current_alert_level == AlertLevel.EMERGENCY or not s.is_passable_for_vehicle
            for s in self.segments
        )
        if has_emergency_segment and self.aggregate_risk_score == 0.0:
            raise ValueError(
                "aggregate_risk_score cannot be 0.0 when route traverses EMERGENCY or impassable segments."
            )

        # 4. Target facility access restriction check
        if self.target_facility is not None:
            is_facility_restricted = (
                self.target_facility.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED
                or self.target_facility.verified_access_road_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
            )
            if is_facility_restricted:
                has_access_warning = any(
                    "restricted" in w.lower() or "inundated" in w.lower() or "access" in w.lower()
                    for w in self.warnings
                )
                if not has_access_warning:
                    raise ValueError(
                        "Target emergency facility has restricted or inundated access; "
                        "route response must include an explicit access restriction warning in warnings."
                    )

        return self
