"""
Sahaay AI - Phase 5 End-to-End Integration & Live-Data Readiness Tests
Tests unified flood intelligence contracts, citizen report lifecycle, near-duplicate suppression,
live data adapter boundaries, contradictory evidence resolution, Decision Engine hardening,
and regression preservation of historical gates.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sahaay.adapters.base import FeedAuthorizationStatus
from sahaay.adapters.registry import default_adapter_registry
from sahaay.api.main import app
from sahaay.decision.contracts import (
    AlertLevel,
    CurrentFloodEvidenceStatus,
    DecisionInput,
    DecisionStatus,
    HazardNature,
    evaluate_decision,
)
from sahaay.reports.schemas import (
    CitizenReportSubmission,
    ReportFreshness,
    ReportValidationStatus,
    ReportVerificationRequest,
    ReportVerificationStatus,
    WaterDepthEstimate,
)
from sahaay.reports.service import CitizenReportService, reset_report_database


@pytest.fixture(autouse=True)
def clean_report_db():
    reset_report_database()
    yield
    reset_report_database()


# ---------------------------------------------------------------------------
# 1. Citizen Report Lifecycle, Deduplication & Verification Tests
# ---------------------------------------------------------------------------

def test_citizen_report_submission_privacy_masking():
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.402345,
        longitude=78.411234,
        location_precision_m=20.0,
        description="Water accumulation under flyover near metro pillar.",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        reporter_contact_raw="confidential_citizen@example.com",
        consent_given=True,
    )
    record = service.submit_report(sub)

    assert record.report_id.startswith("REP-")
    assert record.validation_status == ReportValidationStatus.VALID
    assert record.reporter_id_masked.startswith("ANON-")
    assert "confidential_citizen" not in record.reporter_id_masked
    # Precision < 50m triggers coordinate coarsening to 3 decimal places
    assert record.latitude_coarsened == 17.402
    assert record.longitude_coarsened == 78.411


def test_consent_withheld_rejection():
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.4023,
        longitude=78.4112,
        location_precision_m=50.0,
        description="Spam report without consent",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        consent_given=False,
    )
    record = service.submit_report(sub)
    assert record.validation_status == ReportValidationStatus.SPAM_OR_MALFORMED
    assert "REJECTED_CONSENT_WITHHELD" in record.reason_codes


def test_near_duplicate_suppression_and_corroboration():
    service = CitizenReportService()
    now_dt = datetime.now(timezone.utc)

    # Primary Report
    sub1 = CitizenReportSubmission(
        corridor_id="HYD-LOC-002",
        latitude=17.4095,
        longitude=78.3986,
        location_precision_m=30.0,
        description="First report of rising nala water.",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        reporter_contact_raw="user_alpha@test.com",
        consent_given=True,
    )
    rec1 = service.submit_report(sub1, submission_time=now_dt)
    assert not rec1.is_duplicate
    assert rec1.corroboration_count == 1

    # Near-Duplicate Report (same corridor, 40 meters away, 5 min later, different user)
    sub2 = CitizenReportSubmission(
        corridor_id="HYD-LOC-002",
        latitude=17.4098,
        longitude=78.3989,
        location_precision_m=30.0,
        description="Water is very high near Shaikpet junction.",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        reporter_contact_raw="user_beta@test.com",
        consent_given=True,
    )
    rec2 = service.submit_report(sub2, submission_time=now_dt)
    assert rec2.is_duplicate
    assert rec2.duplicate_of_report_id == rec1.report_id

    # Check parent corroboration count incremented because different reporter
    parent = service._db[rec1.report_id]
    assert parent.corroboration_count == 2
    assert rec2.report_id in parent.linked_report_ids


def test_responder_verification_workflow():
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-005",
        latitude=17.3768,
        longitude=78.4975,
        location_precision_m=25.0,
        description="RUB underpass submerged.",
        estimated_depth=WaterDepthEstimate.WAIST_DEEP_OR_MORE,
        consent_given=True,
    )
    rec = service.submit_report(sub)
    assert rec.verification_status == ReportVerificationStatus.UNVERIFIED

    # Verify by DRF responder
    req = ReportVerificationRequest(
        verifier_id="DRF-UNIT-07",
        verifier_role="GHMC_DRF_OFFICER",
        verification_status=ReportVerificationStatus.VERIFIED_BY_RESPONDER,
        observed_depth_cm=55.0,
        verification_notes="Confirmed severe submergence; road blocked with safety cones.",
    )
    verified = service.verify_report(rec.report_id, req)
    assert verified.verification_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER
    assert "GHMC_DRF_OFFICER:DRF-UNIT-07" == verified.verified_by_entity
    assert any("OBSERVED_DEPTH_55CM" in r for r in verified.reason_codes)


# ---------------------------------------------------------------------------
# 2. Live Data Adapter Boundaries & Status Tests
# ---------------------------------------------------------------------------

def test_adapter_registry_and_live_readiness():
    registry = default_adapter_registry
    status_report = registry.generate_source_status_report()

    summary = status_report["overall_live_readiness_summary"]
    assert summary["total_adapters_registered"] == 4
    # Real-world honesty: Zero unverified live feeds claimed
    assert summary["live_authorized_streams"] == 0
    assert summary["historical_playback_streams"] == 1
    assert summary["pending_approval_streams"] == 2
    assert summary["quarantined_disabled_streams"] == 1


def test_cctv_quarantine_enforcement():
    adapter = default_adapter_registry.get_adapter("MUNICIPAL-CCTV-STREAM")
    assert adapter is not None
    assert adapter.auth_status == FeedAuthorizationStatus.QUARANTINED_DISABLED

    reading = adapter.fetch_latest("HYD-LOC-001")
    assert not reading.data_available
    assert reading.fallback_applied
    assert "QUARANTINED" in reading.error_message


def test_tsdps_adapter_fallback():
    adapter = default_adapter_registry.get_adapter("TSDPS-URBAN-AWS")
    reading = adapter.fetch_latest("HYD-LOC-001")
    assert not reading.is_live_stream
    assert reading.fallback_applied
    assert reading.fallback_mode == "STANDBY_DRY_BASELINE"


def test_nwic_adapter_regional_attribution():
    adapter = default_adapter_registry.get_adapter("NWIC-TELEMETRY-GAUGE")
    reading = adapter.fetch_latest("HYD-LOC-001", lat=17.40, lon=78.45)
    assert reading.data_available
    assert reading.value["station_dist_km"] > 40.0
    assert any("REGIONAL_ATTRIBUTION" in flag for flag in reading.quality_flags)


# ---------------------------------------------------------------------------
# 3. Decision Engine Hardening & Contradictory Evidence Tests
# ---------------------------------------------------------------------------

def test_decision_engine_contradictory_evidence():
    """
    Contradictory evidence: Camera shows dry pavement but fresh report claims deep water.
    Must flag INCONCLUSIVE_CONTRADICTORY and ADVISORY, requiring human verification.
    """
    inp = DecisionInput(
        location_id="HYD-LOC-008",
        road_name="Lakdikapul Junction",
        vision_predicted_class="not_flooded",
        vision_confidence=0.85,
        vision_is_ambiguous=False,
        rainfall_risk_category="LOW",
        rainfall_risk_score=0.05,
        vulnerability_category="MODERATE",
        vulnerability_index=0.35,
        report_age_minutes=10.0,
        is_field_verified=False,
        citizen_report_count_in_zone=1,
        water_depth_estimate="KNEE_DEEP",
        has_contradictory_evidence=True,
    )
    out = evaluate_decision(inp)

    assert out.alert_level == AlertLevel.ADVISORY
    assert out.decision_status == DecisionStatus.INCONCLUSIVE_CONTRADICTORY
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.INCONCLUSIVE
    assert out.requires_human_verification
    assert "CONTRADICTORY_OBSERVATIONS_DETECTED" in out.reason_codes
    assert not out.is_actionable_for_crews


def test_decision_engine_non_silent_missing_rainfall():
    """
    Missing rainfall must trigger INSUFFICIENT_DATA and must NOT be treated as zero rainfall.
    """
    inp = DecisionInput(
        location_id="HYD-LOC-016",
        road_name="Uppal Ring Road Junction",
        rainfall_risk_category="UNKNOWN",
        rainfall_risk_score=0.0,
        missing_inputs=["rain_1h_mm"],
        vulnerability_category="MODERATE",
        vulnerability_index=0.30,
    )
    out = evaluate_decision(inp)

    assert out.decision_status == DecisionStatus.INSUFFICIENT_DATA
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA
    assert "MISSING_PRIMARY_RAINFALL_TELEMETRY" in out.reason_codes
    assert any("not be interpreted as zero rainfall" in w.lower() for w in out.warnings)


def test_decision_engine_modeled_risk_vs_observed_flooding():
    """
    Critical rainfall + Severe vulnerability = WATCH (ELEVATED_ENVIRONMENTAL_RISK),
    NOT confirmed inundation.
    """
    inp = DecisionInput(
        location_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.95,
        vulnerability_category="HIGH",
        vulnerability_index=0.60,
        citizen_report_count_in_zone=0,
        is_field_verified=False,
    )
    out = evaluate_decision(inp)

    assert out.alert_level == AlertLevel.WATCH
    assert out.current_flood_evidence_status == CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK
    assert "PREDICTED_WATERLOGGING_SURGE_ANTICIPATED" in out.reason_codes
    assert any("not confirmed flooded now" in w.lower() for w in out.warnings)


def test_emergency_escalation_policy():
    """
    EMERGENCY requires verified observation + critical rainfall/deep water.
    Vision alone or rainfall alone must NEVER trigger EMERGENCY.
    """
    # Vision alone without rainfall/field verification cannot trigger EMERGENCY
    inp_vision_alone = DecisionInput(
        location_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        vision_predicted_class="flooded",
        vision_confidence=0.99,
        rainfall_risk_category="LOW",
        is_field_verified=False,
    )
    out_vision = evaluate_decision(inp_vision_alone)
    assert out_vision.alert_level == AlertLevel.WARNING
    assert out_vision.alert_level != AlertLevel.EMERGENCY

    # Verified observation + critical rain + deep water escalates to EMERGENCY
    inp_emergency = DecisionInput(
        location_id="HYD-LOC-005",
        road_name="Malakpet RUB",
        vision_predicted_class="flooded",
        vision_confidence=0.95,
        rainfall_risk_category="CRITICAL",
        water_depth_estimate="WAIST_DEEP_OR_MORE",
        is_field_verified=True,
    )
    out_emergency = evaluate_decision(inp_emergency)
    assert out_emergency.alert_level == AlertLevel.EMERGENCY
    assert out_emergency.current_flood_evidence_status == CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE
    assert "EMERGENCY_DEEP_INUNDATION_CONFIRMED" in out_emergency.reason_codes


# ---------------------------------------------------------------------------
# 4. End-to-End API Routes & Demonstration Fixtures Tests
# ---------------------------------------------------------------------------

def test_api_e2e_report_and_verify_flow():
    client = TestClient(app)

    # 1. Citizen submits report
    res_sub = client.post("/api/v1/reports/submit", json={
        "corridor_id": "HYD-LOC-001",
        "latitude": 17.4023,
        "longitude": 78.4112,
        "location_precision_m": 40.0,
        "description": "Rapid water accumulation near flyover ramp.",
        "estimated_depth": "KNEE_DEEP",
        "reporter_contact_raw": "citizen_tester@example.com",
        "consent_given": True,
    })
    assert res_sub.status_code == 201
    rep_data = res_sub.json()
    rep_id = rep_data["report_id"]
    assert rep_data["reporter_id_masked"].startswith("ANON-")

    # 2. Field responder verifies report
    res_ver = client.post(f"/api/v1/reports/verify/{rep_id}", json={
        "verifier_id": "DRF-HQ-1",
        "verifier_role": "GHMC_DRF_OFFICER",
        "verification_status": "VERIFIED_BY_RESPONDER",
        "observed_depth_cm": 35.0,
        "verification_notes": "Verified on-site.",
    })
    assert res_ver.status_code == 200
    assert res_ver.json()["verification_status"] == "VERIFIED_BY_RESPONDER"

    # 3. Decision Engine evaluates with verified report
    res_dec = client.post("/api/v1/decision/evaluate", json={
        "location_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
        "vision_predicted_class": None,
        "rainfall_risk_category": "MEDIUM",
        "vulnerability_category": "HIGH",
        "is_field_verified": True,
        "citizen_report_count_in_zone": 1,
        "report_age_minutes": 5.0,
    })
    assert res_dec.status_code == 200
    dec_data = res_dec.json()
    assert dec_data["alert_level"] == "WARNING"
    assert dec_data["current_flood_evidence_status"] == "OBSERVED_FLOOD_EVIDENCE"


def test_api_dashboard_endpoint():
    client = TestClient(app)
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Sahaay AI" in res.text
    assert "Hyderabad Flood Intelligence Platform" in res.text


def test_end_to_end_scenarios_json_report():
    """Verify that the 10 demonstration scenarios report exists and all scenarios passed."""
    rep_path = Path("reports/phase5/end_to_end_scenarios.json")
    assert rep_path.exists(), "Phase 5 end-to-end scenarios report must exist."

    with open(rep_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_scenarios"] == 10
    assert data["scenarios_passed"] == 10
    assert data["all_scenarios_passed"] is True


def test_vision_v4_readiness_gate_preservation():
    """Verify Vision V4 readiness gate remains strictly NO-GO in Phase 5."""
    audit_path = Path("reports/vision_integrity/v4_phase3_pilot_audit.json")
    assert audit_path.exists()
    with open(audit_path, "r", encoding="utf-8") as f:
        audit = json.load(f)

    assert audit["permission_summary"]["approved_streams"] == 0
    assert audit["data_inventory"]["real_world_images_received"] == 0
    assert "maintain no-go" in audit["recommendation"].lower()

    # Historical checkpoints preserved
    for cp in ["best_model.pt", "v2/model_v2.pt", "v3/model_v3_monsoon.pt"]:
        assert (Path("models/vision") / cp).exists()
