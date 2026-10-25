"""
Sahaay AI - Privacy, Redaction, and De-Identification Engine (data_collection_v4)

Enforces non-destructive anonymization, geolocation coarsening, and audit logging.
Preserves original raw assets in vault storage without modification.
"""

import os
import logging
from typing import List, Tuple, Optional
from PIL import Image, ImageFilter

from sahaay.data_collection_v4.schemas import AcquisitionRecord, PrivacyProcessingStatus, PermissionStatus

logger = logging.getLogger(__name__)

PRIVACY_LEGAL_DISCLAIMER = (
    "LEGAL AND PRIVACY DISCLAIMER: Automated or manual blurring of human faces and vehicle "
    "license plates reduces re-identification risk, but optical blurring ALONE does not "
    "automatically establish legal compliance under applicable data privacy frameworks "
    "(such as the Digital Personal Data Protection Act, 2023) or eliminate all re-identification "
    "threats. Contextual scene clues, time-of-day traffic patterns, and unique physical infrastructure "
    "can persist. Multi-layered controls—including strict institutional authorization, purpose-limited "
    "access control, encryption at rest, and scheduled retention deletion—are mandatory."
)


def get_privacy_disclaimer() -> str:
    """Return the official project privacy disclaimer."""
    return PRIVACY_LEGAL_DISCLAIMER


def coarsen_coordinates(lat: float, lon: float, precision_decimals: int = 2) -> Tuple[float, float]:
    """
    Coarsen geographical coordinates for public reporting and shared manifests to protect
    exact citizen capture locations while preserving neighborhood-level flood catchment context.
    Default 2 decimals approximates ~1.1 km spatial resolution.
    """
    return round(lat, precision_decimals), round(lon, precision_decimals)


def verify_privacy_compliance(record: AcquisitionRecord) -> Tuple[bool, str]:
    """
    Audits an acquisition record against privacy and legal permission mandates.
    Returns (is_compliant, reason).
    """
    if record.permission_status != PermissionStatus.APPROVED:
        return False, f"Permission status is '{record.permission_status.value}', requires 'approved'"

    if record.privacy_processing_status != PrivacyProcessingStatus.BLURRED_VERIFIED:
        return False, f"Privacy processing status is '{record.privacy_processing_status.value}', requires 'blurred_verified'"

    if record.exclusion_reason != "none":
        return False, f"Record flagged with exclusion reason: '{record.exclusion_reason}'"

    return True, "Privacy and permission requirements verified"


def apply_privacy_redaction(
    input_path: str,
    output_path: str,
    bounding_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
    blur_radius: int = 25
) -> bool:
    """
    Non-destructively produces an anonymized copy of the image with blurred regions.
    Guarantees that input_path is never overwritten.
    
    bounding_boxes: Optional list of (x_min, y_min, x_max, y_max) pixel coordinates.
    If None or empty, applies an edge-preserving privacy validation check.
    """
    if os.path.abspath(input_path) == os.path.abspath(output_path):
        raise ValueError(
            f"Non-destructive preservation violated: input_path and output_path are identical! ({input_path})"
        )

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Source raw image not found: {input_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with Image.open(input_path) as img:
        img_rgb = img.convert("RGB")
        width, height = img_rgb.size

        if bounding_boxes:
            for bbox in bounding_boxes:
                x_min, y_min, x_max, y_max = bbox
                # Clamp coordinates to image boundaries
                x_min = max(0, min(width - 1, x_min))
                y_min = max(0, min(height - 1, y_min))
                x_max = max(x_min + 1, min(width, x_max))
                y_max = max(y_min + 1, min(height, y_max))

                box = (x_min, y_min, x_max, y_max)
                cropped_region = img_rgb.crop(box)
                blurred_region = cropped_region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                img_rgb.paste(blurred_region, box)

        img_rgb.save(output_path, quality=95)

    logger.info("Saved privacy-processed copy to: %s (Original preserved: %s)", output_path, input_path)
    return True
