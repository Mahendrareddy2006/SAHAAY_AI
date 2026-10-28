"""
Sahaay AI - Citizen Report Management & Verification Service
Handles report ingestion, privacy coarsening, near-duplicate clustering,
corroboration tracking, responder verification, and freshness expiry.
"""

import hashlib
import logging
import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set

from sahaay.hyderabad_risk.features import haversine_distance_m
from sahaay.reports.schemas import (
    CitizenReportRecord,
    CitizenReportSubmission,
    ReportFreshness,
    ReportValidationStatus,
    ReportVerificationRequest,
    ReportVerificationStatus,
    WaterDepthEstimate,
    ReportCondition,
    SubmissionChannel,
    ConflictStatus,
    StatusTransitionEvent,
)

logger = logging.getLogger(__name__)

# Spatial threshold for near-duplicate reports (meters)
DUPLICATE_RADIUS_METERS = 100.0
# Temporal threshold for near-duplicate clustering (minutes)
DUPLICATE_WINDOW_MINUTES = 30.0

# Authorized reviewer roles permitted to transition reports to VERIFIED_BY_RESPONDER
AUTHORIZED_VERIFIER_ROLES = {
    "GHMC_DRF_OFFICER",
    "TRAFFIC_POLICE_DCP",
    "FIELD_RESEARCH_LEAD",
    "MUNICIPAL_ENGINEER",
    "AUTHORIZED_DISPATCHER",
}

# Hyderabad Metropolitan Area Bounding Box
HYDERABAD_METRO_BOUNDS = {
    "min_lat": 17.15,
    "max_lat": 17.65,
    "min_lon": 78.15,
    "max_lon": 78.70,
}

# In-memory thread-safe store for development & testing
# In production, this interfaces with PostgreSQL/PostGIS
_REPORT_DATABASE: Dict[str, CitizenReportRecord] = {}


def reset_report_database():
    """Resets the report store (primarily for unit test isolation)."""
    global _REPORT_DATABASE
    _REPORT_DATABASE.clear()


def mask_reporter_identity(contact: Optional[str]) -> str:
    """
    Masks user personal identifiers using one-way cryptographic hashing.
    Outputs a non-reversible pseudonymous identifier (e.g. 'ANON-7a9f2b8c').
    """
    if not contact:
        return f"ANON-{uuid.uuid4().hex[:8]}"
    h = hashlib.sha256(contact.strip().lower().encode("utf-8")).hexdigest()
    return f"ANON-{h[:8]}"


def coarsen_coordinates(lat: float, lon: float, precision_m: float) -> Tuple[float, float]:
    """
    Coarsens latitude and longitude to protect private residences.
    If precision radius is small (< 50m), rounds to 3 decimal places (~110m).
    """
    if precision_m < 50.0:
        return round(lat, 3), round(lon, 3)
    return round(lat, 4), round(lon, 4)


def calculate_freshness(timestamp_iso: str, reference_time_utc: Optional[datetime] = None) -> Tuple[ReportFreshness, float]:
    """
    Calculates elapsed time and categorical freshness relative to a reference time.
    """
    if reference_time_utc is None:
        reference_time_utc = datetime.now(timezone.utc)
    
    # Parse timestamp
    sub_dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    elapsed_seconds = max(0.0, (reference_time_utc - sub_dt).total_seconds())
    age_min = round(elapsed_seconds / 60.0, 1)

    if age_min <= 60.0:
        freshness = ReportFreshness.FRESH
    elif age_min <= 180.0:
        freshness = ReportFreshness.AGING
    elif age_min <= 360.0:
        freshness = ReportFreshness.STALE
    else:
        freshness = ReportFreshness.EXPIRED

    return freshness, age_min


class CitizenReportService:
    """
    Service managing citizen report lifecycle, verification, corroboration,
    freshness expiry, conflict detection, and auditable history.
    """

    def __init__(self, db: Optional[Dict[str, CitizenReportRecord]] = None):
        self._db = db if db is not None else _REPORT_DATABASE

    def submit_report(
        self,
        submission: CitizenReportSubmission,
        submission_time: Optional[datetime] = None,
        image_hash: Optional[str] = None
    ) -> CitizenReportRecord:
        """
        Validates, privacy-processes, deduplicates, and stores an incoming report.
        Strictly distinguishes observation time from submission time.
        """
        now_utc = datetime.now(timezone.utc)
        if submission_time is None:
            submission_time = now_utc

        sub_iso = submission_time.isoformat().replace("+00:00", "Z")
        reason_codes: List[str] = []

        # 1. Validation Checks
        if not submission.consent_given:
            logger.warning("Report rejected: Explicit consent not granted.")
            record = CitizenReportRecord(
                report_id=f"REP-{uuid.uuid4().hex[:8]}",
                corridor_id=submission.corridor_id,
                submission_timestamp_utc=sub_iso,
                observation_timestamp_utc=sub_iso,
                latitude_coarsened=submission.latitude,
                longitude_coarsened=submission.longitude,
                location_precision_m=submission.location_precision_m,
                description_sanitized=submission.description.strip(),
                estimated_depth=submission.estimated_depth,
                reported_condition=submission.reported_condition,
                submission_channel=submission.submission_channel,
                reporter_id_masked="REJECTED_NO_CONSENT",
                privacy_redaction_applied=True,
                validation_status=ReportValidationStatus.SPAM_OR_MALFORMED,
                verification_status=ReportVerificationStatus.REJECTED_INVALID,
                freshness=ReportFreshness.EXPIRED,
                reason_codes=["REJECTED_CONSENT_WITHHELD"],
            )
            return record

        # 2. Timestamp Validation (Observation vs Submission)
        obs_iso = sub_iso
        is_timestamp_malformed = False

        if submission.observation_time_utc:
            try:
                obs_dt = datetime.fromisoformat(submission.observation_time_utc.replace("Z", "+00:00"))
                # Future timestamp check
                if obs_dt > submission_time + timedelta(seconds=60):
                    reason_codes.append("OBSERVATION_TIME_AFTER_SUBMISSION")
                    is_timestamp_malformed = True
                elif obs_dt > now_utc + timedelta(seconds=60):
                    reason_codes.append("FUTURE_TIMESTAMP_REJECTED")
                    is_timestamp_malformed = True
                else:
                    obs_iso = obs_dt.isoformat().replace("+00:00", "Z")
            except Exception:
                reason_codes.append("INVALID_OBSERVATION_TIMESTAMP_FORMAT")
                is_timestamp_malformed = True

        if submission_time > now_utc + timedelta(seconds=60):
            reason_codes.append("FUTURE_SUBMISSION_TIMESTAMP_REJECTED")
            is_timestamp_malformed = True

        # Coordinate bounding box check (Hyderabad Metropolitan Region)
        in_bounds = (
            HYDERABAD_METRO_BOUNDS["min_lat"] <= submission.latitude <= HYDERABAD_METRO_BOUNDS["max_lat"]
            and HYDERABAD_METRO_BOUNDS["min_lon"] <= submission.longitude <= HYDERABAD_METRO_BOUNDS["max_lon"]
        )
        if not in_bounds:
            reason_codes.append("OUT_OF_GHMC_BOUNDING_BOX")

        if submission.location_precision_m > 100.0:
            reason_codes.append("IMPRECISE_LOCATION_PRECISION")

        # Determine validation status
        if is_timestamp_malformed:
            val_status = ReportValidationStatus.SPAM_OR_MALFORMED
        elif not in_bounds:
            val_status = ReportValidationStatus.INVALID_OUT_OF_BOUNDS
        else:
            val_status = ReportValidationStatus.VALID

        # 3. Privacy processing
        masked_reporter = mask_reporter_identity(submission.reporter_contact_raw)
        coarse_lat, coarse_lon = coarsen_coordinates(
            submission.latitude, submission.longitude, submission.location_precision_m
        )

        # 4. Deduplication & Corroboration Check
        report_id = f"REP-{uuid.uuid4().hex[:8]}"
        is_dup = False
        parent_id: Optional[str] = None

        for existing in self._db.values():
            if existing.corridor_id != submission.corridor_id:
                continue
            if existing.validation_status != ReportValidationStatus.VALID:
                continue
            if existing.is_duplicate:
                continue

            # Check spatial distance
            dist_m = haversine_distance_m(
                submission.latitude, submission.longitude,
                existing.latitude_coarsened, existing.longitude_coarsened
            )

            # Check temporal gap based on observation time
            _, age_gap_min = calculate_freshness(existing.observation_timestamp_utc, submission_time)

            # Same image hash indicates direct duplicate
            same_image = bool(image_hash and existing.image_hash_dhash and image_hash == existing.image_hash_dhash)

            if (dist_m <= DUPLICATE_RADIUS_METERS and age_gap_min <= DUPLICATE_WINDOW_MINUTES) or same_image:
                is_dup = True
                parent_id = existing.report_id
                reason_codes.append(f"NEAR_DUPLICATE_OF_{parent_id}")
                
                # Update parent corroboration count (raw volume)
                existing.corroboration_count += 1
                existing.linked_report_ids.append(report_id)

                # Independent source check: distinct masked reporter ID AND distinct image hash
                is_independent = (existing.reporter_id_masked != masked_reporter) and not same_image
                if is_independent and val_status == ReportValidationStatus.VALID:
                    existing.independent_sources_count += 1
                    existing.reason_codes.append(f"CORROBORATED_BY_{masked_reporter}")

                    # Promote to CORROBORATED if verified by >= 2 independent sources
                    if existing.independent_sources_count >= 2 and existing.verification_status == ReportVerificationStatus.UNVERIFIED:
                        old_st = existing.verification_status
                        existing.verification_status = ReportVerificationStatus.CORROBORATED
                        existing.status_history.append(
                            StatusTransitionEvent(
                                from_status=old_st,
                                to_status=ReportVerificationStatus.CORROBORATED,
                                transitioned_at_utc=sub_iso,
                                actor_id="SYSTEM",
                                actor_role="COMMUNITY_CORROBORATION_ENGINE",
                                rationale=(
                                    f"Automated corroboration: {existing.independent_sources_count} "
                                    "independent community sources confirmed condition."
                                ),
                                evidence_reference=report_id,
                            )
                        )
                else:
                    existing.reason_codes.append("DUPLICATE_SUBMISSION_SUPPRESSED")
                break

        if not is_dup:
            reason_codes.append("INITIAL_UNVERIFIED_COMMUNITY_REPORT")

        freshness, age_min = calculate_freshness(obs_iso, submission_time)

        # 5. Conflict Detection with active corridor reports
        conflict_status = ConflictStatus.NO_CONFLICT
        conflict_details = None

        if val_status == ReportValidationStatus.VALID:
            for existing in self._db.values():
                if existing.corridor_id != submission.corridor_id:
                    continue
                if existing.validation_status != ReportValidationStatus.VALID:
                    continue
                if existing.freshness == ReportFreshness.EXPIRED:
                    continue

                # Check for contradictory conditions within active window
                cond_a = submission.reported_condition
                cond_b = existing.reported_condition

                flood_like = {ReportCondition.FLOODED_ROAD, ReportCondition.WATERLOGGED_PASSABLE}
                dry_like = {ReportCondition.DRY_ROAD_CLEAR, ReportCondition.WET_ROAD_NO_FLOOD}

                if (cond_a in flood_like and cond_b in dry_like) or (cond_a in dry_like and cond_b in flood_like):
                    conflict_status = ConflictStatus.CONFLICTING_COMMUNITY_REPORTS
                    conflict_details = (
                        f"Contradictory conditions reported in corridor {submission.corridor_id}: "
                        f"{cond_a.value} (new) vs {cond_b.value} (existing {existing.report_id})."
                    )
                    reason_codes.append("CONFLICT_COMMUNITY_CONDITIONS")
                    existing.conflict_status = ConflictStatus.CONFLICTING_COMMUNITY_REPORTS
                    existing.conflict_details = conflict_details
                    if "CONFLICT_COMMUNITY_CONDITIONS" not in existing.reason_codes:
                        existing.reason_codes.append("CONFLICT_COMMUNITY_CONDITIONS")
                    break

        init_status = ReportVerificationStatus.UNVERIFIED if val_status == ReportValidationStatus.VALID else ReportVerificationStatus.REJECTED_INVALID

        record = CitizenReportRecord(
            report_id=report_id,
            corridor_id=submission.corridor_id,
            submission_timestamp_utc=sub_iso,
            observation_timestamp_utc=obs_iso,
            latitude_coarsened=coarse_lat,
            longitude_coarsened=coarse_lon,
            location_precision_m=submission.location_precision_m,
            description_sanitized=submission.description.strip(),
            estimated_depth=submission.estimated_depth,
            reported_condition=submission.reported_condition,
            submission_channel=submission.submission_channel,
            image_reference=submission.image_reference,
            image_hash_dhash=image_hash,
            evidence_reference=submission.evidence_reference,
            reporter_id_masked=masked_reporter,
            privacy_redaction_applied=True,
            validation_status=val_status,
            is_duplicate=is_dup,
            duplicate_of_report_id=parent_id,
            corroboration_count=1,
            independent_sources_count=1,
            linked_report_ids=[],
            verification_status=init_status,
            freshness=freshness,
            age_minutes=age_min,
            reason_codes=reason_codes,
            conflict_status=conflict_status,
            conflict_details=conflict_details,
            status_history=[
                StatusTransitionEvent(
                    from_status=ReportVerificationStatus.UNVERIFIED,
                    to_status=init_status,
                    transitioned_at_utc=sub_iso,
                    actor_id=masked_reporter,
                    actor_role="CITIZEN_REPORTER",
                    rationale="Initial structured community submission.",
                    evidence_reference=submission.evidence_reference,
                )
            ]
        )

        self._db[report_id] = record
        logger.info(f"Ingested report {report_id} for {submission.corridor_id} (duplicate={is_dup}, status={init_status})")
        return record

    def transition_status(
        self,
        report_id: str,
        new_status: ReportVerificationStatus,
        actor_id: str,
        actor_role: str,
        rationale: str,
        evidence_reference: Optional[str] = None,
        observed_depth_cm: Optional[float] = None
    ) -> CitizenReportRecord:
        """
        Auditable state transition enforcement.
        Validates authorization roles, legal state transitions, and records history.
        """
        if report_id not in self._db:
            raise KeyError(f"Report ID '{report_id}' not found in database.")

        record = self._db[report_id]
        old_status = record.verification_status

        # 1. Authorization Role Check for Verification
        if new_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER:
            if actor_role not in AUTHORIZED_VERIFIER_ROLES:
                raise PermissionError(
                    f"Role '{actor_role}' is not authorized to set status to VERIFIED_BY_RESPONDER. "
                    f"Authorized roles are: {sorted(list(AUTHORIZED_VERIFIER_ROLES))}."
                )
            if not rationale or not rationale.strip():
                raise ValueError("Verification requires an explicit, non-empty rationale.")

        # 2. State Machine Rules
        # Prohibit verifying expired reports directly without fresh physical inspection
        if old_status == ReportFreshness.EXPIRED and new_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER:
            raise ValueError(
                f"Cannot verify expired report {report_id}. Expired observations must be freshly re-surveyed."
            )

        # Prohibit unverified directly becoming verified if marked invalid
        if record.validation_status != ReportValidationStatus.VALID and new_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER:
            raise ValueError(
                f"Cannot verify invalid report {report_id} (validation_status={record.validation_status.value})."
            )

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 3. Apply state transition
        record.verification_status = new_status
        record.verified_by_entity = f"{actor_role}:{actor_id}"
        record.verification_timestamp_utc = now_iso
        record.verification_rationale = rationale
        record.evidence_provenance = evidence_reference

        if observed_depth_cm is not None:
            record.reason_codes.append(f"OBSERVED_DEPTH_{round(observed_depth_cm)}CM")

        if new_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER:
            record.reason_codes.append(f"VERIFIED_BY_{actor_role}")
        elif new_status == ReportVerificationStatus.REJECTED_FALSE_ALARM:
            record.reason_codes.append("RESPONDER_MARKED_FALSE_ALARM")
        elif new_status == ReportVerificationStatus.REJECTED_INVALID:
            record.reason_codes.append("MARKED_REJECTED_INVALID")

        # Record auditable transition event
        event = StatusTransitionEvent(
            from_status=old_status,
            to_status=new_status,
            transitioned_at_utc=now_iso,
            actor_id=actor_id,
            actor_role=actor_role,
            rationale=rationale,
            evidence_reference=evidence_reference,
        )
        record.status_history.append(event)
        logger.info(f"Transitioned report {report_id}: {old_status.value} -> {new_status.value} by {actor_role}")
        return record

    def verify_report(self, report_id: str, request: ReportVerificationRequest) -> Optional[CitizenReportRecord]:
        """
        Legacy/backward-compatible wrapper for verification requests.
        """
        if report_id not in self._db:
            return None

        return self.transition_status(
            report_id=report_id,
            new_status=request.verification_status,
            actor_id=request.verifier_id,
            actor_role=request.verifier_role,
            rationale=request.verification_notes,
            evidence_reference=request.evidence_reference,
            observed_depth_cm=request.observed_depth_cm,
        )

    def get_active_reports_for_corridor(
        self,
        corridor_id: str,
        reference_time_utc: Optional[datetime] = None,
        max_age_minutes: float = 180.0,
        include_duplicates: bool = False
    ) -> List[CitizenReportRecord]:
        """
        Retrieves active, non-expired, validated reports for a corridor.
        Updates freshness dynamically relative to reference_time_utc.
        """
        active: List[CitizenReportRecord] = []

        for record in self._db.values():
            if record.corridor_id != corridor_id:
                continue
            if record.validation_status != ReportValidationStatus.VALID:
                continue
            if not include_duplicates and record.is_duplicate:
                continue

            # Update freshness dynamically based on observation timestamp
            freshness, age_min = calculate_freshness(record.observation_timestamp_utc, reference_time_utc)
            record.freshness = freshness
            record.age_minutes = age_min

            if age_min <= max_age_minutes and freshness != ReportFreshness.EXPIRED:
                active.append(record)

        # Sort newest first
        return sorted(active, key=lambda r: r.age_minutes)

    def evaluate_corridor_community_evidence(
        self,
        corridor_id: str,
        reference_time_utc: Optional[datetime] = None,
        max_age_minutes: float = 180.0
    ) -> Dict[str, Any]:
        """
        Synthesizes community reports for decision support.
        Strict Safety Invariants:
        1. Missing reports must NEVER be interpreted as evidence of road safety.
        2. Report volume alone does NOT establish ground truth.
        3. Never infer official road closure or measured water depth from citizen reports.
        """
        active_reports = self.get_active_reports_for_corridor(
            corridor_id=corridor_id,
            reference_time_utc=reference_time_utc,
            max_age_minutes=max_age_minutes,
            include_duplicates=True
        )

        # Safety Invariant: Absence of reports does NOT declare safety
        if not active_reports:
            return {
                "corridor_id": corridor_id,
                "has_active_reports": False,
                "active_reports_count": 0,
                "independent_sources_count": 0,
                "corroboration_volume": 0,
                "evidence_status": "NO_COMMUNITY_REPORTS_AVAILABLE",
                "is_safe_declaration": False,
                "safety_notice": "Absence of community reports does not indicate safe road conditions. Unmonitored corridor.",
                "has_conflict": False,
                "is_verified_by_responder": False,
                "requires_human_verification": False,
            }

        unique_reporters = {r.reporter_id_masked for r in active_reports}
        verified_reports = [
            r for r in active_reports if r.verification_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER
        ]
        conflicting_reports = [
            r for r in active_reports if r.conflict_status == ConflictStatus.CONFLICTING_COMMUNITY_REPORTS
        ]

        has_conflict = len(conflicting_reports) > 0
        is_verified = len(verified_reports) > 0

        # Determine evidence status
        if has_conflict:
            evidence_status = "INCONCLUSIVE_CONTRADICTORY"
        elif is_verified:
            evidence_status = "OBSERVED_VERIFIED_BY_RESPONDER"
        elif len(unique_reporters) >= 2:
            evidence_status = "CORROBORATED_COMMUNITY_EVIDENCE"
        else:
            evidence_status = "UNVERIFIED_SINGLE_SOURCE"

        return {
            "corridor_id": corridor_id,
            "has_active_reports": True,
            "active_reports_count": len(active_reports),
            "independent_sources_count": len(unique_reporters),
            "corroboration_volume": len(active_reports),
            "evidence_status": evidence_status,
            "is_safe_declaration": False,
            "safety_notice": "Community reports are advisory inputs, not autonomous proof of inundation or passability.",
            "has_conflict": has_conflict,
            "is_verified_by_responder": is_verified,
            "verified_report_ids": [r.report_id for r in verified_reports],
            "requires_human_verification": not is_verified or has_conflict,
        }
