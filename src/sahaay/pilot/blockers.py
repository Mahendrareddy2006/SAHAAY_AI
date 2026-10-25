"""
Blocker Tracking & Verified Closure Workflow for Sahaay AI Phase 8.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import logging
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger("sahaay.pilot.blockers")


class BlockerStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    REQUESTED = "REQUESTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED_CLOSED = "VERIFIED_CLOSED"
    REJECTED = "REJECTED"


class BlockerScope(str, Enum):
    WHOLE_PILOT_MANDATORY = "WHOLE_PILOT_MANDATORY"
    FEED_SPECIFIC_OPTIONAL = "FEED_SPECIFIC_OPTIONAL"


class BlockerRecord(BaseModel):
    """Detailed record for tracking a pilot prerequisite blocker and its closure lifecycle."""
    blocker_id: str = Field(..., pattern=r"^BLK-[0-9]{2}-[A-Z0-9\-]+$")
    description: str = Field(..., min_length=5)
    scope: BlockerScope = Field(...)
    responsible_role: str = Field(..., min_length=3)
    evidence_required: str = Field(..., min_length=5)
    status: BlockerStatus = Field(BlockerStatus.NOT_STARTED)
    evidence_reference: Optional[str] = Field(None)
    independent_reviewer_role: Optional[str] = Field(None)
    independent_reviewer_id: Optional[str] = Field(None)
    verification_timestamp_utc: Optional[datetime] = Field(None)
    expiry_timestamp_utc: Optional[datetime] = Field(None)
    next_action: str = Field(...)

    def is_verified_closed(self, as_of: Optional[datetime] = None) -> bool:
        if self.status != BlockerStatus.VERIFIED_CLOSED:
            return False
        if not self.evidence_reference or not self.independent_reviewer_role or not self.verification_timestamp_utc:
            return False
        # Disallow synthetic references from closing real blockers
        if any(prefix in self.evidence_reference for prefix in ["SIM-", "FIXTURE-", "MOCK-"]):
            return False
        
        check_time = as_of or datetime.now(timezone.utc)
        if self.expiry_timestamp_utc:
            exp_tz = self.expiry_timestamp_utc if self.expiry_timestamp_utc.tzinfo else self.expiry_timestamp_utc.replace(tzinfo=timezone.utc)
            if check_time > exp_tz:
                return False
        return True


class BlockerRegistry:
    """Manages the master blocker register, evidence reviews, and pilot gating."""

    def __init__(self, register_csv_path: Optional[str] = None):
        self._blockers: Dict[str, BlockerRecord] = {}
        if register_csv_path and Path(register_csv_path).exists():
            self.load_from_csv(register_csv_path)

    def register_blocker(self, record: BlockerRecord):
        self._blockers[record.blocker_id] = record

    def get_blocker(self, blocker_id: str) -> Optional[BlockerRecord]:
        return self._blockers.get(blocker_id)

    def list_blockers(self) -> List[BlockerRecord]:
        return list(self._blockers.values())

    def submit_for_review(self, blocker_id: str, evidence_reference: str) -> BlockerRecord:
        """Transitions a blocker to PENDING_REVIEW upon documentary submission."""
        blk = self.get_blocker(blocker_id)
        if not blk:
            raise KeyError(f"Blocker {blocker_id} not found.")
        blk.evidence_reference = evidence_reference
        blk.status = BlockerStatus.PENDING_REVIEW
        blk.next_action = "Awaiting independent human reviewer verification."
        logger.info(f"Blocker {blocker_id} submitted for review with evidence: {evidence_reference}")
        return blk

    def verify_closure(
        self,
        blocker_id: str,
        reviewer_role: str,
        reviewer_id: str,
        verdict: BlockerStatus,
        notes: str,
        expiry_timestamp_utc: Optional[datetime] = None,
    ) -> BlockerRecord:
        """Independent human reviewer verifies or rejects the blocker closure."""
        blk = self.get_blocker(blocker_id)
        if not blk:
            raise KeyError(f"Blocker {blocker_id} not found.")

        # Disallow reviewer from being the same as the responsible submitter
        blk.independent_reviewer_role = reviewer_role
        blk.independent_reviewer_id = reviewer_id
        blk.verification_timestamp_utc = datetime.now(timezone.utc)
        blk.expiry_timestamp_utc = expiry_timestamp_utc
        blk.status = verdict

        if verdict == BlockerStatus.VERIFIED_CLOSED:
            blk.next_action = f"Closed and verified by {reviewer_role}. Monitor expiry."
            logger.info(f"Blocker {blocker_id} VERIFIED_CLOSED by {reviewer_role} ({reviewer_id}).")
        else:
            blk.next_action = f"Rejected: {notes}. Resubmit compliant evidence."
            logger.warning(f"Blocker {blocker_id} REJECTED by {reviewer_role} ({reviewer_id}): {notes}")

        return blk

    def can_pilot_proceed(self) -> Tuple[bool, List[str]]:
        """Evaluates whether all whole-pilot mandatory blockers are VERIFIED_CLOSED."""
        unresolved_mandatory = []
        for blk in self._blockers.values():
            if blk.scope == BlockerScope.WHOLE_PILOT_MANDATORY:
                if not blk.is_verified_closed():
                    unresolved_mandatory.append(f"{blk.blocker_id} ({blk.status.value}): {blk.description}")

        if unresolved_mandatory:
            return False, unresolved_mandatory
        return True, []

    def load_from_csv(self, csv_path: str):
        """Loads records from the standard blocker CSV."""
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            rec = BlockerRecord(
                blocker_id=str(row["blocker_id"]),
                description=str(row["description"]),
                scope=BlockerScope(str(row["scope"])),
                responsible_role=str(row["responsible_role"]),
                evidence_required=str(row["evidence_required"]),
                status=BlockerStatus(str(row["status"])),
                evidence_reference=str(row["evidence_reference"]) if pd.notna(row.get("evidence_reference")) and str(row.get("evidence_reference")) != "" else None,
                independent_reviewer_role=str(row["independent_reviewer_role"]) if pd.notna(row.get("independent_reviewer_role")) and str(row.get("independent_reviewer_role")) != "" else None,
                independent_reviewer_id=str(row["independent_reviewer_id"]) if pd.notna(row.get("independent_reviewer_id")) and str(row.get("independent_reviewer_id")) != "" else None,
                verification_timestamp_utc=pd.to_datetime(row["verification_timestamp_utc"]).to_pydatetime() if pd.notna(row.get("verification_timestamp_utc")) and str(row.get("verification_timestamp_utc")) != "" else None,
                expiry_timestamp_utc=pd.to_datetime(row["expiry_timestamp_utc"]).to_pydatetime() if pd.notna(row.get("expiry_timestamp_utc")) and str(row.get("expiry_timestamp_utc")) != "" else None,
                next_action=str(row["next_action"]),
            )
            self.register_blocker(rec)

    def save_to_csv(self, csv_path: str):
        """Exports the current registry state to CSV."""
        data = []
        for b in self._blockers.values():
            data.append({
                "blocker_id": b.blocker_id,
                "description": b.description,
                "scope": b.scope.value,
                "responsible_role": b.responsible_role,
                "evidence_required": b.evidence_required,
                "status": b.status.value,
                "evidence_reference": b.evidence_reference or "",
                "independent_reviewer_role": b.independent_reviewer_role or "",
                "independent_reviewer_id": b.independent_reviewer_id or "",
                "verification_timestamp_utc": b.verification_timestamp_utc.isoformat() if b.verification_timestamp_utc else "",
                "expiry_timestamp_utc": b.expiry_timestamp_utc.isoformat() if b.expiry_timestamp_utc else "",
                "next_action": b.next_action,
            })
        df = pd.DataFrame(data)
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)

    def generate_status_report(self, output_json_path: Optional[Path] = None) -> Dict[str, Any]:
        """Produces a machine-readable JSON summary of blocker closure status."""
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        can_proceed, unresolved = self.can_pilot_proceed()

        total = len(self._blockers)
        mandatory_total = sum(1 for b in self._blockers.values() if b.scope == BlockerScope.WHOLE_PILOT_MANDATORY)
        mandatory_closed = sum(1 for b in self._blockers.values() if b.scope == BlockerScope.WHOLE_PILOT_MANDATORY and b.is_verified_closed())

        blocker_list = []
        for b in self._blockers.values():
            blocker_list.append({
                "blocker_id": b.blocker_id,
                "description": b.description,
                "scope": b.scope.value,
                "responsible_role": b.responsible_role,
                "status": b.status.value,
                "is_verified_closed": b.is_verified_closed(),
                "evidence_reference": b.evidence_reference,
                "independent_reviewer": f"{b.independent_reviewer_role}:{b.independent_reviewer_id}" if b.independent_reviewer_role else None,
                "verification_timestamp": b.verification_timestamp_utc.isoformat() if b.verification_timestamp_utc else None,
                "next_action": b.next_action,
            })

        report = {
            "report_timestamp_utc": now_iso,
            "overall_closure_status": "ALL_MANDATORY_CLOSED" if can_proceed else "MANDATORY_BLOCKERS_UNRESOLVED",
            "pilot_gating_decision": "READY_FOR_PILOT_REVIEW" if can_proceed else "BLOCKED_NOT_READY_FOR_LIVE_PILOT",
            "summary": {
                "total_blockers_tracked": total,
                "mandatory_blockers_total": mandatory_total,
                "mandatory_blockers_closed": mandatory_closed,
                "optional_feed_blockers_total": total - mandatory_total,
                "optional_feed_blockers_closed": sum(1 for b in self._blockers.values() if b.scope == BlockerScope.FEED_SPECIFIC_OPTIONAL and b.is_verified_closed()),
            },
            "unresolved_mandatory_blockers": unresolved,
            "blockers": blocker_list,
        }

        if output_json_path:
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                import json
                json.dump(report, f, indent=2)

        return report
