"""
Unit and integration test suite for Sahaay AI Phase 7:
Pilot Activation Gate, Field Session Management, Blocker Resolution & Operational Suspension.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.pilot.models import (
    PilotState,
    PrerequisiteID,
    PrerequisiteVerificationStatus,
    PrerequisiteRecord,
    TransitionAction,
)
from sahaay.pilot.gate import PilotActivationGate
from sahaay.pilot.session import (
    FieldSessionManager,
    FieldSessionState,
    PreCollectionSafetyCheck,
    PostCollectionSafetyReview,
)
from sahaay.observations.schemas import GroundTruthObservation
from sahaay.observations.ingestion import ObservationIngestionPipeline


@pytest.fixture
def activation_gate():
    return PilotActivationGate()


@pytest.fixture
def session_manager():
    return FieldSessionManager()


# ==============================================================================
# 1. Activation Gate Baseline & Fail-Closed Tests
# ==============================================================================

def test_activation_gate_fails_closed_initially(activation_gate):
    """Verify that gate initializes strictly to BLOCKED_NOT_READY_FOR_LIVE_PILOT."""
    assert activation_gate.current_state == PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT
    report = activation_gate.generate_activation_status_report()
    assert report["pilot_activation_state"] == "BLOCKED_NOT_READY_FOR_LIVE_PILOT"
    assert not report["overall_readiness_summary"]["can_start_field_sessions"]


def test_synthetic_evidence_cannot_satisfy_real_prerequisite(activation_gate):
    """Verify that simulation/fixture IDs are rejected as real evidence."""
    rec = PrerequisiteRecord(
        prereq_id=PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT,
        title="Institutional Agreement",
        status=PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        evidence_reference="SIM-MOU-FAKE-01",  # Synthetic!
        verified_by_role="LEGAL_LEAD",
        verification_timestamp_utc=datetime.now(timezone.utc),
    )
    assert not rec.is_currently_valid()

    rec_fixture = PrerequisiteRecord(
        prereq_id=PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT,
        title="Institutional Agreement",
        status=PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        evidence_reference="FIXTURE-DOC-02",  # Fixture!
        verified_by_role="LEGAL_LEAD",
        verification_timestamp_utc=datetime.now(timezone.utc),
    )
    assert not rec_fixture.is_currently_valid()


def test_expired_prerequisite_fails_validation(activation_gate):
    """Verify that an expired prerequisite is marked invalid."""
    past_time = datetime.now(timezone.utc) - timedelta(days=1)
    rec = PrerequisiteRecord(
        prereq_id=PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT,
        title="Institutional Agreement",
        status=PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        evidence_reference="GO-TS-2026-MOU-01",
        verified_by_role="LEGAL_LEAD",
        verification_timestamp_utc=datetime.now(timezone.utc) - timedelta(days=30),
        expiration_timestamp_utc=past_time,  # Expired!
    )
    assert not rec.is_currently_valid()


def test_cannot_authorize_pilot_directly_while_blocked(activation_gate):
    """Verify that transitioning to PILOT_AUTHORIZED fails while mandatory prereqs are unmet."""
    success, msg = activation_gate.request_state_transition(
        target_state=PilotState.PILOT_AUTHORIZED,
        authorized_by_role="PRINCIPAL_INVESTIGATOR",
        authorized_by_id="PI-HYD-01",
        justification_notes="Attempting direct authorization without prereqs.",
    )
    assert not success
    assert "Cannot authorize pilot" in msg
    assert activation_gate.current_state == PilotState.BLOCKED_NOT_READY_FOR_LIVE_PILOT


# ==============================================================================
# 2. State Transition & Human Authority Matrix Tests
# ==============================================================================

def test_full_prerequisite_clearance_and_human_authorization_lifecycle(activation_gate):
    """Verify the progression: BLOCKED -> READY -> AUTHORIZED -> SUSPENDED -> RE-AUTHORIZED -> COMPLETED."""
    now = datetime.now(timezone.utc)

    # 1. Satisfy remaining 5 mandatory prerequisites with valid evidence
    activation_gate.update_prerequisite_evidence(
        PrerequisiteID.PREREQ_01_INSTITUTIONAL_AGREEMENT,
        PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        "GO-TELANGANA-PLANNING-2026-8812",
        "PRINCIPAL_INVESTIGATOR",
        "PI-01",
    )
    activation_gate.update_prerequisite_evidence(
        PrerequisiteID.PREREQ_02_RESPONSIBLE_LEAD_RECORDED,
        PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        "LETTER-APPOINT-FIELD-LEAD-2026-01",
        "PROJECT_DIRECTOR",
        "DIR-01",
    )
    activation_gate.update_prerequisite_evidence(
        PrerequisiteID.PREREQ_03_SITE_SAFETY_INSPECTIONS,
        PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        "SURVEY-INSPECTION-4-CORRIDORS-2026",
        "FIELD_SAFETY_LEAD",
        "SAFETY-01",
    )
    activation_gate.update_prerequisite_evidence(
        PrerequisiteID.PREREQ_04_PPE_EQUIPMENT_CHECK,
        PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        "INVENTORY-PPE-CLASS2-STAFF-GAUGE-2026",
        "FIELD_OPERATIONS_LEAD",
        "LEAD-01",
    )
    activation_gate.update_prerequisite_evidence(
        PrerequisiteID.PREREQ_05_CONSENT_PRIVACY_DEPLOYED,
        PrerequisiteVerificationStatus.VERIFIED_EVIDENCE_ATTACHED,
        "AUDIT-STAGING-DPDP-COARSENING-2026",
        "LEGAL_AND_COMPLIANCE_LEAD",
        "LEGAL-01",
    )

    # State must autonomously transition to READY_FOR_AUTHORIZED_PILOT_REVIEW
    assert activation_gate.current_state == PilotState.READY_FOR_AUTHORIZED_PILOT_REVIEW

    # Unauthorized role cannot authorize
    fail_auth, fail_msg = activation_gate.request_state_transition(
        PilotState.PILOT_AUTHORIZED,
        authorized_by_role="JUNIOR_DEVELOPER",
        authorized_by_id="DEV-01",
        justification_notes="Trying to approve pilot.",
    )
    assert not fail_auth
    assert "Unauthorized role" in fail_msg

    # Authorized PI role authorizes
    succ_auth, succ_msg = activation_gate.request_state_transition(
        PilotState.PILOT_AUTHORIZED,
        authorized_by_role="PRINCIPAL_INVESTIGATOR",
        authorized_by_id="PI-01",
        justification_notes="All prerequisites verified. Field pilot authorized for Begumpet Corridor.",
    )
    assert succ_auth
    assert activation_gate.current_state == PilotState.PILOT_AUTHORIZED

    # Immediate Safety Suspension
    succ_susp, _ = activation_gate.request_state_transition(
        PilotState.PILOT_SUSPENDED,
        authorized_by_role="FIELD_SAFETY_LEAD",
        authorized_by_id="SAFETY-01",
        justification_notes="Lightning strike detected 4km away. Safety suspension ordered.",
    )
    assert succ_susp
    assert activation_gate.current_state == PilotState.PILOT_SUSPENDED

    # Re-authorize after clearance
    succ_reauth, _ = activation_gate.request_state_transition(
        PilotState.PILOT_AUTHORIZED,
        authorized_by_role="PROJECT_DIRECTOR",
        authorized_by_id="DIR-01",
        justification_notes="Weather cleared for > 45 minutes. Operations resumed.",
    )
    assert succ_reauth
    assert activation_gate.current_state == PilotState.PILOT_AUTHORIZED

    # Complete pilot
    succ_comp, _ = activation_gate.request_state_transition(
        PilotState.PILOT_COMPLETED,
        authorized_by_role="PRINCIPAL_INVESTIGATOR",
        authorized_by_id="PI-01",
        justification_notes="Observation shifts concluded successfully.",
    )
    assert succ_comp
    assert activation_gate.current_state == PilotState.PILOT_COMPLETED


# ==============================================================================
# 3. Field Session Lifecycle & Pre-Check Safety Tests
# ==============================================================================

def test_field_session_blocked_when_gate_not_authorized(session_manager):
    """Verify that a field session cannot start if pilot is not authorized."""
    now = datetime.now(timezone.utc)
    session = session_manager.create_session(
        session_id="SES-20261025-0001",
        corridor_id="CORR-HYD-01",
        vantage_location_name="Rasoolpura Metro Walkway",
        scheduled_start_utc=now,
        scheduled_end_utc=now + timedelta(hours=2),
        is_synthetic=False,
    )

    valid_pre_check = {
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
    }

    # Attempt start with pilot_authorized=False
    success, _, msg = session_manager.start_session("SES-20261025-0001", valid_pre_check, pilot_authorized=False)
    assert not success
    assert "Pilot activation gate is BLOCKED" in msg


def test_pre_collection_safety_check_fails_on_floodwater_entry():
    """Verify that declaring non-zero entry into floodwater fails safety check."""
    bad_pre_check = {
        "vantage_point_clear_of_traffic": True,
        "zero_entry_into_floodwater_confirmed": False,  # Violates Rule 1!
        "lightning_detected_within_10km": False,
        "wind_gusts_exceed_35kmh": False,
        "ppe_gear_verified_for_all": True,
        "first_aid_and_whistles_verified": True,
        "emergency_contacts_saved_on_phones": True,
        "daylight_window_confirmed": True,
        "field_lead_id": "LEAD-01",
        "safety_officer_id": "SAFETY-01",
        "data_recorder_id": "REC-01",
    }
    with pytest.raises(ValueError) as exc:
        PreCollectionSafetyCheck(**bad_pre_check)
    assert "Zero entry into floodwater must be confirmed" in str(exc.value)


def test_pre_collection_safety_check_fails_on_lightning():
    """Verify that lightning detected within 10km fails safety check."""
    lightning_check = {
        "vantage_point_clear_of_traffic": True,
        "zero_entry_into_floodwater_confirmed": True,
        "lightning_detected_within_10km": True,  # Lightning detected!
        "wind_gusts_exceed_35kmh": False,
        "ppe_gear_verified_for_all": True,
        "first_aid_and_whistles_verified": True,
        "emergency_contacts_saved_on_phones": True,
        "daylight_window_confirmed": True,
        "field_lead_id": "LEAD-01",
        "safety_officer_id": "SAFETY-01",
        "data_recorder_id": "REC-01",
    }
    with pytest.raises(ValueError) as exc:
        PreCollectionSafetyCheck(**lightning_check)
    assert "Lightning detected within 10km" in str(exc.value)


def test_field_session_abort_and_closure(session_manager):
    """Verify that an active session can be safely aborted and records incident details."""
    now = datetime.now(timezone.utc)
    session = session_manager.create_session(
        session_id="SES-20261025-0002",
        corridor_id="CORR-HYD-02",
        vantage_location_name="Tolichowki Flyover",
        scheduled_start_utc=now,
        scheduled_end_utc=now + timedelta(hours=2),
        is_synthetic=True,  # Allow synthetic test execution
    )

    valid_pre_check = {
        "vantage_point_clear_of_traffic": True,
        "zero_entry_into_floodwater_confirmed": True,
        "lightning_detected_within_10km": False,
        "wind_gusts_exceed_35kmh": False,
        "ppe_gear_verified_for_all": True,
        "first_aid_and_whistles_verified": True,
        "emergency_contacts_saved_on_phones": True,
        "daylight_window_confirmed": True,
        "field_lead_id": "LEAD-02",
        "safety_officer_id": "SAFETY-02",
        "data_recorder_id": "REC-02",
    }

    succ, active_ses, _ = session_manager.start_session("SES-20261025-0002", valid_pre_check, pilot_authorized=True)
    assert succ
    assert active_ses.session_state == FieldSessionState.ACTIVE_COLLECTING

    # Safety abort
    abort_succ, aborted_ses, _ = session_manager.abort_session(
        "SES-20261025-0002",
        abort_reason="Torrential cross-winds > 40 km/h and railing vibration",
        field_lead_id="LEAD-02",
    )
    assert abort_succ
    assert aborted_ses.session_state == FieldSessionState.SAFETY_ABORTED
    assert aborted_ses.post_safety_review.abort_triggered
    assert "Torrential cross-winds" in aborted_ses.post_safety_review.incident_details


# ==============================================================================
# 4. Evaluation Gate & Ground-Truth Blocking Tests
# ==============================================================================

def test_evaluation_gate_blocks_when_samples_insufficient():
    """Verify that model evaluation gate reports BLOCKED when verified flood episodes are 0."""
    eval_gate_path = os.path.join("reports", "phase7", "evaluation_gate.json")
    assert os.path.exists(eval_gate_path), f"Missing {eval_gate_path}"
    import json
    with open(eval_gate_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["evaluation_gate_status"] == "BLOCKED_INSUFFICIENT_GROUND_TRUTH"
    assert data["eligibility_audit"]["verified_flood_episodes_available"] == 0
    assert data["model_readiness_gates"]["vision_v4_readiness_gate"] == "NO-GO"


def test_data_quality_report_separates_synthetic_and_real():
    """Verify that observation_data_quality.json accurately reports 0 real observations."""
    dq_path = os.path.join("reports", "phase7", "observation_data_quality.json")
    assert os.path.exists(dq_path), f"Missing {dq_path}"
    import json
    with open(dq_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["data_inventory"]["real_world_field_observations_acquired"] == 0
    assert data["evaluation_dataset_eligibility"]["evaluation_eligibility_status"] == "INSUFFICIENT_GROUND_TRUTH_BLOCKED"
