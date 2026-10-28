"""
Sahaay AI - Phase 20: Emergency Mode Schemas
(src/sahaay/emergency/schemas.py)

Canonical data contracts for the offline emergency assessment workflow.
Codifies state machines, human authorization checks, transparent review prioritization,
and strict operational safety boundaries.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadStatusSnapshot,
)
from sahaay.forecast_risk.schemas import (
    ForecastRiskAssessmentOutput,
)
from sahaay.routing.schemas import (
    RiskAwareRouteAssessment,
)


class EmergencyState(str, Enum):
    """
    Validated lifecycle states for emergency-mode assessment.
    Resolution requires explicit human review by an authorized role.
    """
    INACTIVE = "INACTIVE"
    ACTIVE_ASSESSMENT = "ACTIVE_ASSESSMENT"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    DEGRADED_INSUFFICIENT_DATA = "DEGRADED_INSUFFICIENT_DATA"
    RESOLVED_BY_AUTHORIZED_REVIEW = "RESOLVED_BY_AUTHORIZED_REVIEW"


class EmergencyPriority(str, Enum):
    """
    Deterministic triage priority for human review queueing.
    Distinguishes review urgency from certainty of physical flooding.
    """
    P1_URGENT_VERIFIED = "P1_URGENT_VERIFIED"       # Verified deep flooding, impassable corridor, hospital access cutoff
    P2_HIGH_CORROBORATED = "P2_HIGH_CORROBORATED"   # Corroborated citizen reports, severe forecast surge on vulnerable road
    P3_MEDIUM_UNVERIFIED = "P3_MEDIUM_UNVERIFIED"   # Single uncorroborated report, moderate modeled risk
    P4_LOW_ADVISORY = "P4_LOW_ADVISORY"             # Trace rain, dry weather, low susceptibility
    P0_DEGRADED_TRIAGE = "P0_DEGRADED_TRIAGE"       # Defective, stale, or conflicting telemetry requiring data triage


class AuthorizedReviewerRole(str, Enum):
    """
    Authorized municipal roles permitted to review and resolve emergency assessments.
    Automated resolution or unauthorized user roles are strictly prohibited.
    """
    GHMC_DRF_SUPERVISOR = "GHMC_DRF_SUPERVISOR"
    TRAFFIC_POLICE_DUTY_OFFICER = "TRAFFIC_POLICE_DUTY_OFFICER"
    FIELD_SAFETY_LEAD = "FIELD_SAFETY_LEAD"
    EMERGENCY_COORDINATOR = "EMERGENCY_COORDINATOR"
    MUNICIPAL_LIAISON = "MUNICIPAL_LIAISON"
    SYSTEM_ADMINISTRATOR = "SYSTEM_ADMINISTRATOR"


MANDATORY_EMERGENCY_MODE_DISCLAIMER = (
    "ADVISORY EMERGENCY TRIAGE ONLY: Sahaay AI does not independently dispatch emergency responders, "
    "contact public emergency services (112/100/108), close roads, or issue public alerts. "
    "This system provides offline decision-support to assist authorized human coordinators. "
    "Absence of reported flooding does NOT indicate safety. "
    "Physical emergency actions require explicit on-ground command verification."
)

FORBIDDEN_SAFETY_PHRASES = [
    "guaranteed safe",
    "100% safe",
    "completely safe",
    "safe passage guaranteed",
    "zero risk",
    "road is safe",
    "emergency resolved automatically",
    "dispatched automatically",
    "responders en route",
]


class EmergencyResolutionRecord(BaseModel):
    """
    Immutable audit record documenting the authorized human resolution of an emergency state.
    """
    resolution_id: str = Field(..., pattern=r"^RES-[A-Z0-9]{8,16}$")
    reviewer_role: AuthorizedReviewerRole
    reviewer_id: str = Field(..., min_length=3, max_length=50, description="Masked ID of authorized human operator")
    action_type: str = Field(..., min_length=3, max_length=50)
    justification_notes: str = Field(..., min_length=10, max_length=1000)
    timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of resolution action")
    audit_hash: str = Field(..., min_length=64, max_length=64, description="SHA-256 cryptographic signature")
    audit_disclaimer: str = Field(
        "AUDIT DISCLAIMER: Software SHA-256 hash records state snapshot only; does not prove legal identity or tamper-proof storage.",
        description="Software hash disclaimer"
    )

    @classmethod
    def create(
        cls,
        resolution_id: str,
        reviewer_role: AuthorizedReviewerRole,
        reviewer_id: str,
        action_type: str,
        justification_notes: str,
        timestamp_utc: str,
        previous_hash: str = "GENESIS_PHASE20",
    ) -> "EmergencyResolutionRecord":
        payload = f"{resolution_id}|{reviewer_role.value}|{reviewer_id}|{action_type}|{justification_notes}|{timestamp_utc}|{previous_hash}"
        audit_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return cls(
            resolution_id=resolution_id,
            reviewer_role=reviewer_role,
            reviewer_id=reviewer_id,
            action_type=action_type,
            justification_notes=justification_notes,
            timestamp_utc=timestamp_utc,
            audit_hash=audit_hash,
        )


class EmergencyAssessmentInput(BaseModel):
    """
    Structured multi-source evidence container for emergency triage evaluation.
    Preserves provenance and minimizes personal data.
    """
    incident_id: str = Field(..., min_length=3, max_length=50)
    corridor_id: str = Field(..., min_length=3, max_length=50)
    road_name: str = Field(..., min_length=2, max_length=150)
    
    # Traceable multi-source signals
    road_status_snapshot: Optional[RoadStatusSnapshot] = None
    forecast_risk_output: Optional[ForecastRiskAssessmentOutput] = None
    route_assessment_output: Optional[RiskAwareRouteAssessment] = None
    community_report_summary: Optional[Dict[str, Any]] = None
    
    # Geospatial static context
    static_vulnerability_index: Optional[float] = None
    static_vulnerability_category: Optional[str] = None
    
    # Metadata & privacy
    is_synthetic_fixture: bool = Field(False, description="True for unit test fixtures only")
    reporter_id_masked: Optional[str] = Field(None, description="Masked reporter token; personal data stripped")


class EmergencyModeAssessment(BaseModel):
    """
    Formal, explainable emergency-mode triage assessment payload.
    Enforces strict operational boundaries: zero autonomous dispatch,
    zero uncalibrated probability claims, and mandatory human authorization.
    """
    incident_id: str
    corridor_id: str
    road_name: str
    assessment_timestamp_utc: str
    current_state: EmergencyState
    state_transition_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Triage Priority & Explanation
    review_priority: EmergencyPriority
    priority_reason_codes: List[str] = Field(default_factory=list)
    urgency_heuristic_score: float = Field(..., ge=0.0, le=1.0)
    is_calibrated_probability: bool = Field(
        False, description="Must remain False: heuristic urgency score is NOT a calibrated probability"
    )
    evidence_certainty_level: str = "UNKNOWN"

    # Multi-source Context (Separated)
    ground_status_evidence: Dict[str, Any]
    forecast_rainfall_context: Dict[str, Any]
    static_susceptibility_context: Dict[str, Any]
    routing_impact_context: Dict[str, Any]

    # Human Review & Resolution
    resolution_record: Optional[EmergencyResolutionRecord] = None
    missing_critical_inputs: List[str] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)

    # Safety Invariant Flags
    operational_action_authorized: bool = Field(
        False, description="Must remain False: advisory assessment CANNOT authorize real dispatch"
    )
    external_side_effects_triggered: bool = Field(
        False, description="Must remain False: no real dispatch, SMS, or closures can be executed"
    )
    personal_data_masked: bool = Field(
        True, description="Must remain True: PII is strictly stripped or tokenized"
    )
    safety_disclaimer: str = MANDATORY_EMERGENCY_MODE_DISCLAIMER
    engine_status: str = "OFFLINE_EMERGENCY_TRIAGE_LAYER"

    @field_validator("safety_disclaimer")
    @classmethod
    def validate_safety_disclaimer(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety disclaimer contains forbidden phrase: '{phrase}'")
        if "does not independently dispatch" not in v_lower:
            raise ValueError("Safety disclaimer must explicitly declare that dispatch is prohibited.")
        return v

    @model_validator(mode="after")
    def validate_emergency_safety_invariants(self) -> "EmergencyModeAssessment":
        # 1. Invariant: Probability claims prohibition
        if self.is_calibrated_probability:
            raise ValueError("is_calibrated_probability must remain False on emergency assessment.")

        # 2. Invariant: Operational action prohibition
        if self.operational_action_authorized:
            raise ValueError("operational_action_authorized must remain False: advisory triage cannot authorize action.")

        # 3. Invariant: External side-effects prohibition
        if self.external_side_effects_triggered:
            raise ValueError("external_side_effects_triggered must remain False: no external calls permitted.")

        # 4. Invariant: Resolution requires authorized human review
        if self.current_state == EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW:
            if self.resolution_record is None:
                raise ValueError(
                    "State cannot be RESOLVED_BY_AUTHORIZED_REVIEW without a valid EmergencyResolutionRecord."
                )

        # 5. Invariant: Prohibit automatic resolution from silence or timeouts
        all_text = " ".join([
            self.safety_disclaimer,
            " ".join(self.priority_reason_codes),
            " ".join(self.quality_flags),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Emergency assessment contains forbidden phrase: '{phrase}'")

        # 6. Personal data minimization
        if not self.personal_data_masked:
            raise ValueError("personal_data_masked must remain True: reporter PII must be protected.")

        return self
