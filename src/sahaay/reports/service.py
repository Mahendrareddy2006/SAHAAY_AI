"""
Sahaay AI - Citizen Report Management & Verification Service
Handles report ingestion, privacy coarsening, near-duplicate clustering,
corroboration tracking, responder verification, and freshness expiry.
"""

import hashlib
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sahaay.hyderabad_risk.features import haversine_distance_m
from sahaay.reports.schemas import (
    CitizenReportRecord,
    CitizenReportSubmission,
    ReportFreshness,
    ReportValidationStatus,
    ReportVerificationRequest,
    ReportVerificationStatus,
    WaterDepthEstimate,
)

logger = logging.getLogger(__name__)

# Spatial threshold for near-duplicate reports (meters)
DUPLICATE_RADIUS_METERS = 100.0
# Temporal threshold for near-duplicate clustering (minutes)
DUPLICATE_WINDOW_MINUTES = 30.0

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


def calculate_freshness(submission_time_iso: str, reference_time_utc: Optional[datetime] = None) -> Tuple[ReportFreshness, float]:
    """
    Calculates elapsed time and categorical freshness relative to a reference time.
    """
    if reference_time_utc is None:
        reference_time_utc = datetime.now(timezone.utc)
    
    # Parse submission timestamp
    sub_dt = datetime.fromisoformat(submission_time_iso.replace("Z", "+00:00"))
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
    Service managing the citizen report lifecycle, verification, and corroboration.
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
        """
        if submission_time is None:
            submission_time = datetime.now(timezone.utc)

        sub_iso = submission_time.isoformat().replace("+00:00", "Z")
        reason_codes: List[str] = []

        # 1. Validation Checks
        if not submission.consent_given:
            logger.warning("Report rejected: Explicit consent not granted.")
            record = CitizenReportRecord(
                report_id=f"REP-{uuid.uuid4().hex[:8]}",
                corridor_id=submission.corridor_id,
                submission_timestamp_utc=sub_iso,
                latitude_coarsened=submission.latitude,
                longitude_coarsened=submission.longitude,
                location_precision_m=submission.location_precision_m,
                description_sanitized=submission.description.strip(),
                estimated_depth=submission.estimated_depth,
                reporter_id_masked="REJECTED_NO_CONSENT",
                privacy_redaction_applied=True,
                validation_status=ReportValidationStatus.SPAM_OR_MALFORMED,
                freshness=ReportFreshness.EXPIRED,
                reason_codes=["REJECTED_CONSENT_WITHHELD"],
            )
            return record

        # Coordinate bounding box check
        in_bounds = (17.15 <= submission.latitude <= 17.65) and (78.20 <= submission.longitude <= 78.70)
        val_status = ReportValidationStatus.VALID if in_bounds else ReportValidationStatus.INVALID_OUT_OF_BOUNDS
        if not in_bounds:
            reason_codes.append("OUT_OF_GHMC_BOUNDING_BOX")

        # 2. Privacy processing
        masked_reporter = mask_reporter_identity(submission.reporter_contact_raw)
        coarse_lat, coarse_lon = coarsen_coordinates(
            submission.latitude, submission.longitude, submission.location_precision_m
        )

        # 3. Deduplication Check
        report_id = f"REP-{uuid.uuid4().hex[:8]}"
        is_dup = False
        parent_id: Optional[str] = None

        for existing in self._db.values():
            if existing.corridor_id != submission.corridor_id:
                continue
            if existing.validation_status != ReportValidationStatus.VALID:
                continue

            # Check spatial distance
            dist_m = haversine_distance_m(
                submission.latitude, submission.longitude,
                existing.latitude_coarsened, existing.longitude_coarsened
            )

            # Check temporal gap
            _, age_gap_min = calculate_freshness(existing.submission_timestamp_utc, submission_time)

            # Same image hash indicates direct re-upload / duplicate
            same_image = (image_hash and existing.image_hash_dhash and image_hash == existing.image_hash_dhash)

            if (dist_m <= DUPLICATE_RADIUS_METERS and age_gap_min <= DUPLICATE_WINDOW_MINUTES) or same_image:
                is_dup = True
                parent_id = existing.report_id
                reason_codes.append(f"NEAR_DUPLICATE_OF_{parent_id}")
                
                # Update parent corroboration count if different reporter and valid
                if existing.reporter_id_masked != masked_reporter and not same_image:
                    existing.corroboration_count += 1
                    existing.linked_report_ids.append(report_id)
                    existing.reason_codes.append(f"CORROBORATED_BY_{masked_reporter}")
                else:
                    existing.reason_codes.append("DUPLICATE_SUBMISSION_SUPPRESSED")
                break

        if not is_dup:
            reason_codes.append("INITIAL_UNVERIFIED_COMMUNITY_REPORT")

        freshness, age_min = calculate_freshness(sub_iso, submission_time)

        record = CitizenReportRecord(
            report_id=report_id,
            corridor_id=submission.corridor_id,
            submission_timestamp_utc=sub_iso,
            latitude_coarsened=coarse_lat,
            longitude_coarsened=coarse_lon,
            location_precision_m=submission.location_precision_m,
            description_sanitized=submission.description.strip(),
            estimated_depth=submission.estimated_depth,
            image_reference=submission.image_reference,
            image_hash_dhash=image_hash,
            reporter_id_masked=masked_reporter,
            privacy_redaction_applied=True,
            validation_status=val_status,
            is_duplicate=is_dup,
            duplicate_of_report_id=parent_id,
            corroboration_count=1,
            linked_report_ids=[],
            verification_status=ReportVerificationStatus.UNVERIFIED,
            freshness=freshness,
            age_minutes=age_min,
            reason_codes=reason_codes,
        )

        self._db[report_id] = record
        logger.info(f"Ingested report {report_id} for {submission.corridor_id} (duplicate={is_dup})")
        return record

    def verify_report(self, report_id: str, request: ReportVerificationRequest) -> Optional[CitizenReportRecord]:
        """
        Updates the verification status of an existing report.
        """
        if report_id not in self._db:
            return None

        record = self._db[report_id]
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        record.verification_status = request.verification_status
        record.verified_by_entity = f"{request.verifier_role}:{request.verifier_id}"
        record.verification_timestamp_utc = now_iso

        if request.verification_status == ReportVerificationStatus.VERIFIED_BY_RESPONDER:
            record.reason_codes.append(f"VERIFIED_BY_{request.verifier_role}")
            if request.observed_depth_cm is not None:
                record.reason_codes.append(f"OBSERVED_DEPTH_{round(request.observed_depth_cm)}CM")
        elif request.verification_status == ReportVerificationStatus.REJECTED_FALSE_ALARM:
            record.reason_codes.append("RESPONDER_MARKED_FALSE_ALARM")

        return record

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

            # Update freshness dynamically
            freshness, age_min = calculate_freshness(record.submission_timestamp_utc, reference_time_utc)
            record.freshness = freshness
            record.age_minutes = age_min

            if age_min <= max_age_minutes and freshness != ReportFreshness.EXPIRED:
                active.append(record)

        # Sort newest first
        return sorted(active, key=lambda r: r.age_minutes)
