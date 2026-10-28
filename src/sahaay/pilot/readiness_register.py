"""
Sahaay AI - Phase F: Data and Integration Readiness Register
(src/sahaay/pilot/readiness_register.py)

Codifies an evidence-backed, factual readiness register evaluating all 10 essential
dimensions of real-world deployment safety, institutional readiness, and technical contracts.
Enforces that synthetic fixtures, unit tests, and mock adapters are NEVER marked as READY.
"""

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReadinessItemStatus(str, Enum):
    """Factual evaluation state for pilot prerequisites."""
    READY = "READY"                   # Independently verified, fully operational in production
    PARTIAL = "PARTIAL"               # Software contract or mock ready; field/data/institutional dependencies incomplete
    BLOCKED = "BLOCKED"               # Known active blocker preventing safe operational use
    NOT_ASSESSED = "NOT_ASSESSED"     # Scope not yet evaluated against verified standards


class ReadinessRegisterItem(BaseModel):
    """
    Granular audit entry for a single data, integration, or operational requirement.
    """
    item_id: str
    category: str
    title: str
    status: ReadinessItemStatus
    evidence_source: str = Field(..., description="File path, audit script, or artifact proving status")
    explicit_limitations: str = Field(..., description="Unvarnished description of gaps, mocks, and unmonitored scope")
    responsible_party: str = Field(..., description="External institution or project team responsible for clearance")
    clearing_condition: str = Field(..., description="Concrete criteria required to transition status to READY")

    @property
    def limitations(self) -> str:
        return self.explicit_limitations


class DataIntegrationReadinessRegister(BaseModel):
    """
    System-wide integration readiness register and pilot decision authority.
    """
    register_id: str = "SAHAAY-READINESS-REGISTER-V1"
    evaluation_timestamp_utc: str
    overall_pilot_decision: str = "NO_GO"
    summary_counts: Dict[str, int] = Field(default_factory=dict)
    items: List[ReadinessRegisterItem] = Field(default_factory=list)
    primary_blockers: List[str] = Field(default_factory=list)
    smallest_safe_next_actions: List[str] = Field(default_factory=list)
    governance_disclaimer: str = (
        "CONTROLLED PILOT READINESS NOTICE: Sahaay AI remains NO-GO for unmonitored public deployment. "
        "Passing software unit tests and synthetic pipeline benchmarks does NOT satisfy field readiness. "
        "Autonomous physical actions (dispatch, road closures) remain permanently disarmed."
    )

    def get_item(self, item_id: str) -> Optional[ReadinessRegisterItem]:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def get_summary(self) -> Dict[str, Any]:
        return {
            "ready_count": self.summary_counts.get("READY", 0),
            "partial_count": self.summary_counts.get("PARTIAL", 0),
            "blocked_count": self.summary_counts.get("BLOCKED", 0),
            "not_assessed_count": self.summary_counts.get("NOT_ASSESSED", 0),
            "total_requirements": len(self.items),
            "pilot_decision": self.overall_pilot_decision,
        }


def build_default_readiness_register() -> DataIntegrationReadinessRegister:
    """
    Assembles the authoritative 10-item Phase F readiness register based on factual repository evidence.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    items = [
        ReadinessRegisterItem(
            item_id="REG-01-ROAD-NETWORK",
            category="Road Network & Topology",
            title="Road-Network Completeness and Topology",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/road_network/store.py, reports/phase_b/phase_b_results.json",
            explicit_limitations=(
                "Road network catalog contains only ~22 seed segments (~25 centerline km) focused on Tolichowki, "
                "Shaikpet, Khairatabad, and Musarambagh. Disconnected components exist; citywide Greater Hyderabad "
                "routing is topologically unsupported without synthetic edge fabrication."
            ),
            responsible_party="GHMC Town Planning / HMDA GIS Directorate",
            clearing_condition=(
                "Ingestion and topological validation of authoritative GIS centerline geometries covering at least "
                "one complete municipal ward (100% road coverage with verified junction nodes)."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-02-EMERGENCY-DESTINATIONS",
            category="Emergency Facilities",
            title="Verified Emergency Destination Records",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/emergency_destinations/registry.py, reports/phase_e/phase_e_results.json",
            explicit_limitations=(
                "Facilities are synthetic demonstration fixtures (is_synthetic_fixture=True). "
                "Real-time hospital bed occupancy, ICU beds, trauma availability, and power telemetry "
                "are unavailable via automated feeds and remain UNKNOWN."
            ),
            responsible_party="Telangana Health Directorate / GHMC Disaster Management Cell",
            clearing_condition=(
                "Execution of institutional API integration agreement and verification of live intake/bed telemetry "
                "for at least 3 government tertiary hospitals."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-03-AUTHORIZED-WEATHER",
            category="Meteorological Telemetry",
            title="Authorized Weather and Forecast Sources",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/adapters/imd_provider_adapter.py, reports/phase_c/phase_c_results.json",
            explicit_limitations=(
                "Live feed activation from IMD AWS gateway remains BLOCKED pending institutional authorization. "
                "System operates on offline fallback adapters and simulated rainfall fixtures."
            ),
            responsible_party="India Meteorological Department (IMD) / TSDPS",
            clearing_condition=(
                "Execution of formal institutional data-sharing MoU and issuance of authenticated API gateway credentials."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-04-STATION-TELEMETRY-SEMANTICS",
            category="Meteorological Telemetry",
            title="Station Coordinates, Provenance, Freshness & Measurement Semantics",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/hyderabad_risk/weather_pipeline.py, tests/test_phase_c_weather_pipeline.py",
            explicit_limitations=(
                "Only 5 demonstration stations configured. Tipped-bucket rollover handling is unit-tested, "
                "but physical sensor calibration latency, maintenance outages, and clock drift are unmonitored."
            ),
            responsible_party="Telangana State Development Planning Society (TSDPS)",
            clearing_condition=(
                "Direct field telemetry validation against physical rain gauge calibration logs for target pilot corridors."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-05-VERIFIED-FLOOD-OBSERVATIONS",
            category="Ground Truth & Flood Observations",
            title="Timestamped & Independently Verified Flood / Wet-Not-Flooded Observations",
            status=ReadinessItemStatus.BLOCKED,
            evidence_source="reports/phase16/phase16_readiness_report.md, src/sahaay/road_status/service.py",
            explicit_limitations=(
                "No comprehensive, timestamped dataset of ground-truth water depth measurements exists across Hyderabad. "
                "Citizen reports require manual human corroboration; wet-pavement vs deep standing water boundaries "
                "lack physical depth-gauge sensor verification."
            ),
            responsible_party="GHMC Disaster Response Force (DRF) / Hyderabad Traffic Police",
            clearing_condition=(
                "Deployment of certified physical staff gauges or ultrasonic depth sensors on monitored pilot corridors "
                "with logged human inspection records during active monsoon rain events."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-06-VISION-DATA-READINESS",
            category="Computer Vision AI",
            title="Vision Data Provenance, Permissions, Confounding & Evaluation",
            status=ReadinessItemStatus.BLOCKED,
            evidence_source="reports/phase14/phase14_vision_readiness_report.md, reports/vision_integrity/",
            explicit_limitations=(
                "Vision V4 readiness gate evaluates strictly to NO-GO. Web-scraped images exhibit watermark leakage, "
                "source/class confounding, lack of commercial/public-safety redistribution permissions, and absence "
                "of independent local geographic evaluation."
            ),
            responsible_party="Sahaay AI Computer Vision Team / Academic Partner",
            clearing_condition=(
                "Collection and curation of a dedicated, rights-cleared, unconfounded dataset of 1,000+ local Hyderabad "
                "road images under rainy, overcast, dry, and nighttime conditions, passing all V4 data-readiness audits."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-07-COMMUNITY-REPORTS-GOVERNANCE",
            category="Citizen Sensing & Privacy",
            title="Community-Report Consent, Privacy & Verification Governance",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/reports/service.py, src/sahaay/data_collection_v4/governance.py",
            explicit_limitations=(
                "Privacy masking (040-XXXX phone masking, coordinate truncation) and rate limits are enforced in software; "
                "however, formal DPDP Act 2023 public terms of consent, citizen grievance redressal, and dedicated "
                "field responder verification units are unstaffed."
            ),
            responsible_party="GHMC Public Relations / Project Legal Counsel",
            clearing_condition=(
                "Legal sign-off on public citizen-reporting privacy policy and establishment of an SLA-backed "
                "field responder verification mechanism."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-08-HUMAN-REVIEW-STAFFING",
            category="Operational Workflow",
            title="Human-Review Staffing, SLA & Escalation Protocols",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/emergency/workflow.py, src/sahaay/review/workflow.py",
            explicit_limitations=(
                "Deterministic triage state machine and audit-hash recording are functional; however, no 24/7 municipal "
                "review desk is staffed. Escalation protocols are documented but lack designated duty officers."
            ),
            responsible_party="GHMC DRF Command & Control / Hyderabad Traffic Police Operations",
            clearing_condition=(
                "Formal administrative order designating named, trained duty officers for 24/7 emergency review desk "
                "with agreed 15-minute response SLA for P1 triage."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-09-AUTHENTICATION-AND-AUDIT",
            category="Security & Access Control",
            title="Authentication, Authorization & Audit Retention",
            status=ReadinessItemStatus.PARTIAL,
            evidence_source="src/sahaay/security/auth.py, tests/test_phase_f_production_hardening_and_pilot_readiness.py",
            explicit_limitations=(
                "Server-side Bearer token validation and fail-closed operational actions implemented; however, integration "
                "with municipal single sign-on (SSO) / Keycloak and tamper-proof write-once-read-many (WORM) audit storage "
                "remains unintegrated in infrastructure."
            ),
            responsible_party="Municipal IT Directorate / Project Infrastructure Lead",
            clearing_condition=(
                "Binding of API security gateway to institutional OAuth2 / OIDC identity provider and export of audit "
                "chains to append-only cloud storage."
            ),
        ),
        ReadinessRegisterItem(
            item_id="REG-10-INSTITUTIONAL-AGREEMENTS",
            category="Legal & Institutional Authorization",
            title="Institutional Agreements and Operational Ownership",
            status=ReadinessItemStatus.BLOCKED,
            evidence_source="src/sahaay/pilot/gate.py, reports/phase_f/pilot_readiness_checklist.md",
            explicit_limitations=(
                "Zero executed agreements, MoUs, or pilot operating licenses exist with GHMC, Hyderabad Traffic Police, "
                "or Telangana State Disaster Management Authority. Software operates under simulated research protocols."
            ),
            responsible_party="Project Principal Investigator / GHMC Commissioner",
            clearing_condition=(
                "Executed bilateral or tripartite Memorandum of Understanding (MoU) defining legal liability, data ownership, "
                "and pilot operating boundaries."
            ),
        ),
    ]

    summary = {
        ReadinessItemStatus.READY.value: sum(1 for it in items if it.status == ReadinessItemStatus.READY),
        ReadinessItemStatus.PARTIAL.value: sum(1 for it in items if it.status == ReadinessItemStatus.PARTIAL),
        ReadinessItemStatus.BLOCKED.value: sum(1 for it in items if it.status == ReadinessItemStatus.BLOCKED),
        ReadinessItemStatus.NOT_ASSESSED.value: sum(1 for it in items if it.status == ReadinessItemStatus.NOT_ASSESSED),
    }

    primary_blockers = [
        "REG-10: Absence of executed institutional MoU with GHMC / Hyderabad Traffic Police.",
        "REG-06: Computer Vision V4 model gate is strictly BLOCKED (watermark leakage, class confounding).",
        "REG-05: Absence of certified physical ground-truth water depth sensor validation in Hyderabad.",
        "REG-01: Sparse road network catalog (~22 segments) leaves citywide routing unsupported.",
        "REG-02: Emergency destination hospital records are synthetic fixtures lacking live bed telemetry.",
    ]

    smallest_safe_next_actions = [
        "1. Formalize tripartite meeting with GHMC DRF and Hyderabad Traffic Police to define pilot corridor boundaries.",
        "2. Replace web-scraped vision training data with 1,000+ locally captured, rights-cleared, unconfounded images.",
        "3. Bind API security gateway to municipal OAuth2/OIDC identity provider for responder role verification.",
        "4. Deploy certified physical depth gauges on 2 selected pilot corridors (Tolichowki and Shaikpet) for dual-observer verification.",
        "5. Ingest municipal GIS road centerline data for the entire Golconda / Khairatabad zone to eliminate disconnected graph cuts.",
    ]

    return DataIntegrationReadinessRegister(
        evaluation_timestamp_utc=now_iso,
        overall_pilot_decision="NO_GO",
        summary_counts=summary,
        items=items,
        primary_blockers=primary_blockers,
        smallest_safe_next_actions=smallest_safe_next_actions,
    )


default_readiness_register = build_default_readiness_register()
