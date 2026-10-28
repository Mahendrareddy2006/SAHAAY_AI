"""
Sahaay AI - Citizen Report Schemas
Data contracts for citizen flood reports, verification events, privacy masking, and corroboration.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReportValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID_OUT_OF_BOUNDS = "INVALID_OUT_OF_BOUNDS"
    SPAM_OR_MALFORMED = "SPAM_OR_MALFORMED"


class ReportVerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CORROBORATED = "CORROBORATED"
    VERIFIED_BY_RESPONDER = "VERIFIED_BY_RESPONDER"
    REJECTED_FALSE_ALARM = "REJECTED_FALSE_ALARM"
    REJECTED_INVALID = "REJECTED_INVALID"
    EXPIRED = "EXPIRED"


class ReportFreshness(str, Enum):
    FRESH = "FRESH"          # <= 60 minutes
    AGING = "AGING"          # 60 - 180 minutes
    STALE = "STALE"          # 180 - 360 minutes
    EXPIRED = "EXPIRED"      # > 360 minutes


class WaterDepthEstimate(str, Enum):
    PUDDLE_SURFACE_WET = "PUDDLE_SURFACE_WET"      # < 10 cm, passable
    ANKLE_DEEP = "ANKLE_DEEP"                      # 10 - 25 cm, difficult for small vehicles
    KNEE_DEEP = "KNEE_DEEP"                        # 25 - 50 cm, impassable for cars
    WAIST_DEEP_OR_MORE = "WAIST_DEEP_OR_MORE"      # > 50 cm, emergency inundation


class ReportCondition(str, Enum):
    FLOODED_ROAD = "FLOODED_ROAD"
    WATERLOGGED_PASSABLE = "WATERLOGGED_PASSABLE"
    WET_ROAD_NO_FLOOD = "WET_ROAD_NO_FLOOD"
    DRY_ROAD_CLEAR = "DRY_ROAD_CLEAR"
    BLOCKED_DRAIN_SURCHARGE = "BLOCKED_DRAIN_SURCHARGE"
    UNCERTAIN_AMBIGUOUS = "UNCERTAIN_AMBIGUOUS"


class SubmissionChannel(str, Enum):
    WEB_PORTAL = "WEB_PORTAL"
    MOBILE_APP = "MOBILE_APP"
    FIELD_KIOSK = "FIELD_KIOSK"
    SMS_GATEWAY = "SMS_GATEWAY"
    OFFLINE_TEST_FIXTURE = "OFFLINE_TEST_FIXTURE"


class ConflictStatus(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    CONFLICTING_COMMUNITY_REPORTS = "CONFLICTING_COMMUNITY_REPORTS"
    CONFLICTING_PHYSICAL_TELEMETRY = "CONFLICTING_PHYSICAL_TELEMETRY"


class StatusTransitionEvent(BaseModel):
    """
    Auditable log of a verification status transition.
    """
    from_status: ReportVerificationStatus
    to_status: ReportVerificationStatus
    transitioned_at_utc: str
    actor_id: str
    actor_role: str
    rationale: str
    evidence_reference: Optional[str] = None


class CitizenReportSubmission(BaseModel):
    """
    Inbound payload from citizen report web/mobile interface.
    """
    corridor_id: str
    latitude: float = Field(..., ge=17.0, le=17.8)
    longitude: float = Field(..., ge=78.1, le=78.8)
    location_precision_m: float = Field(50.0, ge=1.0, le=5000.0)
    description: str = Field(..., min_length=5, max_length=1000)
    estimated_depth: WaterDepthEstimate = WaterDepthEstimate.ANKLE_DEEP
    image_reference: Optional[str] = None
    reporter_contact_raw: Optional[str] = Field(None, description="Phone/Email to be masked")
    consent_given: bool = Field(..., description="Explicit user consent to share report data for public safety")

    # Phase 15 Community Verification extensions:
    observation_time_utc: Optional[str] = Field(
        None, description="ISO 8601 UTC timestamp when condition was physically observed"
    )
    reported_condition: ReportCondition = Field(
        ReportCondition.FLOODED_ROAD, description="Categorical condition observed by citizen"
    )
    submission_channel: SubmissionChannel = Field(
        SubmissionChannel.WEB_PORTAL, description="Channel through which report was submitted"
    )
    evidence_reference: Optional[str] = Field(
        None, description="External reference (e.g. photo URL or dispatch ID)"
    )


class CitizenReportRecord(BaseModel):
    """
    Stored citizen report record with privacy masking, deduplication, corroboration, and auditable history.
    """
    report_id: str
    corridor_id: str
    submission_timestamp_utc: str
    observation_timestamp_utc: str = Field("", description="Physically observed time, distinct from submission time")
    latitude_coarsened: float
    longitude_coarsened: float
    location_precision_m: float
    description_sanitized: str
    estimated_depth: WaterDepthEstimate
    reported_condition: ReportCondition = ReportCondition.FLOODED_ROAD
    submission_channel: SubmissionChannel = SubmissionChannel.WEB_PORTAL
    image_reference: Optional[str] = None
    image_hash_dhash: Optional[str] = None
    evidence_reference: Optional[str] = None
    
    # Privacy protection
    reporter_id_masked: str
    privacy_redaction_applied: bool = True
    
    # Validation & Quality
    validation_status: ReportValidationStatus = ReportValidationStatus.VALID
    is_duplicate: bool = False
    duplicate_of_report_id: Optional[str] = None
    
    # Corroboration & Verification
    corroboration_count: int = 1
    independent_sources_count: int = 1  # Distinguishes multi-report volume from independent sources
    linked_report_ids: List[str] = Field(default_factory=list)
    verification_status: ReportVerificationStatus = ReportVerificationStatus.UNVERIFIED
    verified_by_entity: Optional[str] = None
    verification_timestamp_utc: Optional[str] = None
    verification_rationale: Optional[str] = None
    evidence_provenance: Optional[str] = None
    
    # Freshness
    freshness: ReportFreshness = ReportFreshness.FRESH
    age_minutes: float = 0.0
    reason_codes: List[str] = Field(default_factory=list)

    # Conflict & Auditability
    conflict_status: ConflictStatus = ConflictStatus.NO_CONFLICT
    conflict_details: Optional[str] = None
    status_history: List[StatusTransitionEvent] = Field(default_factory=list)


class ReportVerificationRequest(BaseModel):
    """
    Payload for municipal responder or field team verification.
    """
    verifier_id: str
    verifier_role: str = Field(..., description="e.g., 'GHMC_DRF_OFFICER', 'TRAFFIC_POLICE'")
    verification_status: ReportVerificationStatus
    observed_depth_cm: Optional[float] = None
    verification_notes: str
    evidence_reference: Optional[str] = None
