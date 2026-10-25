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
    Tracks ground truth annotation, observable evidence, and annotator uncertainty.
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
