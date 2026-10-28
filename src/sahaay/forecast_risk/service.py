"""
Sahaay AI - Phase 18: Forecast Risk Assessment Service
(src/sahaay/forecast_risk/service.py)

Implements an auditable, transparent assessment service that combines forecast rainfall context
with existing vulnerability information without conflating their meanings.
Strictly separates five distinct traceable evidence signals and enforces fail-closed safety.
"""

from datetime import datetime, timezone, timedelta
import logging
import math
from typing import Dict, Any, List, Optional, Tuple

from sahaay.forecast_risk.schemas import (
    ForecastRainfallInput,
    ObservedRainfallContext,
    StaticVulnerabilityContext,
    CurrentRoadStatusContext,
    ForecastRiskAssessmentOutput,
    ForecastDataStatus,
    ForecastQualityFlag,
    MANDATORY_FORECAST_RISK_DISCLAIMER,
)
from sahaay.road_status.schemas import RoadConditionState, RoadVerificationState

logger = logging.getLogger(__name__)

# Operational freshness limits for precipitation forecast models
MAX_NWP_FORECAST_AGE_HOURS = 6.0
MAX_NOWCAST_FORECAST_AGE_HOURS = 1.5
MAX_SUITABLE_SPATIAL_RESOLUTION_KM = 15.0


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


class ForecastRiskAssessmentService:
    """
    Experimental forecast-risk assessment layer.
    Combines meteorological forecast context with static susceptibility while strictly
    isolating observed ground truth and historical outcomes.
    """

    def __init__(self):
        pass

    def evaluate_forecast_risk(
        self,
        segment_id: str,
        road_name: str,
        forecast_inputs: Optional[List[ForecastRainfallInput]] = None,
        observed_context: Optional[ObservedRainfallContext] = None,
        vulnerability_context: Optional[StaticVulnerabilityContext] = None,
        road_status_context: Optional[CurrentRoadStatusContext] = None,
        reference_time_utc: Optional[datetime] = None,
    ) -> ForecastRiskAssessmentOutput:
        """
        Evaluates localized forward-looking flood risk from forecast inputs and static vulnerability.
        """
        now_utc = reference_time_utc or datetime.now(timezone.utc)
        now_iso = now_utc.isoformat().replace("+00:00", "Z")

        quality_flags: List[str] = []
        missing_inputs: List[str] = []
        reason_codes: List[str] = []

        # ----------------------------------------------------------------------
        # Context 1 & 2: Static Susceptibility & Observed Ground Truth
        # ----------------------------------------------------------------------
        v_idx = vulnerability_context.vulnerability_index if vulnerability_context and vulnerability_context.vulnerability_index is not None else 0.10
        v_cat = vulnerability_context.vulnerability_category if vulnerability_context else "UNKNOWN"
        if vulnerability_context is None or vulnerability_context.vulnerability_index is None:
            missing_inputs.append("static_vulnerability")

        static_context_dict = {
            "segment_id": segment_id,
            "vulnerability_index": round(v_idx, 3),
            "vulnerability_category": v_cat,
        }

        # Current Road Status Context (strictly decoupled)
        cond_state = road_status_context.condition_state if road_status_context else RoadConditionState.NO_CURRENT_EVIDENCE
        ver_state = road_status_context.verification_state if road_status_context else RoadVerificationState.UNMONITORED
        road_status_dict = {
            "condition_state": cond_state.value if hasattr(cond_state, "value") else str(cond_state),
            "verification_state": ver_state.value if hasattr(ver_state, "value") else str(ver_state),
            "observation_age_minutes": road_status_context.observation_age_minutes if road_status_context else None,
        }

        # Observed Rainfall Context (strictly decoupled)
        obs_rain_dict = {
            "observed_1h_mm": observed_context.observed_1h_mm if observed_context else None,
            "observed_3h_mm": observed_context.observed_3h_mm if observed_context else None,
            "telemetry_source_id": observed_context.telemetry_source_id if observed_context else None,
            "telemetry_distance_km": observed_context.telemetry_distance_km if observed_context else None,
            "telemetry_freshness_hours": observed_context.telemetry_freshness_hours if observed_context else None,
        }

        # Verified Historical Outcomes Context (strictly documented as 0)
        historical_outcomes_dict = {
            "verified_historical_flood_events_count": 0,
            "verified_historical_controls_count": 0,
            "status": "ZERO_VERIFIED_OUTCOMES_ON_DISK",
        }

        # ----------------------------------------------------------------------
        # Context 3: Forecast Rainfall Analysis
        # ----------------------------------------------------------------------
        # Scenario: Missing Forecast Data
        if not forecast_inputs:
            missing_inputs.append("forecast_rainfall_input")
            reason_codes.append("FORECAST_DATA_MISSING_MARKED_INSUFFICIENT")
            quality_flags.append(ForecastQualityFlag.MISSING_TELEMETRY.value)

            return ForecastRiskAssessmentOutput(
                segment_id=segment_id,
                road_name=road_name,
                assessment_status=ForecastDataStatus.INSUFFICIENT_DATA,
                assessment_timestamp_utc=now_iso,
                forecast_horizon_hours=None,
                forecast_rainfall_context=None,
                observed_rainfall_context=obs_rain_dict,
                static_susceptibility_context=static_context_dict,
                current_road_status_context=road_status_dict,
                verified_historical_outcomes_context=historical_outcomes_dict,
                forecast_risk_category="INSUFFICIENT_DATA",
                heuristic_risk_score=None,
                is_calibrated_probability=False,
                confidence_score=0.10,
                uncertainty_level="HIGH",
                data_quality_flags=quality_flags,
                missing_inputs=missing_inputs,
                reason_codes=sorted(list(set(reason_codes))),
                safety_disclaimer=MANDATORY_FORECAST_RISK_DISCLAIMER,
                is_actionable_for_dispatch=False,
            )

        # Check for multiple forecast inputs (Conflict Detection)
        valid_inputs: List[ForecastRainfallInput] = []
        for fc in forecast_inputs:
            # Check issue time vs reference time
            issue_dt = parse_iso_utc(fc.issue_timestamp_utc)
            if issue_dt and issue_dt > now_utc + timedelta(seconds=60):
                quality_flags.append("FUTURE_ISSUE_TIMESTAMP_REJECTED")
                reason_codes.append("FUTURE_ISSUE_TIMESTAMP_REJECTED")
                continue

            valid_inputs.append(fc)

        if not valid_inputs:
            missing_inputs.append("valid_forecast_inputs")
            reason_codes.append("ALL_FORECAST_INPUTS_INVALID_OR_QUARANTINED")
            return ForecastRiskAssessmentOutput(
                segment_id=segment_id,
                road_name=road_name,
                assessment_status=ForecastDataStatus.INSUFFICIENT_DATA,
                assessment_timestamp_utc=now_iso,
                forecast_horizon_hours=None,
                forecast_rainfall_context=None,
                observed_rainfall_context=obs_rain_dict,
                static_susceptibility_context=static_context_dict,
                current_road_status_context=road_status_dict,
                verified_historical_outcomes_context=historical_outcomes_dict,
                forecast_risk_category="INSUFFICIENT_DATA",
                heuristic_risk_score=None,
                is_calibrated_probability=False,
                confidence_score=0.10,
                uncertainty_level="HIGH",
                data_quality_flags=quality_flags,
                missing_inputs=missing_inputs,
                reason_codes=sorted(list(set(reason_codes))),
                safety_disclaimer=MANDATORY_FORECAST_RISK_DISCLAIMER,
                is_actionable_for_dispatch=False,
            )

        # Conflict Detection across multiple sources
        has_conflict = False
        if len(valid_inputs) >= 2:
            amounts = [fc.rainfall_amount for fc in valid_inputs if fc.rainfall_amount is not None]
            if len(amounts) >= 2 and (max(amounts) - min(amounts) > 20.0):
                has_conflict = True
                quality_flags.append(ForecastQualityFlag.TEMPORALLY_INCONSISTENT.value)
                reason_codes.append("CONFLICTING_FORECASTS_DETECTED")

        # Primary Forecast Input (first or newest valid)
        primary_fc = valid_inputs[0]
        issue_dt = parse_iso_utc(primary_fc.issue_timestamp_utc)
        valid_dt = parse_iso_utc(primary_fc.valid_timestamp_utc)

        # Freshness / Staleness check
        is_stale = False
        if issue_dt:
            age_hours = (now_utc - issue_dt).total_seconds() / 3600.0
            max_age = MAX_NOWCAST_FORECAST_AGE_HOURS if primary_fc.source_type.value == "RADAR_NOWCAST" else MAX_NWP_FORECAST_AGE_HOURS
            if age_hours > max_age:
                is_stale = True
                quality_flags.append(ForecastQualityFlag.STALE.value)
                reason_codes.append("FORECAST_ISSUE_STALE")

        # Spatial Suitability check
        is_spatially_unsuitable = False
        if primary_fc.spatial_resolution_km and primary_fc.spatial_resolution_km > MAX_SUITABLE_SPATIAL_RESOLUTION_KM:
            is_spatially_unsuitable = True
            quality_flags.append(ForecastQualityFlag.SPATIALLY_UNSUITABLE.value)
            reason_codes.append("SPATIAL_RESOLUTION_TOO_COARSE_FOR_CORRIDOR")

        # Compile Forecast Context Dict
        fc_context_dict = {
            "source_id": primary_fc.source_id,
            "source_type": primary_fc.source_type.value,
            "issue_timestamp_utc": primary_fc.issue_timestamp_utc,
            "valid_timestamp_utc": primary_fc.valid_timestamp_utc,
            "forecast_horizon_hours": primary_fc.forecast_horizon_hours,
            "rainfall_amount": primary_fc.rainfall_amount,
            "rainfall_units": primary_fc.rainfall_units.value,
            "accumulation_interval": primary_fc.accumulation_interval.value,
            "is_instantaneous_rate": primary_fc.is_instantaneous_rate,
            "spatial_resolution_km": primary_fc.spatial_resolution_km,
            "is_synthetic_fixture": primary_fc.is_synthetic_fixture,
        }

        # ----------------------------------------------------------------------
        # Determine Assessment Status & Heuristic Scoring
        # ----------------------------------------------------------------------
        if primary_fc.rainfall_amount is None:
            status = ForecastDataStatus.INSUFFICIENT_DATA
            category = "INSUFFICIENT_DATA"
            score = None
            conf = 0.10
            uncertainty = "HIGH"
            reason_codes.append("FORECAST_PRECIPITATION_AMOUNT_NULL")
        elif has_conflict:
            status = ForecastDataStatus.CONFLICTING
            category = "UNKNOWN"
            score = None
            conf = 0.25
            uncertainty = "HIGH"
        elif is_stale:
            status = ForecastDataStatus.STALE
            # Stale forecasts are advisory only and cannot yield critical scores
            conf = 0.35
            uncertainty = "HIGH"
            raw_fc = primary_fc.rainfall_amount
            score = min(1.0, raw_fc * 0.02)
            category = "LOW" if score < 0.30 else "MEDIUM"
        elif is_spatially_unsuitable:
            status = ForecastDataStatus.SPATIALLY_UNSUITABLE
            conf = 0.40
            uncertainty = "HIGH"
            raw_fc = primary_fc.rainfall_amount
            score = min(1.0, raw_fc * 0.02)
            category = "MEDIUM" if score >= 0.40 else "LOW"
        else:
            status = ForecastDataStatus.AVAILABLE_VALID
            raw_fc = primary_fc.rainfall_amount
            
            # Heuristic forecast risk combination
            # Rainfall intensity scaled by static susceptibility
            if raw_fc <= 2.5:
                # Trace rain: negligible risk
                score = 0.05
                category = "CLEAR"
                conf = 0.85
                uncertainty = "LOW"
            elif raw_fc <= 15.0:
                score = (raw_fc * 0.02) * (0.70 + 0.30 * v_idx)
                category = "LOW" if score < 0.25 else "MEDIUM"
                conf = 0.80
                uncertainty = "MEDIUM"
            elif raw_fc <= 35.0:
                score = min(1.0, (raw_fc * 0.02) * (0.60 + 0.40 * v_idx))
                category = "HIGH" if score >= 0.50 else "MEDIUM"
                conf = 0.75
                uncertainty = "MEDIUM"
            else:
                score = min(1.0, (raw_fc * 0.025) * (0.50 + 0.50 * v_idx))
                category = "CRITICAL"
                conf = 0.75
                uncertainty = "LOW"

        # Actionability: only if HIGH/CRITICAL and valid status with conf >= 0.50
        actionable = (category in {"HIGH", "CRITICAL"}) and (status == ForecastDataStatus.AVAILABLE_VALID) and (conf >= 0.50)

        return ForecastRiskAssessmentOutput(
            segment_id=segment_id,
            road_name=road_name,
            assessment_status=status,
            assessment_timestamp_utc=now_iso,
            forecast_horizon_hours=primary_fc.forecast_horizon_hours,
            forecast_rainfall_context=fc_context_dict,
            observed_rainfall_context=obs_rain_dict,
            static_susceptibility_context=static_context_dict,
            current_road_status_context=road_status_dict,
            verified_historical_outcomes_context=historical_outcomes_dict,
            forecast_risk_category=category,
            heuristic_risk_score=round(score, 3) if score is not None else None,
            is_calibrated_probability=False,
            confidence_score=round(conf, 3),
            uncertainty_level=uncertainty,
            data_quality_flags=quality_flags,
            missing_inputs=missing_inputs,
            reason_codes=sorted(list(set(reason_codes))),
            safety_disclaimer=MANDATORY_FORECAST_RISK_DISCLAIMER,
            is_actionable_for_dispatch=actionable,
        )


def evaluate_forecast_risk(
    segment_id: str,
    road_name: str,
    forecast_inputs: Optional[List[ForecastRainfallInput]] = None,
    observed_context: Optional[ObservedRainfallContext] = None,
    vulnerability_context: Optional[StaticVulnerabilityContext] = None,
    road_status_context: Optional[CurrentRoadStatusContext] = None,
    reference_time_utc: Optional[datetime] = None,
) -> ForecastRiskAssessmentOutput:
    """Convenience helper for evaluating forecast risk."""
    svc = ForecastRiskAssessmentService()
    return svc.evaluate_forecast_risk(
        segment_id=segment_id,
        road_name=road_name,
        forecast_inputs=forecast_inputs,
        observed_context=observed_context,
        vulnerability_context=vulnerability_context,
        road_status_context=road_status_context,
        reference_time_utc=reference_time_utc,
    )
