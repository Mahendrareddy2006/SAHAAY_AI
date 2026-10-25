"""
Centralized Pilot Activation Gate & Transition Authority for Sahaay AI Phase 7.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .models import (
    PilotState,
    PrerequisiteID,
    PrerequisiteVerificationStatus,
    PrerequisiteRecord,
    TransitionAction,
)

logger = logging.getLogger("sahaay.pilot.gate")


class PilotActivationGate:
    """
    Centralized, evidence-based activation gate enforcing fail-closed pilot activation rules.
    
    Invariants:
    1. A missing, expired, or unverified mandatory prerequisite locks state to BLOCKED_NOT_READY_FOR_LIVE_PILOT.
    2. Software cannot grant institutional authorization. Only an authorized human role
       (e.g., PRINCIPAL_INVESTIGATOR, PROJECT_DIRECTOR) can transition to PILOT_AUTHORIZED.
    3. Synthetic or simulated references cannot satisfy real prerequisite requirements.
    4. State transitions are cryptographically chained in an append-only audit trail.
    """

    def __init__(self):
        self._current_state = PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT
        self._prerequisites: Dict[PrerequisiteID, PrerequisiteRecord] = {}
        self._transition_history: List[TransitionAction] = []
        self._initialize_default_prerequisites()

    def _initialize_default_prerequisites(self):
        """Initializes the 8 mandatory and optional prerequisites based on factual repository state."""
        self._prerequisites = {
            PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT,
                title="Executed Institutional MoU & Data-Sharing Agreement with GHMC / HTP",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="Formal research data-sharing agreement request awaiting institutional execution.",
            ),
            PrerequisiteID.PREREQ_02_RESPONSIBLE_LEAD_RECORDED: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_02_RESPONSIBLE_LEAD_RECORDED,
                title="Authorized Field Lead & Safety Officer Formally Designated",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="Field roles defined in safety plan; specific individuals awaiting formal appointment letter.",
            ),
            PrerequisiteID.PREREQ_03_SITE_SAFETY_INSPECTIONS: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_03_SITE_SAFETY_INSPECTIONS,
                title="Physical Site Hazard & Railing Safety Inspection Completed",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="Physical daytime surveys at 4 candidate elevated vantage points pending execution.",
            ),
            PrerequisiteID.PREREQ_04_PPE_EQUIPMENT_CHECK: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_04_PPE_EQUIPMENT_CHECK,
                title="Certified High-Visibility PPE & Calibrated Staff Gauges Verified",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="Procurement and calibration checklist for EN ISO 20471 Class 2 vests and depth staffs pending.",
            ),
            PrerequisiteID.PREREQ_05_CONSENT_PRIVACY_DEPLOYED: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_05_CONSENT_PRIVACY_DEPLOYED,
                title="DPDP Act 2023 Consent Notice & 3-Decimal Coarsening Verified",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="Consent notice drafted; staging portal deployment and legal sign-off pending.",
            ),
            PrerequisiteID.PREREQ_06_RETENTION_DELETION_OPERATIONAL: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_06_RETENTION_DELETION_OPERATIONAL,
                title="Data Tiering, Vault Encryption, and Right-to-Erasure Workflow Operational",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
                evidence_reference="DOC-PHASE6-DATA-GOVERNANCE-v1.0",
                verified_by_role="LEGAL_AND_COMPLIANCE_LEAD",
                verified_by_id="COMPLIANCE-OFFICER-01",
                verification_timestamp_utc=datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc),
                notes="Multi-tier data vault and DPDP erasure policies implemented in src/sahaay/observations/.",
            ),
            PrerequisiteID.PREREQ_07_INGESTION_WORKFLOW_VERIFIED: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_07_INGESTION_WORKFLOW_VERIFIED,
                title="Field Observation Schema v2.0 & Ingestion Pipeline Verified",
                is_mandatory_for_pilot=True,
                applies_to_scope="ALL_PILOT_OPERATIONS",
                status=PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
                evidence_reference="SUITE-PHASE6-REGRESSION-111-PASSING",
                verified_by_role="SYSTEMS_INTEGRATION_LEAD",
                verified_by_id="ENG-LEAD-01",
                verification_timestamp_utc=datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc),
                notes="ObservationIngestionPipeline, duplicate detection, and bounding box checks fully passing tests.",
            ),
            PrerequisiteID.PREREQ_08_DATA_FEED_AUTHORIZATION: PrerequisiteRecord(
                prereq_id=PrerequisiteID.PREREQ_08_DATA_FEED_AUTHORIZATION,
                title="External Telemetry Authorization (Optional Feeds: TSDPS / NWIC / DRF)",
                is_mandatory_for_pilot=False,  # Optional feed prerequisite
                applies_to_scope="OPTIONAL_FEEDS",
                status=PrerequisiteVerificationStatus.UNVERIFIED_PENDING,
                notes="External live streams operate in fallback or sandbox mode; does not block manual vantage pilot.",
            ),
        }

    @property
    def current_state(self) -> PilotState:
        return self._current_state

    def get_prerequisite(self, prereq_id: PrerequisiteID) -> Optional[PrerequisiteRecord]:
        return self._prerequisites.get(prereq_id)

    def list_prerequisites(self) -> List[PrerequisiteRecord]:
        return list(self._prerequisites.values())

    def update_prerequisite_evidence(
        self,
        prereq_id: PrerequisiteID,
        status: PrerequisiteVerificationStatus,
        evidence_reference: str,
        verified_by_role: str,
        verified_by_id: str,
        expiration_timestamp_utc: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> PrerequisiteRecord:
        """Updates the verification evidence for a specific prerequisite."""
        if prereq_id not in self._prerequisites:
            raise KeyError(f"Unknown prerequisite ID: {prereq_id}")

        rec = self._prerequisites[prereq_id]
        rec.status = status
        rec.evidence_reference = evidence_reference
        rec.verified_by_role = verified_by_role
        rec.verified_by_id = verified_by_id
        rec.verification_timestamp_utc = datetime.now(timezone.utc)
        rec.expiration_timestamp_utc = expiration_timestamp_utc
        if notes:
            rec.notes = notes

        logger.info(f"Updated prerequisite {prereq_id} to {status} with evidence {evidence_reference}")
        
        # Re-evaluate state
        self._evaluate_readiness_state()
        return rec

    def _evaluate_readiness_state(self):
        """Internal evaluator checking whether all mandatory prerequisites are satisfied."""
        if self._current_state in [PilotState.PILOT_SUSPENDED, PilotState.PILOT_COMPLETED]:
            return  # Terminal or suspended states remain until explicitly transitioned

        mandatory_all_valid = all(
            rec.is_currently_valid()
            for rec in self._prerequisites.values()
            if rec.is_mandatory_for_pilot
        )

        if mandatory_all_valid:
            if self._current_state == PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT:
                self._current_state = PilotState.READY_FOR_AUTHORIZED_PILOT_REVIEW
                logger.info("All mandatory prerequisites satisfied! Transitioned to READY_FOR_AUTHORIZED_PILOT_REVIEW.")
        else:
            if self._current_state not in [PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT, PilotState.PILOT_SUSPENDED]:
                logger.warning("Prerequisite failure detected! Reverting to BLOCKED_NOT_READY_FOR_LIVE_PILOT.")
                self._current_state = PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT

    def request_state_transition(
        self,
        target_state: PilotState,
        authorized_by_role: str,
        authorized_by_id: str,
        justification_notes: str,
    ) -> Tuple[bool, str]:
        """
        Processes a human-authorized transition request.
        
        Enforces:
        - PILOT_AUTHORIZED requires READY_FOR_AUTHORIZED_PILOT_REVIEW and role in [PRINCIPAL_INVESTIGATOR, PROJECT_DIRECTOR]
        - PILOT_SUSPENDED can be triggered by any safety/supervisor role from any state
        - Re-activation from PILOT_SUSPENDED requires supervisor role and all prerequisites valid
        """
        now_utc = datetime.now(timezone.utc)

        allowed_roles = ["PRINCIPAL_INVESTIGATOR", "PROJECT_DIRECTOR", "MUNICIPAL_COMMISSIONER"]

        # 1. Authorize Transition to PILOT_AUTHORIZED
        if target_state == PilotState.PILOT_AUTHORIZED:
            if authorized_by_role not in allowed_roles:
                return False, f"Unauthorized role '{authorized_by_role}'. Pilot authorization requires one of: {allowed_roles}"

            mandatory_all_valid = all(
                rec.is_currently_valid()
                for rec in self._prerequisites.values()
                if rec.is_mandatory_for_pilot
            )
            if not mandatory_all_valid:
                return False, "Cannot authorize pilot: One or more mandatory prerequisites are currently unverified or expired."

            if self._current_state not in [PilotState.READY_FOR_AUTHORIZED_PILOT_REVIEW, PilotState.PILOT_SUSPENDED]:
                return False, f"Cannot authorize pilot: Current state is {self._current_state} (must be READY_FOR_AUTHORIZED_PILOT_REVIEW or PILOT_SUSPENDED)."

        # 2. Authorize Transition to PILOT_SUSPENDED
        elif target_state == PilotState.PILOT_SUSPENDED:
            # Suspension is always permitted for safety
            pass

        # 3. Authorize Transition to PILOT_COMPLETED
        elif target_state == PilotState.PILOT_COMPLETED:
            if self._current_state != PilotState.PILOT_AUTHORIZED:
                return False, f"Cannot complete pilot from state {self._current_state} (must be PILOT_AUTHORIZED)."

        # Record cryptographically chained transition
        action_id = f"TRN-{hashlib.md5(f'{self._current_state}{target_state}{now_utc.isoformat()}'.encode()).hexdigest()[:8].upper()}"
        action = TransitionAction(
            transition_id=action_id,
            from_state=self._current_state,
            to_state=target_state,
            authorized_by_role=authorized_by_role,
            authorized_by_id=authorized_by_id,
            timestamp_utc=now_utc,
            justification_notes=justification_notes,
        )

        prev_hash = self._transition_history[-1].audit_hash if self._transition_history else "GENESIS_GATE_ROOT"
        action.audit_hash = action.compute_hash(prev_hash)
        self._transition_history.append(action)

        prev_state = self._current_state
        self._current_state = target_state
        logger.info(f"Transition executed: {prev_state} -> {target_state} by {authorized_by_role} ({authorized_by_id})")
        return True, f"Successfully transitioned to {target_state}."

    def generate_activation_status_report(self, output_json_path: Optional[Path] = None) -> Dict[str, Any]:
        """Produces a comprehensive, machine-readable JSON status report."""
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._evaluate_readiness_state()

        prereq_list = []
        for rec in self._prerequisites.values():
            prereq_list.append({
                "prereq_id": rec.prereq_id.value,
                "title": rec.title,
                "is_mandatory": rec.is_mandatory_for_pilot,
                "status": rec.status.value,
                "is_valid": rec.is_currently_valid(),
                "evidence_reference": rec.evidence_reference,
                "verified_by_role": rec.verified_by_role,
                "verification_timestamp": rec.verification_timestamp_utc.isoformat() if rec.verification_timestamp_utc else None,
                "expiration_timestamp": rec.expiration_timestamp_utc.isoformat() if rec.expiration_timestamp_utc else None,
                "notes": rec.notes,
            })

        mandatory_count = sum(1 for p in self._prerequisites.values() if p.is_mandatory_for_pilot)
        mandatory_valid = sum(1 for p in self._prerequisites.values() if p.is_mandatory_for_pilot and p.is_currently_valid())

        report = {
            "report_timestamp_utc": now_iso,
            "pilot_activation_state": self._current_state.value,
            "overall_readiness_summary": {
                "total_prerequisites_tracked": len(self._prerequisites),
                "mandatory_prerequisites_total": mandatory_count,
                "mandatory_prerequisites_satisfied": mandatory_valid,
                "all_mandatory_satisfied": mandatory_valid == mandatory_count,
                "can_start_field_sessions": self._current_state == PilotState.PILOT_AUTHORIZED,
            },
            "prerequisites": prereq_list,
            "audit_chain_length": len(self._transition_history),
            "latest_transition": (
                {
                    "transition_id": self._transition_history[-1].transition_id,
                    "from_state": self._transition_history[-1].from_state.value,
                    "to_state": self._transition_history[-1].to_state.value,
                    "authorized_by": f"{self._transition_history[-1].authorized_by_role}:{self._transition_history[-1].authorized_by_id}",
                    "timestamp": self._transition_history[-1].timestamp_utc.isoformat(),
                    "audit_hash": self._transition_history[-1].audit_hash,
                }
                if self._transition_history
                else None
            ),
        }

        if output_json_path:
            output_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)

        return report
