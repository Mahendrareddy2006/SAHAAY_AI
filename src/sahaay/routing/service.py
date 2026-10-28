"""
Sahaay AI - Phase 19: Risk-Aware Routing Assessment Service
(src/sahaay/routing/service.py)

Implements an auditable, offline risk-aware route evaluation service that combines
Phase 16 live road status, Phase 17 static vulnerability, and Phase 18 forecast risk.
Strictly isolates evidence signals, excludes verified impassable segments, disarms
operational dispatch triggers, and prohibits uncalibrated probability or guaranteed safety claims.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any, List, Optional, Tuple

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadEvidenceType,
    RoadStatusSnapshot,
)
from sahaay.forecast_risk.schemas import (
    ForecastRiskAssessmentOutput,
    ForecastDataStatus,
)
from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestination,
    FacilityOperationalStatus,
    MANDATORY_SAFETY_DISCLAIMER,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    SegmentRoutingAssessment,
    RiskAwareRouteAssessment,
    MANDATORY_ROUTING_DISCLAIMER,
)

logger = logging.getLogger(__name__)


class RiskAwareRoutingService:
    """
    Offline risk-aware routing assessment engine.
    Evaluates candidate routes against verified ground status, citizen corroboration,
    forecast rainfall context, and static vulnerability without conflating their meanings.
    """

    def __init__(self):
        pass

    def assess_segment(
        self,
        segment_id: str,
        road_name: str,
        road_status: Optional[RoadStatusSnapshot] = None,
        forecast_risk: Optional[ForecastRiskAssessmentOutput] = None,
        static_vulnerability_index: Optional[float] = None,
        static_vulnerability_category: Optional[str] = None,
        length_meters: float = 500.0,
        vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
    ) -> SegmentRoutingAssessment:
        """
        Evaluates an individual corridor segment against separate evidence signals.
        """
        restriction_reasons: List[str] = []
        caution_notices: List[str] = []
        quality_flags: List[str] = []
        missing_inputs: List[str] = []

        # ----------------------------------------------------------------------
        # 1. Signal 1: Road Status Evidence (Phase 16)
        # ----------------------------------------------------------------------
        if road_status is not None:
            cond_state = road_status.condition_state
            ver_state = road_status.verification_state
            fresh_cat = road_status.freshness_category
            obs_age = road_status.evidence_age_minutes
            src = road_status.evidence_type.value if hasattr(road_status.evidence_type, "value") else str(road_status.evidence_type)
            has_conflict = road_status.has_conflicting_evidence
        else:
            cond_state = RoadConditionState.NO_CURRENT_EVIDENCE
            ver_state = RoadVerificationState.UNMONITORED
            fresh_cat = RoadFreshnessCategory.UNKNOWN
            obs_age = None
            src = "NONE_UNMONITORED"
            has_conflict = False
            missing_inputs.append("road_status_evidence")

        # ----------------------------------------------------------------------
        # 2. Signal 2: Forecast Rainfall Context (Phase 18)
        # ----------------------------------------------------------------------
        if forecast_risk is not None:
            fc_cat = forecast_risk.forecast_risk_category
            fc_score = forecast_risk.heuristic_risk_score
            fc_issue = forecast_risk.forecast_rainfall_context.get("issue_timestamp_utc") if forecast_risk.forecast_rainfall_context else None
            fc_valid = forecast_risk.forecast_rainfall_context.get("valid_timestamp_utc") if forecast_risk.forecast_rainfall_context else None
            fc_horizon = forecast_risk.forecast_horizon_hours
            fc_amount = forecast_risk.forecast_rainfall_context.get("rainfall_amount") if forecast_risk.forecast_rainfall_context else None
            
            # Phase 18 dispatch flag: strictly non-operational
            p18_actionable = forecast_risk.is_actionable_for_dispatch
            if p18_actionable:
                caution_notices.append("PHASE18_DISPATCH_FLAG_ADVISORY_ONLY_NOT_AUTHORIZED_FOR_OPERATIONS")
        else:
            fc_cat = "UNKNOWN"
            fc_score = None
            fc_issue = None
            fc_valid = None
            fc_horizon = None
            fc_amount = None
            p18_actionable = False
            missing_inputs.append("forecast_risk_context")

        # ----------------------------------------------------------------------
        # 3. Signal 3: Static Susceptibility Context (Phase 17)
        # ----------------------------------------------------------------------
        v_idx = static_vulnerability_index if static_vulnerability_index is not None else 0.10
        v_cat = static_vulnerability_category or "UNKNOWN"
        if static_vulnerability_index is None:
            missing_inputs.append("static_vulnerability_index")

        # ----------------------------------------------------------------------
        # 4. Passability Determination Logic
        # ----------------------------------------------------------------------
        is_traversable = True
        is_uncertain = False

        # Rule A: Officially Verified Impassable (Closure)
        if cond_state == RoadConditionState.VERIFIED_IMPASSABLE or (
            ver_state == RoadVerificationState.VERIFIED_BY_RESPONDER and cond_state in {RoadConditionState.VERIFIED_IMPASSABLE}
        ):
            pass_state = PassabilityAssessment.VERIFIED_IMPASSABLE
            is_traversable = False
            is_uncertain = False
            restriction_reasons.append("OFFICIAL_INSPECTION_CONFIRMS_ROAD_IMPASSABLE_OR_SUBMERGED")

        # Rule B: Conflicting Evidence
        elif has_conflict or cond_state == RoadConditionState.CONFLICTING:
            pass_state = PassabilityAssessment.CONFLICTING_EVIDENCE
            is_uncertain = True
            caution_notices.append("CONTRADICTORY_GROUND_REPORTS_PENDING_RECONCILIATION")

        # Rule C: Citizen Corroborated Hazard (Caution / Warning)
        elif cond_state in {RoadConditionState.CORROBORATED, RoadConditionState.VERIFIED_WATERLOGGED} or ver_state == RoadVerificationState.CORROBORATED:
            pass_state = PassabilityAssessment.CORROBORATED_HAZARD
            is_uncertain = True
            caution_notices.append("CITIZEN_CORROBORATED_WATERLOGGING_NOT_OFFICIALLY_VERIFIED")
            if vehicle_type in {VehicleType.TWO_WHEELER, VehicleType.THREE_WHEELER_AUTO}:
                caution_notices.append("LOW_CLEARANCE_VEHICLE_AT_ELEVATED_STALL_RISK")

        # Rule D: Officially Verified Passable
        elif cond_state == RoadConditionState.VERIFIED_PASSABLE and ver_state == RoadVerificationState.VERIFIED_BY_RESPONDER:
            pass_state = PassabilityAssessment.VERIFIED_PASSABLE
            is_traversable = True
            is_uncertain = False

        # Rule E: Stale or Expired Evidence
        elif fresh_cat in {RoadFreshnessCategory.STALE, RoadFreshnessCategory.EXPIRED} or cond_state in {RoadConditionState.STALE, RoadConditionState.EXPIRED}:
            pass_state = PassabilityAssessment.STALE_OR_EXPIRED
            is_uncertain = True
            caution_notices.append(f"ROAD_STATUS_OBSERVATION_IS_{fresh_cat.value}")

        # Rule F: Unverified Single Citizen Report
        elif cond_state == RoadConditionState.UNVERIFIED or ver_state == RoadVerificationState.UNVERIFIED:
            pass_state = PassabilityAssessment.UNVERIFIED_REPORT
            is_uncertain = True
            caution_notices.append("UNVERIFIED_SINGLE_CITIZEN_REPORT_AWAITING_CORROBORATION")

        # Rule G: Unmonitored / No Evidence (CRITICAL: Does NOT mean safe!)
        else:
            pass_state = PassabilityAssessment.UNMONITORED_NO_EVIDENCE
            is_uncertain = True
            caution_notices.append("NO_CURRENT_GROUND_OBSERVATION_DOES_NOT_IMPLY_SAFE_PASSAGE")

        # Contextual Notices: Forecast Rainfall Context (Forecast alone does not prove flooding!)
        if fc_cat in {"HIGH", "CRITICAL"}:
            caution_notices.append("FORECAST_SURGE_ADVISORY_ACTIVE_DOES_NOT_ESTABLISH_ACTIVE_INUNDATION")

        # Contextual Notices: Static Vulnerability Context (Static susceptibility alone is not active flooding!)
        if v_cat in {"HIGH", "SEVERE"}:
            caution_notices.append("STATIC_TOPOGRAPHIC_VULNERABILITY_ELEVATED_NOT_ACTIVE_FLOODING")

        return SegmentRoutingAssessment(
            segment_id=segment_id,
            road_name=road_name,
            length_meters=length_meters,
            passability_state=pass_state,
            is_traversable=is_traversable,
            is_uncertain=is_uncertain,
            condition_state=cond_state,
            verification_state=ver_state,
            freshness_category=fresh_cat,
            observation_age_minutes=obs_age,
            evidence_source=src,
            forecast_risk_category=fc_cat,
            forecast_rainfall_mm=fc_amount,
            forecast_issue_time_utc=fc_issue,
            forecast_valid_time_utc=fc_valid,
            forecast_horizon_hours=fc_horizon,
            forecast_heuristic_score=fc_score,
            is_calibrated_probability=False,
            phase18_dispatch_actionable=p18_actionable,
            static_vulnerability_index=v_idx,
            static_vulnerability_category=v_cat,
            is_static_susceptibility_only=True,
            quality_flags=quality_flags,
            missing_inputs=missing_inputs,
            restriction_reasons=sorted(list(set(restriction_reasons))),
            caution_notices=sorted(list(set(caution_notices))),
        )

    def evaluate_route(
        self,
        route_id: str,
        candidate_segments: List[SegmentRoutingAssessment],
        origin: Dict[str, float],
        destination: Dict[str, float],
        vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
        target_facility: Optional[EmergencyDestination] = None,
        reference_time_utc: Optional[datetime] = None,
    ) -> RiskAwareRouteAssessment:
        """
        Evaluates a sequence of candidate segments for risk-aware route traversal.
        Excludes verified impassable segments and transparently communicates uncertainties.
        """
        now_utc = reference_time_utc or datetime.now(timezone.utc)
        now_iso = now_utc.isoformat().replace("+00:00", "Z")

        warnings: List[str] = []
        exclusion_explanations: List[str] = []

        recommended: List[SegmentRoutingAssessment] = []
        excluded: List[SegmentRoutingAssessment] = []

        # Triage segments: exclude verified impassable
        for seg in candidate_segments:
            if not seg.is_traversable or seg.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE:
                excluded.append(seg)
                exclusion_explanations.append(
                    f"Segment {seg.segment_id} ({seg.road_name}) is excluded from the recommended path: "
                    f"Verified impassable by official field inspection."
                )
            else:
                recommended.append(seg)

        # Handle empty or fully blocked scenarios
        if not candidate_segments:
            return RiskAwareRouteAssessment(
                route_id=route_id,
                assessment_timestamp_utc=now_iso,
                outcome=RouteAssessmentOutcome.UNCERTAIN_INSUFFICIENT_DATA,
                origin=origin,
                destination=destination,
                vehicle_type=vehicle_type,
                target_facility=target_facility,
                total_distance_meters=0.0,
                estimated_duration_seconds=0.0,
                aggregate_heuristic_risk=0.50,
                recommended_segments=[],
                excluded_segments=[],
                impassable_segments_count=0,
                unmonitored_segments_count=0,
                stale_or_conflicting_segments_count=0,
                has_unmonitored_segments=False,
                is_optimality_claimed=False,
                is_guaranteed_safe=False,
                operational_action_authorized=False,
                warnings=["No candidate road segments provided for evaluation."],
                exclusion_explanations=[],
                safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
                engine_status="OFFLINE_INSUFFICIENT_INPUTS",
            )

        if not recommended and excluded:
            return RiskAwareRouteAssessment(
                route_id=route_id,
                assessment_timestamp_utc=now_iso,
                outcome=RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE,
                origin=origin,
                destination=destination,
                vehicle_type=vehicle_type,
                target_facility=target_facility,
                total_distance_meters=0.0,
                estimated_duration_seconds=0.0,
                aggregate_heuristic_risk=1.0,
                recommended_segments=[],
                excluded_segments=excluded,
                impassable_segments_count=len(excluded),
                unmonitored_segments_count=0,
                stale_or_conflicting_segments_count=0,
                has_unmonitored_segments=False,
                is_optimality_claimed=False,
                is_guaranteed_safe=False,
                operational_action_authorized=False,
                warnings=["All candidate corridors are verified impassable due to verified flood inundation."],
                exclusion_explanations=exclusion_explanations,
                safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
                engine_status="OFFLINE_ALL_PATHS_IMPASSABLE",
            )

        # Segment counts on recommended path
        unmonitored_count = sum(
            1 for s in recommended
            if s.passability_state == PassabilityAssessment.UNMONITORED_NO_EVIDENCE
            or s.condition_state == RoadConditionState.NO_CURRENT_EVIDENCE
            or s.verification_state == RoadVerificationState.UNMONITORED
        )
        stale_conflicting_count = sum(
            1 for s in recommended
            if s.passability_state in {
                PassabilityAssessment.STALE_OR_EXPIRED,
                PassabilityAssessment.CONFLICTING_EVIDENCE,
                PassabilityAssessment.CORROBORATED_HAZARD,
            }
        )
        has_unmonitored = unmonitored_count > 0

        if has_unmonitored:
            warnings.append(
                f"Route traverses {unmonitored_count} unmonitored segments with no active ground evidence. "
                "Absence of reported flooding does NOT indicate dry or safe roads."
            )

        if stale_conflicting_count > 0:
            warnings.append(
                f"Route traverses {stale_conflicting_count} segments with stale, expired, or conflicting evidence."
            )

        if excluded:
            warnings.append(
                f"{len(excluded)} candidate segments were excluded due to verified impassable flooding."
            )

        # Facility Access Check
        if target_facility is not None:
            if target_facility.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED:
                warnings.append(
                    f"Target emergency facility {target_facility.name} has inundated and restricted access. "
                    "Proceed with extreme caution or coordinate with emergency services."
                )

        # Distances and Durations (heuristic estimates without topological routing)
        total_dist = sum(s.length_meters for s in recommended)
        total_duration = round(total_dist / 6.94, 1)

        # Aggregate heuristic risk score
        risk_scores = [s.forecast_heuristic_score for s in recommended if s.forecast_heuristic_score is not None]
        vuln_scores = [s.static_vulnerability_index for s in recommended if s.static_vulnerability_index is not None]
        avg_fc_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.15
        avg_vuln = sum(vuln_scores) / len(vuln_scores) if vuln_scores else 0.20
        agg_risk = round(min(1.0, 0.60 * avg_fc_risk + 0.40 * avg_vuln), 3)

        outcome = RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
        if excluded:
            outcome = RouteAssessmentOutcome.BLOCKED_IMPASSABLE_SEGMENTS_PRESENT

        return RiskAwareRouteAssessment(
            route_id=route_id,
            assessment_timestamp_utc=now_iso,
            outcome=outcome,
            origin=origin,
            destination=destination,
            vehicle_type=vehicle_type,
            target_facility=target_facility,
            total_distance_meters=total_dist,
            estimated_duration_seconds=total_duration,
            aggregate_heuristic_risk=agg_risk,
            recommended_segments=recommended,
            excluded_segments=excluded,
            impassable_segments_count=len(excluded),
            unmonitored_segments_count=unmonitored_count,
            stale_or_conflicting_segments_count=stale_conflicting_count,
            has_unmonitored_segments=has_unmonitored,
            is_optimality_claimed=False,
            is_guaranteed_safe=False,
            operational_action_authorized=False,
            warnings=warnings,
            exclusion_explanations=exclusion_explanations,
            safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
            engine_status="OFFLINE_RISK_AWARE_EVALUATION_LAYER",
        )
