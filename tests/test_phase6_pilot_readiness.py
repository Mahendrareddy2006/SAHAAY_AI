"""
Unit and integration test suite for Sahaay AI Phase 6:
Field-Pilot Readiness, Ground-Truth Collection, Data Governance & Operational Validation.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.observations.schemas import (
    GroundTruthObservation,
    ObservationMethod,
    WaterPresenceExtent,
    DepthMeasurementMethod,
    RoadPassability,
    VerificationStatus,
    ConsentPrivacyStatus,
)
from sahaay.observations.ingestion import ObservationIngestionPipeline
from sahaay.review.workflow import (
    ReviewQueueService,
    ReviewItem,
    ReviewItemType,
    ReviewStatus,
    ReviewerRole,
)
from sahaay.adapters.registry import default_adapter_registry
from sahaay.decision.contracts import (
    DecisionInput,
    DecisionOutput,
    DecisionStatus,
    AlertLevel,
    CurrentFloodEvidenceStatus,
    evaluate_decision,
)


@pytest.fixture
def api_client():
    return TestClient(app)


@pytest.fixture
def valid_obs_dict():
    now_utc = datetime.now(timezone.utc)
    return {
        "observation_id": "OBS-20261025-0001",
        "start_time_utc": (now_utc - timedelta(minutes=20)).isoformat(),
        "end_time_utc": (now_utc - timedelta(minutes=15)).isoformat(),
        "timezone": "Asia/Kolkata",
        "corridor_id": "CORR-HYD-01",
        "latitude": 17.442,
        "longitude": 78.473,
        "coordinate_precision_m": 5.0,
        "observer_pseudonym": "OBSERVER-F01",
        "observation_method": "PHYSICAL_VANTAGE_INSPECTION",
        "water_presence_extent": "PARTIAL_LANE_WATERLOGGING",
        "measured_water_depth_cm": 14.5,
        "depth_measurement_method": "CURB_REFERENCE_CALIBRATION",
        "road_passability": "IMPASSABLE_TWO_WHEELERS",
        "rainfall_source": "TSDPS_AWS_BEGUMPET",
        "rainfall_source_timestamp_utc": (now_utc - timedelta(minutes=30)).isoformat(),
        "image_reference": "IMG_OBS_0001_redacted.jpg",
        "quality_flags": "NONE",
        "verification_status": "SUPERVISOR_VERIFIED",
        "verifier_timestamp_utc": (now_utc - timedelta(minutes=10)).isoformat(),
        "consent_and_privacy_status": "DPDP_CONSENT_GRANTED_REDACTED",
        "retention_policy_months": 36,
        "is_synthetic_or_simulated": False,
    }


# ==============================================================================
# 1. Permission and Zero Field Observation Verification
# ==============================================================================

def test_zero_real_observations_in_database():
    """Verify that current ground-truth field observation count is exactly 0."""
    pipeline = ObservationIngestionPipeline()
    # No records ingested initially
    assert len(pipeline._existing_observation_index) == 0


def test_permission_register_has_zero_unverified_approvals():
    """Verify that permission_register.csv records ZERO approved live feeds."""
    perm_path = os.path.join("data", "phase6", "permission_register.csv")
    assert os.path.exists(perm_path), f"Missing {perm_path}"
    
    with open(perm_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    headers = lines[0].strip().split(",")
    status_idx = headers.index("request_status")
    
    for row in lines[1:]:
        parts = row.strip().split(",")
        status = parts[status_idx]
        assert status != "APPROVED", f"Found unauthorized APPROVED status in permission register: {row}"


# ==============================================================================
# 2. Schema and Boundary Validation Tests
# ==============================================================================

def test_valid_observation_ingestion(valid_obs_dict):
    """Verify that a valid observation is accepted by schema and pipeline."""
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=False)
    assert result["success"] is True
    assert result["status"] == "INGESTED"
    assert result["observation_id"] == "OBS-20261025-0001"


def test_future_timestamp_rejected(valid_obs_dict):
    """Verify that observations with future timestamps are rejected."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    valid_obs_dict["start_time_utc"] = future_time
    valid_obs_dict["end_time_utc"] = future_time
    
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=True)
    assert result["success"] is False
    assert "cannot be in the future" in result["error"]


def test_coordinates_outside_hyderabad_rejected(valid_obs_dict):
    """Verify that coordinates outside Hyderabad bounding box are rejected."""
    # Latitude in Mumbai / Delhi
    valid_obs_dict["latitude"] = 19.0760
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=True)
    assert result["success"] is False
    assert "SCHEMA_VALIDATION_ERROR" in result["error"]


def test_withheld_consent_rejected(valid_obs_dict):
    """Verify that observations with consent WITHHELD are strictly rejected."""
    valid_obs_dict["consent_and_privacy_status"] = "WITHHELD"
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=True)
    assert result["success"] is False
    assert "WITHHELD" in result["error"]


def test_no_water_with_positive_depth_rejected(valid_obs_dict):
    """Verify that NO_WATER with positive depth is rejected as contradictory."""
    valid_obs_dict["water_presence_extent"] = "NO_WATER"
    valid_obs_dict["measured_water_depth_cm"] = 25.0
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=True)
    assert result["success"] is False
    assert "measured_water_depth_cm must be 0.0 or None" in result["error"]


def test_synthetic_fixture_quarantined(valid_obs_dict):
    """Verify that synthetic fixtures are quarantined and never marked as real data."""
    valid_obs_dict["is_synthetic_or_simulated"] = True
    pipeline = ObservationIngestionPipeline()
    result = pipeline.ingest_record(valid_obs_dict, dry_run=True)
    assert result["success"] is False
    assert result["error"] == "SYNTHETIC_RECORD_QUARANTINED"


# ==============================================================================
# 3. Duplicate and Disagreement Handling
# ==============================================================================

def test_spatio_temporal_duplicate_flagging(valid_obs_dict):
    """Verify that near-duplicate observations at the same location/time are flagged."""
    pipeline = ObservationIngestionPipeline()
    # Ingest first
    res1 = pipeline.ingest_record(valid_obs_dict, dry_run=False)
    assert res1["success"] is True
    
    # Ingest near-duplicate (different ID, same time, ~10m away)
    dup_dict = dict(valid_obs_dict)
    dup_dict["observation_id"] = "OBS-20261025-0002"
    dup_dict["latitude"] = valid_obs_dict["latitude"] + 0.0001
    
    res2 = pipeline.ingest_record(dup_dict, dry_run=False)
    assert res2["success"] is False
    assert "DUPLICATE" in res2["status"] or "DUPLICATE" in res2["error"]


# ==============================================================================
# 4. Human Review Queue & Cryptographic Hash Chaining
# ==============================================================================

def test_review_queue_workflow_and_hash_chaining():
    """Verify that human review actions form a cryptographically verifiable chain."""
    service = ReviewQueueService()
    
    item = service.enqueue({
        "item_id": "REV-TEST-001",
        "item_type": ReviewItemType.CONTRADICTORY_EVIDENCE,
        "corridor_id": "CORR-HYD-01",
        "alert_level": "ADVISORY",
        "evidence_status": "INCONCLUSIVE",
        "reason_codes": ["CONTRADICTORY_OBSERVATIONS_DETECTED"],
        "conflicting_sources": ["CCTV", "CITIZEN_REPORT"],
    })
    
    assert item.status == ReviewStatus.PENDING_REVIEW
    assert len(service.list_pending()) == 1
    
    # First review action by supervisor
    updated_item = service.record_review_action(
        item_id="REV-TEST-001",
        reviewer_role=ReviewerRole.SUPERVISOR_DISPATCHER,
        reviewer_id="SUP-01",
        action_type="INVESTIGATE_CAMERA",
        justification_notes="PTZ camera angle misaligned; requesting field vantage check.",
        new_status=ReviewStatus.ESCALATED_TO_FIELD_TEAM,
    )
    
    assert updated_item.status == ReviewStatus.ESCALATED_TO_FIELD_TEAM
    assert len(updated_item.audit_chain) == 1
    hash1 = updated_item.audit_chain[0].audit_hash
    assert hash1 is not None and len(hash1) == 64
    
    # Second review action by field lead
    final_item = service.record_review_action(
        item_id="REV-TEST-001",
        reviewer_role=ReviewerRole.FIELD_SAFETY_LEAD,
        reviewer_id="LEAD-01",
        action_type="CONFIRM_GROUND_TRUTH",
        justification_notes="Field Unit verified 15cm standing water in left curb lane.",
        new_status=ReviewStatus.VERIFIED_CONFIRMED,
    )
    
    assert final_item.status == ReviewStatus.VERIFIED_CONFIRMED
    assert len(final_item.audit_chain) == 2
    hash2 = final_item.audit_chain[1].audit_hash
    assert hash2 is not None and len(hash2) == 64
    assert hash1 != hash2


# ==============================================================================
# 5. API Endpoints Integration for Review Queue
# ==============================================================================

def test_api_review_queue_endpoints(api_client):
    """Test GET /api/v1/review/pending and POST /api/v1/review/action."""
    from sahaay.api.routes import review_queue_service
    
    # Enqueue a test item
    review_queue_service.enqueue({
        "item_id": "REV-API-TEST-01",
        "item_type": ReviewItemType.CITIZEN_REPORT,
        "corridor_id": "CORR-HYD-02",
        "evidence_status": "ELEVATED_ENVIRONMENTAL_RISK",
        "reason_codes": ["UNVERIFIED_CITIZEN_REPORT"],
    })
    
    # Query pending
    res = api_client.get("/api/v1/review/pending")
    assert res.status_code == 200
    pending_items = res.json()
    assert any(it["item_id"] == "REV-API-TEST-01" for it in pending_items)
    
    # Submit action
    action_payload = {
        "item_id": "REV-API-TEST-01",
        "reviewer_role": "SUPERVISOR_DISPATCHER",
        "reviewer_id": "SUP-API-TEST",
        "action_type": "DISMISS_FALSE_ALARM",
        "justification_notes": "Citizen photo shows localized puddle on private driveway, not municipal road.",
        "new_status": "DISMISSED_FALSE_ALARM",
    }
    
    post_res = api_client.post("/api/v1/review/action", json=action_payload)
    assert post_res.status_code == 200
    updated = post_res.json()
    assert updated["status"] == "DISMISSED_FALSE_ALARM"
    assert len(updated["audit_chain"]) >= 1


# ==============================================================================
# 6. Safety Gate Preservation & Regression Tests
# ==============================================================================

def test_vision_v4_readiness_gate_remains_no_go():
    """Verify that Vision V4 readiness gate evaluates strictly to NO-GO."""
    from sahaay.adapters.registry import default_adapter_registry
    cctv = default_adapter_registry.get_adapter("MUNICIPAL-CCTV-STREAM")
    assert cctv is not None
    reading = cctv.fetch_latest("CORR-HYD-01")
    assert reading.authorization_status.value == "QUARANTINED_DISABLED"
    assert "QUARANTINED_VISION_V4_GATE_ENFORCED" in reading.quality_flags
    assert "NO-GO" in reading.error_message


def test_missing_telemetry_never_converted_to_zero():
    """Verify that missing rainfall telemetry triggers INSUFFICIENT_DATA and not CLEAR."""
    inp = DecisionInput(
        location_id="CORR-HYD-01",
        road_name="Rasoolpura Junction",
        rainfall_risk_category="UNKNOWN",  # Missing telemetry!
        rainfall_risk_score=0.0,
        missing_inputs=["rain_1h_mm"],
        vulnerability_category="HIGH",
        vulnerability_index=0.75,
        vision_confidence=None,
        citizen_report_count_in_zone=0,
    )
    decision = evaluate_decision(inp)
    assert decision.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert decision.current_flood_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
    assert decision.alert_level != AlertLevel.CLEAR
    assert "TELEMETRY_DATA_MISSING_OR_STALE" in decision.reason_codes
