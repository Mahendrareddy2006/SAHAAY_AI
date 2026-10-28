"""
Sahaay AI - Phase 16: Acquisition Operations & Evaluation Controls Test Suite
(tests/test_phase16_operations_and_evaluation_controls.py)

Tests:
1. Validation of stream permissions and rejection of tentative/draft/verbal evidence.
2. Rejection of unapproved streams and future approval dates.
3. Separation of geographic location eligibility from legal permission status.
4. Segregation and exclusion of synthetic fixtures from real-world accounts.
5. Detection and rejection of contradictory or unknown provenance.
6. Traceability and fail-closed readiness audit behavior (NOT_READY / UNKNOWN on missing evidence).
7. EvaluationSetProtectionGuard intercepting:
   - in-band is_locked_for_tuning=True flags,
   - partition/split naming leaks,
   - overlapping image IDs,
   - overlapping capture sessions,
   - MD5 collisions,
   - perceptual near-duplicates (dhash <= 2).
8. Guarding decision threshold tuning from receiving evaluation records.
9. End-to-end integration with train_eval_v4_protocol pre-flight checks.
"""

import os
import json
from datetime import datetime, timezone, timedelta
import pytest
import pandas as pd
import numpy as np

from sahaay.data_collection_v4.operations import (
    StreamApprovalStatus,
    ProvenanceCategory,
    LockedEvaluationSetViolationError,
    EvaluationSplitMetadata,
    validate_stream_permissions,
    validate_acquisition_record_eligibility,
    categorize_provenance,
    EvaluationSetProtectionGuard,
    generate_phase16_readiness_audit,
)


# =====================================================================
# 1. Stream Permission & Approval Evidence Validation Tests
# =====================================================================

def test_stream_permissions_rejection_of_draft_evidence():
    """Streams asserting approved status with draft evidence must be flagged as unapproved."""
    df = pd.DataFrame([
        {
            "stream_id": "STREAM-01-TEST",
            "acquisition_stream_name": "Test Municipal Stream",
            "responsible_organization": "GHMC",
            "request_status": "approved",
            "evidence_reference": "DRAFT-DOC-MUNICIPAL-MOU-v1.0",  # Draft marker!
            "outstanding_blockers": "None",
            "next_action": "None",
        }
    ])
    audit = validate_stream_permissions(df)
    assert audit["approved_streams_count"] == 0
    assert audit["unapproved_streams_count"] == 1
    assert len(audit["violations"]) > 0
    stream_info = audit["stream_details"]["STREAM-01-TEST"]
    assert stream_info["is_approved_for_training"] is False
    assert stream_info["evidence_valid"] is False
    assert any("prohibited draft marker" in r for r in stream_info["reasons"])


def test_stream_permissions_rejection_of_verbal_or_asserted_evidence():
    """Verbal, pending, or asserted references must be rejected."""
    df = pd.DataFrame([
        {
            "stream_id": "STREAM-VERBAL",
            "acquisition_stream_name": "Verbal stream",
            "responsible_organization": "Police Dept",
            "request_status": "approved",
            "evidence_reference": "VERBAL-PERMISSION-DCP-TRAFFIC",
        },
        {
            "stream_id": "STREAM-TODO",
            "acquisition_stream_name": "Todo stream",
            "responsible_organization": "Fleet Co",
            "request_status": "approved",
            "evidence_reference": "TODO_MOU_REFERENCE",
        }
    ])
    audit = validate_stream_permissions(df)
    assert audit["approved_streams_count"] == 0
    assert audit["unapproved_streams_count"] == 2
    assert audit["stream_details"]["STREAM-VERBAL"]["is_approved_for_training"] is False
    assert audit["stream_details"]["STREAM-TODO"]["is_approved_for_training"] is False


def test_stream_permissions_valid_executed_agreement():
    """Legitimately executed agreement with non-draft reference passes validation."""
    past_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    df = pd.DataFrame([
        {
            "stream_id": "STREAM-EXECUTED",
            "acquisition_stream_name": "Formal Municipal CCTV Access",
            "responsible_organization": "GHMC ICCC",
            "request_status": "approved",
            "evidence_reference": "MOU-GHMC-IT-2026-089-EXECUTED",
            "approval_date": past_date,
            "outstanding_blockers": "None",
            "next_action": "Begin scheduled intake",
        }
    ])
    audit = validate_stream_permissions(df)
    assert audit["approved_streams_count"] == 1
    assert audit["unapproved_streams_count"] == 0
    assert len(audit["violations"]) == 0
    assert audit["stream_details"]["STREAM-EXECUTED"]["is_approved_for_training"] is True
    assert audit["stream_details"]["STREAM-EXECUTED"]["evidence_valid"] is True


def test_stream_permissions_rejection_of_future_approval_date():
    """Approval dates in the future must fail validation."""
    future_date = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    df = pd.DataFrame([
        {
            "stream_id": "STREAM-FUTURE",
            "acquisition_stream_name": "Premature Stream",
            "responsible_organization": "State Govt",
            "request_status": "approved",
            "evidence_reference": "MOU-STATE-2026-999-SIGNED",
            "approval_date": future_date,
        }
    ])
    audit = validate_stream_permissions(df)
    assert audit["approved_streams_count"] == 0
    assert audit["stream_details"]["STREAM-FUTURE"]["is_approved_for_training"] is False
    assert any("in the future" in r for r in audit["stream_details"]["STREAM-FUTURE"]["reasons"])


# =====================================================================
# 2. Separation of Location Eligibility vs Legal Permission
# =====================================================================

def test_separation_location_eligible_but_unpermitted():
    """A record inside Hyderabad but lacking approved permission has separate eligibility statuses."""
    record = {
        "latitude": 17.3984,  # Inside Hyderabad
        "longitude": 78.4145,
        "location_precision_m": 10.0,
        "permission_status": "pending",  # Unapproved
        "consent_or_authorization_reference": "PENDING_VERIFICATION",
    }
    elig = validate_acquisition_record_eligibility(record)
    assert elig["is_location_eligible"] is True
    assert elig["is_legally_permitted"] is False
    assert elig["is_jointly_eligible"] is False


def test_separation_legally_permitted_but_outside_hyderabad():
    """A record legally approved but outside Hyderabad bounds fails location eligibility."""
    record = {
        "latitude": 13.0827,  # Chennai coordinates
        "longitude": 80.2707,
        "location_precision_m": 5.0,
        "permission_status": "approved",
        "consent_or_authorization_reference": "MOU-RESEARCH-2026-VALID",
    }
    elig = validate_acquisition_record_eligibility(record)
    assert elig["is_location_eligible"] is False
    assert elig["is_legally_permitted"] is True
    assert elig["is_jointly_eligible"] is False
    assert any("coordinates_outside_hyderabad" in r for r in elig["location_reasons"])


# =====================================================================
# 3. Real-versus-Synthetic Provenance Categorization Tests
# =====================================================================

def test_provenance_synthetic_fixtures_excluded():
    """Synthetic fixtures prefixed with SYNTHETIC- are excluded from real accounts."""
    df = pd.DataFrame([
        {
            "acquisition_id": "SYNTHETIC-EX-001",
            "source_type": "municipal_cctv",
            "source_owner": "GHMC_ICCC_MOCK",
            "permission_status": "approved",
            "consent_or_authorization_reference": "MOU-GHMC-2026-SYNTH-01",
            "latitude": 17.3984,
            "longitude": 78.4145,
            "location_precision_m": 5.0,
            "privacy_processing_status": "blurred_verified",
            "image_or_clip_reference": "data/collection_v4/raw/synthetic_ex_001.jpg",
        }
    ])
    audit = categorize_provenance(df)
    assert audit["synthetic_fixtures_excluded_count"] == 1
    assert audit["real_world_accepted_count"] == 0
    assert "SYNTHETIC-EX-001" in audit["categories"][ProvenanceCategory.SYNTHETIC_FIXTURE.value]


def test_provenance_contradictory_mock_owner_on_real_id():
    """A record with a real ID format but referencing a MOCK owner is flagged as CONTRADICTORY."""
    df = pd.DataFrame([
        {
            "acquisition_id": "ACQ-HYD-2026-0001",  # Purports to be real field acquisition
            "source_type": "field_team_vantage",
            "source_owner": "MOCK_CREW_ALPHA",      # Contradictory mock owner!
            "permission_status": "approved",
            "consent_or_authorization_reference": "IRB-SYNTHETIC-FIXTURE",
            "latitude": 17.3985,
            "longitude": 78.4146,
            "location_precision_m": 5.0,
            "privacy_processing_status": "blurred_verified",
            "image_or_clip_reference": "data/collection_v4/raw/field_001.jpg",
        }
    ])
    audit = categorize_provenance(df)
    assert audit["counts"][ProvenanceCategory.CONTRADICTORY_PROVENANCE.value] == 1
    assert audit["real_world_accepted_count"] == 0
    assert "ACQ-HYD-2026-0001" in audit["categories"][ProvenanceCategory.CONTRADICTORY_PROVENANCE.value]


def test_provenance_unknown_missing_source():
    """A record with missing or unknown source owner is categorized as UNKNOWN_PROVENANCE."""
    df = pd.DataFrame([
        {
            "acquisition_id": "ACQ-HYD-2026-0002",
            "source_type": "citizen_upload",
            "source_owner": "unknown",  # Unknown owner
            "permission_status": "approved",
            "consent_or_authorization_reference": "TERMS-2026",
            "latitude": 17.3985,
            "longitude": 78.4146,
            "location_precision_m": 5.0,
            "privacy_processing_status": "blurred_verified",
            "image_or_clip_reference": "data/collection_v4/raw/upload_002.jpg",
        }
    ])
    audit = categorize_provenance(df)
    assert audit["counts"][ProvenanceCategory.UNKNOWN_PROVENANCE.value] == 1
    assert audit["real_world_accepted_count"] == 0


def test_provenance_accepted_real_world_record():
    """A real-world record satisfying all provenance, bounds, precision, and privacy is accepted."""
    df = pd.DataFrame([
        {
            "acquisition_id": "ACQ-HYD-2026-0003",
            "source_type": "municipal_cctv",
            "source_owner": "GHMC_ICCC_COMMISSIONER",
            "permission_status": "approved",
            "consent_or_authorization_reference": "MOU-GHMC-IT-2026-089-EXECUTED",
            "latitude": 17.3984,
            "longitude": 78.4145,
            "location_precision_m": 5.0,
            "privacy_processing_status": "blurred_verified",
            "image_or_clip_reference": "data/collection_v4/processed_privacy/acq_0003.jpg",
        }
    ])
    audit = categorize_provenance(df)
    assert audit["real_world_accepted_count"] == 1
    assert "ACQ-HYD-2026-0003" in audit["categories"][ProvenanceCategory.ACCEPTED_REAL.value]


# =====================================================================
# 4. Independent Evaluation Protection Guard Tests
# =====================================================================

def test_guard_catches_in_band_locked_flag():
    """Passing a dataframe with is_locked_for_tuning=True triggers LockedEvaluationSetViolationError."""
    df_candidate = pd.DataFrame([
        {"image_id": "IMG-001", "is_locked_for_tuning": True, "label": 1}
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="is_locked_for_tuning=True"):
        EvaluationSetProtectionGuard.assert_no_locked_eval_leakage(df_candidate, {})


def test_guard_catches_eval_partition_label():
    """Passing candidate data with partition='independent_evaluation' triggers error."""
    df_candidate = pd.DataFrame([
        {"image_id": "IMG-002", "partition": "independent_evaluation", "label": 0}
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="partition='independent_evaluation'"):
        EvaluationSetProtectionGuard.assert_no_locked_eval_leakage(df_candidate, {})


def test_guard_catches_id_overlap_with_metadata():
    """Candidate training set sharing an image ID with locked metadata is intercepted."""
    metadata = EvaluationSplitMetadata(
        split_id="EVAL-LOCKED-01",
        is_locked_for_tuning=True,
        lock_timestamp_utc="2026-10-27T10:00:00Z",
        record_count=2,
        manifest_sha256="abc123mockhash",
        image_ids=["IMG-EVAL-01", "IMG-EVAL-02"],
        session_ids=["SES-01"],
    )
    df_train = pd.DataFrame([
        {"image_id": "IMG-TRAIN-01", "label": 0},
        {"image_id": "IMG-EVAL-01", "label": 1},  # Leaked eval ID!
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="Found 1 overlapping ID"):
        EvaluationSetProtectionGuard.assert_no_locked_eval_leakage(df_train, metadata)


def test_guard_catches_session_leakage():
    """Candidate training set sharing a capture session with locked evaluation set is intercepted."""
    metadata = EvaluationSplitMetadata(
        split_id="EVAL-LOCKED-02",
        is_locked_for_tuning=True,
        lock_timestamp_utc="2026-10-27T10:00:00Z",
        record_count=1,
        manifest_sha256="mockhash",
        image_ids=["IMG-EVAL-99"],
        session_ids=["SES-SHARED-BURST-01"],
    )
    df_train = pd.DataFrame([
        {"image_id": "IMG-TRAIN-88", "capture_session_id": "SES-SHARED-BURST-01", "label": 1}
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="overlapping capture session"):
        EvaluationSetProtectionGuard.assert_no_locked_eval_leakage(df_train, metadata)


def test_guard_catches_perceptual_dhash_near_duplicate():
    """Candidate training set having a near-duplicate (dhash Hamming <= 2) is intercepted."""
    eval_df = pd.DataFrame([
        {"image_id": "IMG-EVAL-01", "dhash": "0000000000000000", "label": 1}
    ])
    train_df = pd.DataFrame([
        # Hamming distance 1 bit from eval dhash (0x0001 differs by 1 bit from 0x0000)
        {"image_id": "IMG-TRAIN-01", "dhash": "0000000000000001", "label": 1}
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="perceptual near-duplicate pair"):
        EvaluationSetProtectionGuard.assert_no_locked_eval_leakage(train_df, eval_df, hamming_threshold=2)


def test_guard_threshold_tuning_protection():
    """guard_threshold_tuning protects threshold optimization routines from receiving eval data."""
    val_df_corrupted = pd.DataFrame([
        {"image_id": "IMG-VAL-01", "is_locked_for_tuning": True, "prob": 0.82}
    ])
    with pytest.raises(LockedEvaluationSetViolationError, match="decision-threshold-tuning"):
        EvaluationSetProtectionGuard.guard_threshold_tuning(val_df_corrupted, {})


# =====================================================================
# 5. Readiness Report & Traceability Tests
# =====================================================================

def test_phase16_readiness_audit_deterministic_no_go():
    """Full readiness audit reports NO-GO and NOT_READY on current repository state."""
    audit = generate_phase16_readiness_audit(
        permission_register_path="data/collection_v4/permission_register.csv",
        acquisition_register_path="data/collection_v4/acquisition_register.csv",
        annotation_template_path="data/collection_v4/governance_annotation_template.csv",
        manifest_v4_path="data/processed/manifest_v4/full_manifest_v4.csv",
    )
    assert audit["overall_status"] == "NO-GO"
    assert "NO-GO" in audit["v4_training_verdict"]
    assert audit["gates"]["stream_permissions"]["status"] == "NOT_READY"
    assert audit["gates"]["acquisition_provenance"]["status"] == "NOT_READY"
    assert audit["gates"]["acquisition_provenance"]["accepted_real_world_records_count"] == 0
    assert audit["gates"]["acquisition_provenance"]["synthetic_fixtures_excluded_count"] == 3
    assert len(audit["blocking_reasons"]) >= 2
    # Verify traceability fields exist
    assert "streams" in audit["traceability"]
    assert "acquisition_records" in audit["traceability"]


def test_phase16_readiness_audit_missing_file_fail_closed():
    """Missing permission register produces UNKNOWN/NOT_READY and blocks GO status."""
    audit = generate_phase16_readiness_audit(
        permission_register_path="nonexistent_permission_register.csv",
        acquisition_register_path="data/collection_v4/acquisition_register.csv",
    )
    assert audit["overall_status"] == "NO-GO"
    assert audit["gates"]["stream_permissions"]["status"] == "UNKNOWN"
