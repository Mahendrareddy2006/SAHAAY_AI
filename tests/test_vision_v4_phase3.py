"""
Sahaay AI - Vision V4 Phase 3 Test Suite: Permission Onboarding & Pilot Collection

Asserts:
1. Permission register schema, stream tracking, and truthful request statuses.
2. Completeness and legal disclaimers of all 6 onboarding draft documents.
3. Pilot plan candidate corridor safety constraints and vantage verification.
4. Pilot collection audit execution, real vs synthetic data separation.
5. Preservation of the NO-GO training readiness gate.
6. Strict preservation of historical model checkpoints and manifests.
"""

import os
import json
import pytest
import pandas as pd

from scripts.audit_v4_pilot_collection import audit_pilot_collection
from scripts.check_v4_data_readiness import evaluate_readiness


# --- 1. Permission Register Integrity & Truthfulness ---

def test_permission_register_exists_and_valid():
    perm_csv = os.path.join("data", "collection_v4", "permission_register.csv")
    assert os.path.exists(perm_csv), f"Permission register missing: {perm_csv}"

    df = pd.read_csv(perm_csv)
    expected_cols = [
        "stream_id",
        "acquisition_stream_name",
        "responsible_organization",
        "required_agreement_type",
        "intended_data_use_training_rights",
        "privacy_and_retention_conditions",
        "access_restrictions",
        "request_status",
        "evidence_reference",
        "outstanding_blockers",
        "next_action",
        "responsible_role",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing required column in permission register: {col}"

    assert len(df) == 4, f"Expected 4 streams, found {len(df)}"

    stream_ids = set(df["stream_id"])
    assert stream_ids == {
        "STREAM-01-MUNICIPAL-CCTV",
        "STREAM-02-CITIZEN-UPLOAD",
        "STREAM-03-FIELD-VANTAGE",
        "STREAM-04-COMMERCIAL-DASHCAM",
    }


def test_permission_register_has_zero_unverified_approvals():
    """
    Ensure no stream is falsely marked 'approved' without documented evidence.
    Currently, all streams must be 'pending' or 'not_started'.
    """
    perm_csv = os.path.join("data", "collection_v4", "permission_register.csv")
    df = pd.read_csv(perm_csv)

    approved = df[df["request_status"] == "approved"]
    assert len(approved) == 0, (
        f"Found {len(approved)} streams falsely marked as approved without executed agreements!"
    )

    for _, row in df.iterrows():
        assert row["request_status"] in ["pending", "not_started"], (
            f"Stream {row['stream_id']} has unexpected status: {row['request_status']}"
        )
        assert "DRAFT" in str(row["evidence_reference"]), (
            f"Stream {row['stream_id']} must reference DRAFT onboarding materials."
        )


# --- 2. Onboarding Packet Completeness & Legal Disclaimers ---

def test_onboarding_packet_files_exist():
    required_drafts = [
        "municipal_data_access_request.md",
        "data_sharing_permitted_use_checklist.md",
        "citizen_consent_and_privacy_notice.md",
        "field_collection_safety_checklist.md",
        "commercial_dashcam_partner_request.md",
        "data_retention_deletion_access_checklist.md",
    ]
    for draft_file in required_drafts:
        p = os.path.join("docs", "phase3_onboarding", draft_file)
        assert os.path.exists(p), f"Missing onboarding packet document: {p}"
        assert os.path.getsize(p) > 200, f"Onboarding document empty: {p}"

        with open(p, "r", encoding="utf-8") as f:
            content = f.read()

        # Ensure legal notice/disclaimer is prominent
        assert any(term in content for term in ["LEGAL NOTICE", "NOTICE", "CRITICAL", "SAFETY FIRST"]), (
            f"Document {draft_file} is missing mandatory legal or safety disclaimer header!"
        )


# --- 3. Pilot Collection Plan & Site Constraints ---

def test_pilot_plan_defines_four_candidate_sites():
    pilot_plan_path = os.path.join("docs", "vision_v4_phase3_pilot_plan.md")
    assert os.path.exists(pilot_plan_path), f"Pilot plan missing: {pilot_plan_path}"

    with open(pilot_plan_path, "r", encoding="utf-8") as f:
        content = f.read()

    for site_id in ["PILOT-LOC-01", "PILOT-LOC-02", "PILOT-LOC-03", "PILOT-LOC-04"]:
        assert site_id in content, f"Pilot plan missing site definition: {site_id}"

    assert "Stop-Work Order" in content or "Stop-Work Authority" in content, (
        "Pilot plan missing mandatory stop-work authority definition."
    )


# --- 4. Pilot Collection Audit & Separation of Synthetic Fixtures ---

def test_pilot_collection_audit_execution(tmp_path):
    output_json = tmp_path / "pilot_audit_test.json"
    audit = audit_pilot_collection(output_audit_path=str(output_json))

    assert audit["pilot_operational_status"] == "AWAITING_LEGAL_EXECUTION"
    assert audit["permission_summary"]["approved_streams"] == 0
    assert audit["data_inventory"]["real_world_images_received"] == 0
    assert audit["data_inventory"]["synthetic_schema_fixtures"] >= 2
    assert audit["annotation_audit"]["real_images_annotated"] == 0
    assert audit["annotation_audit"]["inter_annotator_agreement_status"] == "INSUFFICIENT_REAL_DATA"
    assert len(audit["remaining_blockers"]) > 0


# --- 5. Preservation of NO-GO Readiness Gate ---

def test_readiness_gate_preserves_no_go_status():
    report = evaluate_readiness(use_synthetic_fixture=False)
    assert report["overall_status"] == "NO-GO"
    assert len(report["blocking_reasons"]) >= 3
    assert any("0 authorized real-world records" in b for b in report["blocking_reasons"])
    assert any("Source-label confounding" in b for b in report["blocking_reasons"])
    assert any("Insufficient multi-source cross-representation" in b for b in report["blocking_reasons"])


# --- 6. Historical Artifact Preservation ---

def test_historical_artifacts_remain_unmodified():
    historical_checkpoints = [
        os.path.join("models", "vision", "best_model.pt"),
        os.path.join("models", "vision", "v2", "model_v2.pt"),
        os.path.join("models", "vision", "v3", "model_v3_monsoon.pt"),
    ]
    for ckpt in historical_checkpoints:
        assert os.path.exists(ckpt), f"Historical checkpoint missing: {ckpt}"
        assert os.path.getsize(ckpt) > 1000, f"Historical checkpoint empty: {ckpt}"

    historical_manifests = [
        os.path.join("data", "processed", "train.csv"),
        os.path.join("data", "processed", "manifest_v2", "train_v2.csv"),
        os.path.join("data", "processed", "manifest_v3", "train_v3.csv"),
        os.path.join("data", "processed", "manifest_v4", "train_v4.csv"),
    ]
    for mf in historical_manifests:
        assert os.path.exists(mf), f"Historical manifest missing: {mf}"
        assert os.path.getsize(mf) > 1000, f"Historical manifest empty: {mf}"
