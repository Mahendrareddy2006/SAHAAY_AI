"""
Human-Verified Evidence Intake & Documentary Validation Service for Sahaay AI Phase 8.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import logging
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger("sahaay.pilot.evidence")


class EvidenceCategory(str, Enum):
    INSTITUTIONAL_MOU = "INSTITUTIONAL_MOU"
    SITE_SAFETY_INSPECTION = "SITE_SAFETY_INSPECTION"
    PPE_EQUIPMENT_AUDIT = "PPE_EQUIPMENT_AUDIT"
    ROLE_DESIGNATION_LETTER = "ROLE_DESIGNATION_LETTER"
    DPDP_PRIVACY_AUDIT = "DPDP_PRIVACY_AUDIT"
    SOURCE_TELEMETRY_LICENSE = "SOURCE_TELEMETRY_LICENSE"


class EvidenceStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    VERIFIED_VALID = "VERIFIED_VALID"
    REJECTED_DEFICIENT = "REJECTED_DEFICIENT"
    EXPIRED = "EXPIRED"


class EvidenceDocumentRecord(BaseModel):
    """Metadata schema representing legal, safety, or institutional documentation."""
    evidence_id: str = Field(..., pattern=r"^EVD-[A-Z0-9\-]{6,20}$")
    category: EvidenceCategory = Field(...)
    title: str = Field(..., min_length=5)
    issuing_authority: str = Field(..., min_length=3)
    document_reference_hash: str = Field(..., min_length=8, description="SHA-256 or official filing reference")
    permitted_scope: List[str] = Field(..., min_length=1, description="List of approved corridor IDs or feed scopes")
    execution_date: datetime = Field(...)
    expiration_date: Optional[datetime] = Field(None)
    verification_status: EvidenceStatus = Field(EvidenceStatus.SUBMITTED)
    verified_by_role: Optional[str] = Field(None)
    verified_by_id: Optional[str] = Field(None)
    verification_notes: Optional[str] = Field(None)

    @model_validator(mode="after")
    def validate_dates_and_evidence(self) -> "EvidenceDocumentRecord":
        # Disallow synthetic references from being accepted as real
        if any(prefix in self.evidence_id for prefix in ["SIM-", "FIXTURE-", "MOCK-"]):
            raise ValueError(f"Synthetic ID {self.evidence_id} cannot be registered as real evidence.")
        
        if self.expiration_date and self.expiration_date < self.execution_date:
            raise ValueError(f"expiration_date ({self.expiration_date}) cannot be before execution_date ({self.execution_date})")

        return self

    def is_currently_valid_for_scope(self, target_scope: str, as_of: Optional[datetime] = None) -> Tuple[bool, str]:
        """Evaluates whether this document is verified, unexpired, and covers target scope."""
        if self.verification_status != EvidenceStatus.VERIFIED_VALID:
            return False, f"Document verification status is {self.verification_status.value} (not VERIFIED_VALID)."

        if not self.verified_by_role or not self.verified_by_id:
            return False, "Document lacks independent reviewer sign-off."

        check_time = as_of or datetime.now(timezone.utc)
        if self.expiration_date:
            exp_tz = self.expiration_date if self.expiration_date.tzinfo else self.expiration_date.replace(tzinfo=timezone.utc)
            if check_time > exp_tz:
                return False, f"Document expired on {exp_tz.isoformat()}."

        # Scope checking
        if "ALL_PILOT_OPERATIONS" not in self.permitted_scope and target_scope not in self.permitted_scope:
            return False, f"Document scope {self.permitted_scope} does not cover target scope '{target_scope}'."

        return True, "Document is verified, unexpired, and covers target scope."


class EvidenceIntakeService:
    """Manages registration, independent audit, and scope validation for real documentary evidence."""

    def __init__(self):
        self._vault: Dict[str, EvidenceDocumentRecord] = {}

    def register_evidence(self, data: Dict[str, Any]) -> EvidenceDocumentRecord:
        """Registers a newly submitted evidence document record."""
        rec = EvidenceDocumentRecord(**data)
        self._vault[rec.evidence_id] = rec
        logger.info(f"Registered evidence record {rec.evidence_id} (Category: {rec.category.value})")
        return rec

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceDocumentRecord]:
        return self._vault.get(evidence_id)

    def review_evidence(
        self,
        evidence_id: str,
        reviewer_role: str,
        reviewer_id: str,
        verdict: EvidenceStatus,
        notes: str,
    ) -> EvidenceDocumentRecord:
        """Independent human reviewer records verification verdict."""
        rec = self.get_evidence(evidence_id)
        if not rec:
            raise KeyError(f"Evidence record {evidence_id} not found.")

        rec.verified_by_role = reviewer_role
        rec.verified_by_id = reviewer_id
        rec.verification_status = verdict
        rec.verification_notes = notes

        logger.info(f"Evidence {evidence_id} reviewed by {reviewer_role} ({reviewer_id}): {verdict.value}")
        return rec

    def find_valid_evidence(self, category: EvidenceCategory, target_scope: str) -> Optional[EvidenceDocumentRecord]:
        """Finds any verified, unexpired document matching category and scope."""
        for rec in self._vault.values():
            if rec.category == category:
                is_valid, _ = rec.is_currently_valid_for_scope(target_scope)
                if is_valid:
                    return rec
        return None
