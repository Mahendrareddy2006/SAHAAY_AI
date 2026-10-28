"""
Sahaay AI - Phase 17: Transparent Local Flood-Risk Baseline Model
(src/sahaay/flood_risk/baseline.py)

Implements an explainable, deterministic baseline for localized forward-looking flood risk.
Strictly separates:
1. Static susceptibility V(s)
2. Current observed condition O(s, t)
3. Forward-looking predicted risk R(s, t + Δt)
Enforces non-silent missingness, non-probabilistic transparency, and fail-closed safety.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sahaay.flood_risk.schemas import (
    LocalFloodRiskInput,
    LocalFloodRiskAssessment,
    RiskForecastCategory,
    MANDATORY_FLOOD_RISK_DISCLAIMER,
)

logger = logging.getLogger(__name__)


class TransparentLocalFloodRiskBaseline:
    """
    Transparent rules-based baseline model for localized flood-risk assessment.
    Prevents black-box overfitting and serves as the scientific reference benchmark.
    """

    def __init__(self):
        pass

    def evaluate(self, inp: LocalFloodRiskInput) -> LocalFloodRiskAssessment:
        now_utc = datetime.now(timezone.utc)
        eval_iso = inp.evaluation_timestamp_utc or now_utc.isoformat().replace("+00:00", "Z")

        contributing_factors: List[str] = []
        reason_codes: List[str] = []
        missing_inputs: List[str] = []

        # ----------------------------------------------------------------------
        # Dimension 1: Static Susceptibility Baseline
        # ----------------------------------------------------------------------
        v_idx = inp.vulnerability_index if inp.vulnerability_index is not None else 0.10
        v_cat = inp.vulnerability_category or "LOW"
        if inp.vulnerability_index is None:
            missing_inputs.append("vulnerability_index")
            contributing_factors.append("Static vulnerability score unprovided; defaulted to baseline low exposure.")
        else:
            contributing_factors.append(f"Static road susceptibility index: {v_idx:.3f} ({v_cat})")

        # ----------------------------------------------------------------------
        # Dimension 2: Current Observed Ground Status (Strictly Decoupled)
        # ----------------------------------------------------------------------
        if inp.current_road_condition is not None:
            cond_str = inp.current_road_condition.value if hasattr(inp.current_road_condition, "value") else str(inp.current_road_condition)
            ver_str = "REPORTED_OR_VERIFIED"
        else:
            cond_str = "NO_CURRENT_EVIDENCE"
            ver_str = "UNMONITORED"
            reason_codes.append("NO_CURRENT_OBSERVATIONS_AVAILABLE")

        contributing_factors.append(f"Current observed road state: {cond_str} (Verification: {ver_str})")

        # ----------------------------------------------------------------------
        # Dimension 3: Forward-Looking Predicted Risk Calculation
        # ----------------------------------------------------------------------
        r1h = inp.rainfall_1h_mm
        r3h = inp.rainfall_3h_mm or 0.0
        f1h = inp.rainfall_forecast_1h_mm
        f3h = inp.rainfall_forecast_3h_mm or 0.0

        # Safety Check: Non-Silent Missingness
        if r1h is None and f1h is None:
            missing_inputs.append("rainfall_telemetry")
            reason_codes.append("rainfall_telemetry_missing")
            contributing_factors.append(
                "Primary rainfall telemetry and forecast feeds missing; forward risk cannot be evaluated."
            )
            return LocalFloodRiskAssessment(
                segment_id=inp.segment_id,
                road_name=inp.road_name,
                corridor_zone=inp.corridor_zone,
                forecast_horizon_hours=inp.forecast_horizon_hours,
                evaluation_timestamp_utc=eval_iso,
                static_vulnerability_index=round(v_idx, 3),
                static_vulnerability_category=v_cat,
                current_observed_condition=cond_str,
                current_observation_verification_state=ver_str,
                predicted_risk_category=RiskForecastCategory.UNKNOWN,
                predicted_risk_score=0.0,
                is_calibrated_probability=False,
                confidence_score=0.10,
                uncertainty_level="HIGH",
                contributing_factors=contributing_factors,
                missing_inputs=missing_inputs,
                reason_codes=sorted(list(set(reason_codes))),
                safety_notice=MANDATORY_FLOOD_RISK_DISCLAIMER,
                is_actionable_for_dispatch=False,
            )

        # Baseline Rainfall Intensity Scoring
        effective_r1h = r1h if r1h is not None else 0.0
        effective_f1h = f1h if f1h is not None else 0.0

        if r1h is None:
            missing_inputs.append("observed_rainfall_1h")
            reason_codes.append("OBSERVED_RAIN_MISSING_USING_FORECAST")
        if f1h is None:
            missing_inputs.append("forecast_rainfall_1h")

        # Intensity calculation (weighted observed + forward forecast)
        immediate_intensity = effective_r1h + (0.85 * effective_f1h)
        sustained_surge = max(r3h, f3h) * 0.35

        # Raw precipitation risk score [0.0, 1.0]
        raw_precip_score = (immediate_intensity * 0.02) + (sustained_surge * 0.01)
        raw_precip_score = min(1.0, max(0.0, raw_precip_score))

        # Combine with static vulnerability: V amplifies rainfall risk, but does NOT create risk in dry weather
        if raw_precip_score <= 0.05:
            # Dry or negligible rain: Vulnerability alone does not create flood risk
            combined_score = raw_precip_score
            contributing_factors.append("Dry weather or negligible precipitation; road drainage fully adequate.")
        else:
            # Under active precipitation, high vulnerability scales risk
            combined_score = raw_precip_score * (0.60 + (0.40 * v_idx))
            combined_score = min(1.0, max(0.0, combined_score))
            contributing_factors.append(
                f"Rainfall intensity ({immediate_intensity:.1f} mm/h) amplified by road susceptibility factor ({v_idx:.2f})."
            )

        # Confidence Calculation with Distance & Freshness Decay
        base_confidence = 0.85
        if inp.telemetry_station_dist_km is not None and inp.telemetry_station_dist_km > 15.0:
            dist_penalty = min(0.35, (inp.telemetry_station_dist_km - 15.0) * 0.01)
            base_confidence -= dist_penalty
            reason_codes.append("TELEMETRY_DISTANCE_DISCOUNT_APPLIED")
            contributing_factors.append(f"Station distance decay: {inp.telemetry_station_dist_km:.1f} km away (-{dist_penalty:.2f})")

        if inp.telemetry_freshness_hours is not None and inp.telemetry_freshness_hours > 1.5:
            fresh_penalty = min(0.40, (inp.telemetry_freshness_hours - 1.5) * 0.08)
            base_confidence -= fresh_penalty
            reason_codes.append("TELEMETRY_FRESHNESS_DISCOUNT_APPLIED")
            contributing_factors.append(f"Telemetry staleness decay: {inp.telemetry_freshness_hours:.1f}h old (-{fresh_penalty:.2f})")

        if missing_inputs:
            base_confidence -= min(0.30, len(missing_inputs) * 0.10)

        confidence_score = max(0.10, min(1.0, base_confidence))

        # Categorical Risk Classification
        if combined_score >= 0.70:
            category = RiskForecastCategory.CRITICAL
            uncertainty = "LOW" if confidence_score >= 0.70 else "MEDIUM"
        elif combined_score >= 0.45:
            category = RiskForecastCategory.HIGH
            uncertainty = "LOW" if confidence_score >= 0.70 else "MEDIUM"
        elif combined_score >= 0.20:
            category = RiskForecastCategory.MEDIUM
            uncertainty = "MEDIUM" if confidence_score >= 0.60 else "HIGH"
        elif combined_score >= 0.05:
            category = RiskForecastCategory.LOW
            uncertainty = "LOW" if confidence_score >= 0.70 else "MEDIUM"
        else:
            category = RiskForecastCategory.CLEAR
            uncertainty = "LOW"

        # Actionability flag: requires HIGH/CRITICAL risk AND reasonable confidence
        actionable = (category in {RiskForecastCategory.HIGH, RiskForecastCategory.CRITICAL}) and (confidence_score >= 0.45)

        return LocalFloodRiskAssessment(
            segment_id=inp.segment_id,
            road_name=inp.road_name,
            corridor_zone=inp.corridor_zone,
            forecast_horizon_hours=inp.forecast_horizon_hours,
            evaluation_timestamp_utc=eval_iso,
            static_vulnerability_index=round(v_idx, 3),
            static_vulnerability_category=v_cat,
            current_observed_condition=cond_str,
            current_observation_verification_state=ver_str,
            predicted_risk_category=category,
            predicted_risk_score=round(combined_score, 3),
            is_calibrated_probability=False,
            confidence_score=round(confidence_score, 3),
            uncertainty_level=uncertainty,
            contributing_factors=contributing_factors,
            missing_inputs=missing_inputs,
            reason_codes=sorted(list(set(reason_codes))),
            safety_notice=MANDATORY_FLOOD_RISK_DISCLAIMER,
            is_actionable_for_dispatch=actionable,
        )


def evaluate_local_flood_risk(inp: LocalFloodRiskInput) -> LocalFloodRiskAssessment:
    """Convenience helper for evaluating localized flood risk."""
    baseline = TransparentLocalFloodRiskBaseline()
    return baseline.evaluate(inp)
