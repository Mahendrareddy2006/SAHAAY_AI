"""
Sahaay AI - Phase 18: Forecast Risk Schemas
Canonical data contracts for precipitation forecasts, multi-source evidence separation,
temporal validation, quality indicators, and non-autonomous advisory assessments.
"""

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from sahaay.road_status.schemas import RoadConditionState, RoadVerificationState


class PrecipitationUnit(str, Enum):
    """Authorized physical precipitation measurement units."""
    MILLIMETERS = "mm"
    MILLIMETERS_PER_HOUR = "mm/h"
    CENTIMETERS = "cm"
    INCHES = "in"


class AccumulationInterval(str, Enum):
    """Temporal integration period over which rainfall accumulation is defined."""
    INTERVAL_15M = "15m"
    INTERVAL_30M = "30m"
    INTERVAL_1H = "1h"
    INTERVAL_3H = "3h"
    INTERVAL_6H = "6h"
    INTERVAL_24H = "24h"
    INSTANTANEOUS_RATE = "instantaneous_rate"


class ForecastSourceType(str, Enum):
    """Categorical source modality providing numerical weather predictions."""
    OFFICIAL_MET_AGENCY_IMD = "OFFICIAL_MET_AGENCY_IMD"
    REGIONAL_TSDPS_ADVISORY = "REGIONAL_TSDPS_ADVISORY"
    NUMERICAL_WEATHER_PREDICTION_NWP = "NUMERICAL_WEATHER_PREDICTION_NWP"
    RADAR_NOWCAST = "RADAR_NOWCAST"
    GLOBAL_OPEN_MODEL = "GLOBAL_OPEN_MODEL"
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"


class ForecastQualityFlag(str, Enum):
    """Auditable data quality and consistency flags."""
    VALID = "VALID"
    STALE = "STALE"
    SPATIALLY_UNSUITABLE = "SPATIALLY_UNSUITABLE"
    TEMPORALLY_INCONSISTENT = "TEMPORALLY_INCONSISTENT"
    HORIZON_MISMATCH = "HORIZON_MISMATCH"
    UNSUPPORTED_UNITS = "UNSUPPORTED_UNITS"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    NEGATIVE_VALUE = "NEGATIVE_VALUE"
    EXCESSIVE_RATE = "EXCESSIVE_RATE"
    MISSING_TELEMETRY = "MISSING_TELEMETRY"
    UNAUTHORIZED_PROVIDER = "UNAUTHORIZED_PROVIDER"


class ForecastDataStatus(str, Enum):
    """Overall status of forecast data availability and reliability."""
    AVAILABLE_VALID = "AVAILABLE_VALID"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    SPATIALLY_UNSUITABLE = "SPATIALLY_UNSUITABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNKNOWN = "UNKNOWN"


MANDATORY_FORECAST_RISK_DISCLAIMER = (
    "ADVISORY ONLY: Sahaay AI localized forecast-risk assessment is a forward-looking advisory "
    "based on meteorological weather models and does not guarantee road safety, dry pavement, "
    "or safe passage. Forecasts involve inherent atmospheric uncertainty. "
    "Exercise driver discretion and comply with on-ground traffic police directives. "
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


class ForecastRainfallInput(BaseModel):
    """
    Validated schema for external forecast precipitation inputs.
    Strictly decouples accumulation totals from instantaneous rates, enforces non-negativity,
    validates temporal coherence, and tracks spatial suitability.
    """
    location_id: str = Field(..., min_length=2, max_length=50, description="Road segment ID or corridor reference")
    source_id: str = Field(..., min_length=2, max_length=100, description="Identifies provider or numerical model run")
    source_type: ForecastSourceType
    issue_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp when forecast model run was issued")
    valid_timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp for which forecast is valid")
    forecast_horizon_hours: float = Field(..., ge=0.0, le=168.0, description="Hours elapsed from issue to valid time")
    
    # Quantitative precipitation value
    rainfall_amount: Optional[float] = Field(None, description="Precipitation quantity; None if missing")
    rainfall_units: PrecipitationUnit = PrecipitationUnit.MILLIMETERS
    accumulation_interval: AccumulationInterval = AccumulationInterval.INTERVAL_1H
    is_instantaneous_rate: bool = Field(False, description="True if value represents mm/h rate rather than accumulated mm")
    
    # Spatial attributes
    latitude: Optional[float] = Field(None, ge=17.0, le=17.8)
    longitude: Optional[float] = Field(None, ge=78.1, le=78.8)
    spatial_resolution_km: Optional[float] = Field(None, ge=0.1, le=100.0)
    
    # Metadata & Quality
    quality_flags: List[ForecastQualityFlag] = Field(default_factory=list)
    is_synthetic_fixture: bool = Field(False, description="True if record is a test fixture; fixtures never claim operational skill")

    @model_validator(mode="after")
    def validate_forecast_contract(self) -> "ForecastRainfallInput":
        # 1. Parse timestamps into UTC-aware datetimes
        try:
            issue_dt = datetime.fromisoformat(self.issue_timestamp_utc.replace("Z", "+00:00"))
            if issue_dt.tzinfo is None:
                issue_dt = issue_dt.replace(tzinfo=timezone.utc)
            issue_dt = issue_dt.astimezone(timezone.utc)
        except Exception:
            raise ValueError(f"Invalid issue_timestamp_utc format: '{self.issue_timestamp_utc}'")

        try:
            valid_dt = datetime.fromisoformat(self.valid_timestamp_utc.replace("Z", "+00:00"))
            if valid_dt.tzinfo is None:
                valid_dt = valid_dt.replace(tzinfo=timezone.utc)
            valid_dt = valid_dt.astimezone(timezone.utc)
        except Exception:
            raise ValueError(f"Invalid valid_timestamp_utc format: '{self.valid_timestamp_utc}'")

        # 2. Temporal ordering: valid time must be >= issue time
        if valid_dt < issue_dt:
            raise ValueError(
                f"valid_timestamp_utc ({self.valid_timestamp_utc}) cannot be before issue_timestamp_utc ({self.issue_timestamp_utc})"
            )

        # 3. Horizon consistency: check that forecast_horizon_hours matches (valid_dt - issue_dt) within tolerance (0.1h)
        expected_horizon = round((valid_dt - issue_dt).total_seconds() / 3600.0, 2)
        if abs(self.forecast_horizon_hours - expected_horizon) > 0.1:
            raise ValueError(
                f"forecast_horizon_hours ({self.forecast_horizon_hours}) does not match temporal difference "
                f"between issue and valid timestamps ({expected_horizon} hours)"
            )

        # 4. Rainfall value physical bounds: non-negativity and finite checks
        if self.rainfall_amount is not None:
            if math.isnan(self.rainfall_amount) or math.isinf(self.rainfall_amount):
                raise ValueError("rainfall_amount must be a finite numerical value, not NaN or Inf")
            if self.rainfall_amount < 0.0:
                raise ValueError(f"rainfall_amount cannot be negative: {self.rainfall_amount}")
            if self.rainfall_amount > 300.0:
                raise ValueError(f"rainfall_amount exceeds physical extreme cloudburst limit (300mm): {self.rainfall_amount}")

        # 5. Distinction between accumulation total and instantaneous rate
        if self.is_instantaneous_rate and self.rainfall_units not in {PrecipitationUnit.MILLIMETERS_PER_HOUR}:
            raise ValueError("Instantaneous rainfall rate must use 'mm/h' units, not cumulative accumulation units")

        return self


class ObservedRainfallContext(BaseModel):
    """Separate context for physical rain gauge telemetry."""
    observed_1h_mm: Optional[float] = None
    observed_3h_mm: Optional[float] = None
    observation_timestamp_utc: Optional[str] = None
    telemetry_source_id: Optional[str] = None
    telemetry_distance_km: Optional[float] = None
    telemetry_freshness_hours: Optional[float] = None


class StaticVulnerabilityContext(BaseModel):
    """Separate context for physical geospatial susceptibility."""
    segment_id: str
    vulnerability_index: Optional[float] = None
    vulnerability_category: str = "UNKNOWN"


class CurrentRoadStatusContext(BaseModel):
    """Separate context for current physical road conditions on the ground."""
    condition_state: RoadConditionState = RoadConditionState.NO_CURRENT_EVIDENCE
    verification_state: RoadVerificationState = RoadVerificationState.UNMONITORED
    observation_age_minutes: Optional[float] = None


class ForecastRiskAssessmentOutput(BaseModel):
    """
    Experimental forecast-risk assessment payload.
    Strictly separates five distinct traceable evidence signals:
    1. Forecast rainfall context
    2. Observed rainfall context
    3. Static flood susceptibility
    4. Current road-status evidence
    5. Verified historical flood outcomes
    """
    segment_id: str
    road_name: str
    assessment_status: ForecastDataStatus
    assessment_timestamp_utc: str
    forecast_horizon_hours: Optional[float] = None

    # FIVE DISTINCT TRACEABLE EVIDENCE SIGNALS:
    forecast_rainfall_context: Optional[Dict[str, Any]] = None
    observed_rainfall_context: Optional[Dict[str, Any]] = None
    static_susceptibility_context: Dict[str, Any]
    current_road_status_context: Dict[str, Any]
    verified_historical_outcomes_context: Dict[str, Any]

    # Heuristic Risk Output (Explicitly Uncalibrated)
    forecast_risk_category: str = "UNKNOWN"
    heuristic_risk_score: Optional[float] = None
    is_calibrated_probability: bool = Field(
        False, description="Must remain False: heuristic score is NOT a calibrated probability"
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    uncertainty_level: str = "HIGH"

    # Quality & Reasoning
    data_quality_flags: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    safety_disclaimer: str = MANDATORY_FORECAST_RISK_DISCLAIMER
    is_actionable_for_dispatch: bool = False

    @field_validator("safety_disclaimer")
    @classmethod
    def validate_safety_disclaimer(cls, v: str) -> str:
        v_lower = v.lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in v_lower:
                raise ValueError(f"Safety disclaimer contains forbidden phrase: '{phrase}'")
        return v

    @model_validator(mode="after")
    def validate_safety_invariants(self) -> "ForecastRiskAssessmentOutput":
        # 1. Prohibit forbidden safety claims across all text fields
        all_text = " ".join([
            self.road_name,
            self.safety_disclaimer,
            " ".join(self.data_quality_flags),
            " ".join(self.reason_codes),
        ]).lower()
        for phrase in FORBIDDEN_SAFETY_PHRASES:
            if phrase in all_text:
                raise ValueError(f"Payload contains forbidden safety claim: '{phrase}'")

        # 2. Invariant: Probability claims prohibition
        if self.is_calibrated_probability:
            raise ValueError(
                "is_calibrated_probability cannot be declared True: heuristic output is NOT a calibrated probability."
            )

        # 3. Invariant: Missing or unsuitable forecast must remain UNKNOWN / INSUFFICIENT_DATA
        if self.assessment_status in {ForecastDataStatus.INSUFFICIENT_DATA, ForecastDataStatus.UNKNOWN}:
            if self.forecast_risk_category not in {"UNKNOWN", "INSUFFICIENT_DATA"}:
                raise ValueError(
                    f"forecast_risk_category must be UNKNOWN or INSUFFICIENT_DATA when assessment status is {self.assessment_status.value}"
                )
            if self.heuristic_risk_score is not None:
                raise ValueError(
                    "heuristic_risk_score must be None when forecast data is missing or insufficient"
                )

        # 4. Invariant: Forecast alone does NOT infer current flooding
        # If current road status has no active ground observation, it must remain NO_CURRENT_EVIDENCE / UNMONITORED
        current_cond = self.current_road_status_context.get("condition_state")
        if current_cond in {"NO_CURRENT_EVIDENCE", "UNKNOWN"}:
            if self.forecast_risk_category == "CRITICAL" and current_cond != "NO_CURRENT_EVIDENCE":
                raise ValueError("Forecast rainfall cannot declare current active inundation without ground observations.")

        return self
