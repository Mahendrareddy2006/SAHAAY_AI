"""
Sahaay AI - Phase 16: Live Road Status Schemas
Canonical data contracts for multi-source road condition representation, evidence fusion,
temporal provenance, verification states, and safety invariants.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.reports.schemas import (
    SubmissionChannel,
    ReportCondition,
    WaterDepthEstimate,
    ReportVerificationStatus,
)


class RoadConditionState(str, Enum):
    """
    Canonical road condition states.
    Strictly distinguishes absence of evidence, stale observations,
    contradictory reports, unverified claims, and verified ground truths.
    """
    UNKNOWN = "UNKNOWN"                               # No current observation or unmonitored road segment
    NO_CURRENT_EVIDENCE = "NO_CURRENT_EVIDENCE"       # Monitored corridor but no active observations within window
    STALE = "STALE"                                   # Evidence aged (180-360 min) requiring fresh field re-survey
    EXPIRED = "EXPIRED"                               # Evidence past retention window (>360 min); cannot determine condition
    CONFLICTING = "CONFLICTING"                       # Contradictory reports/telemetry detected without human resolution
    UNVERIFIED = "UNVERIFIED"                         # Single uncorroborated community report awaiting field verification
    CORROBORATED = "CORROBORATED"                     # >=2 independent community sources concordant; awaiting responder
    VERIFIED_PASSABLE = "VERIFIED_PASSABLE"           # Officially verified by authorized responder as dry/passable
    VERIFIED_WATERLOGGED = "VERIFIED_WATERLOGGED"     # Officially verified by authorized responder as waterlogged
    VERIFIED_IMPASSABLE = "VERIFIED_IMPASSABLE"       # Officially verified by authorized responder as impassable/hazardous


class RoadEvidenceType(str, Enum):
    """
    Source modality providing the evidence.
    """
    NO_EVIDENCE = "NO_EVIDENCE"
    COMMUNITY_REPORT = "COMMUNITY_REPORT"
    FIELD_RESPONDER_INSPECTION = "FIELD_RESPONDER_INSPECTION"
    PHYSICAL_TELEMETRY = "PHYSICAL_TELEMETRY"
    CALIBRATED_CAMERA = "CALIBRATED_CAMERA"
    RAINFALL_PROXIMITY_TELEMETRY = "RAINFALL_PROXIMITY_TELEMETRY"
    STATIC_SUSCEPTIBILITY_MODEL = "STATIC_SUSCEPTIBILITY_MODEL"


class RoadFreshnessCategory(str, Enum):
    """
    Freshness classification determined by physical observation time.
    """
    FRESH = "FRESH"          # <= 60 minutes
    AGING = "AGING"          # 60 - 180 minutes
    STALE = "STALE"          # 180 - 360 minutes
    EXPIRED = "EXPIRED"      # > 360 minutes
    UNKNOWN = "UNKNOWN"      # Missing timestamp or no observation


class RoadVerificationState(str, Enum):
    """
    Verification lifecycle state of the road condition.
    """
    UNMONITORED = "UNMONITORED"
    UNVERIFIED = "UNVERIFIED"
    CORROBORATED = "CORROBORATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED_BY_RESPONDER = "VERIFIED_BY_RESPONDER"
    REJECTED_FALSE_ALARM = "REJECTED_FALSE_ALARM"
    REJECTED_INVALID = "REJECTED_INVALID"
    EXPIRED = "EXPIRED"


class UncertaintyLevel(str, Enum):
    """
    Qualitative uncertainty classification for decision support.
    """
    HIGH = "HIGH"        # Missing observations, conflicting evidence, or unverified single source
    MEDIUM = "MEDIUM"    # Corroborated community reports or aging responder observations
    LOW = "LOW"          # Fresh responder verification or calibrated multi-sensor telemetry


class EvidenceProvenanceRecord(BaseModel):
    """
    Auditable provenance record tracking individual evidence contributions.
    """
    evidence_type: RoadEvidenceType
    source_id_masked: str = Field(..., description="Masked reporter hash or responder identifier")
    source_channel: SubmissionChannel = SubmissionChannel.WEB_PORTAL
    raw_report_volume: int = Field(1, ge=1, description="Total reports received from this source")
    independent_sources_count: int = Field(1, ge=1, description="Independent corroborating entities")
    evidence_reference: Optional[str] = None
    image_reference: Optional[str] = None
    is_synthetic: bool = Field(False, description="Synthetic records are strictly segregated from live decisions")
    observation_timestamp_utc: Optional[str] = None
    ingestion_timestamp_utc: Optional[str] = None


MANDATORY_ROAD_SAFETY_NOTICE = (
    "ADVISORY ONLY: Sahaay AI does not guarantee road safety, dry pavement, or clear passage. "
    "Urban drainage and waterlogging conditions can change rapidly during monsoon downpours. "
    "Exercise driver discretion and comply with on-ground traffic police directives. "
    "Autonomous road closures and automated emergency dispatch are strictly prohibited."
)

FORBIDDEN_SAFETY_PHRASES = [
    "guaranteed safe",
    "100% safe",
    "completely safe",
    "safe passage guaranteed",
    "zero risk",
    "road is safe",
    "certified safe",
    "fully safe",
    "safe for all vehicles without risk",
]


class RoadStatusSnapshot(BaseModel):
    """
    Canonical, auditable Live Road Status snapshot for a road segment or corridor.
    Adheres strictly to safety policies:
    - Never declares guaranteed safety or safe passage.
    - Decouples observation timestamp from ingestion timestamp.
    - Separates static vulnerability and rainfall from active road inundation.
    - Does not infer measured depth or passability without verified authority.
    """
    road_segment_id: str = Field(..., min_length=3, max_length=50, description="e.g. HYD-LOC-001 or OSM segment ID")
    road_name: str = Field(..., min_length=2, max_length=150)
    corridor_zone: Optional[str] = Field(None, description="e.g. West Zone, Central Zone")
    latitude_coarsened: Optional[float] = Field(None, ge=17.0, le=17.8)
    longitude_coarsened: Optional[float] = Field(None, ge=78.1, le=78.8)
    location_precision_m: Optional[float] = Field(None, ge=1.0, le=5000.0)

    # Condition & Evidence
    condition_state: RoadConditionState
    evidence_type: RoadEvidenceType

    # Timestamps (strictly decoupled)
    observation_timestamp_utc: Optional[str] = Field(
        None, description="ISO-8601 UTC timestamp of actual physical observation"
    )
    ingestion_timestamp_utc: Optional[str] = Field(
        None, description="ISO-8601 UTC timestamp when observation was ingested/submitted"
    )
    last_status_update_utc: str = Field(..., description="ISO-8601 UTC timestamp of status computation")
    expiration_timestamp_utc: Optional[str] = Field(
        None, description="ISO-8601 UTC timestamp after which this evidence expires"
    )

    # Freshness & Uncertainty
    freshness_category: RoadFreshnessCategory
    evidence_age_minutes: Optional[float] = Field(None, ge=0.0)
    verification_state: RoadVerificationState
    verified_by_entity: Optional[str] = Field(None, description="Role and identifier of verifying authority")
    uncertainty_level: UncertaintyLevel
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    # Conflict Tracking
    has_conflicting_evidence: bool = False
    conflict_details: Optional[str] = None

    # Quantitative ground truths (gated strictly to authorized verifiers)
    measured_water_depth_cm: Optional[float] = Field(
        None, ge=0.0, le=500.0, description="Calibrated measurement in cm; None for unverified"
    )
    depth_measurement_method: str = Field(
        "unmeasured", description="Method used to measure water depth"
    )
    verified_passability: str = Field(
        "unverified_unknown", description="Verified vehicle passability tier"
    )

    # Provenance & Multi-Source Context
    provenance_records: List[EvidenceProvenanceRecord] = Field(default_factory=list)
    environmental_rainfall_category: str = Field(
        "UNKNOWN", description="Modeled/observed rainfall risk category (LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN)"
    )
    environmental_rainfall_score: float = Field(0.0, ge=0.0, le=1.0)
    static_vulnerability_category: str = Field(
        "UNKNOWN", description="Static geospatial susceptibility tier (LOW, MODERATE, HIGH, SEVERE, UNKNOWN)"
    )
    static_vulnerability_index: float = Field(0.0, ge=0.0, le=1.0)

    # Operational Metadata & Audit Trail
    reason_codes: List[str] = Field(default_factory=list)
    safety_notice: str = Field(MANDATORY_ROAD_SAFETY_NOTICE)
    is_actionable_for_dispatch: bool = False

    @field_validator("safety_notice")
    @classmethod
    def validate_safety_notice_phrasing(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety notice contains forbidden phrasing implying guaranteed safety: '{phrase}'")
        return v

    @model_validator(mode="after")
    def validate_safety_invariants(self) -> "RoadStatusSnapshot":
        # 1. Prohibit any string field asserting guaranteed safety
        all_text = " ".join([
            self.road_name,
            self.safety_notice,
            self.conflict_details or "",
            " ".join(self.reason_codes),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Payload contains forbidden safety assertion: '{phrase}'")

        # 2. Invariant: Missing or unmonitored evidence cannot have high confidence
        if self.condition_state in {RoadConditionState.UNKNOWN, RoadConditionState.NO_CURRENT_EVIDENCE}:
            if self.confidence_score > 0.25:
                raise ValueError(
                    f"Confidence score ({self.confidence_score}) cannot exceed 0.25 for condition state {self.condition_state.value}"
                )
            if self.uncertainty_level != UncertaintyLevel.HIGH:
                raise ValueError(
                    f"Uncertainty level must be HIGH for {self.condition_state.value}, got {self.uncertainty_level.value}"
                )

        # 3. Invariant: Measured water depth requires authorized verification or physical telemetry
        authorized_for_depth = (
            self.verification_state == RoadVerificationState.VERIFIED_BY_RESPONDER
            or self.evidence_type == RoadEvidenceType.PHYSICAL_TELEMETRY
        )
        if not authorized_for_depth and self.measured_water_depth_cm is not None:
            raise ValueError(
                "measured_water_depth_cm cannot be declared without VERIFIED_BY_RESPONDER or PHYSICAL_TELEMETRY evidence"
            )

        # 4. Invariant: Passability cannot declare passable without verification
        if not authorized_for_depth and self.verified_passability not in {"unverified_unknown", "UNKNOWN"}:
            raise ValueError(
                f"verified_passability cannot declare '{self.verified_passability}' without authorized verification"
            )

        # 5. Invariant: Expired or stale evidence cannot masquerade as FRESH
        if self.condition_state == RoadConditionState.STALE and self.freshness_category == RoadFreshnessCategory.FRESH:
            raise ValueError("STALE condition state cannot be categorized with FRESH freshness")

        return self


class RoadStatusEvaluationInput(BaseModel):
    """
    Offline input payload for road status fusion evaluation.
    Used for unit testing, scenario simulations, and service integration.
    """
    road_segment_id: str
    road_name: Optional[str] = None
    corridor_zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    community_reports: List[Dict[str, Any]] = Field(default_factory=list)
    field_observations: List[Dict[str, Any]] = Field(default_factory=list)
    rainfall_risk_category: Optional[str] = "UNKNOWN"
    rainfall_risk_score: Optional[float] = 0.0
    vulnerability_category: Optional[str] = "UNKNOWN"
    vulnerability_index: Optional[float] = 0.0
    evaluation_timestamp_utc: Optional[str] = None
