"""
Sahaay AI - Phase D: Canonical Corridor Evidence Assessment Schemas
(src/sahaay/corridor_evidence/schemas.py)

Canonical data contracts integrating:
- Static road network infrastructure (Phase A)
- Directed topological graph connectivity (Phase B)
- Operational weather ingestion & rainfall pipeline (Phase C)
- Community report verification and conflict resolution (Phase 15)
- Multi-source live road status & ground truth gating (Phase 16)
- Transparent local flood-risk heuristics (Phase 17)
- Multi-horizon forecast risk service (Phase 18)
- Risk-aware routing & safety pruning (Phase 19)
- Emergency assessment workflows & disarmed dispatch (Phase 20)
- End-to-end evidence boundaries & non-inference contracts (Phase 21)

Strict Safety Semantics Enforced:
1. Non-silent missingness: missing data evaluates to UNKNOWN or INSUFFICIENT_DATA; never default to 0.0 mm dry weather.
2. Absence of reports never implies that a road is safe, dry, or passable.
3. Strict 5-signal evidence separation: F (forecast), R (observed rain), V (susceptibility), O (observed road), H (history = 0).
4. Forecast precipitation and observed gauge rainfall alone NEVER prove current road inundation or road closure.
5. Static vulnerability is strictly a static heuristic, NEVER current flood status.
6. Community reports do not silently become ground truth without authorized responder inspection.
7. Conflicting reports remain explicitly CONFLICTING until resolved by authorized verification.
8. Vision abstention [0.35, 0.65] strictly propagates as INCONCLUSIVE.
9. Uncalibrated scores are NEVER converted into calibrated flood probabilities.
10. Autonomous road closures, automated emergency dispatch, and public siren alerts are strictly prohibited.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
    MANDATORY_ROAD_SAFETY_NOTICE,
    FORBIDDEN_SAFETY_PHRASES,
)
from sahaay.road_network.schemas import MANDATORY_MAP_DATA_DISCLAIMER


class CorridorEvidenceState(str, Enum):
    """
    Canonical evidence state synthesized across all available sensory and reporting modalities.
    Strictly distinguishes ground-verified conditions, citizen corroboration,
    contradictory reports, meteorological vigilance, stale data, and missing evidence.
    """
    VERIFIED_IMPASSABLE = "VERIFIED_IMPASSABLE"                 # Official responder confirms road closed/submerged
    VERIFIED_WATERLOGGED = "VERIFIED_WATERLOGGED"               # Official responder confirms standing water (hazardous)
    VERIFIED_PASSABLE = "VERIFIED_PASSABLE"                     # Official responder confirms road clear/passable
    CORROBORATED_HAZARD = "CORROBORATED_HAZARD"                 # >=2 independent citizen reports of flooding
    UNVERIFIED_REPORT = "UNVERIFIED_REPORT"                     # Single citizen report awaiting corroboration/responder
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"               # Contradictory reports/sensors (e.g., dry camera vs flooded report)
    ELEVATED_METEOROLOGICAL_RISK = "ELEVATED_METEOROLOGICAL_RISK" # Heavy rain or forecast on vulnerable road; inundation UNPROVEN
    STALE_EVIDENCE = "STALE_EVIDENCE"                           # Observations aged beyond freshness window (>180 min)
    NO_CURRENT_EVIDENCE = "NO_CURRENT_EVIDENCE"                 # Monitored corridor but no observations in active window
    UNMONITORED_UNKNOWN = "UNMONITORED_UNKNOWN"                 # Unmonitored corridor or primary feeds unavailable


class EvidenceSufficiency(str, Enum):
    """
    Integrity and completeness classification of the available evidence base.
    """
    SUFFICIENT = "SUFFICIENT"                   # High-integrity, multi-source corroboration or official inspection
    DEGRADED = "DEGRADED"                       # Partial, aging, or single-source uncorroborated evidence
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"     # Missing primary telemetry, sensor outage, or unmonitored road
    CONFLICTING = "CONFLICTING"                 # Unresolved contradictory observations


class RoadStatusEvidenceSection(BaseModel):
    """Component 1: Current physical road status and ground truth supporting evidence."""
    condition_state: RoadConditionState = RoadConditionState.UNKNOWN
    verification_state: RoadVerificationState = RoadVerificationState.UNMONITORED
    evidence_type: RoadEvidenceType = RoadEvidenceType.NO_EVIDENCE
    verified_by_entity: Optional[str] = Field(None, description="Role and identifier of verifying authority")
    measured_water_depth_cm: Optional[float] = Field(None, ge=0.0, description="Calibrated measurement in cm")
    depth_measurement_method: str = "unmeasured"
    observation_timestamp_utc: Optional[str] = None
    ingestion_timestamp_utc: Optional[str] = None
    evidence_age_minutes: Optional[float] = None
    freshness_category: RoadFreshnessCategory = RoadFreshnessCategory.UNKNOWN
    is_verified_impassable: bool = False
    is_verified_waterlogged: bool = False
    is_verified_passable: bool = False
    supporting_evidence_summary: str = "No current ground observation available."


class CommunityReportsEvidenceSection(BaseModel):
    """Component 2: Citizen community submissions, verification lifecycle, and conflicts."""
    report_count: int = Field(0, ge=0)
    independent_sources_count: int = Field(0, ge=0)
    verification_status: str = "UNMONITORED"
    oldest_report_age_minutes: Optional[float] = None
    newest_report_age_minutes: Optional[float] = None
    has_conflicts: bool = False
    conflict_summary: Optional[str] = None
    citizen_claims_summary: str = "Zero citizen reports submitted in current active window."


class ObservedRainfallEvidenceSection(BaseModel):
    """Component 3: Real-time observed rainfall telemetry, freshness, and station provenance."""
    data_availability: str = Field("AVAILABLE", description="AVAILABLE, OUTAGE, MISSING_TELEMETRY, STALE")
    rainfall_1h_mm: Optional[float] = Field(None, ge=0.0)
    rainfall_3h_mm: Optional[float] = Field(None, ge=0.0)
    rainfall_6h_mm: Optional[float] = Field(None, ge=0.0)
    rainfall_24h_mm: Optional[float] = Field(None, ge=0.0)
    instantaneous_rate_mm_hr: Optional[float] = Field(None, ge=0.0, le=300.0)
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    station_distance_km: Optional[float] = None
    observation_timestamp_utc: Optional[str] = None
    freshness_hours: Optional[float] = None
    qc_flags: List[str] = Field(default_factory=list)
    is_valid_measured_zero: bool = False
    provenance_provider: Optional[str] = None


class ForecastRainfallEvidenceSection(BaseModel):
    """Component 4: Forward-looking precipitation forecast and horizon uncertainty."""
    forecast_source_status: str = Field(
        "BLOCKED_NO_AUTHORIZED_FEED",
        description="BLOCKED_NO_AUTHORIZED_FEED, AVAILABLE_OFFLINE_TEST, or UNAVAILABLE"
    )
    forecast_horizon_hours: int = 1
    forecast_amount_mm: Optional[float] = Field(None, ge=0.0)
    precipitation_band: str = "UNKNOWN"
    forecast_risk_category: str = "UNKNOWN"
    uncertainty_description: str = "Forecast precipitation band based on uncalibrated numerical weather model."
    issue_timestamp_utc: Optional[str] = None
    valid_timestamp_utc: Optional[str] = None
    does_forecast_prove_inundation: bool = Field(
        False,
        description="MANDATORY SAFETY INVARIANT: Forecast rainfall alone NEVER proves active road inundation"
    )

    @field_validator("does_forecast_prove_inundation")
    @classmethod
    def validate_does_forecast_prove_inundation(cls, v: bool) -> bool:
        if v is True:
            raise ValueError("Safety violation: Forecast rainfall alone cannot prove ground inundation.")
        return v


class StaticSusceptibilityEvidenceSection(BaseModel):
    """Component 5: Topographic and drainage flood susceptibility (clearly identified as static heuristic)."""
    susceptibility_heuristic_type: str = "STATIC_INFRASTRUCTURE_HEURISTIC"
    vulnerability_index: float = Field(..., ge=0.0, le=1.0)
    vulnerability_category: str = Field("UNKNOWN", description="LOW, MODERATE, HIGH, SEVERE, UNKNOWN")
    elevation_min_m: Optional[float] = None
    elevation_max_m: Optional[float] = None
    is_current_flood_status: bool = Field(
        False,
        description="MANDATORY SAFETY INVARIANT: Static vulnerability is NEVER current flood status"
    )
    description: str = "Static terrain slope, depression depth, and drainage proximity baseline."

    @field_validator("is_current_flood_status")
    @classmethod
    def validate_is_current_flood_status(cls, v: bool) -> bool:
        if v is True:
            raise ValueError("Safety violation: Static vulnerability cannot be represented as current flood status.")
        return v


class VisionEvidenceSection(BaseModel):
    """Component 6: Computer vision flood inference, quality gate, and abstention state."""
    inference_available: bool = False
    predicted_class: Optional[str] = None
    calibrated_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    quality_gate_passed: bool = False
    is_inconclusive_abstention: bool = False
    abstention_reason: Optional[str] = None
    image_reference: Optional[str] = None
    inference_timestamp_utc: Optional[str] = None


class HistoricalInundationEvidenceSection(BaseModel):
    """Component 7: Verified historical inundation outcome records (Phase 17/18 documentation)."""
    verified_historical_outcomes_count: int = Field(
        0,
        description="Real verified positive inundation episodes documented in repository (documented as 0)"
    )
    has_calibrated_statistical_model: bool = Field(
        False,
        description="Supervised model training status (documented as False pending verified outcome registry)"
    )
    historical_evidence_notes: str = (
        "Zero verified historical flood outcome records currently cataloged for this corridor. "
        "No uncalibrated supervised machine learning flood model is deployed."
    )


class CorridorEvidenceAssessment(BaseModel):
    """
    Canonical, unified corridor-level evidence assessment.
    Integrates all 7 distinct evidence components, enforces temporal provenance,
    surfaces unresolved conflicts, and guarantees non-inference safety invariants.
    """
    corridor_id: str = Field(..., min_length=3, max_length=64)
    road_name: str = Field(..., min_length=2, max_length=150)
    zone: Optional[str] = None

    # Temporal Provenance (Strictly Decoupled)
    assessment_timestamp_utc: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when this unified assessment was computed"
    )
    source_timestamps: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Strict mapping preserving observation vs ingestion vs assessment timestamps"
    )

    # High-Level Synthesized State
    evidence_state: CorridorEvidenceState
    evidence_sufficiency: EvidenceSufficiency
    has_unresolved_conflicts: bool = False
    explanation_codes: List[str] = Field(default_factory=list)
    compact_explanation: str = Field(..., description="Compact human-readable explanation of assigned evidence state")

    # The 7 Distinct Evidence Signal Sections
    road_status: RoadStatusEvidenceSection
    community_reports: CommunityReportsEvidenceSection
    observed_rainfall: ObservedRainfallEvidenceSection
    forecast_rainfall: ForecastRainfallEvidenceSection
    static_susceptibility: StaticSusceptibilityEvidenceSection
    vision_evidence: VisionEvidenceSection
    historical_inundation: HistoricalInundationEvidenceSection = Field(default_factory=HistoricalInundationEvidenceSection)

    # Routing & Action Boundaries
    is_traversable_for_routing: bool = True
    routing_penalty_multiplier: float = Field(1.0, ge=1.0)
    operational_action_authorized: bool = Field(
        False,
        description="Autonomous road closures and emergency dispatch are strictly disarmed"
    )

    # Disclaimers & Geographic Coverage Warnings
    coverage_warning: str = Field(
        "SPARSE_SEED_CATALOG_22_SEGMENTS_NOT_CITYWIDE: Sparse ~25.6 km seed catalog does not provide citywide navigation.",
        description="Explicit notice preventing false claims of comprehensive metropolitan coverage"
    )
    safety_notice: str = Field(MANDATORY_ROAD_SAFETY_NOTICE)
    map_disclaimer: str = Field(MANDATORY_MAP_DATA_DISCLAIMER)

    @field_validator("safety_notice")
    @classmethod
    def validate_safety_notice(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety notice contains forbidden phrasing: '{phrase}'")
        return v

    @field_validator("road_name")
    @classmethod
    def validate_road_name(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Road name contains forbidden safety phrasing: '{phrase}'")
        return v
