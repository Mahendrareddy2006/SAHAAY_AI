"""Ground-truth observation schemas and validation models for Sahaay AI Phase 6."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
import re
from pydantic import BaseModel, Field, field_validator, model_validator


class ObservationMethod(str, Enum):
    PHYSICAL_VANTAGE_INSPECTION = "PHYSICAL_VANTAGE_INSPECTION"
    CALIBRATED_STAFF_GAUGE = "CALIBRATED_STAFF_GAUGE"
    OFFICIAL_DISPATCH_RECORD = "OFFICIAL_DISPATCH_RECORD"
    TELEMETRY_SENSOR = "TELEMETRY_SENSOR"


class WaterPresenceExtent(str, Enum):
    NO_WATER = "NO_WATER"
    SURFACE_WETNESS_OR_PUDDLE = "SURFACE_WETNESS_OR_PUDDLE"
    PARTIAL_LANE_WATERLOGGING = "PARTIAL_LANE_WATERLOGGING"
    FULL_ROADWAY_INUNDATION = "FULL_ROADWAY_INUNDATION"
    UNABLE_TO_OBSERVE = "UNABLE_TO_OBSERVE"
    INSUFFICIENT_QUALITY = "INSUFFICIENT_QUALITY"


class DepthMeasurementMethod(str, Enum):
    PHYSICAL_GAUGE_STAFF = "PHYSICAL_GAUGE_STAFF"
    CURB_REFERENCE_CALIBRATION = "CURB_REFERENCE_CALIBRATION"
    ESTIMATED_WHEEL_SUBMERSION = "ESTIMATED_WHEEL_SUBMERSION"
    NOT_MEASURED = "NOT_MEASURED"


class RoadPassability(str, Enum):
    PASSABLE_ALL_VEHICLES = "PASSABLE_ALL_VEHICLES"
    IMPASSABLE_TWO_WHEELERS = "IMPASSABLE_TWO_WHEELERS"
    IMPASSABLE_LOW_SEDANS = "IMPASSABLE_LOW_SEDANS"
    IMPASSABLE_ALL_LIGHT_VEHICLES = "IMPASSABLE_ALL_LIGHT_VEHICLES"
    TOTALLY_IMPASSABLE = "TOTALLY_IMPASSABLE"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SUPERVISOR_VERIFIED = "SUPERVISOR_VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ConsentPrivacyStatus(str, Enum):
    DPDP_CONSENT_GRANTED_REDACTED = "DPDP_CONSENT_GRANTED_REDACTED"
    EXEMPT_RESEARCH_PUBLIC = "EXEMPT_RESEARCH_PUBLIC"
    WITHHELD = "WITHHELD"


class GroundTruthObservation(BaseModel):
    """Calibrated, auditable ground-truth field observation record."""

    observation_id: str = Field(..., pattern=r"^OBS-[0-9]{8}-[0-9]{4}$")
    start_time_utc: datetime = Field(...)
    end_time_utc: datetime = Field(...)
    timezone: str = Field("Asia/Kolkata")
    corridor_id: str = Field(..., min_length=3)
    latitude: float = Field(..., ge=17.20, le=17.60, description="Hyderabad Metropolitan bounding box")
    longitude: float = Field(..., ge=78.20, le=78.65, description="Hyderabad Metropolitan bounding box")
    coordinate_precision_m: float = Field(..., gt=0.0, le=100.0)
    observer_pseudonym: str = Field(..., pattern=r"^OBSERVER-[A-Z0-9]{3,8}$")
    observation_method: ObservationMethod = Field(...)
    water_presence_extent: WaterPresenceExtent = Field(...)
    measured_water_depth_cm: Optional[float] = Field(None, ge=0.0, le=300.0)
    depth_measurement_method: DepthMeasurementMethod = Field(...)
    road_passability: RoadPassability = Field(...)
    rainfall_source: str = Field(..., min_length=3)
    rainfall_source_timestamp_utc: datetime = Field(...)
    image_reference: Optional[str] = None
    quality_flags: str = Field("NONE")
    verification_status: VerificationStatus = Field(VerificationStatus.DRAFT)
    verifier_timestamp_utc: Optional[datetime] = None
    related_incident_id: Optional[str] = None
    consent_and_privacy_status: ConsentPrivacyStatus = Field(...)
    retention_policy_months: int = Field(36, ge=1, le=120)
    is_synthetic_or_simulated: bool = Field(False)

    @field_validator("consent_and_privacy_status")
    @classmethod
    def validate_consent(cls, v: ConsentPrivacyStatus) -> ConsentPrivacyStatus:
        if v == ConsentPrivacyStatus.WITHHELD:
            raise ValueError("Records with consent WITHHELD are strictly prohibited from ingestion.")
        return v

    @model_validator(mode="after")
    def validate_temporal_and_measurement_consistency(self) -> "GroundTruthObservation":
        # Temporal order
        if self.end_time_utc < self.start_time_utc:
            raise ValueError(f"end_time_utc ({self.end_time_utc}) cannot be before start_time_utc ({self.start_time_utc})")

        # Future check
        now_utc = datetime.now(timezone.utc)
        # Ensure start_time has timezone
        start_tz = self.start_time_utc if self.start_time_utc.tzinfo else self.start_time_utc.replace(tzinfo=timezone.utc)
        if start_tz > now_utc:
            raise ValueError(f"start_time_utc ({self.start_time_utc}) cannot be in the future.")

        # Depth consistency
        if self.water_presence_extent == WaterPresenceExtent.NO_WATER:
            if self.measured_water_depth_cm is not None and self.measured_water_depth_cm > 0.0:
                raise ValueError("measured_water_depth_cm must be 0.0 or None when water_presence_extent is NO_WATER.")

        if self.measured_water_depth_cm is not None and self.measured_water_depth_cm > 0.0:
            if self.depth_measurement_method == DepthMeasurementMethod.NOT_MEASURED:
                raise ValueError("depth_measurement_method cannot be NOT_MEASURED when measured_water_depth_cm is > 0.")

        # Verification consistency
        if self.verification_status == VerificationStatus.SUPERVISOR_VERIFIED:
            if not self.verifier_timestamp_utc:
                raise ValueError("verifier_timestamp_utc is required when verification_status is SUPERVISOR_VERIFIED.")

        return self
