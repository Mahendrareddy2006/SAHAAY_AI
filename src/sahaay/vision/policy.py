"""
Sahaay AI - Vision Decision Policy & Calibrated Abstention Rules
Defines explicit decision boundaries, probability direction, and ambiguity band abstention
for Flood Vision inference without deep learning runtime dependencies.
"""

from enum import Enum
from typing import Tuple


class CalibratedVisionDecision(str, Enum):
    """Calibrated operational decision categories for advisory vision inference."""
    FLOOD_EVIDENCE_DETECTED = "FLOOD_EVIDENCE_DETECTED"
    NO_CURRENT_FLOOD_EVIDENCE = "NO_CURRENT_FLOOD_EVIDENCE"
    INCONCLUSIVE = "INCONCLUSIVE"


# Class index mapping from training configuration:
# 0 -> not_flooded (negative class)
# 1 -> flooded (positive class)
FLOOD_CLASS_INDEX = 1
NOT_FLOODED_CLASS_INDEX = 0

# Established Phase 11 Handover Ambiguity Band: [0.35, 0.65]
DEFAULT_ABSTENTION_LOWER_BOUND = 0.35
DEFAULT_ABSTENTION_UPPER_BOUND = 0.65


def evaluate_vision_abstention_boundary(
    raw_flood_probability: float,
    lower_threshold: float = DEFAULT_ABSTENTION_LOWER_BOUND,
    upper_threshold: float = DEFAULT_ABSTENTION_UPPER_BOUND,
) -> Tuple[CalibratedVisionDecision, float, bool]:
    """
    Evaluates calibrated continuous flood probability against mandatory abstention boundaries.

    Invariants:
    1. raw_prob >= upper_threshold (0.65) -> FLOOD_EVIDENCE_DETECTED (confidence = raw_prob)
    2. raw_prob <= lower_threshold (0.35) -> NO_CURRENT_FLOOD_EVIDENCE (confidence = 1.0 - raw_prob)
    3. lower_threshold < raw_prob < upper_threshold -> INCONCLUSIVE (model strictly abstains)
    4. NO_CURRENT_FLOOD_EVIDENCE indicates only absence of visible standing water in frame;
       it NEVER guarantees that the road is safe or passable.

    Args:
        raw_flood_probability: Continuous probability in [0.0, 1.0] representing class 1 (flooded).
        lower_threshold: Non-flood decision upper bound (inclusive). Default 0.35.
        upper_threshold: Flood decision lower bound (inclusive). Default 0.65.

    Returns:
        Tuple of (CalibratedVisionDecision, confidence, is_ambiguous).
    """
    if not isinstance(raw_flood_probability, (int, float)):
        raise TypeError(f"raw_flood_probability must be float, got {type(raw_flood_probability)}")

    if raw_flood_probability < 0.0 or raw_flood_probability > 1.0:
        raise ValueError(f"raw_flood_probability must be in range [0.0, 1.0], got {raw_flood_probability}")

    confidence = round(max(raw_flood_probability, 1.0 - raw_flood_probability), 4)

    if raw_flood_probability >= upper_threshold:
        return CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, confidence, False
    elif raw_flood_probability <= lower_threshold:
        return CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, confidence, False
    else:
        # Strictly in ambiguity band (0.35, 0.65) -> Model must abstain
        return CalibratedVisionDecision.INCONCLUSIVE, confidence, True
