"""
Sahaay AI - Phase 19: Risk-Aware Routing Schemas
(src/sahaay/routing/schemas.py)

Codifies validated schemas for risk-aware routing assessments.
Strictly separates:
1. Verified road passability or impassability
2. Corroborated citizen reports
3. Stale, expired, conflicting, or unmonitored road status
4. Experimental forecast rainfall risk (Phase 18)
5. Static flood susceptibility (Phase 17)
6. Telemetry missingness and suitability

Enforces non-autonomous advisory rules and disarms operational dispatch flags.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
)
from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestination,
    FacilityOperationalStatus,
    MANDATORY_SAFETY_DISCLAIMER,
)


class PassabilityAssessment(str, Enum):
    """Auditable passability classification for a road segment."""
    VERIFIED_PASSABLE = "VERIFIED_PASSABLE"                     # Official field inspection confirms normal/passable
    VERIFIED_IMPASSABLE = "VERIFIED_IMPASSABLE"                 # Official field inspection confirms flooded/submerged
    CORROBORATED_HAZARD = "CORROBORATED_HAZARD"                 # Multi-citizen corroborated report of waterlogging
    UNVERIFIED_REPORT = "UNVERIFIED_REPORT"                     # Single citizen or unverified sensor report
    STALE_OR_EXPIRED = "STALE_OR_EXPIRED"                       # Observations older than validity window (> 6h)
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"               # Incompatible reports (e.g., passable vs submerged)
    UNMONITORED_NO_EVIDENCE = "UNMONITORED_NO_EVIDENCE"         # No observations on record (NOT safe!)
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"                     # Telemetry missing or defective


class RouteAssessmentOutcome(str, Enum):
    """High-level route feasibility verdict."""
    ADVISORY_TRAVERSABLE_WITH_CAUTION = "ADVISORY_TRAVERSABLE_WITH_CAUTION"
    BLOCKED_IMPASSABLE_SEGMENTS_PRESENT = "BLOCKED_IMPASSABLE_SEGMENTS_PRESENT"
    ALL_CANDIDATE_ROUTES_IMPASSABLE = "ALL_CANDIDATE_ROUTES_IMPASSABLE"
    UNCERTAIN_INSUFFICIENT_DATA = "UNCERTAIN_INSUFFICIENT_DATA"
    TOPOLOGY_UNSUPPORTED = "TOPOLOGY_UNSUPPORTED"


FORBIDDEN_SAFETY_PHRASES = [
    "guaranteed safe",
    "100% safe",
    "completely safe",
    "safe passage guaranteed",
    "zero risk",
    "road is safe",
    "route is safe",
    "certified safe",
    "fully safe",
    "safe for all vehicles without risk",
    "zero risk route",
    "flood-free route",
]

MANDATORY_ROUTING_DISCLAIMER = (
    "ADVISORY ROUTING ONLY: Sahaay AI does not guarantee safe passage or optimal routing. "
    "Urban waterlogging conditions change rapidly during severe monsoon downpours. "
    "Absence of reported flooding does NOT indicate dry pavement or safe transit. "
    "Forecast rainfall and static susceptibility are advisory indicators only. "
    "Exercise driver discretion and comply with on-ground traffic police directives. "
    "Autonomous road closures and automated emergency dispatch are strictly prohibited."
)


class SegmentRoutingAssessment(BaseModel):
    """
    Granular, auditable assessment of a candidate road corridor or segment.
    Strictly separates five distinct evidence channels:
    1. Ground road-status evidence (Phase 16)
    2. Forecast precipitation context (Phase 18)
    3. Static vulnerability context (Phase 17)
    4. Passability verdict and traversal feasibility
    5. Quality, uncertainty, and reason codes
    """
    segment_id: str
    road_name: str
    length_meters: float = Field(default=500.0, ge=0.0)
    passability_state: PassabilityAssessment
    is_traversable: bool = Field(True, description="False if segment is verified impassable")
    is_uncertain: bool = Field(False, description="True if evidence is unmonitored, stale, expired, or conflicting")
    
    # --------------------------------------------------------------------------
    # Signal 1: Ground Road-Status Evidence (Phase 16)
    # --------------------------------------------------------------------------
    condition_state: RoadConditionState = RoadConditionState.NO_CURRENT_EVIDENCE
    verification_state: RoadVerificationState = RoadVerificationState.UNMONITORED
    freshness_category: RoadFreshnessCategory = RoadFreshnessCategory.UNKNOWN
    observation_age_minutes: Optional[float] = None
    evidence_source: Optional[str] = None

    # --------------------------------------------------------------------------
    # Signal 2: Forecast Precipitation Context (Phase 18)
    # --------------------------------------------------------------------------
    forecast_risk_category: str = "UNKNOWN"
    forecast_rainfall_mm: Optional[float] = None
    forecast_issue_time_utc: Optional[str] = None
    forecast_valid_time_utc: Optional[str] = None
    forecast_horizon_hours: Optional[float] = None
    forecast_heuristic_score: Optional[float] = None
    is_calibrated_probability: bool = Field(
        False, description="Must remain False: heuristic score is NOT a calibrated probability"
    )
    phase18_dispatch_actionable: bool = Field(
        False, description="Phase 18 dispatch flag is non-operational and cannot trigger real action"
    )

    # --------------------------------------------------------------------------
    # Signal 3: Static Susceptibility Context (Phase 17)
    # --------------------------------------------------------------------------
    static_vulnerability_index: Optional[float] = None
    static_vulnerability_category: str = "UNKNOWN"
    is_static_susceptibility_only: bool = Field(
        True, description="Labels static index as susceptibility only, not observed flood inundation"
    )

    # --------------------------------------------------------------------------
    # Signal 4: Quality, Uncertainty, & Explanations
    # --------------------------------------------------------------------------
    quality_flags: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    restriction_reasons: List[str] = Field(default_factory=list)
    caution_notices: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segment_safety_invariants(self) -> "SegmentRoutingAssessment":
        # 1. Verified Impassable must not be traversable
        if self.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE:
            if self.is_traversable:
                raise ValueError("Segment cannot be is_traversable=True when passability_state is VERIFIED_IMPASSABLE")

        # 2. Unmonitored or missing evidence must be marked uncertain
        if self.passability_state in {
            PassabilityAssessment.UNMONITORED_NO_EVIDENCE,
            PassabilityAssessment.STALE_OR_EXPIRED,
            PassabilityAssessment.CONFLICTING_EVIDENCE,
            PassabilityAssessment.INSUFFICIENT_DATA,
        }:
            if not self.is_uncertain:
                raise ValueError(
                    f"Segment must have is_uncertain=True when passability_state is {self.passability_state.value}"
                )

        # 3. Probability claims prohibition
        if self.is_calibrated_probability:
            raise ValueError("is_calibrated_probability must remain False on segment assessment")

        # 4. Prohibit guaranteed safety phrasing across notices
        all_text = " ".join([
            self.road_name,
            " ".join(self.restriction_reasons),
            " ".join(self.caution_notices),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Segment contains forbidden safety claim: '{phrase}'")

        return self


class RiskAwareRouteAssessment(BaseModel):
    """
    Formal explainable routing evaluation payload.
    Provides transparent segment assessments, unmonitored segment accounting,
    operational non-actionability disclaimers, and statutory warnings.
    """
    route_id: str
    assessment_timestamp_utc: str
    outcome: RouteAssessmentOutcome
    origin: Dict[str, float]
    destination: Dict[str, float]
    vehicle_type: VehicleType
    target_facility: Optional[EmergencyDestination] = None

    # Traversal metrics
    total_distance_meters: float = Field(..., ge=0.0)
    estimated_duration_seconds: float = Field(..., ge=0.0)
    aggregate_heuristic_risk: float = Field(..., ge=0.0, le=1.0)
    
    # Segment assessments
    recommended_segments: List[SegmentRoutingAssessment] = Field(default_factory=list)
    excluded_segments: List[SegmentRoutingAssessment] = Field(default_factory=list)

    # Auditable Counts
    impassable_segments_count: int = 0
    unmonitored_segments_count: int = 0
    stale_or_conflicting_segments_count: int = 0
    has_unmonitored_segments: bool = False

    # Safety Invariant Flags
    is_optimality_claimed: bool = Field(
        False, description="Must remain False: full topological road graph is unverified/absent"
    )
    is_guaranteed_safe: bool = Field(
        False, description="Must remain False: routing advisory NEVER guarantees safety"
    )
    operational_action_authorized: bool = Field(
        False, description="Must remain False: Phase 18 actionability CANNOT trigger real dispatch or closure"
    )

    # Explanations and Disclaimers
    warnings: List[str] = Field(default_factory=list)
    exclusion_explanations: List[str] = Field(default_factory=list)
    safety_disclaimer: str = MANDATORY_ROUTING_DISCLAIMER
    engine_status: str = "OFFLINE_RISK_AWARE_EVALUATION_LAYER"

    @field_validator("safety_disclaimer")
    @classmethod
    def validate_safety_disclaimer(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety disclaimer contains forbidden phrase: '{phrase}'")
        if "does not guarantee safe passage" not in v_lower:
            raise ValueError("Safety disclaimer must explicitly state that the route is NOT guaranteed safe.")
        return v

    @model_validator(mode="after")
    def validate_route_safety_invariants(self) -> "RiskAwareRouteAssessment":
        # 1. Prohibit forbidden claims across all warning texts
        all_text = " ".join([
            self.safety_disclaimer,
            " ".join(self.warnings),
            " ".join(self.exclusion_explanations),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Route payload contains forbidden safety claim: '{phrase}'")

        # 2. Strict invariant: is_guaranteed_safe must be False
        if self.is_guaranteed_safe:
            raise ValueError("is_guaranteed_safe must remain False: routing advisory NEVER guarantees safety.")

        # 3. Strict invariant: operational_action_authorized must be False
        if self.operational_action_authorized:
            raise ValueError("operational_action_authorized must remain False: advisory cannot trigger operations.")

        # 4. Strict invariant: is_optimality_claimed must be False
        if self.is_optimality_claimed:
            raise ValueError("is_optimality_claimed must remain False: road network graph is incomplete.")

        # 5. Cross-field: Unmonitored segments consistency
        unmonitored_in_recs = [
            s for s in self.recommended_segments
            if s.passability_state == PassabilityAssessment.UNMONITORED_NO_EVIDENCE
            or s.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
            or s.verification_state == RoadVerificationState.UNMONITORED
        ]
        if unmonitored_in_recs and not self.has_unmonitored_segments:
            raise ValueError("has_unmonitored_segments must be True when recommended route traverses unmonitored segments.")

        # 6. Cross-field: Impassable segments must not be recommended
        impassable_in_recs = [
            s for s in self.recommended_segments
            if s.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE
            or not s.is_traversable
        ]
        if impassable_in_recs:
            raise ValueError(
                f"Recommended route contains {len(impassable_in_recs)} verified impassable segments! "
                "Verified impassable segments must be excluded."
            )

        # 7. Destination access check
        if self.target_facility is not None:
            is_facility_restricted = (
                self.target_facility.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED
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
