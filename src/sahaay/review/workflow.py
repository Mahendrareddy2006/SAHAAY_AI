"""Operational Human Review Queue & Incident Audit Service for Sahaay AI Phase 6."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("sahaay.review.workflow")


class ReviewItemType(str, Enum):
    CITIZEN_REPORT = "CITIZEN_REPORT"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    HIGH_RISK_ENVIRONMENTAL = "HIGH_RISK_ENVIRONMENTAL"
    SUSPECTED_DUPLICATE_CLUSTER = "SUSPECTED_DUPLICATE_CLUSTER"


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED_CONFIRMED = "VERIFIED_CONFIRMED"
    DISMISSED_FALSE_ALARM = "DISMISSED_FALSE_ALARM"
    ESCALATED_TO_FIELD_TEAM = "ESCALATED_TO_FIELD_TEAM"
    ESCALATED_TO_DRF = "ESCALATED_TO_DRF"


class ReviewerRole(str, Enum):
    SUPERVISOR_DISPATCHER = "SUPERVISOR_DISPATCHER"
    FIELD_SAFETY_LEAD = "FIELD_SAFETY_LEAD"
    SYSTEM_ADMINISTRATOR = "SYSTEM_ADMINISTRATOR"
    MUNICIPAL_LIAISON = "MUNICIPAL_LIAISON"


class ReviewAction(BaseModel):
    action_id: str = Field(..., pattern=r"^ACT-[A-Z0-9]{8}$")
    reviewer_role: ReviewerRole = Field(...)
    reviewer_id: str = Field(..., min_length=3)
    action_type: str = Field(..., min_length=3)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification_notes: str = Field(..., min_length=5)
    audit_hash: Optional[str] = None

    def compute_hash(self, prev_hash: str = "") -> str:
        payload = f"{self.action_id}|{self.reviewer_role}|{self.reviewer_id}|{self.action_type}|{self.timestamp_utc.isoformat()}|{self.justification_notes}|{prev_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReviewItem(BaseModel):
    item_id: str = Field(...)
    item_type: ReviewItemType = Field(...)
    corridor_id: str = Field(...)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alert_level: str = Field("ADVISORY")
    evidence_status: str = Field(...)
    reason_codes: List[str] = Field(default_factory=list)
    conflicting_sources: List[str] = Field(default_factory=list)
    status: ReviewStatus = Field(ReviewStatus.PENDING_REVIEW)
    audit_chain: List[ReviewAction] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewQueueService:
    """Manages the human-in-the-loop operational review queue with cryptographically chained actions."""

    def __init__(self):
        self._queue: Dict[str, ReviewItem] = {}

    def enqueue(self, item_dict: Dict[str, Any]) -> ReviewItem:
        item = ReviewItem(**item_dict)
        self._queue[item.item_id] = item
        logger.info(f"Enqueued item {item.item_id} for human review (Type: {item.item_type}).")
        return item

    def get_item(self, item_id: str) -> Optional[ReviewItem]:
        return self._queue.get(item_id)

    def list_pending(self) -> List[ReviewItem]:
        return [item for item in self._queue.values() if item.status == ReviewStatus.PENDING_REVIEW]

    def record_review_action(
        self,
        item_id: str,
        reviewer_role: ReviewerRole,
        reviewer_id: str,
        action_type: str,
        justification_notes: str,
        new_status: ReviewStatus,
    ) -> ReviewItem:
        item = self.get_item(item_id)
        if not item:
            raise KeyError(f"Review item {item_id} not found in queue.")

        action_id = f"ACT-{hashlib.md5(f'{item_id}{datetime.now(timezone.utc).isoformat()}'.encode()).hexdigest()[:8].upper()}"
        action = ReviewAction(
            action_id=action_id,
            reviewer_role=reviewer_role,
            reviewer_id=reviewer_id,
            action_type=action_type,
            justification_notes=justification_notes,
        )

        # Chained hash
        prev_hash = item.audit_chain[-1].audit_hash if item.audit_chain else "GENESIS_REVIEW_ROOT"
        action.audit_hash = action.compute_hash(prev_hash)

        item.audit_chain.append(action)
        item.status = new_status
        logger.info(f"Review item {item_id} transitioned to {new_status} by {reviewer_role} ({reviewer_id}).")
        return item
