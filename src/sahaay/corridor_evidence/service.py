"""
Sahaay AI - Phase D: Canonical Corridor Evidence Service
(src/sahaay/corridor_evidence/service.py)

Synthesizes multi-source evidence across all existing Sahaay AI subsystems into a
unified, auditable, corridor-level evidence view:
1. Static road network infrastructure (Phase A)
2. Directed topological graph routing constraints (Phase B)
3. Operational weather ingestion & rainfall pipeline (Phase C)
4. Community report verification and conflict resolution (Phase 15)
5. Multi-source live road status & ground truth gating (Phase 16)
6. Transparent local flood-risk heuristics (Phase 17)
7. Multi-horizon forecast risk service (Phase 18)
8. Risk-aware routing & safety pruning (Phase 19)
9. Emergency assessment workflows & disarmed dispatch (Phase 20)
10. End-to-end evidence boundaries & non-inference contracts (Phase 21)

Non-Negotiable Safety Semantics Enforced:
- Missing or stale evidence remains UNKNOWN or INSUFFICIENT_DATA; no synthetic dry zero rainfall.
- Absence of reports NEVER implies that a road is safe, dry, or passable.
- Forecast rainfall and observed rainfall alone NEVER prove current road inundation or road closure.
- Static vulnerability is strictly a static heuristic, NEVER current flood status.
- Community reports do not silently become ground truth without authorized responder inspection.
- Conflicting reports remain explicitly CONFLICTING until resolved by authorized verification.
- Vision abstention [0.35, 0.65] strictly propagates as INCONCLUSIVE.
- Uncalibrated scores are NEVER converted into calibrated flood probabilities.
- Autonomous road closures and emergency dispatch remain strictly disarmed.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from sahaay.corridor_evidence.schemas import (
    CorridorEvidenceState,
    EvidenceSufficiency,
    RoadStatusEvidenceSection,
    CommunityReportsEvidenceSection,
    ObservedRainfallEvidenceSection,
    ForecastRainfallEvidenceSection,
    StaticSusceptibilityEvidenceSection,
    VisionEvidenceSection,
    HistoricalInundationEvidenceSection,
    CorridorEvidenceAssessment,
)
from sahaay.road_network.schemas import RoadSegment
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    RoadStatusSnapshot,
    UncertaintyLevel,
)
from sahaay.road_status.service import default_road_status_service
from sahaay.hyderabad_risk.weather_pipeline import default_weather_pipeline
from sahaay.hyderabad_risk.schemas import RainfallRiskResult
from sahaay.forecast_risk.schemas import ForecastRiskAssessmentOutput
from sahaay.reports.schemas import CitizenReportRecord, ReportVerificationStatus
from sahaay.vision.policy import (
    evaluate_vision_abstention_boundary,
    CalibratedVisionDecision,
    DEFAULT_ABSTENTION_LOWER_BOUND,
    DEFAULT_ABSTENTION_UPPER_BOUND,
)

logger = logging.getLogger(__name__)


class CorridorEvidenceService:
    """
    Unified corridor evidence assessment engine.
    Fuses static road infrastructure with live observations, meteorological telemetry,
    forward-looking forecasts, and community submissions into a canonical evidence view.
    """

    def __init__(
        self,
        road_store=None,
        road_status_service=None,
        weather_pipeline=None,
    ):
        self.road_store = road_store or default_road_network_store
        self.road_status_service = road_status_service or default_road_status_service
        self.weather_pipeline = weather_pipeline or default_weather_pipeline
        self._lock = threading.Lock()
        self._corridor_vision_cache: Dict[str, Dict[str, Any]] = {}
        self._image_hash_cache: Dict[str, Dict[str, Any]] = {}

    def check_and_register_image_hash(
        self,
        image_hash: str,
        corridor_id: Optional[str] = None,
        max_age_seconds: float = 3600.0,
    ) -> Tuple[bool, str]:
        """
        Deduplicates image submissions using SHA-256 hash.
        Prevents identical images from inflating independent corroboration counts.
        Returns (is_duplicate, status_message).
        """
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            if image_hash in self._image_hash_cache:
                entry = self._image_hash_cache[image_hash]
                age = now - entry["timestamp"]
                if age <= max_age_seconds:
                    return True, "DUPLICATE_IMAGE_IGNORED_FOR_CORROBORATION"
            self._image_hash_cache[image_hash] = {
                "timestamp": now,
                "corridor_id": corridor_id,
            }
            return False, "UNIQUE_IMAGE_REGISTERED"

    def record_vision_evidence(
        self,
        corridor_id: str,
        vision_result: Dict[str, Any],
        image_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registers optical vision inference as provisional corridor evidence.
        Enforces safety contracts:
        - NEVER infers water depth (cm) or vehicle passability.
        - NEVER marks road as verified flooded or passable solely from vision inference.
        - Unvalidated model inference is strictly marked is_provisional_evidence=True.
        - Inconclusive/abstained results are preserved explicitly.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        cleaned_result = dict(vision_result)
        cleaned_result["measured_water_depth_cm"] = None
        cleaned_result["is_provisional_evidence"] = True
        cleaned_result["verification_status"] = "PROVISIONAL_UNVERIFIED"
        cleaned_result["corridor_id"] = corridor_id
        if "inference_timestamp_utc" not in cleaned_result:
            cleaned_result["inference_timestamp_utc"] = now_iso

        is_duplicate = False
        dedup_status = "NOT_CHECKED"
        if image_hash:
            is_dup, dedup_status = self.check_and_register_image_hash(image_hash, corridor_id=corridor_id)
            is_duplicate = is_dup

        cleaned_result["is_duplicate_submission"] = is_duplicate
        cleaned_result["deduplication_status"] = dedup_status

        with self._lock:
            self._corridor_vision_cache[corridor_id] = cleaned_result

        return cleaned_result

    def get_latest_vision_evidence(self, corridor_id: str) -> Optional[Dict[str, Any]]:
        """Returns the latest registered provisional vision evidence for a corridor."""
        with self._lock:
            return self._corridor_vision_cache.get(corridor_id)

    def clear_vision_cache(self) -> None:
        """Clears vision evidence cache for testing isolation."""
        with self._lock:
            self._corridor_vision_cache.clear()
            self._image_hash_cache.clear()

    def assess_corridor(
        self,
        corridor_id: str,
        road_segment: Optional[RoadSegment] = None,
        road_status_snapshot: Optional[RoadStatusSnapshot] = None,
        weather_result: Optional[RainfallRiskResult] = None,
        forecast_result: Optional[ForecastRiskAssessmentOutput] = None,
        vision_result: Optional[Dict[str, Any]] = None,
        community_reports: Optional[List[CitizenReportRecord]] = None,
        evaluation_timestamp_utc: Optional[str] = None,
    ) -> CorridorEvidenceAssessment:
        """
        Generates a canonical corridor-level evidence assessment for the specified corridor.
        Strictly preserves provenance, decouples timestamps, and enforces non-inference safety.
        """
        now_utc = datetime.now(timezone.utc)
        assessment_iso = evaluation_timestamp_utc or now_utc.isoformat().replace("+00:00", "Z")

        # ----------------------------------------------------------------------
        # 1. Static Road Infrastructure (Phase A)
        # ----------------------------------------------------------------------
        seg = road_segment or self.road_store.get_segment(corridor_id)
        if seg is None:
            # Check secondary search by corridor_id
            for s in self.road_store.list_segments():
                if s.corridor_id == corridor_id:
                    seg = s
                    break

        road_name = seg.road_name if seg else f"Corridor {corridor_id}"
        zone = seg.zone if seg else None
        v_idx = seg.static_vulnerability_index if (seg and seg.static_vulnerability_index is not None) else 0.10
        v_cat = seg.static_vulnerability_category if (seg and seg.static_vulnerability_category) else "LOW"
        elev_min = seg.elevation_min_m if seg else None
        elev_max = seg.elevation_max_m if seg else None

        static_section = StaticSusceptibilityEvidenceSection(
            susceptibility_heuristic_type="STATIC_INFRASTRUCTURE_HEURISTIC",
            vulnerability_index=round(v_idx, 3),
            vulnerability_category=v_cat,
            elevation_min_m=elev_min,
            elevation_max_m=elev_max,
            is_current_flood_status=False,  # MANDATORY INVARIANT
            description=(
                f"Static infrastructure susceptibility: {v_cat} tier (index: {v_idx:.3f}). "
                "Static vulnerability is an infrastructure baseline and is NEVER current flood status."
            ),
        )

        # ----------------------------------------------------------------------
        # 2. Road Status Evidence & Ground Truth (Phase 16)
        # ----------------------------------------------------------------------
        status_snap = road_status_snapshot
        if status_snap is None:
            try:
                status_snap = self.road_status_service.get_corridor_status(corridor_id)
            except Exception as e:
                logger.debug(f"Could not retrieve live road status for {corridor_id}: {e}")
                status_snap = None

        if status_snap is not None:
            cond_state = status_snap.condition_state
            ver_state = status_snap.verification_state
            ev_type = status_snap.evidence_type
            verifier = status_snap.verified_by_entity
            water_depth = status_snap.measured_water_depth_cm
            depth_method = status_snap.depth_measurement_method
            obs_time = status_snap.observation_timestamp_utc
            ingest_time = status_snap.ingestion_timestamp_utc
            evidence_age = status_snap.evidence_age_minutes
            freshness = status_snap.freshness_category
            is_impassable = (cond_state == RoadConditionState.VERIFIED_IMPASSABLE)
            is_waterlogged = (cond_state == RoadConditionState.VERIFIED_WATERLOGGED)
            is_passable = (cond_state == RoadConditionState.VERIFIED_PASSABLE)
            has_snap_conflict = status_snap.has_conflicting_evidence
            conflict_details = status_snap.conflict_details
            supp_summary = f"Condition: {cond_state.value}, Verification: {ver_state.value}, Modality: {ev_type.value}"
        else:
            cond_state = RoadConditionState.UNKNOWN
            ver_state = RoadVerificationState.UNMONITORED
            ev_type = RoadEvidenceType.NO_EVIDENCE
            verifier = None
            water_depth = None
            depth_method = "unmeasured"
            obs_time = None
            ingest_time = None
            evidence_age = None
            freshness = RoadFreshnessCategory.UNKNOWN
            is_impassable = False
            is_waterlogged = False
            is_passable = False
            has_snap_conflict = False
            conflict_details = None
            supp_summary = "No current ground observation available; corridor unmonitored."

        road_status_section = RoadStatusEvidenceSection(
            condition_state=cond_state,
            verification_state=ver_state,
            evidence_type=ev_type,
            verified_by_entity=verifier,
            measured_water_depth_cm=water_depth,
            depth_measurement_method=depth_method,
            observation_timestamp_utc=obs_time,
            ingestion_timestamp_utc=ingest_time,
            evidence_age_minutes=evidence_age,
            freshness_category=freshness,
            is_verified_impassable=is_impassable,
            is_verified_waterlogged=is_waterlogged,
            is_verified_passable=is_passable,
            supporting_evidence_summary=supp_summary,
        )

        # ----------------------------------------------------------------------
        # 3. Community Reports Evidence (Phase 15)
        # ----------------------------------------------------------------------
        reports_count = 0
        indep_count = 0
        verif_status_str = "UNMONITORED"
        oldest_age = None
        newest_age = None
        has_report_conflict = has_snap_conflict
        conflict_msg = conflict_details

        if community_reports is not None and len(community_reports) > 0:
            reports_count = len(community_reports)
            unique_senders = set(
                getattr(r, "reporter_id_masked", None) or getattr(r, "masked_reporter_id", None)
                for r in community_reports
            )
            unique_senders.discard(None)
            indep_count = max(len(unique_senders), 1)

            # Age analysis
            ages = []
            flooded_claims = False
            clear_claims = False
            for r in community_reports:
                obs_t = getattr(r, "observation_timestamp_utc", None) or getattr(r, "submission_timestamp_utc", None)
                if obs_t:
                    try:
                        r_dt = datetime.fromisoformat(obs_t.replace("Z", "+00:00"))
                        age_m = max(0.0, (now_utc - r_dt).total_seconds() / 60.0)
                        ages.append(age_m)
                    except Exception:
                        pass

                cond = getattr(r, "reported_condition", None) or getattr(r, "condition_type", None)
                if hasattr(cond, "value"):
                    cond = cond.value
                cond_str = str(cond).upper() if cond else ""
                if any(k in cond_str for k in ("FLOOD", "WATERLOG", "IMPASSABLE")):
                    flooded_claims = True
                if any(k in cond_str for k in ("CLEAR", "DRY", "PASSABLE")) and not any(k in cond_str for k in ("WATERLOG", "IMPASSABLE")):
                    clear_claims = True

            if ages:
                oldest_age = max(ages)
                newest_age = min(ages)

            # Check for conflict among citizen reports (flooded vs dry)
            if flooded_claims and clear_claims:
                has_report_conflict = True
                conflict_msg = "Contradictory citizen submissions detected: simultaneous waterlogged and passable claims."

            v_stat = getattr(community_reports[0], "verification_status", "UNMONITORED")
            verif_status_str = v_stat.value if hasattr(v_stat, "value") else str(v_stat)
            claims_str = f"{reports_count} citizen report(s) logged ({indep_count} independent source(s))."
        elif status_snap is not None and status_snap.provenance_records:
            comm_recs = [p for p in status_snap.provenance_records if p.evidence_type == RoadEvidenceType.COMMUNITY_REPORT]
            if comm_recs:
                reports_count = sum(p.raw_report_volume for p in comm_recs)
                indep_count = sum(p.independent_sources_count for p in comm_recs)
                verif_status_str = ver_state.value
                claims_str = f"{reports_count} citizen report(s) from {indep_count} independent contributor(s)."
            else:
                claims_str = "Zero citizen reports submitted in current active window."
        else:
            claims_str = "Zero citizen reports submitted in current active window."

        community_section = CommunityReportsEvidenceSection(
            report_count=reports_count,
            independent_sources_count=indep_count,
            verification_status=verif_status_str,
            oldest_report_age_minutes=oldest_age,
            newest_report_age_minutes=newest_age,
            has_conflicts=has_report_conflict,
            conflict_summary=conflict_msg,
            citizen_claims_summary=claims_str,
        )

        # ----------------------------------------------------------------------
        # 4. Observed Rainfall Telemetry (Phase C / Phase 13)
        # ----------------------------------------------------------------------
        weather_eval = weather_result
        if weather_eval is None:
            # Coordinate lookup for corridor
            if seg is not None and seg.geometry.coordinates:
                mid_idx = len(seg.geometry.coordinates) // 2
                c_lon, c_lat = seg.geometry.coordinates[mid_idx]
            else:
                c_lat, c_lon = 17.40, 78.45

            try:
                weather_eval = self.weather_pipeline.evaluate_corridor_weather(
                    corridor_id=corridor_id,
                    corridor_lat=c_lat,
                    corridor_lon=c_lon,
                )
            except Exception as e:
                logger.debug(f"Could not retrieve weather evaluation for {corridor_id}: {e}")
                weather_eval = None

        if weather_eval is not None:
            # Check for non-silent missingness / outage
            is_outage = (weather_eval.risk_category == "UNKNOWN") or ("QC_MISSING_VALUE" in weather_eval.qc_flags)
            is_valid_zero = ("VALID_MEASURED_ZERO" in weather_eval.qc_flags)

            prov = getattr(weather_eval, "observation_provenance", {}) or {}
            r_1h = getattr(weather_eval, "rain_1h_mm", None)
            if r_1h is None and isinstance(prov, dict):
                r_1h = prov.get("rain_1h_mm")

            if is_outage and r_1h is None:
                avail_status = "OUTAGE_OR_MISSING_DATA"
            elif weather_eval.data_freshness_hours is not None and weather_eval.data_freshness_hours > 6.0:
                avail_status = "STALE"
            else:
                avail_status = "AVAILABLE"

            r_3h = getattr(weather_eval, "rain_3h_mm", None)
            if r_3h is None and isinstance(prov, dict):
                r_3h = prov.get("rain_3h_mm")
            r_6h = getattr(weather_eval, "rain_6h_mm", None)
            if r_6h is None and isinstance(prov, dict):
                r_6h = prov.get("rain_6h_mm")
            r_24h = getattr(weather_eval, "rain_24h_mm", None)
            if r_24h is None and isinstance(prov, dict):
                r_24h = prov.get("rain_24h_mm")
            r_rate = getattr(weather_eval, "instantaneous_rate_mm_hr", None)
            if r_rate is None and isinstance(prov, dict):
                r_rate = prov.get("instantaneous_rate_mm_hr")
            st_id = getattr(weather_eval, "station_id", None)
            st_name = getattr(weather_eval, "station_name", None) or (prov.get("station_name") if isinstance(prov, dict) else None)
            st_dist = weather_eval.station_dist_km
            obs_dt_str = weather_eval.data_timestamp
            fresh_h = weather_eval.data_freshness_hours
            qc_flgs = list(weather_eval.qc_flags)
            provider_str = weather_eval.provider
        else:
            avail_status = "MISSING_TELEMETRY"
            r_1h = None
            r_3h = None
            r_6h = None
            r_24h = None
            r_rate = None
            st_id = None
            st_name = None
            st_dist = None
            obs_dt_str = None
            fresh_h = None
            qc_flgs = ["QC_MISSING_VALUE"]
            is_valid_zero = False
            provider_str = None

        rainfall_section = ObservedRainfallEvidenceSection(
            data_availability=avail_status,
            rainfall_1h_mm=r_1h,
            rainfall_3h_mm=r_3h,
            rainfall_6h_mm=r_6h,
            rainfall_24h_mm=r_24h,
            instantaneous_rate_mm_hr=r_rate,
            station_id=st_id,
            station_name=st_name,
            station_distance_km=st_dist,
            observation_timestamp_utc=obs_dt_str,
            freshness_hours=fresh_h,
            qc_flags=qc_flgs,
            is_valid_measured_zero=is_valid_zero,
            provenance_provider=provider_str,
        )

        # ----------------------------------------------------------------------
        # 5. Forecast Rainfall Context (Phase 18)
        # ----------------------------------------------------------------------
        fc_eval = forecast_result
        if fc_eval is None:
            if seg is not None and seg.geometry.coordinates:
                mid_idx = len(seg.geometry.coordinates) // 2
                c_lon, c_lat = seg.geometry.coordinates[mid_idx]
            else:
                c_lat, c_lon = 17.40, 78.45

            try:
                fc_eval = self.weather_pipeline.evaluate_corridor_forecast_risk(
                    corridor_id=corridor_id,
                    road_name=road_name,
                    corridor_lat=c_lat,
                    corridor_lon=c_lon,
                    forecast_inputs=None,  # Live external feed is blocked
                    static_vulnerability_index=v_idx,
                    static_vulnerability_category=v_cat,
                )
            except Exception as e:
                logger.debug(f"Could not retrieve forecast risk for {corridor_id}: {e}")
                fc_eval = None

        if fc_eval is not None:
            fc_status = getattr(fc_eval, "forecast_source_status", None)
            if not fc_status and hasattr(fc_eval, "assessment_status"):
                fc_status = fc_eval.assessment_status.value if hasattr(fc_eval.assessment_status, "value") else str(fc_eval.assessment_status)
            fc_status = fc_status or "AVAILABLE_OFFLINE_TEST"
            fc_horizon = int(fc_eval.forecast_horizon_hours) if fc_eval.forecast_horizon_hours is not None else 1
            fc_cat = getattr(fc_eval, "forecast_risk_category", "UNKNOWN")
            fc_ctx = fc_eval.forecast_rainfall_context or {}
            fc_amt = fc_ctx.get("rainfall_amount")
            fc_band = fc_ctx.get("precipitation_band", "UNKNOWN")
            fc_issue = fc_ctx.get("issue_timestamp_utc")
            fc_valid = fc_ctx.get("valid_timestamp_utc")
            fc_desc = (
                f"Multi-horizon precipitation forecast: {fc_band} band ({fc_cat} category) "
                f"for horizon {fc_horizon}h. Source status: {fc_status}."
            )
        else:
            fc_status = "BLOCKED_NO_AUTHORIZED_FEED"
            fc_horizon = 1
            fc_cat = "UNKNOWN"
            fc_amt = None
            fc_band = "UNKNOWN"
            fc_issue = None
            fc_valid = None
            fc_desc = "Zero authorized live forecast feeds configured. Fallback to INSUFFICIENT_DATA."

        forecast_section = ForecastRainfallEvidenceSection(
            forecast_source_status=fc_status,
            forecast_horizon_hours=fc_horizon,
            forecast_amount_mm=fc_amt,
            precipitation_band=fc_band,
            forecast_risk_category=fc_cat,
            uncertainty_description=fc_desc,
            issue_timestamp_utc=fc_issue,
            valid_timestamp_utc=fc_valid,
            does_forecast_prove_inundation=False,  # MANDATORY INVARIANT
        )

        # ----------------------------------------------------------------------
        # 6. Computer Vision Inference & Quality Gate
        # ----------------------------------------------------------------------
        active_vision = vision_result or self.get_latest_vision_evidence(corridor_id)
        if active_vision is not None:
            v_avail = True
            v_pred_raw = active_vision.get("predicted_class")
            v_conf_raw = active_vision.get("confidence")
            v_prob_raw = active_vision.get("raw_probability")
            v_is_inconc_raw = active_vision.get("is_inconclusive", False)
            v_ref = active_vision.get("image_reference")
            v_ts = active_vision.get("inference_timestamp_utc") or assessment_iso

            # Quality Gate Check
            if v_is_inconc_raw or v_pred_raw == "inconclusive":
                v_quality_pass = False
                v_is_abstention = True
                v_pred_final = "inconclusive"
                v_conf_final = v_conf_raw
                v_abstention_reason = active_vision.get("rejection_reason", "Image quality gate failed (luminance/variance out of bounds).")
            elif v_prob_raw is not None and isinstance(v_prob_raw, (int, float)):
                # Evaluate against calibrated abstention interval [0.35, 0.65]
                try:
                    decision, conf, is_ambig = evaluate_vision_abstention_boundary(float(v_prob_raw))
                    if is_ambig or decision == CalibratedVisionDecision.INCONCLUSIVE:
                        v_quality_pass = True
                        v_is_abstention = True
                        v_pred_final = "inconclusive"
                        v_conf_final = conf
                        v_abstention_reason = (
                            f"Vision probability {v_prob_raw:.3f} falls within abstention boundary "
                            f"[{DEFAULT_ABSTENTION_LOWER_BOUND}, {DEFAULT_ABSTENTION_UPPER_BOUND}]; model strictly abstains."
                        )
                    elif decision == CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED:
                        v_quality_pass = True
                        v_is_abstention = False
                        v_pred_final = "flooded"
                        v_conf_final = conf
                        v_abstention_reason = None
                    else:
                        v_quality_pass = True
                        v_is_abstention = False
                        v_pred_final = "not_flooded"
                        v_conf_final = conf
                        v_abstention_reason = None
                except Exception as e:
                    v_quality_pass = False
                    v_is_abstention = True
                    v_pred_final = "inconclusive"
                    v_conf_final = None
                    v_abstention_reason = f"Vision probability evaluation failed: {e}"
            else:
                v_quality_pass = True
                v_is_abstention = False
                v_pred_final = v_pred_raw
                v_conf_final = v_conf_raw
                v_abstention_reason = None
        else:
            v_avail = False
            v_pred_final = None
            v_conf_final = None
            v_quality_pass = False
            v_is_abstention = False
            v_abstention_reason = "No optical image submitted or inference unperformed."
            v_ref = None
            v_ts = None

        vision_section = VisionEvidenceSection(
            inference_available=v_avail,
            predicted_class=v_pred_final,
            calibrated_confidence=v_conf_final,
            quality_gate_passed=v_quality_pass,
            is_inconclusive_abstention=v_is_abstention,
            abstention_reason=v_abstention_reason,
            image_reference=v_ref,
            inference_timestamp_utc=v_ts,
        )

        # ----------------------------------------------------------------------
        # 7. Contradiction Detection Across Modalities
        # ----------------------------------------------------------------------
        cross_conflict = has_report_conflict

        # Conflict: High confidence camera asserts dry, but citizen asserts flooded
        citizen_flooded_asserted = (
            community_section.report_count >= 1
            or cond_state in (RoadConditionState.CORROBORATED, RoadConditionState.UNVERIFIED)
            or (status_snap is not None and status_snap.evidence_type == RoadEvidenceType.COMMUNITY_REPORT)
        )
        if (
            vision_section.inference_available
            and vision_section.predicted_class == "not_flooded"
            and (vision_section.calibrated_confidence or 0.0) >= 0.75
            and not vision_section.is_inconclusive_abstention
            and citizen_flooded_asserted
        ):
            cross_conflict = True
            conflict_msg = (
                "Contradictory evidence: Citizen submission indicates waterlogging, but calibrated camera confirms dry pavement."
            )

        # Conflict: High confidence camera asserts flooded, but responder verifies passable
        if (
            vision_section.inference_available
            and vision_section.predicted_class == "flooded"
            and (vision_section.calibrated_confidence or 0.0) >= 0.75
            and road_status_section.is_verified_passable
        ):
            cross_conflict = True
            conflict_msg = (
                "Contradictory evidence: Responder verified passable, but optical camera detects standing floodwater."
            )

        # ----------------------------------------------------------------------
        # 8. Canonical Synthesis & Explanation Code Assignment
        # ----------------------------------------------------------------------
        explanation_codes: List[str] = []
        is_traversable = True
        routing_penalty = 1.0

        # RULE 1: Officially Verified Impassable (Highest Priority)
        if road_status_section.is_verified_impassable:
            evidence_state = CorridorEvidenceState.VERIFIED_IMPASSABLE
            evidence_sufficiency = EvidenceSufficiency.SUFFICIENT
            compact_explanation = "Authorized field inspection confirmed road impassable due to hazardous floodwaters."
            explanation_codes.append("OFFICIAL_INSPECTION_CONFIRMED_IMPASSABLE")
            is_traversable = False
            routing_penalty = 999.0

        # RULE 2: Officially Verified Waterlogged (High Caution)
        elif road_status_section.is_verified_waterlogged:
            evidence_state = CorridorEvidenceState.VERIFIED_WATERLOGGED
            evidence_sufficiency = EvidenceSufficiency.SUFFICIENT
            compact_explanation = "Authorized field inspection confirmed active waterlogging; severe delay/stall risk."
            explanation_codes.append("OFFICIAL_INSPECTION_CONFIRMED_WATERLOGGED")
            is_traversable = True
            routing_penalty = 15.0

        # RULE 3: Officially Verified Passable
        elif road_status_section.is_verified_passable:
            evidence_state = CorridorEvidenceState.VERIFIED_PASSABLE
            evidence_sufficiency = EvidenceSufficiency.SUFFICIENT
            compact_explanation = "Authorized field inspection confirmed road dry and passable at observation time."
            explanation_codes.append("OFFICIAL_INSPECTION_CONFIRMED_PASSABLE")
            is_traversable = True
            routing_penalty = 1.0

        # RULE 4: Unresolved Contradictory Evidence
        elif cross_conflict or cond_state == RoadConditionState.CONFLICTING:
            evidence_state = CorridorEvidenceState.CONFLICTING_EVIDENCE
            evidence_sufficiency = EvidenceSufficiency.CONFLICTING
            compact_explanation = "Contradictory observations detected across sensor/report streams; field verification required."
            explanation_codes.append("CONTRADICTORY_OBSERVATIONS_UNRESOLVED")
            is_traversable = True
            routing_penalty = 5.0

        # RULE 5: Citizen Corroborated Hazard (>=2 independent sources)
        elif cond_state == RoadConditionState.CORROBORATED or community_section.independent_sources_count >= 2:
            evidence_state = CorridorEvidenceState.CORROBORATED_HAZARD
            evidence_sufficiency = EvidenceSufficiency.DEGRADED
            compact_explanation = "Multiple independent citizen reports assert waterlogging; awaiting authorized verification."
            explanation_codes.append("CITIZEN_CORROBORATED_WATERLOGGING_UNVERIFIED")
            is_traversable = True
            routing_penalty = 8.0

        # RULE 6: Single Unverified Citizen Report
        elif cond_state == RoadConditionState.UNVERIFIED or community_section.report_count == 1:
            evidence_state = CorridorEvidenceState.UNVERIFIED_REPORT
            evidence_sufficiency = EvidenceSufficiency.DEGRADED
            compact_explanation = "Single citizen hazard report submitted; awaiting corroboration or responder inspection."
            explanation_codes.append("UNVERIFIED_SINGLE_CITIZEN_REPORT")
            is_traversable = True
            routing_penalty = 2.5

        # RULE 7: Elevated Meteorological Risk (Forecast / Rainfall on Vulnerable Road)
        elif (
            forecast_section.forecast_risk_category in {"HIGH", "CRITICAL"}
            or (rainfall_section.rainfall_1h_mm is not None and rainfall_section.rainfall_1h_mm >= 30.0)
        ):
            evidence_state = CorridorEvidenceState.ELEVATED_METEOROLOGICAL_RISK
            evidence_sufficiency = EvidenceSufficiency.DEGRADED
            compact_explanation = "Elevated rainfall or forecast on vulnerable road corridor. Ground inundation is UNPROVEN."
            explanation_codes.append("ELEVATED_METEOROLOGICAL_VIGILANCE_INUNDATION_UNPROVEN")
            is_traversable = True
            routing_penalty = 2.0

        # RULE 8: Stale Evidence
        elif freshness in {RoadFreshnessCategory.STALE, RoadFreshnessCategory.EXPIRED} or cond_state in {RoadConditionState.STALE, RoadConditionState.EXPIRED}:
            evidence_state = CorridorEvidenceState.STALE_EVIDENCE
            evidence_sufficiency = EvidenceSufficiency.DEGRADED
            compact_explanation = "Ground evidence is aged (>180 min); condition cannot be reliably established."
            explanation_codes.append("OBSERVATION_FRESHNESS_DECAYED")
            is_traversable = True
            routing_penalty = 1.5

        # RULE 9: No Current Evidence (Monitored Corridor, zero active reports)
        elif cond_state == RoadConditionState.NO_CURRENT_EVIDENCE or (seg is not None and community_section.report_count == 0 and rainfall_section.rainfall_1h_mm == 0.0):
            evidence_state = CorridorEvidenceState.NO_CURRENT_EVIDENCE
            evidence_sufficiency = EvidenceSufficiency.INSUFFICIENT_DATA
            compact_explanation = "Monitored corridor has no active reports in observation window; does NOT imply safe passage."
            explanation_codes.append("NO_CURRENT_GROUND_OBSERVATION_NOT_PROVEN_SAFE")
            is_traversable = True
            routing_penalty = 1.0

        # RULE 10: Unmonitored Network Segment or Missing Primary Data
        else:
            evidence_state = CorridorEvidenceState.UNMONITORED_UNKNOWN
            evidence_sufficiency = EvidenceSufficiency.INSUFFICIENT_DATA
            compact_explanation = "Corridor condition unknown; absent observations do not establish safety or dry pavement."
            explanation_codes.append("UNMONITORED_OR_MISSING_PRIMARY_FEEDS")
            is_traversable = True
            routing_penalty = 1.0

        # Contextual notes
        if rainfall_section.data_availability != "AVAILABLE":
            explanation_codes.append("RAINFALL_TELEMETRY_UNAVAILABLE_OR_OUTAGE")

        if forecast_section.forecast_source_status == "BLOCKED_NO_AUTHORIZED_FEED":
            explanation_codes.append("LIVE_FORECAST_FEED_BLOCKED_PENDING_MOU")

        if vision_section.is_inconclusive_abstention:
            explanation_codes.append("VISION_ABSTENTION_INCONCLUSIVE")

        # ----------------------------------------------------------------------
        # 9. Temporal Provenance Record
        # ----------------------------------------------------------------------
        source_timestamps = {
            "road_status_observation_utc": road_status_section.observation_timestamp_utc,
            "road_status_ingestion_utc": road_status_section.ingestion_timestamp_utc,
            "rainfall_observation_utc": rainfall_section.observation_timestamp_utc,
            "forecast_issue_utc": forecast_section.issue_timestamp_utc,
            "forecast_valid_utc": forecast_section.valid_timestamp_utc,
            "vision_inference_utc": vision_section.inference_timestamp_utc,
            "assessment_generated_utc": assessment_iso,
        }

        return CorridorEvidenceAssessment(
            corridor_id=corridor_id,
            road_name=road_name,
            zone=zone,
            assessment_timestamp_utc=assessment_iso,
            source_timestamps=source_timestamps,
            evidence_state=evidence_state,
            evidence_sufficiency=evidence_sufficiency,
            has_unresolved_conflicts=cross_conflict,
            explanation_codes=explanation_codes,
            compact_explanation=compact_explanation,
            road_status=road_status_section,
            community_reports=community_section,
            observed_rainfall=rainfall_section,
            forecast_rainfall=forecast_section,
            static_susceptibility=static_section,
            vision_evidence=vision_section,
            historical_inundation=HistoricalInundationEvidenceSection(),
            is_traversable_for_routing=is_traversable,
            routing_penalty_multiplier=routing_penalty,
            operational_action_authorized=False,  # MANDATORY INVARIANT
        )

    def assess_all_corridors(self) -> List[CorridorEvidenceAssessment]:
        """
        Generates canonical corridor evidence assessments for all road segments in the store catalog.
        """
        assessments: List[CorridorEvidenceAssessment] = []
        for seg in self.road_store.list_segments():
            cid = seg.corridor_id or seg.segment_id
            try:
                assessments.append(self.assess_corridor(corridor_id=cid, road_segment=seg))
            except Exception as e:
                logger.error(f"Failed to assess corridor {cid}: {e}")
        return assessments


# Default singleton instance
default_corridor_evidence_service = CorridorEvidenceService()
