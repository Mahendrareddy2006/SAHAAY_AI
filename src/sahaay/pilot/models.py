"""
Pilot Activation Gate Data Models & State Definitions for Sahaay AI Phase 7.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
import hashlib
from pydantic import BaseModel, Field, model_validator


class PilotState(str, Enum):
    BLOCKED_NOT_READY_FOR_LIVE_PILOT = "BLOCKED_NOT_READY_FOR_LIVE_PILOT"
    READY_FOR_AUTHORIZED_PILOT_REVIEW = "READY_FOR_AUTHORIZED_PILOT_REVIEW"
    PILOT_AUTHORIZED = "PILOT_AUTHORIZED"
    PILOT_SUSPENDED = "PILOT_SUSPENDED"
    PILOT_COMPLETED = "PILOT_COMPLETED"


class PrerequisiteID(str, Enum):
    PREREQ_01_INSTITUTIONAL_AGREEMENT = "PREREQ_01_INSTITUTIONAL_AGREEMENT"
    PREREQ_02_RESPONSIBLE_LEAD_RECORDED = "PREREQ_02_RESPONSIBLE_LEAD_RECORDED"
    PREREQ_03_SITE_SAFETY_INSPECTIONS = "PREREQ_03_SITE_SAFETY_INSPECTIONS"
    PREREQ_04_PPE_EQUIPMENT_CHECK = "PREREQ_04_PPE_EQUIPMENT_CHECK"
    PREREQ_05_CONSENT_PRIVACY_DEPLOYED = "PREREQ_05_CONSENT_PRIVACY_DEPLOYED"
    PREREQ_06_RETENTION_DELETION_OPERATIONAL = "PREREQ_06_RETENTION_DELETION_OPERATIONAL"
    PREREQ_07_INGESTION_WORKFLOW_VERIFIED = "PREREQ_07_INGESTION_WORKFLOW_VERIFIED"
    PREREQ_08_DATA_FEED_AUTHORIZATION = "PREREQ_08_DATA_FEED_AUTHORIZATION"


class PrerequisiteVerificationStatus(str, Enum):
    UNVERIFIED_PENDING = "UNVERIFIED_PENDING"
    VERIFIED_EVIDENCE_ATTACHED = "VERIFIED_EVIDENCE_ATTACHED"
    REJECTED_INSUFFICIENT = "REJECTED_INSUFFICIENT"
    EXPIRED = "EXPIRED"


class PrerequisiteRecord(BaseModel):
    """Auditable prerequisite entry representing a legal, safety, or technical gate condition."""
    prereq_id: PrerequisiteID = Field(...)
    title: str = Field(...)
    is_mandatory_for_pilot: bool = Field(True)
    applies_to_scope: str = Field("ALL_PILOT_OPERATIONS", description="ALL_PILOT_OPERATIONS or specific feed ID")
    status: PrerequisiteVerificationStatus = Field(PrerequisiteVerificationStatus.UNVERIFIED_PENDING)
    evidence_reference: Optional[str] = Field(None, description="Document ID or signed filing reference")
    verified_by_role: Optional[str] = Field(None)
    verified_by_id: Optional[str] = Field(None)
    verification_timestamp_utc: Optional[datetime] = Field(None)
    expiration_timestamp_utc: Optional[datetime] = Field(None)
    notes: Optional[str] = Field(None)

    def is_currently_valid(self, as_of: Optional[datetime] = None) -> bool:
        """Evaluates whether this prerequisite is currently satisfied and not expired."""
        if self.status != PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED:
            return False
        if not self.evidence_reference or not self.verified_by_role or not self.verification_timestamp_utc:
            return False
        # Disallow synthetic fixture as real-world evidence
        if "SIM-" in self.evidence_reference or "FIXTURE-" in self.evidence_reference or "MOCK-" in self.evidence_reference:
            return False

        check_time = as_of or datetime.now(timezone.utc)
        if self.expiration_timestamp_utc:
            exp_tz = self.expiration_timestamp_utc if self.expiration_timestamp_utc.tzinfo else self.expiration_timestamp_utc.replace(tzinfo=timezone.utc)
            if check_time > exp_tz:
                return False
        return True


class TransitionAction(BaseModel):
    """Attributable, cryptographically signed state transition audit record."""
    transition_id: str = Field(..., pattern=r"^TRN-[A-Z0-9]{8}$")
    from_state: PilotState = Field(...)
    to_state: PilotState = Field(...)
    authorized_by_role: str = Field(..., min_length=3)
    authorized_by_id: str = Field(..., min_length=3)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification_notes: str = Field(..., min_length=10)
    audit_hash: Optional[str] = None

    def compute_hash(self, prev_hash: str = "") -> str:
        payload = f"{self.transition_id}|{self.from_state}|{self.to_state}|{self.authorized_by_role}|{self.authorized_by_id}|{self.timestamp_utc.isoformat()}|{self.justification_notes}|{prev_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
