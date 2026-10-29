"""
Sahaay AI - Phase 16: Live Road Status Service & Evidence Fusion Engine
Implements offline evaluation of road conditions, timestamp hygiene, freshness decay,
conflict resolution, corroboration tracking, and non-autonomous safety invariants.
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

import pandas as pd

from sahaay.reports.schemas import (
    CitizenReportRecord,
    ReportFreshness,
    ReportValidationStatus,
    ReportVerificationStatus,
    ReportCondition,
    SubmissionChannel,
    ConflictStatus,
)
from sahaay.reports.service import CitizenReportService
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    EvidenceProvenanceRecord,
    RoadStatusSnapshot,
    RoadStatusEvaluationInput,
    MANDATORY_ROAD_SAFETY_NOTICE,
)

logger = logging.getLogger(__name__)

# Proposed Freshness Policy Thresholds (documented for institutional review & approval)
COMMUNITY_REPORT_FRESH_MINUTES = 60.0
COMMUNITY_REPORT_AGING_MINUTES = 180.0
COMMUNITY_REPORT_STALE_MINUTES = 360.0
COMMUNITY_REPORT_EXPIRY_MINUTES = 360.0

RESPONDER_VERIFICATION_FRESH_MINUTES = 120.0
RESPONDER_VERIFICATION_AGING_MINUTES = 240.0
RESPONDER_VERIFICATION_STALE_MINUTES = 480.0
RESPONDER_VERIFICATION_EXPIRY_MINUTES = 480.0

TELEMETRY_FRESH_MINUTES = 15.0
TELEMETRY_AGING_MINUTES = 60.0
TELEMETRY_STALE_MINUTES = 120.0
TELEMETRY_EXPIRY_MINUTES = 120.0


def parse_iso_utc(ts: Optional[str]) -> Optional[datetime]:
    """Safely parses an ISO-8601 string into a UTC-aware datetime object."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def calculate_evidence_freshness(
    obs_time_iso: Optional[str],
    reference_time_utc: Optional[datetime] = None,
    is_responder: bool = False,
    is_telemetry: bool = False,
) -> Tuple[RoadFreshnessCategory, Optional[float]]:
    """
    Calculates elapsed age in minutes and categorical freshness relative to physical observation time.
    """
    if reference_time_utc is None:
        reference_time_utc = datetime.now(timezone.utc)

    obs_dt = parse_iso_utc(obs_time_iso)
    if obs_dt is None:
        return RoadFreshnessCategory.UNKNOWN, None

    elapsed_seconds = max(0.0, (reference_time_utc - obs_dt).total_seconds())
    age_min = round(elapsed_seconds / 60.0, 1)

    if is_responder:
        fresh_thr = RESPONDER_VERIFICATION_FRESH_MINUTES
        aging_thr = RESPONDER_VERIFICATION_AGING_MINUTES
        stale_thr = RESPONDER_VERIFICATION_STALE_MINUTES
    elif is_telemetry:
        fresh_thr = TELEMETRY_FRESH_MINUTES
        aging_thr = TELEMETRY_AGING_MINUTES
        stale_thr = TELEMETRY_STALE_MINUTES
    else:
        fresh_thr = COMMUNITY_REPORT_FRESH_MINUTES
        aging_thr = COMMUNITY_REPORT_AGING_MINUTES
        stale_thr = COMMUNITY_REPORT_STALE_MINUTES

    if age_min <= fresh_thr:
        freshness = RoadFreshnessCategory.FRESH
    elif age_min <= aging_thr:
        freshness = RoadFreshnessCategory.AGING
    elif age_min <= stale_thr:
        freshness = RoadFreshnessCategory.STALE
    else:
        freshness = RoadFreshnessCategory.EXPIRED

    return freshness, age_min


class LiveRoadStatusService:
    """
    Offline Live Road Status evaluation service.
    Implements multi-source evidence fusion, non-silent missingness,
    timestamp hygiene, and fail-closed safety policies.
    """

    def __init__(
        self,
        report_service: Optional[CitizenReportService] = None,
        corridors_csv_path: Optional[str] = "data/hyderabad_risk/derived/hyderabad_risk_features.csv",
    ):
        self._report_service = report_service if report_service is not None else CitizenReportService()
        self._corridors_csv_path = Path(corridors_csv_path) if corridors_csv_path else None
        self._corridor_features_cache: Dict[str, Dict[str, Any]] = {}
        self._load_corridor_features()

    def _load_corridor_features(self):
        """Loads static Hyderabad corridor baseline features if available."""
        if self._corridors_csv_path and self._corridors_csv_path.exists():
            try:
                df = pd.read_csv(self._corridors_csv_path)
                for row in df.to_dict(orient="records"):
                    cid = str(row.get("location_id", "")).strip()
                    if cid:
                        self._corridor_features_cache[cid] = row
            except Exception as e:
                logger.warning(f"Could not load corridor features cache: {e}")

    def evaluate_road_status(
        self,
        input_data: RoadStatusEvaluationInput,
        reference_time_utc: Optional[datetime] = None,
    ) -> RoadStatusSnapshot:
        """
        Pure, deterministic evidence fusion engine evaluating road condition state.
        Adheres to non-autonomous safety invariants:
        - Absence of observations NEVER yields DRY or SAFE.
        - Rainfall or vulnerability alone NEVER yields road inundation.
        - Observation time (not ingestion time) dictates freshness.
        - Unverified community reports NEVER declare measured depth or passability.
        - Conflicting reports produce CONFLICTING status until authorized resolution.
        """
        now_utc = reference_time_utc if reference_time_utc is not None else datetime.now(timezone.utc)
        now_iso = now_utc.isoformat().replace("+00:00", "Z")

        # Resolve corridor metadata from cache if not provided in input
        loc_id = input_data.road_segment_id
        meta = self._corridor_features_cache.get(loc_id, {})
        road_name = input_data.road_name or meta.get("corridor_name") or f"Road Corridor {loc_id}"
        corridor_zone = input_data.corridor_zone or meta.get("zone")
        lat = input_data.latitude if input_data.latitude is not None else meta.get("latitude")
        lon = input_data.longitude if input_data.longitude is not None else meta.get("longitude")

        # Environmental & Vulnerability baselines
        rain_cat = input_data.rainfall_risk_category or meta.get("rainfall_risk_category", "UNKNOWN")
        rain_score = float(input_data.rainfall_risk_score if input_data.rainfall_risk_score is not None else meta.get("rainfall_risk_score", 0.0))
        vuln_cat = input_data.vulnerability_category or meta.get("vulnerability_category", "UNKNOWN")
        vuln_index = float(input_data.vulnerability_index if input_data.vulnerability_index is not None else meta.get("vulnerability_index", 0.0))

        reason_codes: List[str] = []
        provenance_records: List[EvidenceProvenanceRecord] = []

        # -------------------------------------------------------------
        # 1. Ingest, Filter, and Validate Community & Field Observations
        # -------------------------------------------------------------
        valid_reports: List[Dict[str, Any]] = []
        has_future_timestamp = False
        has_malformed_timestamp = False
        has_delayed_submission = False

        raw_items = list(input_data.community_reports) + list(input_data.field_observations)

        for item in raw_items:
            # Check synthetic segregation
            if item.get("is_synthetic") is True or item.get("is_synthetic_or_simulated") is True:
                reason_codes.append("SYNTHETIC_EVIDENCE_EXCLUDED")
                continue

            # Extract timestamps
            obs_iso = item.get("observation_timestamp_utc") or item.get("observation_time_utc")
            sub_iso = item.get("submission_timestamp_utc") or item.get("ingestion_timestamp_utc") or now_iso

            obs_dt = parse_iso_utc(obs_iso)
            sub_dt = parse_iso_utc(sub_iso)

            # Check timestamp formatting
            if obs_iso and obs_dt is None:
                has_malformed_timestamp = True
                reason_codes.append("MALFORMED_TIMESTAMP_REJECTED")
                continue

            # Check future timestamps
            if obs_dt and obs_dt > now_utc + timedelta(seconds=60):
                has_future_timestamp = True
                reason_codes.append("FUTURE_TIMESTAMP_REJECTED")
                continue

            if sub_dt and sub_dt > now_utc + timedelta(seconds=60):
                has_future_timestamp = True
                reason_codes.append("FUTURE_SUBMISSION_TIMESTAMP_REJECTED")
                continue

            # Check observation after submission
            if obs_dt and sub_dt and obs_dt > sub_dt + timedelta(seconds=60):
                reason_codes.append("OBSERVATION_TIME_AFTER_SUBMISSION")
                continue

            # Check delayed submission
            if obs_dt and sub_dt:
                time_lag_sec = (sub_dt - obs_dt).total_seconds()
                if time_lag_sec > 1800.0:  # > 30 min submission delay
                    has_delayed_submission = True

            clean_item = dict(item)
            clean_item["_obs_dt"] = obs_dt
            clean_item["_sub_dt"] = sub_dt
            clean_item["_obs_iso"] = obs_iso
            clean_item["_sub_iso"] = sub_iso
            valid_reports.append(clean_item)

        if has_delayed_submission:
            reason_codes.append("DELAYED_SUBMISSION_EVALUATED_BY_OBSERVATION_TIME")

        # -------------------------------------------------------------
        # 2. Handle Scenario: Zero Valid Observations (Missing Data)
        # -------------------------------------------------------------
        if not valid_reports:
            # Evaluate environmental and vulnerability context
            if rain_cat in {"HIGH", "CRITICAL"}:
                reason_codes.append("RAINFALL_PRESENT_WITHOUT_ROAD_OBSERVATIONS")
            if vuln_cat in {"HIGH", "SEVERE"}:
                reason_codes.append("STATIC_VULNERABILITY_WITHOUT_ACTIVE_EVIDENCE")

            reason_codes.append("NO_OBSERVATIONS_AVAILABLE")

            return RoadStatusSnapshot(
                road_segment_id=loc_id,
                road_name=road_name,
                corridor_zone=corridor_zone,
                latitude_coarsened=lat,
                longitude_coarsened=lon,
                location_precision_m=50.0 if lat else None,
                condition_state=RoadConditionState.NO_CURRENT_EVIDENCE,
                evidence_type=RoadEvidenceType.NO_EVIDENCE,
                observation_timestamp_utc=None,
                ingestion_timestamp_utc=None,
                last_status_update_utc=now_iso,
                expiration_timestamp_utc=None,
                freshness_category=RoadFreshnessCategory.UNKNOWN,
                evidence_age_minutes=None,
                verification_state=RoadVerificationState.UNMONITORED,
                verified_by_entity=None,
                uncertainty_level=UncertaintyLevel.HIGH,
                confidence_score=0.10,
                has_conflicting_evidence=False,
                conflict_details=None,
                measured_water_depth_cm=None,
                depth_measurement_method="unmeasured",
                verified_passability="unverified_unknown",
                provenance_records=[],
                environmental_rainfall_category=rain_cat,
                environmental_rainfall_score=rain_score,
                static_vulnerability_category=vuln_cat,
                static_vulnerability_index=vuln_index,
                reason_codes=sorted(list(set(reason_codes))),
                safety_notice=MANDATORY_ROAD_SAFETY_NOTICE,
                is_actionable_for_dispatch=False,
            )

        # -------------------------------------------------------------
        # 3. Categorize Evidence & Detect Conflicts
        # -------------------------------------------------------------
        flood_like_conditions = {
            "FLOODED_ROAD", "WATERLOGGED_PASSABLE", "VERIFIED_WATERLOGGED",
            "VERIFIED_IMPASSABLE", "inundated_shallow", "inundated_deep",
            "BLOCKED_DRAIN_SURCHARGE", "FULL_ROADWAY_INUNDATION",
            "PARTIAL_LANE_WATERLOGGING"
        }
        dry_like_conditions = {
            "DRY_ROAD_CLEAR", "WET_ROAD_NO_FLOOD", "VERIFIED_PASSABLE",
            "dry", "wet_sheen", "NO_WATER"
        }

        responder_reports: List[Dict[str, Any]] = []
        community_reports: List[Dict[str, Any]] = []

        for r in valid_reports:
            v_status = str(r.get("verification_status", "")).upper()
            role = str(r.get("verifier_role", "") or r.get("verified_by_entity", "")).upper()
            if v_status == "VERIFIED_BY_RESPONDER" or "RESPONDER" in role or "POLICE" in role or "GHMC" in role:
                responder_reports.append(r)
            else:
                community_reports.append(r)

        # Build provenance records
        masked_reporters: Set[str] = set()
        for r in valid_reports:
            rep_id = r.get("reporter_id_masked") or r.get("observer_pseudonym") or f"ANON-{r.get('report_id', 'SRC')[:8]}"
            masked_reporters.add(rep_id)

            ev_type = (
                RoadEvidenceType.FIELD_RESPONDER_INSPECTION
                if r in responder_reports
                else RoadEvidenceType.COMMUNITY_REPORT
            )
            provenance_records.append(
                EvidenceProvenanceRecord(
                    evidence_type=ev_type,
                    source_id_masked=rep_id,
                    source_channel=SubmissionChannel.WEB_PORTAL,
                    raw_report_volume=1,
                    independent_sources_count=1,
                    evidence_reference=r.get("evidence_reference") or r.get("image_reference"),
                    image_reference=r.get("image_reference"),
                    is_synthetic=False,
                    observation_timestamp_utc=r.get("_obs_iso"),
                    ingestion_timestamp_utc=r.get("_sub_iso"),
                )
            )

        # Check for conflicting conditions within active reports
        flood_reports = [
            r for r in valid_reports
            if str(r.get("reported_condition", "")).upper() in flood_like_conditions
            or str(r.get("condition_state", "")).upper() in flood_like_conditions
            or str(r.get("water_presence_extent", "")).upper() in flood_like_conditions
        ]
        dry_reports = [
            r for r in valid_reports
            if str(r.get("reported_condition", "")).upper() in dry_like_conditions
            or str(r.get("condition_state", "")).upper() in dry_like_conditions
            or str(r.get("water_presence_extent", "")).upper() in dry_like_conditions
        ]

        has_conflict = len(flood_reports) > 0 and len(dry_reports) > 0
        conflict_details: Optional[str] = None
        if has_conflict:
            conflict_details = (
                f"Contradictory conditions reported: {len(flood_reports)} flood-indicative vs "
                f"{len(dry_reports)} dry-indicative reports."
            )

        # -------------------------------------------------------------
        # 4. Synthesize Status: Hierarchy of Evidence
        # Tier 1: Authorized Responder Verification (Highest)
        # Tier 2: Corroborated / Unverified Community Reports
        # -------------------------------------------------------------

        # Check if an authorized responder report exists
        if responder_reports:
            # Sort responder reports newest observation first
            responder_reports.sort(
                key=lambda x: x["_obs_dt"] or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )
            latest_responder = responder_reports[0]
            resp_obs_iso = latest_responder.get("_obs_iso")
            resp_freshness, resp_age_min = calculate_evidence_freshness(
                resp_obs_iso, reference_time_utc=now_utc, is_responder=True
            )

            # Check if responder observation is newer than conflicting community reports
            if has_conflict:
                newest_community_dt = max(
                    [c["_obs_dt"] for c in community_reports if c["_obs_dt"]] or [datetime.min.replace(tzinfo=timezone.utc)]
                )
                if latest_responder["_obs_dt"] and latest_responder["_obs_dt"] >= newest_community_dt:
                    has_conflict = False
                    conflict_details = None
                    reason_codes.append("CONFLICT_RESOLVED_BY_RESPONDER_INSPECTION")

            if resp_freshness == RoadFreshnessCategory.EXPIRED:
                condition_state = RoadConditionState.EXPIRED
                freshness_cat = RoadFreshnessCategory.EXPIRED
                uncertainty = UncertaintyLevel.HIGH
                conf_score = 0.15
                reason_codes.append("OBSERVATION_EXPIRED_EXCLUDED")
                meas_depth = None
                passability = "unverified_unknown"
            elif resp_freshness == RoadFreshnessCategory.STALE:
                condition_state = RoadConditionState.STALE
                freshness_cat = RoadFreshnessCategory.STALE
                uncertainty = UncertaintyLevel.HIGH
                conf_score = 0.35
                reason_codes.append("OBSERVATION_STALE_REQUIRES_RESURVEY")
                meas_depth = None
                passability = "unverified_unknown"
            elif has_conflict:
                condition_state = RoadConditionState.CONFLICTING
                freshness_cat = resp_freshness
                uncertainty = UncertaintyLevel.HIGH
                conf_score = 0.30
                reason_codes.append("CONTRADICTORY_COMMUNITY_REPORTS_DETECTED")
                meas_depth = None
                passability = "unverified_unknown"
            else:
                # Active fresh/aging responder verification
                raw_cond = latest_responder.get("reported_condition", "")
                cond_str = (raw_cond.value if hasattr(raw_cond, "value") else str(raw_cond)).upper()
                if any(k in cond_str for k in {"FLOODED_ROAD", "VERIFIED_IMPASSABLE", "FULL_ROADWAY_INUNDATION"}):
                    condition_state = RoadConditionState.VERIFIED_IMPASSABLE
                    passability = latest_responder.get("verified_passability") or "impassable_all_vehicles"
                elif any(k in cond_str for k in {"WATERLOGGED_PASSABLE", "VERIFIED_WATERLOGGED", "PARTIAL_LANE_WATERLOGGING"}):
                    condition_state = RoadConditionState.VERIFIED_WATERLOGGED
                    passability = latest_responder.get("verified_passability") or "impassable_two_wheelers"
                else:
                    condition_state = RoadConditionState.VERIFIED_PASSABLE
                    passability = latest_responder.get("verified_passability") or "passable_all_vehicles"

                freshness_cat = resp_freshness
                uncertainty = UncertaintyLevel.LOW if resp_freshness == RoadFreshnessCategory.FRESH else UncertaintyLevel.MEDIUM
                conf_score = 0.90 if resp_freshness == RoadFreshnessCategory.FRESH else 0.75
                meas_depth = latest_responder.get("observed_depth_cm") or latest_responder.get("measured_water_depth_cm")
                reason_codes.append("VERIFIED_BY_OFFICIAL_RESPONDER")

            # Expiration ISO
            exp_iso = None
            if latest_responder["_obs_dt"]:
                exp_iso = (latest_responder["_obs_dt"] + timedelta(minutes=RESPONDER_VERIFICATION_EXPIRY_MINUTES)).isoformat().replace("+00:00", "Z")

            return RoadStatusSnapshot(
                road_segment_id=loc_id,
                road_name=road_name,
                corridor_zone=corridor_zone,
                latitude_coarsened=lat,
                longitude_coarsened=lon,
                location_precision_m=50.0,
                condition_state=condition_state,
                evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                observation_timestamp_utc=resp_obs_iso,
                ingestion_timestamp_utc=latest_responder.get("_sub_iso"),
                last_status_update_utc=now_iso,
                expiration_timestamp_utc=exp_iso,
                freshness_category=freshness_cat,
                evidence_age_minutes=resp_age_min,
                verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER if condition_state in {
                    RoadConditionState.VERIFIED_PASSABLE, RoadConditionState.VERIFIED_WATERLOGGED, RoadConditionState.VERIFIED_IMPASSABLE
                } else RoadVerificationState.UNDER_REVIEW,
                verified_by_entity=latest_responder.get("verified_by_entity") or f"{latest_responder.get('verifier_role', 'RESPONDER')}:{latest_responder.get('verifier_id', 'OFFICER')}",
                uncertainty_level=uncertainty,
                confidence_score=conf_score,
                has_conflicting_evidence=has_conflict,
                conflict_details=conflict_details,
                measured_water_depth_cm=meas_depth,
                depth_measurement_method=latest_responder.get("depth_measurement_method", "responder_manual" if meas_depth else "unmeasured"),
                verified_passability=passability,
                provenance_records=provenance_records,
                environmental_rainfall_category=rain_cat,
                environmental_rainfall_score=rain_score,
                static_vulnerability_category=vuln_cat,
                static_vulnerability_index=vuln_index,
                reason_codes=sorted(list(set(reason_codes))),
                safety_notice=MANDATORY_ROAD_SAFETY_NOTICE,
                is_actionable_for_dispatch=condition_state in {RoadConditionState.VERIFIED_IMPASSABLE, RoadConditionState.CONFLICTING},
            )

        # -------------------------------------------------------------
        # Tier 2: Community Reports (Unverified by Responders)
        # -------------------------------------------------------------
        # Sort community reports newest observation first
        community_reports.sort(
            key=lambda x: x["_obs_dt"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )
        newest_report = community_reports[0]
        newest_obs_iso = newest_report.get("_obs_iso")
        comm_freshness, comm_age_min = calculate_evidence_freshness(
            newest_obs_iso, reference_time_utc=now_utc, is_responder=False
        )

        # Check for conflicting reports
        if has_conflict:
            condition_state = RoadConditionState.CONFLICTING
            uncertainty = UncertaintyLevel.HIGH
            conf_score = 0.25
            reason_codes.append("CONTRADICTORY_COMMUNITY_REPORTS_DETECTED")
        elif comm_freshness == RoadFreshnessCategory.EXPIRED:
            condition_state = RoadConditionState.EXPIRED
            uncertainty = UncertaintyLevel.HIGH
            conf_score = 0.15
            reason_codes.append("OBSERVATION_EXPIRED_EXCLUDED")
        elif comm_freshness == RoadFreshnessCategory.STALE:
            condition_state = RoadConditionState.STALE
            uncertainty = UncertaintyLevel.HIGH
            conf_score = 0.30
            reason_codes.append("OBSERVATION_STALE_REQUIRES_RESURVEY")
        else:
            # Fresh or Aging community evidence
            # Distinguish raw volume from independent corroborating sources
            unique_sources = {
                r.get("reporter_id_masked") or r.get("reporter_contact_raw") or r.get("report_id")
                for r in community_reports
            }
            raw_volume = len(community_reports)
            independent_count = len(unique_sources)

            if independent_count >= 2:
                condition_state = RoadConditionState.CORROBORATED
                uncertainty = UncertaintyLevel.MEDIUM
                conf_score = 0.65 if comm_freshness == RoadFreshnessCategory.FRESH else 0.50
                reason_codes.append("CORROBORATED_BY_INDEPENDENT_COMMUNITY_SOURCES")
            else:
                condition_state = RoadConditionState.UNVERIFIED
                uncertainty = UncertaintyLevel.HIGH
                conf_score = 0.40 if comm_freshness == RoadFreshnessCategory.FRESH else 0.30
                reason_codes.append("UNVERIFIED_COMMUNITY_REPORT")
                if raw_volume > 1:
                    reason_codes.append("SINGLE_SOURCE_MULTIPLE_REPORTS_UNPROMOTED")

        # Invariant enforcement: depth and passability must be unverified for community reports
        meas_depth = None
        passability = "unverified_unknown"

        exp_iso = None
        if newest_report["_obs_dt"]:
            exp_iso = (newest_report["_obs_dt"] + timedelta(minutes=COMMUNITY_REPORT_EXPIRY_MINUTES)).isoformat().replace("+00:00", "Z")

        # Environmental context
        if rain_cat in {"HIGH", "CRITICAL"}:
            reason_codes.append("RAINFALL_ELEVATED_RISK_ACTIVE")
        if vuln_cat in {"HIGH", "SEVERE"}:
            reason_codes.append("STATIC_VULNERABILITY_ELEVATED")

        ver_state = (
            RoadVerificationState.CORROBORATED
            if condition_state == RoadConditionState.CORROBORATED
            else RoadVerificationState.UNVERIFIED
        )

        return RoadStatusSnapshot(
            road_segment_id=loc_id,
            road_name=road_name,
            corridor_zone=corridor_zone,
            latitude_coarsened=lat,
            longitude_coarsened=lon,
            location_precision_m=50.0,
            condition_state=condition_state,
            evidence_type=RoadEvidenceType.COMMUNITY_REPORT,
            observation_timestamp_utc=newest_obs_iso,
            ingestion_timestamp_utc=newest_report.get("_sub_iso"),
            last_status_update_utc=now_iso,
            expiration_timestamp_utc=exp_iso,
            freshness_category=comm_freshness,
            evidence_age_minutes=comm_age_min,
            verification_state=ver_state,
            verified_by_entity=None,
            uncertainty_level=uncertainty,
            confidence_score=conf_score,
            has_conflicting_evidence=has_conflict,
            conflict_details=conflict_details,
            measured_water_depth_cm=meas_depth,
            depth_measurement_method="unmeasured",
            verified_passability=passability,
            provenance_records=provenance_records,
            environmental_rainfall_category=rain_cat,
            environmental_rainfall_score=rain_score,
            static_vulnerability_category=vuln_cat,
            static_vulnerability_index=vuln_index,
            reason_codes=sorted(list(set(reason_codes))),
            safety_notice=MANDATORY_ROAD_SAFETY_NOTICE,
            is_actionable_for_dispatch=condition_state in {RoadConditionState.CONFLICTING, RoadConditionState.CORROBORATED},
        )

    def get_corridor_status(
        self,
        corridor_id: str,
        reference_time_utc: Optional[datetime] = None,
    ) -> RoadStatusSnapshot:
        """
        Retrieves active community reports and evaluates live road status for a corridor.
        """
        reports = self._report_service.get_active_reports_for_corridor(
            corridor_id=corridor_id,
            reference_time_utc=reference_time_utc,
            max_age_minutes=COMMUNITY_REPORT_EXPIRY_MINUTES,
            include_duplicates=True,
        )

        # Convert records to dictionary format for evaluation
        report_dicts = [r.model_dump() for r in reports]

        inp = RoadStatusEvaluationInput(
            road_segment_id=corridor_id,
            community_reports=report_dicts,
            evaluation_timestamp_utc=reference_time_utc.isoformat() if reference_time_utc else None,
        )
        return self.evaluate_road_status(inp, reference_time_utc=reference_time_utc)

    def get_all_corridors_status(
        self,
        reference_time_utc: Optional[datetime] = None,
    ) -> List[RoadStatusSnapshot]:
        """
        Evaluates offline road status snapshot across all 20 Hyderabad pilot corridors.
        """
        snapshots: List[RoadStatusSnapshot] = []
        # Fallback to standard 20 corridors if cache is empty
        cids = list(self._corridor_features_cache.keys()) or [
            f"HYD-LOC-{i:03d}" for i in range(1, 21)
        ]
        for cid in sorted(cids):
            snapshots.append(self.get_corridor_status(cid, reference_time_utc=reference_time_utc))
        return snapshots


# Module-level singleton instance for application route handlers
default_road_status_service = LiveRoadStatusService()
