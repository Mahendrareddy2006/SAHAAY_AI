"""
Sahaay AI - Phase 17: Local Flood-Risk Model Schemas
Canonical schemas defining prediction targets, outcome data readiness accounting,
leakage-free evaluation partitioning, and multi-dimensional risk assessments.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import RoadConditionState, RoadFreshnessCategory


class RiskForecastCategory(str, Enum):
    """Categorical classification for forward-looking localized flood risk."""
    CLEAR = "CLEAR"              # Normal drainage capacity; no anticipated accumulation
    LOW = "LOW"                  # Minor localized runoff; negligible mobility disruption
    MEDIUM = "MEDIUM"            # Moderate accumulation potential on vulnerable road segments
    HIGH = "HIGH"                # Significant waterlogging anticipated; disruption likely
    CRITICAL = "CRITICAL"        # Severe inundation imminent or cloudburst conditions
    UNKNOWN = "UNKNOWN"          # Missing primary telemetry or unmonitored road segment


class DataReadinessVerdict(str, Enum):
    """Formal readiness gate decision for supervised model fitting."""
    READY_FOR_MODELING = "READY_FOR_MODELING"
    INSUFFICIENT_DATA_NO_GO = "INSUFFICIENT_DATA_NO_GO"
    BLOCKED_BY_PERMISSIONS = "BLOCKED_BY_PERMISSIONS"


class PredictionHorizonHours(int, Enum):
    """Supported forward-looking forecast horizons."""
    HORIZON_1H = 1
    HORIZON_2H = 2
    HORIZON_3H = 3


MANDATORY_FLOOD_RISK_DISCLAIMER = (
    "ADVISORY ONLY: Sahaay AI localized flood-risk assessment is a heuristic, forward-looking advisory "
    "and does not guarantee road safety, dry pavement, or clear passage. "
    "Heuristic baseline model pending empirical ground-truth event data. "
    "Drivers must exercise discretion and comply with on-ground traffic police directives. "
    "Autonomous road closures and automated emergency dispatch are strictly prohibited."
)

FORBIDDEN_SAFETY_PHRASES = [
    "guaranteed safe",
    "100% safe",
    "completely safe",
    "safe passage guaranteed",
    "zero risk",
    "road is safe",
    "certified safe",
    "fully safe",
    "safe for all vehicles without risk",
]


class FloodPredictionTargetSpec(BaseModel):
    """
    Formal specification of the localized flood-risk prediction target.
    Must be formally defined and sealed prior to fitting any machine learning model.
    """
    target_name: str = "localized_road_inundation_event"
    definition: str = (
        "Occurrence of standing floodwater on a designated road corridor segment with measured or verified "
        "water depth >= 10.0 cm covering >= 1 traffic lane during the forecast horizon."
    )
    spatial_unit: str = "Road corridor segment (length <= 1000m, bounded within GHMC metropolitan limits)"
    temporal_prediction_horizon: str = "1 to 3 hours forward-looking from observation time t0"
    depth_threshold_cm: float = 10.0
    lane_submersion_minimum: int = 1
    decision_boundary_threshold: float = 0.50
    intended_users: List[str] = Field(
        default_factory=lambda: [
            "GHMC Disaster Response Force (DRF) Dispatchers",
            "Hyderabad Traffic Police (HTP) Field Commanders",
            "Emergency Ambulance Fleet Routing Advisory",
            "Citizen Public Situational Awareness Portal"
        ]
    )
    operational_actionability: str = (
        "Non-autonomous decision support: alerts human supervisors to deploy desilting crews, "
        "stage rescue tenders, and adjust dynamic traffic advisories."
    )


class OutcomeDataInventory(BaseModel):
    """
    Structured accounting of available outcome data for the intended prediction target.
    Enforces rigorous segregation of real verified observations from synthetic fixtures,
    unverified community reports, and static susceptibility baselines.
    """
    audit_timestamp_utc: str
    target_spec: FloodPredictionTargetSpec = Field(default_factory=FloodPredictionTargetSpec)
    
    # Ground Truth Accounts
    candidate_road_segments_count: int = Field(0, description="Total road corridors tracked")
    verified_flood_outcome_records_count: int = Field(0, description="Real verified positive inundation episodes")
    verified_non_flood_outcome_records_count: int = Field(0, description="Real verified negative dry/wet episodes")
    independent_storm_events_count: int = Field(0, description="Distinct meteorological storm episodes")
    
    # Non-Outcome Artifacts Accounted
    static_hotspot_placemarks_count: int = Field(0, description="Chronic historical locations lacking timestamps")
    synthetic_fixtures_count: int = Field(0, description="Synthetic or template records strictly excluded")
    unverified_community_reports_count: int = Field(0, description="Citizen submissions awaiting field verification")
    climatological_summary_years: int = Field(0, description="Monthly gridded historical climatology")
    
    # Data Readiness Gate Verdict
    data_readiness_verdict: DataReadinessVerdict = DataReadinessVerdict.INSUFFICIENT_DATA_NO_GO
    supervised_training_authorized: bool = False
    predictive_claims_authorized: bool = False
    
    # Explicit Blockers & Prerequisites
    unresolved_blockers: List[str] = Field(default_factory=list)
    prerequisites_to_reopen_gate: List[str] = Field(default_factory=list)


class LocalFloodRiskInput(BaseModel):
    """
    Input feature vector for forward-looking localized flood-risk assessment.
    Enforces explicit missingness semantics (missing telemetry must remain None/UNKNOWN).
    """
    segment_id: str = Field(..., description="e.g. HYD-LOC-001 or road corridor segment ID")
    road_name: str
    corridor_zone: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=17.0, le=17.8)
    longitude: Optional[float] = Field(None, ge=78.1, le=78.8)
    forecast_horizon_hours: int = Field(1, ge=1, le=3)
    
    # Precipitation Telemetry & Forecasts
    rainfall_1h_mm: Optional[float] = Field(None, ge=0.0, description="Observed rainfall over past 1h in mm")
    rainfall_3h_mm: Optional[float] = Field(None, ge=0.0, description="Observed rainfall over past 3h in mm")
    rainfall_forecast_1h_mm: Optional[float] = Field(None, ge=0.0, description="Short-term rainfall forecast for next 1h")
    rainfall_forecast_3h_mm: Optional[float] = Field(None, ge=0.0, description="Short-term rainfall forecast for next 3h")
    telemetry_station_dist_km: Optional[float] = Field(None, ge=0.0)
    telemetry_freshness_hours: Optional[float] = Field(None, ge=0.0)
    
    # Static Vulnerability
    vulnerability_index: Optional[float] = Field(None, ge=0.0, le=1.0)
    vulnerability_category: Optional[str] = "UNKNOWN"
    
    # Current Observed Ground Truth (Decoupled Dimension)
    current_road_condition: Optional[RoadConditionState] = None
    current_road_freshness: Optional[RoadFreshnessCategory] = None
    evaluation_timestamp_utc: Optional[str] = None


class LocalFloodRiskAssessment(BaseModel):
    """
    Canonical forward-looking localized flood-risk assessment output.
    Strictly separates:
    1. Static physical susceptibility V(s)
    2. Current observed ground status O(s, t)
    3. Forward-looking predicted risk R(s, t + Δt)
    """
    segment_id: str
    road_name: str
    corridor_zone: Optional[str] = None
    forecast_horizon_hours: int
    evaluation_timestamp_utc: str
    
    # DIMENSION 1: Static Physical Susceptibility
    static_vulnerability_index: float = Field(..., ge=0.0, le=1.0)
    static_vulnerability_category: str
    
    # DIMENSION 2: Current Observed Condition
    current_observed_condition: str
    current_observation_verification_state: str
    
    # DIMENSION 3: Forward-Looking Predicted Risk
    predicted_risk_category: RiskForecastCategory
    predicted_risk_score: float = Field(..., ge=0.0, le=1.0)
    is_calibrated_probability: bool = Field(
        False, description="Must remain False unless empirical calibration has been scientifically proven"
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    uncertainty_level: str = "HIGH"
    
    # Explainability & Audit Trail
    contributing_factors: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    safety_notice: str = MANDATORY_FLOOD_RISK_DISCLAIMER
    is_actionable_for_dispatch: bool = False

    @field_validator("safety_notice")
    @classmethod
    def validate_safety_notice(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety notice contains forbidden phrase: '{phrase}'")
        return v

    @model_validator(mode="after")
    def validate_model_safety_invariants(self) -> "LocalFloodRiskAssessment":
        # 1. Prohibit any field asserting guaranteed safety
        all_text = " ".join([
            self.road_name,
            self.safety_notice,
            " ".join(self.contributing_factors),
            " ".join(self.reason_codes),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Assessment payload contains forbidden safety claim: '{phrase}'")

        # 2. Invariant: Uncalibrated probability declaration
        if self.is_calibrated_probability:
            raise ValueError(
                "is_calibrated_probability cannot be declared True: empirical probability calibration "
                "has not been demonstrated on verified Hyderabad ground-truth outcomes."
            )

        # 3. Invariant: Missing telemetry produces UNKNOWN risk category
        if "rainfall_telemetry_missing" in self.reason_codes and self.predicted_risk_category not in {RiskForecastCategory.UNKNOWN, RiskForecastCategory.CLEAR}:
            # Missing primary rainfall cannot yield confident HIGH or CRITICAL without telemetry
            if self.predicted_risk_category in {RiskForecastCategory.HIGH, RiskForecastCategory.CRITICAL}:
                raise ValueError("Cannot assign HIGH or CRITICAL risk when primary rainfall telemetry is missing.")

        return self


class EvaluationSplitSpecification(BaseModel):
    """
    Specification for leakage-free evaluation splitting.
    Enforces strict event-grouped and spatially-grouped holdouts to prevent
    temporal autocorrelation and spatial geographic leakage.
    """
    split_id: str
    grouping_dimension: str = "independent_storm_event_and_spatial_corridor"
    train_events: List[str] = Field(default_factory=list)
    eval_events: List[str] = Field(default_factory=list)
    train_segments: List[str] = Field(default_factory=list)
    eval_segments: List[str] = Field(default_factory=list)
    event_overlap_detected: bool = False
    spatial_overlap_detected: bool = False
    is_leakage_free: bool = True
