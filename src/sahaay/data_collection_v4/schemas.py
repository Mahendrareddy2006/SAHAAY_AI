"""
Sahaay AI - Data Collection V4 Schema Definitions
Defines strict Pydantic models, Enums, and validation constraints for Hyderabad field data.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class PermissionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    MUNICIPAL_CCTV = "municipal_cctv"
    CITIZEN_UPLOAD = "citizen_upload"
    FIELD_TEAM_VANTAGE = "field_team_vantage"
    COMMERCIAL_DASHCAM = "commercial_dashcam"


class CaptureMethod(str, Enum):
    FIXED_CCTV = "fixed_cctv"
    SMARTPHONE_REAR = "smartphone_rear"
    DSLR_TRIPOD = "dslr_tripod"
    DASHCAM_FORWARD = "dashcam_forward"


class WeatherCondition(str, Enum):
    CLEAR = "clear"
    OVERCAST = "overcast"
    LIGHT_RAIN = "light_rain"
    HEAVY_RAIN = "heavy_rain"
    TORRENTIAL_DOWNPOUR = "torrential_downpour"


class LightingCondition(str, Enum):
    DAYLIGHT = "daylight"
    TWILIGHT_DUSK = "twilight_dusk"
    TWILIGHT_DAWN = "twilight_dawn"
    NIGHT_STREETLIGHTS = "night_streetlights"
    NIGHT_UNLIT = "night_unlit"


class RoadSurfaceCondition(str, Enum):
    DRY = "dry"
    WET_SHEEN = "wet_sheen"
    WET_PUDDLES_POTHOLES = "wet_puddles_potholes"
    INUNDATED_SHALLOW = "inundated_shallow"
    INUNDATED_DEEP = "inundated_deep"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED_QUALITY = "rejected_quality"
    REJECTED_SAFETY = "rejected_safety"


class PrivacyProcessingStatus(str, Enum):
    UNPROCESSED = "unprocessed"
    BLURRED_VERIFIED = "blurred_verified"
    QUARANTINED_PII = "quarantined_pii"


class AnnotationLabel(str, Enum):
    FLOODED_ROAD = "flooded_road"
    WET_NO_VISIBLE_INUNDATION = "wet_no_visible_inundation"
    DRY_ROAD = "dry_road"
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"


class AdjudicationStatus(str, Enum):
    UNADJUDICATED = "unadjudicated"
    CONSENSUS = "consensus"
    ADJUDICATED_BY_LEAD = "adjudicated_by_lead"
    REJECTED_AMBIGUOUS = "rejected_ambiguous"


class DepthMeasurementMethod(str, Enum):
    UNMEASURED = "unmeasured"
    ULTRASONIC_TELEMETRY = "ultrasonic_telemetry"
    STAFF_GAUGE = "staff_gauge"
    CALIBRATED_CURB_STANDARD = "calibrated_curb_standard"
    RESPONDER_MANUAL = "responder_manual"


class VerifiedPassability(str, Enum):
    UNVERIFIED_UNKNOWN = "unverified_unknown"
    PASSABLE_ALL_VEHICLES = "passable_all_vehicles"
    IMPASSABLE_TWO_WHEELERS = "impassable_two_wheelers"
    IMPASSABLE_FOUR_WHEELERS = "impassable_four_wheelers"
    IMPASSABLE_ALL_VEHICLES = "impassable_all_vehicles"


class ImageQualityStatus(str, Enum):
    SUFFICIENT = "sufficient"
    UNCERTAIN_SEVERE_GLARE = "uncertain_severe_glare"
    OCCLUDED_BY_SPRAY = "occluded_by_spray"
    INSUFFICIENT_RESOLUTION = "insufficient_resolution"
    UNDER_ILLUMINATED_NIGHT = "under_illuminated_night"
    AMBIGUOUS_PERSPECTIVE = "ambiguous_perspective"


class AcquisitionRecord(BaseModel):
    """
    Tracks provenance, capture conditions, consent, and privacy status for an acquired asset.
    """
    acquisition_id: str = Field(..., description="Unique acquisition record ID")
    location_id: str = Field(..., description="Corridor foreign key (e.g., HYD-LOC-001)")
    capture_timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    source_type: SourceType
    source_owner: str
    permission_status: PermissionStatus
    consent_or_authorization_reference: Optional[str] = Field(None, description="MOU or terms ID")
    capture_method: CaptureMethod
    camera_or_device_id_pseudonymous: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_precision_m: float = Field(..., gt=0.0)
    weather_condition: WeatherCondition
    lighting_condition: LightingCondition
    road_surface_condition: RoadSurfaceCondition
    image_or_clip_reference: str
    annotation_status: str = Field("unassigned")
    review_status: ReviewStatus = Field(ReviewStatus.PENDING)
    privacy_processing_status: PrivacyProcessingStatus = Field(PrivacyProcessingStatus.UNPROCESSED)
    retention_expiry: str
    exclusion_reason: str = Field("none")
    capture_session_id: Optional[str] = Field(
        None, description="Identifier grouping sequential frames captured in one session, patrol, or video clip"
    )

    @model_validator(mode="after")
    def validate_permission_and_consent(self) -> "AcquisitionRecord":
        if self.permission_status == PermissionStatus.APPROVED:
            ref = (self.consent_or_authorization_reference or "").strip()
            if not ref or ref.upper() in ["PENDING", "UNKNOWN", "PENDING_VERIFICATION", "NONE"]:
                raise ValueError(
                    f"Acquisition {self.acquisition_id} marked as APPROVED must provide a valid "
                    "consent_or_authorization_reference (e.g. MOU, IRB, or Terms reference)."
                )
        return self


class AnnotationRecord(BaseModel):
    """
    Tracks ground truth annotation, observable evidence, independent measurements, and annotator uncertainty.
    Enforces strict separation between visual appearance, verified flood events, physical water depth,
    and road passability.
    """
    image_id: str
    annotator_id_pseudonymous: str
    label: AnnotationLabel
    visible_water_extent: str = Field(..., description="none, isolated_puddles, partial_lane, curb_to_curb")
    road_obstruction_evidence: str = Field(..., description="none, slow_traffic, diverted_traffic, stalled_vehicles")
    visibility_quality: str = Field(..., description="high_clarity, moderate_spray, heavy_rain_obscured, glare")
    lighting_condition: LightingCondition
    occlusion: str = Field("none", description="none, tree_branch, vehicle_spray, partial_lens_flare")
    label_confidence: float = Field(..., ge=0.0, le=1.0)
    adjudication_status: AdjudicationStatus = Field(AdjudicationStatus.UNADJUDICATED)
    adjudicated_label: Optional[AnnotationLabel] = None
    annotation_notes: Optional[str] = None

    # Phase 15 explicit decoupled fields:
    is_wet_non_flooded: bool = Field(False, description="Flag for wet road surface without contiguous inundation")
    verified_flood_event_id: Optional[str] = Field(None, description="External flood event identifier if independently verified")
    event_verification_source: str = Field("unverified", description="Authority or organization verifying flood event")
    measured_water_depth_mm: Optional[float] = Field(None, ge=0.0, description="Physically measured water depth in mm, NEVER inferred from image")
    depth_measurement_time: Optional[str] = Field(None, description="ISO timestamp of depth measurement")
    depth_measurement_method: DepthMeasurementMethod = Field(DepthMeasurementMethod.UNMEASURED, description="Method used to measure water depth")
    verified_road_passability: VerifiedPassability = Field(VerifiedPassability.UNVERIFIED_UNKNOWN, description="Independently verified passability, NEVER inferred from classifier")
    image_quality_status: ImageQualityStatus = Field(ImageQualityStatus.SUFFICIENT, description="Image quality / clarity category")

    @model_validator(mode="after")
    def validate_governance_invariants(self) -> "AnnotationRecord":
        # 1. Depth measurement method consistency
        if self.measured_water_depth_mm is not None and self.measured_water_depth_mm > 0.0:
            if self.depth_measurement_method == DepthMeasurementMethod.UNMEASURED:
                raise ValueError(
                    f"Annotation for image {self.image_id} has measured_water_depth_mm={self.measured_water_depth_mm} "
                    "but depth_measurement_method is 'unmeasured'. Physical measurement method must be specified."
                )
        if self.depth_measurement_method != DepthMeasurementMethod.UNMEASURED:
            if self.measured_water_depth_mm is None:
                raise ValueError(
                    f"Annotation for image {self.image_id} specifies depth_measurement_method="
                    f"'{self.depth_measurement_method.value}' but measured_water_depth_mm is None."
                )

        # 2. Rejection of model-inferred depth or passability
        method_str = str(self.depth_measurement_method.value).lower()
        if "model" in method_str or "infer" in method_str or "classifier" in method_str:
            raise ValueError(
                f"Prohibited depth measurement method '{self.depth_measurement_method.value}'. "
                "Water depth must NEVER be inferred from an image classifier."
            )

        source_str = str(self.event_verification_source).lower()
        if "model" in source_str or "classifier" in source_str:
            raise ValueError(
                f"Prohibited event verification source '{self.event_verification_source}'. "
                "Event verification must come from an independent authority, never a computer vision model."
            )

        if self.verified_road_passability != VerifiedPassability.UNVERIFIED_UNKNOWN:
            if self.event_verification_source.strip().lower() in ["unverified", "none", ""]:
                raise ValueError(
                    f"Annotation for image {self.image_id} asserts verified_road_passability="
                    f"'{self.verified_road_passability.value}', but event_verification_source is unverified. "
                    "Road passability must NEVER be inferred from image classification alone."
                )

        # 3. Wet non-flooded road distinction
        if self.is_wet_non_flooded and self.label == AnnotationLabel.FLOODED_ROAD:
            raise ValueError(
                f"Contradictory annotation for image {self.image_id}: is_wet_non_flooded=True cannot be "
                "labeled as FLOODED_ROAD. Wet non-flooded roads must be kept distinct from inundated roads."
            )

        return self


class ImageAuditResult(BaseModel):
    """
    Technical and cryptographic audit result for an ingested image file.
    """
    file_path: str
    exists: bool
    decodable: bool
    width: int = 0
    height: int = 0
    aspect_ratio: float = 0.0
    file_size_kb: float = 0.0
    md5: str = ""
    sha256: str = ""
    dhash: str = ""
    error_message: Optional[str] = None
