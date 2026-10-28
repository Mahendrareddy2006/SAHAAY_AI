"""
Sahaay AI - Phase 17: Local Flood-Risk Readiness Audit Script
(scripts/audit_phase17_local_flood_risk.py)

Generates the formal Phase 17 readiness report artifact:
reports/phase17/phase17_readiness_report.json
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from sahaay.flood_risk.readiness import audit_outcome_data_readiness
from sahaay.flood_risk.schemas import (
    LocalFloodRiskInput,
    RiskForecastCategory,
)
from sahaay.flood_risk.baseline import evaluate_local_flood_risk
from sahaay.flood_risk.evaluation import EventAndSpatialSplitter
from sahaay.road_status.schemas import RoadConditionState


def generate_phase17_readiness_report() -> Dict[str, Any]:
    now_utc = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = now_utc.isoformat().replace("+00:00", "Z")

    # 1. Forensic Outcome Data Readiness Audit
    inventory = audit_outcome_data_readiness(audit_timestamp=now_iso)

    # 2. Baseline Scenario Evaluations
    # Scenario A: Missing Telemetry
    scen_missing = evaluate_local_flood_risk(
        LocalFloodRiskInput(
            segment_id="HYD-LOC-001",
            road_name="Tolichowki Flyover Underpass",
            vulnerability_index=0.55,
            rainfall_1h_mm=None,
            rainfall_forecast_1h_mm=None,
        )
    )

    # Scenario B: Heavy Rain on Vulnerable Road
    scen_heavy = evaluate_local_flood_risk(
        LocalFloodRiskInput(
            segment_id="HYD-LOC-002",
            road_name="Shaikpet Nala Road",
            vulnerability_index=0.60,
            rainfall_1h_mm=25.0,
            rainfall_forecast_1h_mm=15.0,
            telemetry_station_dist_km=5.0,
            telemetry_freshness_hours=0.5,
        )
    )

    # Scenario C: Dry Weather on Severe Vulnerability Road
    scen_dry = evaluate_local_flood_risk(
        LocalFloodRiskInput(
            segment_id="HYD-LOC-003",
            road_name="Begumpet Rasoolpura Underpass",
            vulnerability_index=0.85,
            vulnerability_category="SEVERE",
            rainfall_1h_mm=0.0,
            rainfall_forecast_1h_mm=0.0,
        )
    )

    # 3. Evaluation Split Protocol Verification
    splitter = EventAndSpatialSplitter()
    mock_events = ["STORM-2023-07", "STORM-2023-09", "STORM-2024-08", "STORM-2024-10"]
    mock_segments = ["HYD-LOC-001", "HYD-LOC-002", "HYD-LOC-003", "HYD-LOC-004"]
    split_spec = splitter.generate_splits(mock_events, mock_segments)

    report_payload = {
        "report_phase": "Phase 17",
        "title": "Local Flood-Risk Modeling Feasibility & Outcome Data Readiness Report",
        "timestamp_utc": now_iso,
        "operational_mode": "OFFLINE_ENGINEERING_ADVISORY",
        "live_telemetry_active": False,
        "target_specification": inventory.target_spec.model_dump(),
        "outcome_data_readiness": {
            "candidate_road_segments_count": inventory.candidate_road_segments_count,
            "verified_flood_outcome_records_count": inventory.verified_flood_outcome_records_count,
            "verified_non_flood_outcome_records_count": inventory.verified_non_flood_outcome_records_count,
            "independent_storm_events_count": inventory.independent_storm_events_count,
            "static_hotspot_placemarks_count": inventory.static_hotspot_placemarks_count,
            "synthetic_fixtures_count": inventory.synthetic_fixtures_count,
            "unverified_community_reports_count": inventory.unverified_community_reports_count,
            "climatological_summary_years": inventory.climatological_summary_years,
            "verdict": inventory.data_readiness_verdict.value,
            "supervised_training_authorized": inventory.supervised_training_authorized,
            "predictive_claims_authorized": inventory.predictive_claims_authorized,
            "unresolved_blockers": inventory.unresolved_blockers,
            "prerequisites_to_reopen_gate": inventory.prerequisites_to_reopen_gate,
        },
        "baseline_scenarios_evaluated": {
            "missing_telemetry": {
                "predicted_risk_category": scen_missing.predicted_risk_category.value,
                "confidence_score": scen_missing.confidence_score,
                "current_observed_condition": scen_missing.current_observed_condition,
                "missing_inputs": scen_missing.missing_inputs,
            },
            "heavy_surge_vulnerable_corridor": {
                "predicted_risk_category": scen_heavy.predicted_risk_category.value,
                "predicted_risk_score": scen_heavy.predicted_risk_score,
                "confidence_score": scen_heavy.confidence_score,
                "is_actionable_for_dispatch": scen_heavy.is_actionable_for_dispatch,
                "current_observed_condition": scen_heavy.current_observed_condition,
            },
            "dry_weather_severe_vulnerability": {
                "predicted_risk_category": scen_dry.predicted_risk_category.value,
                "predicted_risk_score": scen_dry.predicted_risk_score,
                "static_vulnerability_category": scen_dry.static_vulnerability_category,
                "current_observed_condition": scen_dry.current_observed_condition,
            }
        },
        "evaluation_protocol": {
            "splitter_protocol": split_spec.grouping_dimension,
            "is_leakage_free": split_spec.is_leakage_free,
            "train_events": split_spec.train_events,
            "eval_events": split_spec.eval_events,
            "train_segments": split_spec.train_segments,
            "eval_segments": split_spec.eval_segments,
            "sealed_vision_test_partition_guarded": True,
        },
        "final_gate_decision": {
            "engineering_implementation_status": "COMPLETE",
            "empirical_readiness_status": "NO-GO (LOCKED)",
            "supervised_model_training_status": "NO-GO (LOCKED)",
            "predictive_performance_claims": "PROHIBITED_UNEARNED",
        }
    }
    return report_payload


if __name__ == "__main__":
    report = generate_phase17_readiness_report()
    os.makedirs("reports/phase17", exist_ok=True)
    out_path = Path("reports/phase17/phase17_readiness_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Readiness report generated at: {out_path}")
    print(f"Verdict: {report['outcome_data_readiness']['verdict']}")
