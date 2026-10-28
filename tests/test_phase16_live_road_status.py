"""
Sahaay AI - Phase 16: Live Road Status Test Suite
(tests/test_phase16_live_road_status.py)

Comprehensive offline tests for:
1. Fresh verified observation (authorized responder inspection)
2. Fresh unverified community report (single source)
3. Stale observation (180 - 360 min requires resurvey)
4. Missing evidence (unmonitored segment; NEVER implies dry or safe)
5. Conflicting reports (contradictory conditions without human resolution)
6. Delayed submission with an older observation time (observation time dictates freshness)
7. Future or malformed timestamps (quarantined/rejected)
8. Rainfall present without verified road evidence (environmental risk, not inundation)
9. Static vulnerability without current observations (susceptibility, not inundation)
10. Multiple reports from the same source not counted as independent corroboration
11. Independent sources promoting to CORROBORATED
12. Strict prohibition of guaranteed safety assertions
13. Expired evidence (>360 min) not presented as current
14. Responder verification resolving community conflicts
15. FastAPI endpoint integration (/api/v1/road-status/evaluate and /api/v1/road-status/snapshot)
16. Full 20-corridor offline evaluation coverage
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.reports.schemas import (
    CitizenReportSubmission,
    ReportCondition,
    WaterDepthEstimate,
    SubmissionChannel,
    ReportVerificationStatus,
    ReportVerificationRequest,
)
from sahaay.reports.service import CitizenReportService, reset_report_database
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    RoadStatusSnapshot,
    RoadStatusEvaluationInput,
    FORBIDDEN_SAFETY_PHRASES,
)
from sahaay.road_status.service import (
    LiveRoadStatusService,
    calculate_evidence_freshness,
    COMMUNITY_REPORT_FRESH_MINUTES,
    COMMUNITY_REPORT_STALE_MINUTES,
    COMMUNITY_REPORT_EXPIRY_MINUTES,
)


@pytest.fixture(autouse=True)
def clean_database():
    reset_report_database()
    yield
    reset_report_database()


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def road_service():
    report_svc = CitizenReportService(db={})
    return LiveRoadStatusService(report_service=report_svc)


# =====================================================================
# 1. Fresh Verified Observation Test
# =====================================================================

def test_fresh_verified_observation(road_service):
    """
    Fresh observation verified by an authorized responder produces
    VERIFIED_WATERLOGGED or VERIFIED_IMPASSABLE with LOW uncertainty and optional verified depth.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=20)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-001",
        road_name="Tolichowki Flyover Underpass",
        field_observations=[
            {
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "submission_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "verification_status": "VERIFIED_BY_RESPONDER",
                "verifier_role": "GHMC_DRF_OFFICER",
                "verifier_id": "DRF-UNIT-04",
                "reported_condition": "WATERLOGGED_PASSABLE",
                "observed_depth_cm": 22.0,
                "verified_passability": "impassable_two_wheelers",
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.VERIFIED_WATERLOGGED
    assert snapshot.evidence_type == RoadEvidenceType.FIELD_RESPONDER_INSPECTION
    assert snapshot.verification_state == RoadVerificationState.VERIFIED_BY_RESPONDER
    assert snapshot.uncertainty_level == UncertaintyLevel.LOW
    assert snapshot.confidence_score >= 0.85
    assert snapshot.measured_water_depth_cm == 22.0
    assert snapshot.verified_passability == "impassable_two_wheelers"
    assert "VERIFIED_BY_OFFICIAL_RESPONDER" in snapshot.reason_codes
    assert snapshot.freshness_category == RoadFreshnessCategory.FRESH


# =====================================================================
# 2. Fresh Unverified Community Report Test
# =====================================================================

def test_fresh_unverified_community_report(road_service):
    """
    A single fresh citizen report produces UNVERIFIED condition, HIGH uncertainty,
    and measured_water_depth_cm MUST remain None.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=15)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-002",
        road_name="Shaikpet Nala Road",
        community_reports=[
            {
                "report_id": "REP-COMM-001",
                "reporter_id_masked": "ANON-9f8a2b1c",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "submission_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
                "estimated_depth": "KNEE_DEEP",  # Subjective estimate, NOT ground truth
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.UNVERIFIED
    assert snapshot.evidence_type == RoadEvidenceType.COMMUNITY_REPORT
    assert snapshot.verification_state == RoadVerificationState.UNVERIFIED
    assert snapshot.uncertainty_level == UncertaintyLevel.HIGH
    assert snapshot.confidence_score == 0.40
    # Mandatory invariant: Subjective estimate is NOT converted to measured depth
    assert snapshot.measured_water_depth_cm is None
    assert snapshot.verified_passability == "unverified_unknown"
    assert "UNVERIFIED_COMMUNITY_REPORT" in snapshot.reason_codes


# =====================================================================
# 3. Stale Observation Test
# =====================================================================

def test_stale_observation(road_service):
    """
    An observation between 180 and 360 minutes old must produce STALE status,
    with reason code OBSERVATION_STALE_REQUIRES_RESURVEY.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=240)  # 4 hours old

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-003",
        community_reports=[
            {
                "report_id": "REP-STALE-001",
                "reporter_id_masked": "ANON-11223344",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "submission_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.STALE
    assert snapshot.freshness_category == RoadFreshnessCategory.STALE
    assert snapshot.uncertainty_level == UncertaintyLevel.HIGH
    assert "OBSERVATION_STALE_REQUIRES_RESURVEY" in snapshot.reason_codes


# =====================================================================
# 4. Missing Evidence (Absence of Observations != Safe)
# =====================================================================

def test_missing_evidence(road_service):
    """
    Missing observations must produce NO_CURRENT_EVIDENCE / UNKNOWN.
    Under NO circumstances may an unmonitored road be classified as DRY or SAFE.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-004",
        road_name="Khairatabad Flyover Junction",
        community_reports=[],
        field_observations=[],
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
    assert snapshot.evidence_type == RoadEvidenceType.NO_EVIDENCE
    assert snapshot.verification_state == RoadVerificationState.UNMONITORED
    assert snapshot.freshness_category == RoadFreshnessCategory.UNKNOWN
    assert snapshot.uncertainty_level == UncertaintyLevel.HIGH
    assert snapshot.confidence_score <= 0.20
    assert "NO_OBSERVATIONS_AVAILABLE" in snapshot.reason_codes
    assert "not guarantee road safety" in snapshot.safety_notice.lower()


# =====================================================================
# 5. Conflicting Reports Test
# =====================================================================

def test_conflicting_reports(road_service):
    """
    Contradictory credible reports (flooded vs dry) without responder resolution
    must produce CONFLICTING status and high uncertainty.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs1 = now_utc - timedelta(minutes=20)
    t_obs2 = now_utc - timedelta(minutes=15)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-005",
        community_reports=[
            {
                "report_id": "REP-FLOOD-01",
                "reporter_id_masked": "ANON-AAAA1111",
                "observation_timestamp_utc": t_obs1.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
            {
                "report_id": "REP-DRY-01",
                "reporter_id_masked": "ANON-BBBB2222",
                "observation_timestamp_utc": t_obs2.isoformat().replace("+00:00", "Z"),
                "reported_condition": "DRY_ROAD_CLEAR",
            },
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.CONFLICTING
    assert snapshot.has_conflicting_evidence is True
    assert snapshot.uncertainty_level == UncertaintyLevel.HIGH
    assert snapshot.is_actionable_for_dispatch is True
    assert "CONTRADICTORY_COMMUNITY_REPORTS_DETECTED" in snapshot.reason_codes


# =====================================================================
# 6. Delayed Submission with Older Observation Time Test
# =====================================================================

def test_delayed_submission_older_observation_time(road_service):
    """
    A report submitted 5 minutes ago but observed 200 minutes ago must be evaluated
    using the observation time (200 min -> STALE), NOT the submission time (5 min -> FRESH).
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=200)   # Physical observation 200 min ago
    t_sub = now_utc - timedelta(minutes=5)     # Ingested 5 min ago

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-006",
        community_reports=[
            {
                "report_id": "REP-DELAYED-01",
                "reporter_id_masked": "ANON-DELAYED01",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "submission_timestamp_utc": t_sub.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    # Freshness must reflect the 200 min observation age (STALE), not 5 min submission age!
    assert snapshot.freshness_category == RoadFreshnessCategory.STALE
    assert snapshot.condition_state == RoadConditionState.STALE
    assert snapshot.evidence_age_minutes == 200.0
    assert "DELAYED_SUBMISSION_EVALUATED_BY_OBSERVATION_TIME" in snapshot.reason_codes


# =====================================================================
# 7. Future or Malformed Timestamps Test
# =====================================================================

def test_future_or_malformed_timestamps(road_service):
    """
    Future timestamps (> 60s ahead) and malformed ISO strings must be quarantined/rejected,
    falling back safely to NO_CURRENT_EVIDENCE without crashing.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_future = now_utc + timedelta(hours=2)

    # Scenario A: Future observation timestamp
    inp_future = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-007",
        community_reports=[
            {
                "report_id": "REP-FUTURE-01",
                "observation_timestamp_utc": t_future.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            }
        ]
    )
    snap_future = road_service.evaluate_road_status(inp_future, reference_time_utc=now_utc)
    assert snap_future.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
    assert "FUTURE_TIMESTAMP_REJECTED" in snap_future.reason_codes

    # Scenario B: Malformed timestamp string
    inp_malformed = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-007",
        community_reports=[
            {
                "report_id": "REP-MALFORMED-01",
                "observation_timestamp_utc": "invalid-non-iso-timestamp",
                "reported_condition": "FLOODED_ROAD",
            }
        ]
    )
    snap_malformed = road_service.evaluate_road_status(inp_malformed, reference_time_utc=now_utc)
    assert snap_malformed.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
    assert "MALFORMED_TIMESTAMP_REJECTED" in snap_malformed.reason_codes


# =====================================================================
# 8. Rainfall Present Without Verified Road Evidence
# =====================================================================

def test_rainfall_present_without_verified_road_evidence(road_service):
    """
    Heavy or CRITICAL rainfall in the absence of road observations must NOT establish
    road inundation. The road condition must remain NO_CURRENT_EVIDENCE.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-008",
        rainfall_risk_category="CRITICAL",
        rainfall_risk_score=0.92,
        community_reports=[],
        field_observations=[],
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
    assert snapshot.environmental_rainfall_category == "CRITICAL"
    assert snapshot.environmental_rainfall_score == 0.92
    assert "RAINFALL_PRESENT_WITHOUT_ROAD_OBSERVATIONS" in snapshot.reason_codes
    assert snapshot.condition_state != RoadConditionState.VERIFIED_IMPASSABLE
    assert snapshot.condition_state != RoadConditionState.VERIFIED_WATERLOGGED


# =====================================================================
# 9. Static Vulnerability Without Current Observations
# =====================================================================

def test_static_vulnerability_without_current_observations(road_service):
    """
    Severe static vulnerability (near drain/hotspot) does not establish active flooding.
    Must remain NO_CURRENT_EVIDENCE.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-009",
        vulnerability_category="SEVERE",
        vulnerability_index=0.88,
        community_reports=[],
        field_observations=[],
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
    assert snapshot.static_vulnerability_category == "SEVERE"
    assert snapshot.static_vulnerability_index == 0.88
    assert "STATIC_VULNERABILITY_WITHOUT_ACTIVE_EVIDENCE" in snapshot.reason_codes


# =====================================================================
# 10. Multiple Reports From Same Source Not Independent Corroboration
# =====================================================================

def test_multiple_reports_same_source_not_independent_corroboration(road_service):
    """
    Multiple submissions from the SAME masked reporter count toward raw report volume,
    but independent_sources_count remains 1 and status remains UNVERIFIED.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=10)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-010",
        community_reports=[
            {
                "report_id": "REP-SPAM-01",
                "reporter_id_masked": "ANON-SAME-USER",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
            {
                "report_id": "REP-SPAM-02",
                "reporter_id_masked": "ANON-SAME-USER",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
            {
                "report_id": "REP-SPAM-03",
                "reporter_id_masked": "ANON-SAME-USER",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    # Must remain UNVERIFIED because all 3 reports originate from a single source
    assert snapshot.condition_state == RoadConditionState.UNVERIFIED
    assert snapshot.verification_state == RoadVerificationState.UNVERIFIED
    assert "SINGLE_SOURCE_MULTIPLE_REPORTS_UNPROMOTED" in snapshot.reason_codes


# =====================================================================
# 11. Independent Sources Promote to CORROBORATED
# =====================================================================

def test_independent_sources_promote_to_corroborated(road_service):
    """
    Submissions from >= 2 DISTINCT masked reporters promote status to CORROBORATED.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=15)

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-011",
        community_reports=[
            {
                "report_id": "REP-CORR-01",
                "reporter_id_masked": "ANON-USER-ALPHA",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
            {
                "report_id": "REP-CORR-02",
                "reporter_id_masked": "ANON-USER-BETA",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.CORROBORATED
    assert snapshot.verification_state == RoadVerificationState.CORROBORATED
    assert snapshot.uncertainty_level == UncertaintyLevel.MEDIUM
    assert snapshot.confidence_score >= 0.60
    assert "CORROBORATED_BY_INDEPENDENT_COMMUNITY_SOURCES" in snapshot.reason_codes


# =====================================================================
# 12. No Status Output Implying Guaranteed Safety
# =====================================================================

def test_no_status_output_implying_guaranteed_safety():
    """
    Pydantic schema validator strictly rejects any text containing forbidden
    safety claims like 'guaranteed safe', '100% safe', 'road is safe', etc.
    """
    for forbidden in FORBIDDEN_SAFETY_PHRASES:
        with pytest.raises(ValueError, match="forbidden"):
            RoadStatusSnapshot(
                road_segment_id="HYD-LOC-012",
                road_name=f"Corridor with {forbidden}",
                condition_state=RoadConditionState.NO_CURRENT_EVIDENCE,
                evidence_type=RoadEvidenceType.NO_EVIDENCE,
                last_status_update_utc="2026-10-27T12:00:00Z",
                freshness_category=RoadFreshnessCategory.UNKNOWN,
                verification_state=RoadVerificationState.UNMONITORED,
                uncertainty_level=UncertaintyLevel.HIGH,
                confidence_score=0.10,
            )


# =====================================================================
# 13. Expired Evidence Not Presented As Current
# =====================================================================

def test_expired_evidence_not_presented_as_current(road_service):
    """
    Evidence older than 360 minutes (> 6 hours) is EXPIRED and strictly excluded
    from establishing current road condition.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_obs = now_utc - timedelta(minutes=420)  # 7 hours old

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-013",
        community_reports=[
            {
                "report_id": "REP-EXP-01",
                "reporter_id_masked": "ANON-OLD-01",
                "observation_timestamp_utc": t_obs.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.EXPIRED
    assert snapshot.freshness_category == RoadFreshnessCategory.EXPIRED
    assert "OBSERVATION_EXPIRED_EXCLUDED" in snapshot.reason_codes
    assert snapshot.measured_water_depth_cm is None


# =====================================================================
# 14. Responder Verification Resolves Community Conflicts
# =====================================================================

def test_responder_verification_resolves_conflict(road_service):
    """
    When conflicting community reports exist, an on-site inspection by an
    authorized responder that occurs after the reports resolves the conflict.
    """
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    t_comm1 = now_utc - timedelta(minutes=45)
    t_comm2 = now_utc - timedelta(minutes=40)
    t_resp = now_utc - timedelta(minutes=15)  # Responder inspected AFTER conflicting reports

    inp = RoadStatusEvaluationInput(
        road_segment_id="HYD-LOC-014",
        community_reports=[
            {
                "report_id": "REP-C1",
                "reporter_id_masked": "ANON-C1",
                "observation_timestamp_utc": t_comm1.isoformat().replace("+00:00", "Z"),
                "reported_condition": "FLOODED_ROAD",
            },
            {
                "report_id": "REP-C2",
                "reporter_id_masked": "ANON-C2",
                "observation_timestamp_utc": t_comm2.isoformat().replace("+00:00", "Z"),
                "reported_condition": "DRY_ROAD_CLEAR",
            },
        ],
        field_observations=[
            {
                "observation_timestamp_utc": t_resp.isoformat().replace("+00:00", "Z"),
                "verification_status": "VERIFIED_BY_RESPONDER",
                "verifier_role": "GHMC_DRF_OFFICER",
                "verifier_id": "DRF-LEAD-01",
                "reported_condition": "WATERLOGGED_PASSABLE",
                "observed_depth_cm": 15.0,
                "verified_passability": "impassable_two_wheelers",
            }
        ]
    )

    snapshot = road_service.evaluate_road_status(inp, reference_time_utc=now_utc)

    assert snapshot.condition_state == RoadConditionState.VERIFIED_WATERLOGGED
    assert snapshot.has_conflicting_evidence is False
    assert "CONFLICT_RESOLVED_BY_RESPONDER_INSPECTION" in snapshot.reason_codes
    assert snapshot.measured_water_depth_cm == 15.0


# =====================================================================
# 15. FastAPI Endpoint Integration Tests
# =====================================================================

def test_api_road_status_evaluate_endpoint(test_client):
    """
    Tests POST /api/v1/road-status/evaluate endpoint.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "road_segment_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
        "community_reports": [
            {
                "report_id": "REP-API-01",
                "reporter_id_masked": "ANON-API-USER",
                "observation_timestamp_utc": now_iso,
                "reported_condition": "FLOODED_ROAD"
            }
        ],
        "rainfall_risk_category": "MEDIUM",
        "rainfall_risk_score": 0.45
    }

    resp = test_client.post("/api/v1/road-status/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["road_segment_id"] == "HYD-LOC-001"
    assert data["condition_state"] == "UNVERIFIED"
    assert "UNVERIFIED_COMMUNITY_REPORT" in data["reason_codes"]
    assert "ADVISORY ONLY" in data["safety_notice"]


def test_api_road_status_snapshot_endpoint(test_client):
    """
    Tests GET /api/v1/road-status/snapshot/{corridor_id} endpoint.
    """
    resp = test_client.get("/api/v1/road-status/snapshot/HYD-LOC-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["road_segment_id"] == "HYD-LOC-001"
    assert data["condition_state"] in [
        "NO_CURRENT_EVIDENCE", "UNVERIFIED", "CORROBORATED",
        "VERIFIED_PASSABLE", "VERIFIED_WATERLOGGED", "VERIFIED_IMPASSABLE"
    ]
    assert data["safety_notice"].startswith("ADVISORY ONLY")


# =====================================================================
# 16. All 20 Hyderabad Corridors Offline Snapshot Test
# =====================================================================

def test_all_corridors_offline_snapshot_execution(road_service):
    """
    Tests offline road status evaluation across all 20 Hyderabad pilot corridors.
    """
    snapshots = road_service.get_all_corridors_status()
    assert len(snapshots) == 20
    for snap in snapshots:
        assert snap.road_segment_id.startswith("HYD-LOC-")
        assert snap.condition_state in RoadConditionState
        assert snap.uncertainty_level in UncertaintyLevel
        assert snap.confidence_score <= 1.0
        assert "ADVISORY ONLY" in snap.safety_notice
