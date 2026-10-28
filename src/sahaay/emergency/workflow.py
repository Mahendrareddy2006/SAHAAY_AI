"""
Sahaay AI - Phase 20: Emergency Workflow Engine
(src/sahaay/emergency/workflow.py)

Implements the offline emergency assessment workflow engine.
Prioritizes urgent reports deterministically, tracks state transitions,
enforces role-based resolution checks, and disarms autonomous side effects.
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadStatusSnapshot,
)
from sahaay.forecast_risk.schemas import (
    ForecastRiskAssessmentOutput,
)
from sahaay.routing.contracts import (
    FacilityOperationalStatus,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    RiskAwareRouteAssessment,
)
from sahaay.emergency.schemas import (
    EmergencyState,
    EmergencyPriority,
    AuthorizedReviewerRole,
    EmergencyResolutionRecord,
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
    MANDATORY_EMERGENCY_MODE_DISCLAIMER,
)

logger = logging.getLogger(__name__)


# Allowed State Machine Transitions
VALID_STATE_TRANSITIONS = {
    EmergencyState.INACTIVE: {
        EmergencyState.ACTIVE_ASSESSMENT,
        EmergencyState.NEEDS_HUMAN_REVIEW,
        EmergencyState.DEGRADED_INSUFFICIENT_DATA,
    },
    EmergencyState.ACTIVE_ASSESSMENT: {
        EmergencyState.NEEDS_HUMAN_REVIEW,
        EmergencyState.DEGRADED_INSUFFICIENT_DATA,
        EmergencyState.INACTIVE,
    },
    EmergencyState.NEEDS_HUMAN_REVIEW: {
        EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW,
        EmergencyState.DEGRADED_INSUFFICIENT_DATA,
    },
    EmergencyState.DEGRADED_INSUFFICIENT_DATA: {
        EmergencyState.NEEDS_HUMAN_REVIEW,
        EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW,
    },
    EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW: {
        EmergencyState.INACTIVE,
    },
}


class EmergencyWorkflowEngine:
    """
    Offline emergency assessment workflow coordinator.
    Enforces auditable state transitions, role-based review resolution,
    and deterministic triage prioritization without autonomous external side-effects.
    """

    def __init__(self):
        pass

    def evaluate_emergency_assessment(
        self,
        input_data: EmergencyAssessmentInput,
        previous_assessment: Optional[EmergencyModeAssessment] = None,
        reference_time_utc: Optional[datetime] = None,
    ) -> EmergencyModeAssessment:
        """
        Evaluates incoming multi-source evidence and determines the emergency assessment state
        and review priority.
        """
        now_utc = reference_time_utc or datetime.now(timezone.utc)
        now_iso = now_utc.isoformat().replace("+00:00", "Z")

        priority_reasons: List[str] = []
        missing_inputs: List[str] = []
        quality_flags: List[str] = []

        # ----------------------------------------------------------------------
        # 1. Compile & Separate Evidence Channels
        # ----------------------------------------------------------------------
        # Context 1: Ground Road Status Evidence
        if input_data.road_status_snapshot:
            snap = input_data.road_status_snapshot
            ground_evidence = {
                "condition_state": snap.condition_state.value,
                "verification_state": snap.verification_state.value,
                "freshness_category": snap.freshness_category.value,
                "evidence_age_minutes": snap.evidence_age_minutes,
                "measured_water_depth_cm": snap.measured_water_depth_cm,
                "has_conflicting_evidence": snap.has_conflicting_evidence,
                "source_modality": snap.evidence_type.value,
            }
        else:
            ground_evidence = {
                "condition_state": "NO_CURRENT_EVIDENCE",
                "verification_state": "UNMONITORED",
                "freshness_category": "UNKNOWN",
                "evidence_age_minutes": None,
                "measured_water_depth_cm": None,
                "has_conflicting_evidence": False,
                "source_modality": "NONE",
            }
            missing_inputs.append("ground_road_status_evidence")

        # Context 2: Forecast Rainfall Context
        if input_data.forecast_risk_output:
            fc = input_data.forecast_risk_output
            forecast_context = {
                "assessment_status": fc.assessment_status.value,
                "forecast_risk_category": fc.forecast_risk_category,
                "heuristic_risk_score": fc.heuristic_risk_score,
                "forecast_horizon_hours": fc.forecast_horizon_hours,
                "is_calibrated_probability": False,
                "source_id": fc.forecast_rainfall_context.get("source_id") if fc.forecast_rainfall_context else None,
                "rainfall_amount": fc.forecast_rainfall_context.get("rainfall_amount") if fc.forecast_rainfall_context else None,
            }
        else:
            forecast_context = {
                "assessment_status": "UNKNOWN",
                "forecast_risk_category": "UNKNOWN",
                "heuristic_risk_score": None,
                "is_calibrated_probability": False,
            }
            missing_inputs.append("forecast_rainfall_context")

        # Context 3: Static Susceptibility Context
        v_idx = input_data.static_vulnerability_index if input_data.static_vulnerability_index is not None else 0.10
        v_cat = input_data.static_vulnerability_category or "UNKNOWN"
        if input_data.static_vulnerability_index is None:
            missing_inputs.append("static_vulnerability_index")

        static_context = {
            "vulnerability_index": v_idx,
            "vulnerability_category": v_cat,
            "is_static_only": True,
        }

        # Context 4: Routing Impact Context
        if input_data.route_assessment_output:
            rte = input_data.route_assessment_output
            routing_context = {
                "route_outcome": rte.outcome.value,
                "impassable_segments_count": rte.impassable_segments_count,
                "has_unmonitored_segments": rte.has_unmonitored_segments,
                "target_facility_restricted": (
                    rte.target_facility is not None
                    and rte.target_facility.operational_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED
                ),
            }
        else:
            routing_context = {
                "route_outcome": "UNASSESSED",
                "impassable_segments_count": 0,
                "has_unmonitored_segments": False,
                "target_facility_restricted": False,
            }

        # ----------------------------------------------------------------------
        # 2. Deterministic Prioritization & Urgency Heuristics
        # ----------------------------------------------------------------------
        cond = ground_evidence["condition_state"]
        ver = ground_evidence["verification_state"]
        fresh = ground_evidence["freshness_category"]
        depth = ground_evidence["measured_water_depth_cm"]
        conflict = ground_evidence["has_conflicting_evidence"]
        target_restricted = routing_context["target_facility_restricted"]
        fc_cat = forecast_context["forecast_risk_category"]

        # Rule 1: Degraded Mode Trigger (Conflicting or Stale evidence)
        if conflict or cond == RoadConditionState.CONFLICTING.value:
            priority = EmergencyPriority.P0_DEGRADED_TRIAGE
            urgency = 0.40
            certainty = "UNCERTAIN"
            state = EmergencyState.DEGRADED_INSUFFICIENT_DATA
            priority_reasons.append("CONTRADICTORY_EVIDENCE_REQUIRES_DATA_TRIAGE")
            quality_flags.append("CONFLICTING_REPORTS")

        elif fresh in {RoadFreshnessCategory.EXPIRED.value} or cond == RoadConditionState.EXPIRED.value:
            priority = EmergencyPriority.P0_DEGRADED_TRIAGE
            urgency = 0.35
            certainty = "UNCERTAIN"
            state = EmergencyState.DEGRADED_INSUFFICIENT_DATA
            priority_reasons.append("ROAD_STATUS_EVIDENCE_EXPIRED")
            quality_flags.append("EXPIRED_TELEMETRY")

        # Rule 2: Priority P1 Urgent Verified (Immediate Human Review)
        elif (
            cond == RoadConditionState.VERIFIED_IMPASSABLE.value
            or (depth is not None and depth >= 30.0 and ver == RoadVerificationState.VERIFIED_BY_RESPONDER.value)
            or target_restricted
        ):
            priority = EmergencyPriority.P1_URGENT_VERIFIED
            urgency = 0.95
            certainty = "VERIFIED"
            state = EmergencyState.NEEDS_HUMAN_REVIEW
            if cond == RoadConditionState.VERIFIED_IMPASSABLE.value:
                priority_reasons.append("VERIFIED_IMPASSABLE_FLOODING_BY_RESPONDER")
            if target_restricted:
                priority_reasons.append("EMERGENCY_HOSPITAL_ACCESS_INUNDATED_AND_RESTRICTED")
            if depth is not None and depth >= 30.0:
                priority_reasons.append(f"VERIFIED_DEEP_WATER_MEASUREMENT_{depth}CM")

        # Rule 3: Priority P2 High Corroborated
        elif (
            cond in {RoadConditionState.CORROBORATED.value, RoadConditionState.VERIFIED_WATERLOGGED.value}
            or ver == RoadVerificationState.CORROBORATED.value
            or (fc_cat in {"HIGH", "CRITICAL"} and v_cat in {"HIGH", "SEVERE"})
        ):
            priority = EmergencyPriority.P2_HIGH_CORROBORATED
            urgency = 0.75
            certainty = "CORROBORATED" if ver == RoadVerificationState.CORROBORATED.value else "PREDICTED_RISK"
            state = EmergencyState.NEEDS_HUMAN_REVIEW
            if ver == RoadVerificationState.CORROBORATED.value:
                priority_reasons.append("CORROBORATED_CITIZEN_REPORTS_OF_WATERLOGGING")
            if fc_cat in {"HIGH", "CRITICAL"} and v_cat in {"HIGH", "SEVERE"}:
                priority_reasons.append("CRITICAL_FORECAST_RAIN_SURGE_ON_SEVERELY_VULNERABLE_CORRIDOR")

        # Rule 4: Priority P3 Medium Unverified
        elif cond == RoadConditionState.UNVERIFIED.value or ver == RoadVerificationState.UNVERIFIED.value:
            priority = EmergencyPriority.P3_MEDIUM_UNVERIFIED
            urgency = 0.50
            certainty = "UNVERIFIED"
            state = EmergencyState.NEEDS_HUMAN_REVIEW
            priority_reasons.append("UNVERIFIED_SINGLE_CITIZEN_REPORT_AWAITING_FIELD_CHECK")

        # Rule 5: Priority P4 Low Advisory
        else:
            priority = EmergencyPriority.P4_LOW_ADVISORY
            urgency = 0.10
            certainty = "UNKNOWN"
            state = EmergencyState.ACTIVE_ASSESSMENT
            priority_reasons.append("BASELINE_ENVIRONMENTAL_MONITORING_NO_ACTIVE_URGENCY")

        # ----------------------------------------------------------------------
        # 3. State History & Transitions
        # ----------------------------------------------------------------------
        history = list(previous_assessment.state_transition_history) if previous_assessment else []
        prev_state = previous_assessment.current_state if previous_assessment else EmergencyState.INACTIVE

        if prev_state != state:
            # Validate allowed transition
            allowed = VALID_STATE_TRANSITIONS.get(prev_state, set())
            if state not in allowed:
                # If direct transition is not valid, default to NEEDS_HUMAN_REVIEW
                state = EmergencyState.NEEDS_HUMAN_REVIEW

            history.append({
                "from_state": prev_state.value,
                "to_state": state.value,
                "timestamp_utc": now_iso,
                "reason": priority_reasons[0] if priority_reasons else "STATE_MACHINE_TRANSITION",
            })

        return EmergencyModeAssessment(
            incident_id=input_data.incident_id,
            corridor_id=input_data.corridor_id,
            road_name=input_data.road_name,
            assessment_timestamp_utc=now_iso,
            current_state=state,
            state_transition_history=history,
            review_priority=priority,
            priority_reason_codes=sorted(list(set(priority_reasons))),
            urgency_heuristic_score=round(urgency, 3),
            is_calibrated_probability=False,
            evidence_certainty_level=certainty,
            ground_status_evidence=ground_evidence,
            forecast_rainfall_context=forecast_context,
            static_susceptibility_context=static_context,
            routing_impact_context=routing_context,
            resolution_record=None,
            missing_critical_inputs=missing_inputs,
            quality_flags=quality_flags,
            operational_action_authorized=False,
            external_side_effects_triggered=False,
            personal_data_masked=True,
            safety_disclaimer=MANDATORY_EMERGENCY_MODE_DISCLAIMER,
            engine_status="OFFLINE_EMERGENCY_TRIAGE_LAYER",
        )

    def resolve_emergency(
        self,
        assessment: EmergencyModeAssessment,
        reviewer_role: AuthorizedReviewerRole,
        reviewer_id: str,
        action_type: str,
        justification_notes: str,
        reference_time_utc: Optional[datetime] = None,
    ) -> EmergencyModeAssessment:
        """
        Records an authorized human review action that resolves an active emergency mode.
        Requires an AuthorizedReviewerRole and substantive justification notes (>= 10 chars).
        Computes SHA-256 cryptographic audit hash.
        """
        now_utc = reference_time_utc or datetime.now(timezone.utc)
        now_iso = now_utc.isoformat().replace("+00:00", "Z")

        # 1. State check: must be in a resolvable state
        if assessment.current_state not in {
            EmergencyState.NEEDS_HUMAN_REVIEW,
            EmergencyState.DEGRADED_INSUFFICIENT_DATA,
            EmergencyState.ACTIVE_ASSESSMENT,
        }:
            raise ValueError(
                f"Cannot resolve assessment in state {assessment.current_state.value}. "
                "Assessment must be in NEEDS_HUMAN_REVIEW, DEGRADED_INSUFFICIENT_DATA, or ACTIVE_ASSESSMENT."
            )

        # 2. Role authorization check
        if not isinstance(reviewer_role, AuthorizedReviewerRole):
            raise PermissionError(f"Reviewer role '{reviewer_role}' is not an authorized municipal reviewer.")

        # 3. Justification check
        if not justification_notes or len(justification_notes.strip()) < 10:
            raise ValueError("Substantive justification notes (minimum 10 characters) are required for resolution.")

        # 4. Generate Resolution Record with Cryptographic Hash
        res_id = f"RES-{hashlib.md5(f'{assessment.incident_id}{now_iso}'.encode()).hexdigest()[:10].upper()}"
        last_hash = (
            assessment.state_transition_history[-1].get("reason", "GENESIS_PHASE20")
            if assessment.state_transition_history
            else "GENESIS_PHASE20"
        )
        resolution = EmergencyResolutionRecord.create(
            resolution_id=res_id,
            reviewer_role=reviewer_role,
            reviewer_id=reviewer_id,
            action_type=action_type,
            justification_notes=justification_notes.strip(),
            timestamp_utc=now_iso,
            previous_hash=last_hash,
        )

        # 5. Transition to RESOLVED_BY_AUTHORIZED_REVIEW
        new_history = list(assessment.state_transition_history)
        new_history.append({
            "from_state": assessment.current_state.value,
            "to_state": EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW.value,
            "timestamp_utc": now_iso,
            "reason": f"RESOLVED_BY_HUMAN_OPERATOR_{reviewer_role.value}:{action_type}",
            "audit_hash": resolution.audit_hash,
        })

        return EmergencyModeAssessment(
            incident_id=assessment.incident_id,
            corridor_id=assessment.corridor_id,
            road_name=assessment.road_name,
            assessment_timestamp_utc=now_iso,
            current_state=EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW,
            state_transition_history=new_history,
            review_priority=assessment.review_priority,
            priority_reason_codes=assessment.priority_reason_codes,
            urgency_heuristic_score=assessment.urgency_heuristic_score,
            is_calibrated_probability=False,
            evidence_certainty_level=assessment.evidence_certainty_level,
            ground_status_evidence=assessment.ground_status_evidence,
            forecast_rainfall_context=assessment.forecast_rainfall_context,
            static_susceptibility_context=assessment.static_susceptibility_context,
            routing_impact_context=assessment.routing_impact_context,
            resolution_record=resolution,
            missing_critical_inputs=assessment.missing_critical_inputs,
            quality_flags=assessment.quality_flags,
            operational_action_authorized=False,
            external_side_effects_triggered=False,
            personal_data_masked=True,
            safety_disclaimer=MANDATORY_EMERGENCY_MODE_DISCLAIMER,
            engine_status="RESOLVED_AUDITED_OFFLINE",
        )

    def attempt_auto_resolve_on_timeout(self, assessment: EmergencyModeAssessment) -> None:
        """
        SAFETY RULE: Automatic resolution of an emergency from timeouts, absence of reports,
        or telemetry silence is strictly prohibited.
        """
        raise RuntimeError(
            "SAFETY VIOLATION: Automatic resolution of emergency mode on timeout or telemetry silence "
            "is strictly prohibited. Resolution requires authorized human review."
        )
