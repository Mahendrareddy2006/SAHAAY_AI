"""
Sahaay AI - Phase 15: Community Verification Test Suite
(tests/test_phase15_community_verification.py)

Tests:
1. Structured report intake validating observation time vs submission time.
2. Rejection of observation time occurring after submission time.
3. Rejection of future timestamps.
4. Out-of-bounds coordinate handling (GHMC bounding box).
5. Quarantine of submissions lacking explicit consent.
6. Privacy masking of reporter contact info and coordinate coarsening.
7. Unverified default state invariant (submission is NOT automatic proof of flood).
8. Corroboration distinct from raw volume (multiple submissions from same reporter vs independent sources).
9. Role-based verification access control (rejection of unauthorized verifiers).
10. Authorized responder verification workflow with auditable history trail.
11. State machine rules (prohibiting verification of expired reports).
12. Freshness calculation and dynamic aging (fresh, aging, stale, expired).
13. Conflict detection across active corridor reports (opposing conditions).
14. Corridor evidence synthesis: absence of reports must NOT be interpreted as safe.
15. Subjective depth estimate decoupling invariant (never treated as measured ground truth).
"""

from datetime import datetime, timezone, timedelta
import pytest

from sahaay.reports.schemas import (
    CitizenReportSubmission,
    CitizenReportRecord,
    ReportFreshness,
    ReportValidationStatus,
    ReportVerificationRequest,
    ReportVerificationStatus,
    ReportCondition,
    SubmissionChannel,
    ConflictStatus,
    WaterDepthEstimate,
    StatusTransitionEvent,
)
from sahaay.reports.service import (
    CitizenReportService,
    AUTHORIZED_VERIFIER_ROLES,
    HYDERABAD_METRO_BOUNDS,
    calculate_freshness,
    coarsen_coordinates,
    mask_reporter_identity,
    reset_report_database,
)


@pytest.fixture(autouse=True)
def clean_db():
    reset_report_database()
    yield
    reset_report_database()


# =====================================================================
# 1. Structured Intake & Timestamp Validation Tests
# =====================================================================

def test_intake_observation_distinct_from_submission():
    """Observation timestamp is captured separately from submission timestamp."""
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)
    t_obs = now_utc - timedelta(minutes=25)
    t_sub = now_utc - timedelta(minutes=5)

    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        location_precision_m=20.0,
        description="Water pooling near flyover pillars.",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        submission_channel=SubmissionChannel.MOBILE_APP,
        observation_time_utc=t_obs.isoformat(),
        consent_given=True,
    )
    rec = service.submit_report(sub, submission_time=t_sub)

    assert rec.validation_status == ReportValidationStatus.VALID
    assert rec.observation_timestamp_utc == t_obs.isoformat().replace("+00:00", "Z")
    assert rec.submission_timestamp_utc == t_sub.isoformat().replace("+00:00", "Z")
    assert rec.observation_timestamp_utc != rec.submission_timestamp_utc


def test_intake_rejection_of_observation_after_submission():
    """Reports where observation time is in the future relative to submission time must be flagged."""
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)
    t_obs = now_utc + timedelta(minutes=15)  # After submission!
    t_sub = now_utc

    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Time-traveling flood observation.",
        observation_time_utc=t_obs.isoformat(),
        consent_given=True,
    )
    rec = service.submit_report(sub, submission_time=t_sub)

    assert rec.validation_status == ReportValidationStatus.SPAM_OR_MALFORMED
    assert "OBSERVATION_TIME_AFTER_SUBMISSION" in rec.reason_codes


def test_intake_rejection_of_future_submission_timestamp():
    """Reports with submission timestamp in the future must be rejected."""
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)
    future_sub = now_utc + timedelta(hours=2)

    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Premature submission.",
        consent_given=True,
    )
    rec = service.submit_report(sub, submission_time=future_sub)

    assert rec.validation_status == ReportValidationStatus.SPAM_OR_MALFORMED
    assert "FUTURE_SUBMISSION_TIMESTAMP_REJECTED" in rec.reason_codes


def test_intake_out_of_bounds_rejection():
    """Submissions outside the Hyderabad metropolitan boundary are flagged as out of bounds."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-OUT",
        latitude=17.0500,  # Outside Hyderabad metropolitan boundary (min_lat 17.15)
        longitude=78.1200,  # Outside boundary (min_lon 78.15)
        description="Report outside Hyderabad metropolitan boundary.",
        consent_given=True,
    )
    rec = service.submit_report(sub)

    assert rec.validation_status == ReportValidationStatus.INVALID_OUT_OF_BOUNDS
    assert "OUT_OF_GHMC_BOUNDING_BOX" in rec.reason_codes
    assert rec.verification_status == ReportVerificationStatus.REJECTED_INVALID


def test_intake_missing_consent_quarantined():
    """Submissions without explicit consent are quarantined and reporter identity unrecorded."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Report without consent.",
        reporter_contact_raw="+91-9876543210",
        consent_given=False,
    )
    rec = service.submit_report(sub)

    assert rec.validation_status == ReportValidationStatus.SPAM_OR_MALFORMED
    assert rec.reporter_id_masked == "REJECTED_NO_CONSENT"
    assert "REJECTED_CONSENT_WITHHELD" in rec.reason_codes


# =====================================================================
# 2. Privacy & De-Identification Tests
# =====================================================================

def test_privacy_masking_and_coordinate_coarsening():
    """Raw contact is cryptographically hashed and precise coordinates are coarsened."""
    raw_contact = "resident_tolichowki@gmail.com"
    masked = mask_reporter_identity(raw_contact)
    assert masked.startswith("ANON-")
    assert raw_contact not in masked

    lat, lon = 17.398421, 78.414592
    c_lat, c_lon = coarsen_coordinates(lat, lon, precision_m=20.0)
    assert c_lat == 17.398
    assert c_lon == 78.415


# =====================================================================
# 3. Unverified Default State & Safety Invariant Tests
# =====================================================================

def test_unverified_default_state_invariant():
    """A submitted report enters strictly as UNVERIFIED; never automatic proof of flooding."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-002",
        latitude=17.4095,
        longitude=78.3986,
        description="Water visible on Shaikpet main road.",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        consent_given=True,
    )
    rec = service.submit_report(sub)

    assert rec.verification_status == ReportVerificationStatus.UNVERIFIED
    assert rec.verified_by_entity is None
    assert "INITIAL_UNVERIFIED_COMMUNITY_REPORT" in rec.reason_codes


def test_subjective_depth_estimate_decoupling_invariant():
    """Community water depth is strictly a subjective estimate, not measured telemetry."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-002",
        latitude=17.4095,
        longitude=78.3986,
        description="Water seems knee deep to pedestrian.",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        consent_given=True,
    )
    rec = service.submit_report(sub)

    assert rec.estimated_depth == WaterDepthEstimate.KNEE_DEEP
    # Verified by responder has not happened; depth cannot be treated as official
    assert rec.verification_status != ReportVerificationStatus.VERIFIED_BY_RESPONDER


# =====================================================================
# 4. Corroboration vs Volume Separation Tests
# =====================================================================

def test_corroboration_distinct_from_raw_volume():
    """
    Submissions from the SAME reporter increment raw report volume, but NOT independent sources.
    Only submissions from DIFFERENT reporters advance status to CORROBORATED.
    """
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)
    t0 = now_utc - timedelta(minutes=20)

    # Report 1: Volunteer Alpha
    sub1 = CitizenReportSubmission(
        corridor_id="HYD-LOC-003",
        latitude=17.3688,
        longitude=78.5042,
        location_precision_m=20.0,
        description="Musi causeway water rising near guard rail.",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        reporter_contact_raw="volunteer_alpha@ngo.org",
        consent_given=True,
    )
    rec1 = service.submit_report(sub1, submission_time=t0)
    assert rec1.corroboration_count == 1
    assert rec1.independent_sources_count == 1
    assert rec1.verification_status == ReportVerificationStatus.UNVERIFIED

    # Report 2: Same volunteer Alpha submits again (near-duplicate)
    sub2 = CitizenReportSubmission(
        corridor_id="HYD-LOC-003",
        latitude=17.3689,
        longitude=78.5043,
        location_precision_m=20.0,
        description="Still rising at causeway.",
        estimated_depth=WaterDepthEstimate.ANKLE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        reporter_contact_raw="volunteer_alpha@ngo.org",  # Same reporter!
        consent_given=True,
    )
    rec2 = service.submit_report(sub2, submission_time=t0 + timedelta(minutes=2))
    assert rec2.is_duplicate is True
    parent = service._db[rec1.report_id]
    # Raw volume incremented, but independent sources count remained 1!
    assert parent.corroboration_count == 2
    assert parent.independent_sources_count == 1
    assert parent.verification_status == ReportVerificationStatus.UNVERIFIED

    # Report 3: Volunteer Beta (Independent source) submits
    sub3 = CitizenReportSubmission(
        corridor_id="HYD-LOC-003",
        latitude=17.3687,
        longitude=78.5041,
        location_precision_m=20.0,
        description="Confirming water overflowing at Moosarambagh causeway.",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        reporter_contact_raw="volunteer_beta@traffic.in",  # Different reporter!
        consent_given=True,
    )
    rec3 = service.submit_report(sub3, submission_time=t0 + timedelta(minutes=5))
    parent = service._db[rec1.report_id]
    # Independent sources incremented to 2 -> Automated promotion to CORROBORATED!
    assert parent.corroboration_count == 3
    assert parent.independent_sources_count == 2
    assert parent.verification_status == ReportVerificationStatus.CORROBORATED
    # Verified transition event logged in history
    assert any(ev.to_status == ReportVerificationStatus.CORROBORATED for ev in parent.status_history)


# =====================================================================
# 5. Role-Based Verification Access Control & Auditability Tests
# =====================================================================

def test_unauthorized_verifier_role_rejected():
    """Attempting verification with an unauthorized role raises PermissionError."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Pooling water.",
        consent_given=True,
    )
    rec = service.submit_report(sub)

    with pytest.raises(PermissionError, match="not authorized to set status to VERIFIED_BY_RESPONDER"):
        service.transition_status(
            report_id=rec.report_id,
            new_status=ReportVerificationStatus.VERIFIED_BY_RESPONDER,
            actor_id="USER-PUBLIC-101",
            actor_role="CITIZEN_REPORTER",  # Unauthorized role
            rationale="I am sure it is flooded.",
        )


def test_authorized_responder_verification_with_audit_trail():
    """Authorized municipal responder successfully verifies report with complete audit history."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Significant ponding at underpass.",
        consent_given=True,
    )
    rec = service.submit_report(sub)

    verified_rec = service.transition_status(
        report_id=rec.report_id,
        new_status=ReportVerificationStatus.VERIFIED_BY_RESPONDER,
        actor_id="DRF-OFFICER-72",
        actor_role="GHMC_DRF_OFFICER",  # Authorized role
        rationale="DRF Unit 12 on site; confirmed 20cm inundation over 40m stretch.",
        evidence_reference="DISPATCH-LOG-GHMC-2026-881",
        observed_depth_cm=20.0,
    )

    assert verified_rec.verification_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER
    assert verified_rec.verified_by_entity == "GHMC_DRF_OFFICER:DRF-OFFICER-72"
    assert "VERIFIED_BY_GHMC_DRF_OFFICER" in verified_rec.reason_codes
    assert "OBSERVED_DEPTH_20CM" in verified_rec.reason_codes
    # Audit trail verification
    assert len(verified_rec.status_history) >= 2
    latest_event = verified_rec.status_history[-1]
    assert latest_event.to_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER
    assert latest_event.actor_role == "GHMC_DRF_OFFICER"
    assert latest_event.evidence_reference == "DISPATCH-LOG-GHMC-2026-881"


def test_prohibited_transition_from_expired_to_verified():
    """Expired reports cannot be directly verified; fresh field survey required."""
    service = CitizenReportService()
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-001",
        latitude=17.3984,
        longitude=78.4145,
        description="Water was high earlier.",
        consent_given=True,
    )
    rec = service.submit_report(sub)
    # Manually mark as expired
    rec.verification_status = ReportFreshness.EXPIRED

    with pytest.raises(ValueError, match="Cannot verify expired report"):
        service.transition_status(
            report_id=rec.report_id,
            new_status=ReportVerificationStatus.VERIFIED_BY_RESPONDER,
            actor_id="DRF-OFFICER-72",
            actor_role="GHMC_DRF_OFFICER",
            rationale="Trying to verify old report.",
        )


# =====================================================================
# 6. Freshness & Dynamic Aging Tests
# =====================================================================

def test_freshness_lifecycle_and_expiration():
    """Tests categorical freshness degradation over time."""
    now_utc = datetime.now(timezone.utc)

    # 30 minutes old -> FRESH
    t_fresh = (now_utc - timedelta(minutes=30)).isoformat()
    f_fresh, age_fresh = calculate_freshness(t_fresh, now_utc)
    assert f_fresh == ReportFreshness.FRESH
    assert 29.0 <= age_fresh <= 31.0

    # 120 minutes old -> AGING
    t_aging = (now_utc - timedelta(minutes=120)).isoformat()
    f_aging, age_aging = calculate_freshness(t_aging, now_utc)
    assert f_aging == ReportFreshness.AGING

    # 240 minutes old -> STALE
    t_stale = (now_utc - timedelta(minutes=240)).isoformat()
    f_stale, age_stale = calculate_freshness(t_stale, now_utc)
    assert f_stale == ReportFreshness.STALE

    # 400 minutes old -> EXPIRED
    t_expired = (now_utc - timedelta(minutes=400)).isoformat()
    f_expired, age_expired = calculate_freshness(t_expired, now_utc)
    assert f_expired == ReportFreshness.EXPIRED


# =====================================================================
# 7. Conflict Detection Tests
# =====================================================================

def test_conflict_detection_opposing_conditions():
    """Detects when reports in the same active corridor assert contradictory conditions."""
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)

    # Report A: Flooded road
    sub_a = CitizenReportSubmission(
        corridor_id="HYD-LOC-004",
        latitude=17.4401,
        longitude=78.3489,
        location_precision_m=30.0,
        description="Gachibowli junction inundated, waist deep.",
        estimated_depth=WaterDepthEstimate.WAIST_DEEP_OR_MORE,
        reported_condition=ReportCondition.FLOODED_ROAD,
        consent_given=True,
    )
    rec_a = service.submit_report(sub_a, submission_time=now_utc - timedelta(minutes=15))

    # Report B: Dry road
    sub_b = CitizenReportSubmission(
        corridor_id="HYD-LOC-004",
        latitude=17.4402,
        longitude=78.3490,
        location_precision_m=30.0,
        description="Gachibowli junction is clear and totally dry.",
        estimated_depth=WaterDepthEstimate.PUDDLE_SURFACE_WET,
        reported_condition=ReportCondition.DRY_ROAD_CLEAR,
        consent_given=True,
    )
    rec_b = service.submit_report(sub_b, submission_time=now_utc - timedelta(minutes=10))

    assert rec_b.conflict_status == ConflictStatus.CONFLICTING_COMMUNITY_REPORTS
    assert "CONFLICT_COMMUNITY_CONDITIONS" in rec_b.reason_codes
    assert "CONFLICT_COMMUNITY_CONDITIONS" in rec_a.reason_codes


# =====================================================================
# 8. Corridor Evidence Synthesis Safety Invariant Tests
# =====================================================================

def test_corridor_evidence_missing_reports_not_safe():
    """Absence of community reports must NEVER be interpreted as road safety."""
    service = CitizenReportService()
    eval_res = service.evaluate_corridor_community_evidence(corridor_id="HYD-LOC-UNREPORTED")

    assert eval_res["has_active_reports"] is False
    assert eval_res["evidence_status"] == "NO_COMMUNITY_REPORTS_AVAILABLE"
    assert eval_res["is_safe_declaration"] is False
    assert "Unmonitored corridor" in eval_res["safety_notice"]


def test_corridor_evidence_conflicting_reports_requires_human_verification():
    """Corridor with contradictory reports triggers INCONCLUSIVE_CONTRADICTORY and requires human verification."""
    service = CitizenReportService()
    now_utc = datetime.now(timezone.utc)

    sub_flood = CitizenReportSubmission(
        corridor_id="HYD-LOC-005",
        latitude=17.3768,
        longitude=78.4975,
        description="Underpass flooded.",
        reported_condition=ReportCondition.FLOODED_ROAD,
        consent_given=True,
    )
    service.submit_report(sub_flood, submission_time=now_utc)

    sub_dry = CitizenReportSubmission(
        corridor_id="HYD-LOC-005",
        latitude=17.3769,
        longitude=78.4976,
        description="Underpass dry.",
        reported_condition=ReportCondition.DRY_ROAD_CLEAR,
        consent_given=True,
    )
    service.submit_report(sub_dry, submission_time=now_utc)

    eval_res = service.evaluate_corridor_community_evidence(corridor_id="HYD-LOC-005", reference_time_utc=now_utc)
    assert eval_res["has_conflict"] is True
    assert eval_res["evidence_status"] == "INCONCLUSIVE_CONTRADICTORY"
    assert eval_res["requires_human_verification"] is True
    assert eval_res["is_safe_declaration"] is False
