"""
Unit and integration test suite for Sahaay AI Phase 8:
Blocker Closure Workflow, Evidence Intake Service, Pilot Scope Matrix, and Operational Controls.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sahaay.pilot.models import (
    PilotState,
    PrerequisiteID,
    PrerequisiteVerificationStatus,
    PrerequisiteRecord,
)
from sahaay.pilot.gate import PilotActivationGate
from sahaay.pilot.session import FieldSessionManager, FieldSessionState
from sahaay.pilot.blockers import (
    BlockerStatus,
    BlockerScope,
    BlockerRecord,
    BlockerRegistry,
)
from sahaay.pilot.evidence import (
    EvidenceCategory,
    EvidenceStatus,
    EvidenceDocumentRecord,
    EvidenceIntakeService,
)


# ==============================================================================
# 1. Blocker Registry & Lifecycle Tests
# ==============================================================================

def test_blocker_lifecycle_and_transition():
    """Verify standard 5-state lifecycle for blocker records."""
    registry = BlockerRegistry()
    blk = BlockerRecord(
        blocker_id="BLK-01-INST-MOU",
        description="Institutional MoU with GHMC & Hyderabad Traffic Police",
        scope=BlockerScope.WHOLE_PILOT_MANDATORY,
        responsible_role="LEGAL_COUNSEL",
        evidence_required="Executed bilateral agreement copy",
        status=BlockerStatus.NOT_STARTED,
        next_action="Draft agreement terms.",
    )
    registry.register_blocker(blk)
    assert not blk.is_verified_closed()

    # Step 1: Submit for review
    registry.submit_for_review("BLK-01-INST-MOU", "DOC-REF-LEGAL-2026-088")
    assert blk.status == BlockerStatus.PENDING_REVIEW
    assert not blk.is_verified_closed()

    # Step 2: Verification closure by independent reviewer
    registry.verify_closure(
        blocker_id="BLK-01-INST-MOU",
        reviewer_role="EXTERNAL_COMPLIANCE_AUDITOR",
        reviewer_id="AUDITOR-01",
        verdict=BlockerStatus.VERIFIED_CLOSED,
        notes="Verified official stamp and signature from GHMC Commissioner.",
        expiry_timestamp_utc=datetime.now(timezone.utc) + timedelta(days=365),
    )
    assert blk.status == BlockerStatus.VERIFIED_CLOSED
    assert blk.is_verified_closed()


def test_synthetic_evidence_cannot_close_real_blocker():
    """Verify that simulated or fixture references cannot close real blockers."""
    blk = BlockerRecord(
        blocker_id="BLK-02-SITE-SAFETY",
        description="Physical site hazard inspection",
        scope=BlockerScope.WHOLE_PILOT_MANDATORY,
        responsible_role="FIELD_SAFETY_OFFICER",
        evidence_required="Inspection checklist and photos",
        status=BlockerStatus.VERIFIED_CLOSED,
        evidence_reference="SIM-FIXTURE-SITE-001",  # Synthetic reference!
        independent_reviewer_role="SAFETY_DIRECTOR",
        independent_reviewer_id="SAFETY-DIR-01",
        verification_timestamp_utc=datetime.now(timezone.utc),
        next_action="Ready.",
    )
    # Must fail because reference contains SIM- / FIXTURE-
    assert not blk.is_verified_closed()


def test_blocker_expiry_detection():
    """Verify that an expired verification revokes closed status."""
    now_utc = datetime.now(timezone.utc)
    blk = BlockerRecord(
        blocker_id="BLK-03-PPE-CHECK",
        description="PPE procurement and calibration audit",
        scope=BlockerScope.WHOLE_PILOT_MANDATORY,
        responsible_role="SAFETY_OFFICER",
        evidence_required="Calibration logs",
        status=BlockerStatus.VERIFIED_CLOSED,
        evidence_reference="CERT-PPE-HYD-2026-01",
        independent_reviewer_role="CHIEF_SAFETY_INSPECTOR",
        independent_reviewer_id="INSP-01",
        verification_timestamp_utc=now_utc - timedelta(days=60),
        expiry_timestamp_utc=now_utc - timedelta(days=1),  # Expired yesterday!
        next_action="Re-certify PPE.",
    )
    assert not blk.is_verified_closed(as_of=now_utc)


def test_whole_pilot_mandatory_vs_optional_scoping():
    """Verify that unresolved optional feed blockers do not prevent pilot activation, but mandatory ones do."""
    registry = BlockerRegistry()

    # Mandatory blocker - closed
    blk_mand = BlockerRecord(
        blocker_id="BLK-01-INST-MOU",
        description="Institutional MoU",
        scope=BlockerScope.WHOLE_PILOT_MANDATORY,
        responsible_role="LEGAL_COUNSEL",
        evidence_required="MoU document",
        status=BlockerStatus.VERIFIED_CLOSED,
        evidence_reference="DOC-GHMC-MOU-2026-REAL",
        independent_reviewer_role="LEGAL_AUDITOR",
        independent_reviewer_id="AUD-01",
        verification_timestamp_utc=datetime.now(timezone.utc),
        next_action="Monitor.",
    )
    registry.register_blocker(blk_mand)

    # Optional feed blocker - pending
    blk_opt = BlockerRecord(
        blocker_id="BLK-05-TSDPS-TELEMETRY",
        description="TSDPS live API feed token",
        scope=BlockerScope.FEED_SPECIFIC_OPTIONAL,
        responsible_role="SYSTEMS_LEAD",
        evidence_required="API Gateway SLA",
        status=BlockerStatus.REQUESTED,
        next_action="Awaiting API token.",
    )
    registry.register_blocker(blk_opt)

    # Can pilot proceed? Yes, because only mandatory blockers are gating for the whole pilot
    can_proceed, unresolved = registry.can_pilot_proceed()
    assert can_proceed is True
    assert len(unresolved) == 0

    # If mandatory blocker is rejected, pilot cannot proceed
    blk_mand.status = BlockerStatus.REJECTED
    can_proceed2, unresolved2 = registry.can_pilot_proceed()
    assert can_proceed2 is False
    assert len(unresolved2) == 1
    assert "BLK-01-INST-MOU" in unresolved2[0]


# ==============================================================================
# 2. Evidence Intake Service Tests
# ==============================================================================

def test_evidence_intake_registration_and_review():
    """Verify registering real evidence metadata and human verification review."""
    intake = EvidenceIntakeService()
    now_utc = datetime.now(timezone.utc)

    rec = intake.register_evidence({
        "evidence_id": "EVD-MOU-GHMC-001",
        "category": EvidenceCategory.INSTITUTIONAL_MOU,
        "title": "GHMC Research Data Sharing and Vantage Point Agreement",
        "issuing_authority": "Greater Hyderabad Municipal Corporation",
        "document_reference_hash": "sha256:4a8b7f198c6d3210ebfac9081e7d23a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0",
        "permitted_scope": ["ALL_PILOT_OPERATIONS"],
        "execution_date": now_utc - timedelta(days=5),
        "expiration_date": now_utc + timedelta(days=360),
    })

    assert rec.verification_status == EvidenceStatus.SUBMITTED
    valid, msg = rec.is_currently_valid_for_scope("CORR-HYD-01")
    assert not valid
    assert "not VERIFIED_VALID" in msg

    # Review by authorized legal counsel
    reviewed = intake.review_evidence(
        evidence_id="EVD-MOU-GHMC-001",
        reviewer_role="LEGAL_COUNSEL",
        reviewer_id="LEGAL-01",
        verdict=EvidenceStatus.VERIFIED_VALID,
        notes="Executed copy on file; verified via GHMC legal cell.",
    )
    assert reviewed.verification_status == EvidenceStatus.VERIFIED_VALID
    valid2, _ = reviewed.is_currently_valid_for_scope("CORR-HYD-01")
    assert valid2 is True


def test_evidence_intake_rejects_synthetic_id():
    """Verify that synthetic IDs cannot be registered into the evidence service."""
    intake = EvidenceIntakeService()
    now_utc = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="Synthetic ID"):
        intake.register_evidence({
            "evidence_id": "EVD-SIM-MOCK-001",
            "category": EvidenceCategory.SITE_SAFETY_INSPECTION,
            "title": "Mock inspection",
            "issuing_authority": "Mock Authority",
            "document_reference_hash": "mock-hash-12345",
            "permitted_scope": ["CORR-HYD-01"],
            "execution_date": now_utc,
        })


def test_evidence_intake_rejects_contradictory_dates():
    """Verify that expiration before execution raises validation error."""
    intake = EvidenceIntakeService()
    now_utc = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="cannot be before execution_date"):
        intake.register_evidence({
            "evidence_id": "EVD-SAFETY-001",
            "category": EvidenceCategory.PPE_EQUIPMENT_AUDIT,
            "title": "PPE audit",
            "issuing_authority": "Safety Board",
            "document_reference_hash": "hash-ppe-audit-001",
            "permitted_scope": ["ALL_PILOT_OPERATIONS"],
            "execution_date": now_utc,
            "expiration_date": now_utc - timedelta(days=1),  # Contradictory!
        })


def test_evidence_intake_out_of_scope_rejection():
    """Verify that document approved only for Corridor 2 fails scope check for Corridor 1."""
    now_utc = datetime.now(timezone.utc)
    rec = EvidenceDocumentRecord(
        evidence_id="EVD-SITE-INSP-02",
        category=EvidenceCategory.SITE_SAFETY_INSPECTION,
        title="Dilsukhnagar Metro Walkway Inspection",
        issuing_authority="HMDA Safety Committee",
        document_reference_hash="sha256:dilsukhnagar-inspection-approved",
        permitted_scope=["CORR-HYD-02"],  # Only corridor 2!
        execution_date=now_utc - timedelta(days=1),
        verification_status=EvidenceStatus.VERIFIED_VALID,
        verified_by_role="SAFETY_OFFICER",
        verified_by_id="SAFETY-01",
    )

    valid_c2, _ = rec.is_currently_valid_for_scope("CORR-HYD-02")
    assert valid_c2 is True

    valid_c1, msg_c1 = rec.is_currently_valid_for_scope("CORR-HYD-01")
    assert valid_c1 is False
    assert "does not cover target scope" in msg_c1


# ==============================================================================
# 3. Operational Stop & Recovery Controls Tests
# ==============================================================================

def test_operational_suspension_and_recovery_flow():
    """Verify full suspension trigger, gate locking, and human recovery signoff."""
    gate = PilotActivationGate()
    manager = FieldSessionManager()
    now_utc = datetime.now(timezone.utc)

    # Transition to SUSPENDED from BLOCKED
    succ, msg = gate.request_state_transition(
        target_state=PilotState.PILOT_SUSPENDED,
        authorized_by_role="SAFETY_OFFICER",
        authorized_by_id="SAFETY-OFFICER-01",
        justification_notes="Precautionary squall warning detected.",
    )
    assert succ is True
    assert gate.current_state == PilotState.PILOT_SUSPENDED

    # Ensure field session startup is blocked while gate is SUSPENDED
    manager.create_session(
        session_id="SES-20261025-0099",
        corridor_id="CORR-HYD-01",
        vantage_location_name="Rasoolpura Concourse",
        scheduled_start_utc=now_utc,
        scheduled_end_utc=now_utc + timedelta(hours=1),
        is_synthetic=False,
    )
    start_succ, _, start_err = manager.start_session(
        "SES-20261025-0099",
        {
            "vantage_point_clear_of_traffic": True,
            "zero_entry_into_floodwater_confirmed": True,
            "lightning_detected_within_10km": False,
            "wind_gusts_exceed_35kmh": False,
            "ppe_gear_verified_for_all": True,
            "first_aid_and_whistles_verified": True,
            "emergency_contacts_saved_on_phones": True,
            "daylight_window_confirmed": True,
            "field_lead_id": "LEAD-01",
            "safety_officer_id": "SAFETY-01",
            "data_recorder_id": "REC-01",
        },
        pilot_authorized=(gate.current_state == PilotState.PILOT_AUTHORIZED),
    )
    assert start_succ is False
    assert "Pilot activation gate is BLOCKED" in start_err or "BLOCKED_NOT_READY" in start_err

    # Attempt recovery without satisfying mandatory prerequisites
    recov_succ, recov_msg = gate.request_state_transition(
        target_state=PilotState.PILOT_AUTHORIZED,
        authorized_by_role="PROJECT_DIRECTOR",
        authorized_by_id="DIR-01",
        justification_notes="Attempted recovery before prerequisites verified.",
    )
    assert recov_succ is False
    assert "mandatory prerequisites are currently unverified" in recov_msg


def test_simulated_incident_fixture_structure():
    """Verify that the simulated incident fixture exists and contains required safety keys."""
    fixture_path = Path("data/phase8/suspension_fixtures/operational_incident_simulation.json")
    assert fixture_path.exists(), "Incident simulation fixture must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["simulation_metadata"]["is_synthetic_or_simulated"] is True
    assert data["incident_event"]["autonomous_dispatch_prohibited"] is True
    assert data["incident_event"]["road_closure_initiated"] is False
    assert "recovery_procedure" in data
    assert data["recovery_procedure"]["human_authorization_signoff"]["recovery_authorized"] is True


# ==============================================================================
# 4. Truthful Accounting & Evaluation Gate Tests
# ==============================================================================

def test_truthful_zero_real_observations_and_evaluation_gate():
    """Verify that Phase 8 reports zero real observations and preserves the evaluation gate."""
    dq_path = Path("reports/phase8/first_observation_quality.json")
    assert dq_path.exists()
    with open(dq_path, "r", encoding="utf-8") as f:
        dq = json.load(f)
    assert dq["data_accounting"]["real_world_observations_in_database"] == 0
    assert dq["data_accounting"]["real_world_active_sessions_conducted"] == 0

    eval_gate_path = Path("reports/phase8/evaluation_gate.json")
    assert eval_gate_path.exists()
    with open(eval_gate_path, "r", encoding="utf-8") as f:
        eg = json.load(f)
    assert eg["evaluation_gate_status"] == "BLOCKED_INSUFFICIENT_GROUND_TRUTH"
    assert "NO-GO" in eg["subsystem_evaluation_boundaries"]["vision_v4_optical_classifier"]
    assert eg["sample_size_audit"]["verified_flood_episodes_required"] == 50
    assert eg["sample_size_audit"]["verified_non_flood_episodes_required"] == 100
    assert eg["sample_size_audit"]["independent_storm_dates_required"] == 4
