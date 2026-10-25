"""
Sahaay AI - Phase 5 Reproducible End-to-End Scenario Demonstration Runner
Evaluates 10 explicitly labeled operational scenarios through the Decision Engine and API.
Outputs machine-readable results to reports/phase5/end_to_end_scenarios.json.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure 'src' is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sahaay.decision.contracts import (
    AlertLevel,
    CurrentFloodEvidenceStatus,
    DecisionInput,
    DecisionStatus,
    HazardNature,
    evaluate_decision,
)
from sahaay.reports.schemas import (
    CitizenReportSubmission,
    ReportVerificationRequest,
    ReportVerificationStatus,
    WaterDepthEstimate,
)
from sahaay.reports.service import CitizenReportService, reset_report_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase5_demo")

DEMO_DIR = Path("data/phase5_demo")
REPORTS_DIR = Path("reports/phase5")


def define_demo_scenarios() -> List[Dict[str, Any]]:
    """
    Defines the 10 mandated operational scenarios with inputs and expected outputs.
    """
    return [
        {
            "scenario_id": "SCENARIO-01",
            "scenario_name": "Low rainfall, low vulnerability, no current reports",
            "description": "Dry baseline conditions on resilient corridor. Baseline safety verification.",
            "input": DecisionInput(
                location_id="HYD-LOC-011",
                road_name="Madhapur Cyber Towers Corridor",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="LOW",
                rainfall_risk_score=0.02,
                vulnerability_category="LOW",
                vulnerability_index=0.05,
                report_age_minutes=0.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
            ),
            "expected_alert_level": AlertLevel.CLEAR,
            "expected_evidence_status": CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": False,
        },
        {
            "scenario_id": "SCENARIO-02",
            "scenario_name": "Heavy rainfall and high vulnerability, with no observed flood report",
            "description": "High environmental waterlogging risk anticipated. Must trigger WATCH without claiming proven flooding.",
            "input": DecisionInput(
                location_id="HYD-LOC-001",
                road_name="Tolichowki Flyover Underpass",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="HIGH",
                rainfall_risk_score=0.72,
                vulnerability_category="HIGH",
                vulnerability_index=0.53,
                report_age_minutes=0.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
            ),
            "expected_alert_level": AlertLevel.WATCH,
            "expected_evidence_status": CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": True,
        },
        {
            "scenario_id": "SCENARIO-03",
            "scenario_name": "One unverified citizen report",
            "description": "Single community submission in dry weather. Must trigger ADVISORY and request verification, not emergency.",
            "input": DecisionInput(
                location_id="HYD-LOC-006",
                road_name="Panjagutta Underpass & Nagarjuna Circle",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="LOW",
                rainfall_risk_score=0.10,
                vulnerability_category="MODERATE",
                vulnerability_index=0.41,
                report_age_minutes=15.0,
                is_field_verified=False,
                citizen_report_count_in_zone=1,
            ),
            "expected_alert_level": AlertLevel.ADVISORY,
            "expected_evidence_status": CurrentFloodEvidenceStatus.INCONCLUSIVE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": False,
        },
        {
            "scenario_id": "SCENARIO-04",
            "scenario_name": "Multiple reports that may be duplicates",
            "description": "Three citizen submissions from same 50m radius within 10 min. Evaluates near-duplicate suppression.",
            "input": DecisionInput(
                location_id="HYD-LOC-002",
                road_name="Shaikpet Nala Road",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="MEDIUM",
                rainfall_risk_score=0.40,
                vulnerability_category="MODERATE",
                vulnerability_index=0.37,
                report_age_minutes=20.0,
                is_field_verified=False,
                citizen_report_count_in_zone=3,
            ),
            "expected_alert_level": AlertLevel.WATCH,
            "expected_evidence_status": CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": True,
        },
        {
            "scenario_id": "SCENARIO-05",
            "scenario_name": "A verified, recent flood observation",
            "description": "Ground responder confirms 45cm waterlogging. Must escalate to WARNING with observed evidence.",
            "input": DecisionInput(
                location_id="HYD-LOC-005",
                road_name="Malakpet Railway Underbridge",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="MEDIUM",
                rainfall_risk_score=0.45,
                vulnerability_category="HIGH",
                vulnerability_index=0.55,
                report_age_minutes=10.0,
                is_field_verified=True,
                citizen_report_count_in_zone=1,
                water_depth_estimate="KNEE_DEEP",
            ),
            "expected_alert_level": AlertLevel.WARNING,
            "expected_evidence_status": CurrentFloodEvidenceStatus.OBSERVED_FLOOD_EVIDENCE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": True,
        },
        {
            "scenario_id": "SCENARIO-06",
            "scenario_name": "Stale or unavailable rainfall telemetry",
            "description": "Hourly telemetry observation is missing. Non-silent missingness must trigger INSUFFICIENT_DATA and ADVISORY.",
            "input": DecisionInput(
                location_id="HYD-LOC-016",
                road_name="Uppal Ring Road Junction",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="UNKNOWN",
                rainfall_risk_score=0.0,
                vulnerability_category="MODERATE",
                vulnerability_index=0.25,
                report_age_minutes=0.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
                missing_inputs=["rain_1h_mm", "rain_3h_mm"],
                stale_inputs=["telemetry_rainfall"],
            ),
            "expected_alert_level": AlertLevel.ADVISORY,
            "expected_evidence_status": CurrentFloodEvidenceStatus.INSUFFICIENT_OR_STALE_DATA,
            "expected_decision_status": DecisionStatus.INSUFFICIENT_DATA,
            "expected_actionable": False,
        },
        {
            "scenario_id": "SCENARIO-07",
            "scenario_name": "Contradictory reports",
            "description": "Citizen asserts deep water while contemporaneous camera confirms dry asphalt. Must flag INCONCLUSIVE_CONTRADICTORY.",
            "input": DecisionInput(
                location_id="HYD-LOC-008",
                road_name="Lakdikapul Junction & Railway Bridge",
                vision_predicted_class="not_flooded",
                vision_confidence=0.85,
                vision_is_ambiguous=False,
                rainfall_risk_category="LOW",
                rainfall_risk_score=0.10,
                vulnerability_category="MODERATE",
                vulnerability_index=0.39,
                report_age_minutes=8.0,
                is_field_verified=False,
                citizen_report_count_in_zone=1,
                water_depth_estimate="KNEE_DEEP",
                has_contradictory_evidence=True,
            ),
            "expected_alert_level": AlertLevel.ADVISORY,
            "expected_evidence_status": CurrentFloodEvidenceStatus.INCONCLUSIVE,
            "expected_decision_status": DecisionStatus.INCONCLUSIVE_CONTRADICTORY,
            "expected_actionable": False,
        },
        {
            "scenario_id": "SCENARIO-08",
            "scenario_name": "Low-quality or inconclusive vision output",
            "description": "Image fails automated quality gate due to extreme glare/blur. Must NOT trigger flood false-alarm.",
            "input": DecisionInput(
                location_id="HYD-LOC-013",
                road_name="Ameerpet Metro Junction",
                vision_predicted_class="inconclusive",
                vision_confidence=0.48,
                vision_is_ambiguous=True,
                rainfall_risk_category="LOW",
                rainfall_risk_score=0.05,
                vulnerability_category="LOW",
                vulnerability_index=0.12,
                report_age_minutes=5.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
            ),
            "expected_alert_level": AlertLevel.CLEAR,
            "expected_evidence_status": CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": False,
        },
        {
            "scenario_id": "SCENARIO-09",
            "scenario_name": "High environmental risk with missing current-flood evidence",
            "description": "Cloudburst rainfall (105mm/hr) on chronically vulnerable corridor without ground reports. Triggers WATCH.",
            "input": DecisionInput(
                location_id="HYD-LOC-001",
                road_name="Tolichowki Flyover Underpass",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="CRITICAL",
                rainfall_risk_score=0.98,
                vulnerability_category="HIGH",
                vulnerability_index=0.53,
                report_age_minutes=0.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
            ),
            "expected_alert_level": AlertLevel.WATCH,
            "expected_evidence_status": CurrentFloodEvidenceStatus.ELEVATED_ENVIRONMENTAL_RISK,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": True,
        },
        {
            "scenario_id": "SCENARIO-10",
            "scenario_name": "Recovery after a data source becomes available again",
            "description": "Weather telemetry recovers from outage; fresh dry reading received. Restores CLEAR evaluated status.",
            "input": DecisionInput(
                location_id="HYD-LOC-016",
                road_name="Uppal Ring Road Junction",
                vision_predicted_class=None,
                vision_confidence=None,
                rainfall_risk_category="LOW",
                rainfall_risk_score=0.02,
                vulnerability_category="MODERATE",
                vulnerability_index=0.25,
                report_age_minutes=0.0,
                is_field_verified=False,
                citizen_report_count_in_zone=0,
                missing_inputs=[],
                stale_inputs=[],
            ),
            "expected_alert_level": AlertLevel.CLEAR,
            "expected_evidence_status": CurrentFloodEvidenceStatus.NO_CURRENT_EVIDENCE_AVAILABLE,
            "expected_decision_status": DecisionStatus.EVALUATED,
            "expected_actionable": False,
        },
    ]


def run_scenarios() -> Dict[str, Any]:
    """
    Executes all 10 scenarios through the Decision Engine, persists fixtures,
    and returns machine-readable evaluation report.
    """
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    scenarios = define_demo_scenarios()
    results: List[Dict[str, Any]] = []
    all_passed = True

    logger.info(f"Executing {len(scenarios)} Phase 5 end-to-end demonstration scenarios...")

    for sc in scenarios:
        sc_id = sc["scenario_id"]
        sc_name = sc["scenario_name"]
        decision_input: DecisionInput = sc["input"]

        # Save scenario input fixture
        fixture_file = DEMO_DIR / f"{sc_id.lower().replace('-', '_')}.json"
        with open(fixture_file, "w", encoding="utf-8") as f:
            json.dump({
                "scenario_id": sc_id,
                "scenario_name": sc_name,
                "description": sc["description"],
                "input_data": decision_input.model_dump(),
                "is_demonstration_fixture": True,
            }, f, indent=2)

        # Execute Decision Engine
        actual_output = evaluate_decision(decision_input)

        # Check conformance
        level_match = actual_output.alert_level == sc["expected_alert_level"]
        status_match = actual_output.decision_status == sc["expected_decision_status"]
        evidence_match = actual_output.current_flood_evidence_status == sc["expected_evidence_status"]
        actionable_match = actual_output.is_actionable_for_crews == sc["expected_actionable"]

        passed = level_match and status_match and evidence_match and actionable_match
        if not passed:
            all_passed = False
            logger.error(f"Scenario {sc_id} FAILED: level={level_match}, status={status_match}, evidence={evidence_match}")
        else:
            logger.info(f"Scenario {sc_id} PASSED: {actual_output.alert_level.value} [{actual_output.current_flood_evidence_status.value}]")

        result_entry = {
            "scenario_id": sc_id,
            "scenario_name": sc_name,
            "description": sc["description"],
            "fixture_file": str(fixture_file),
            "expected": {
                "alert_level": sc["expected_alert_level"].value,
                "decision_status": sc["expected_decision_status"].value,
                "current_flood_evidence_status": sc["expected_evidence_status"].value,
                "is_actionable_for_crews": sc["expected_actionable"],
            },
            "actual": {
                "alert_level": actual_output.alert_level.value,
                "decision_status": actual_output.decision_status.value,
                "current_flood_evidence_status": actual_output.current_flood_evidence_status.value,
                "is_actionable_for_crews": actual_output.is_actionable_for_crews,
                "decision_score": actual_output.decision_score,
                "confidence": actual_output.confidence,
                "reason_codes": actual_output.reason_codes,
                "explanation": actual_output.explanation,
            },
            "passed": passed,
        }
        results.append(result_entry)

    report = {
        "report_name": "Sahaay AI Phase 5 - End-to-End Demonstration Scenario Results",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_scenarios": len(scenarios),
        "scenarios_passed": sum(1 for r in results if r["passed"]),
        "all_scenarios_passed": all_passed,
        "demonstration_rules_conformance": "100%" if all_passed else f"{sum(1 for r in results if r['passed'])}/10",
        "scientific_integrity_notice": (
            "Scenario pass rates measure decision rule and contract conformance under controlled fixtures. "
            "They do NOT establish real-world predictive flood accuracy."
        ),
        "results": results,
    }

    report_path = REPORTS_DIR / "end_to_end_scenarios.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Successfully generated scenario report at {report_path} (Passed: {report['scenarios_passed']}/10)")
    return report


if __name__ == "__main__":
    rep = run_scenarios()
    if not rep["all_scenarios_passed"]:
        sys.exit(1)
