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
    VERIFIED_BY_RESPONDER = "VERIFIED_BY_RESPONDER"
    REJECTED_FALSE_ALARM = "REJECTED_FALSE_ALARM"


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


class CitizenReportRecord(BaseModel):
    """
    Stored citizen report record with privacy masking, deduplication, and corroboration status.
    """
    report_id: str
    corridor_id: str
    submission_timestamp_utc: str
    latitude_coarsened: float
    longitude_coarsened: float
    location_precision_m: float
    description_sanitized: str
    estimated_depth: WaterDepthEstimate
    image_reference: Optional[str] = None
    image_hash_dhash: Optional[str] = None
    
    # Privacy protection
    reporter_id_masked: str
    privacy_redaction_applied: bool = True
    
    # Validation & Quality
    validation_status: ReportValidationStatus = ReportValidationStatus.VALID
    is_duplicate: bool = False
    duplicate_of_report_id: Optional[str] = None
    
    # Corroboration & Verification
    corroboration_count: int = 1
    linked_report_ids: List[str] = Field(default_factory=list)
    verification_status: ReportVerificationStatus = ReportVerificationStatus.UNVERIFIED
    verified_by_entity: Optional[str] = None
    verification_timestamp_utc: Optional[str] = None
    
    # Freshness
    freshness: ReportFreshness = ReportFreshness.FRESH
    age_minutes: float = 0.0
    reason_codes: List[str] = Field(default_factory=list)


class ReportVerificationRequest(BaseModel):
    """
    Payload for municipal responder or field team verification.
    """
    verifier_id: str
    verifier_role: str = Field(..., description="e.g., 'GHMC_DRF_OFFICER', 'TRAFFIC_POLICE'")
    verification_status: ReportVerificationStatus
    observed_depth_cm: Optional[float] = None
    verification_notes: str
