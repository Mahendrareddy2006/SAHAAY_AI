"""
Sahaay AI - Vision Decision Policy & Calibrated Abstention Rules
Defines explicit decision boundaries, probability direction, and ambiguity band abstention
for Flood Vision inference without deep learning runtime dependencies.

SCIENTIFIC & SAFETY DIRECTIVE:
Continuous model probabilities reflect laboratory/web-trained baseline prototypes (e.g. MobileNetV3)
and must NOT be claimed as calibrated for real-world Hyderabad road corridors unless supported
by authorized, empirical local field evaluation evidence.
"""

import math
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CalibratedVisionDecision(str, Enum):
    """Calibrated operational decision categories for advisory vision inference."""
    FLOOD_EVIDENCE_DETECTED = "FLOOD_EVIDENCE_DETECTED"
    NO_CURRENT_FLOOD_EVIDENCE = "NO_CURRENT_FLOOD_EVIDENCE"
    INCONCLUSIVE = "INCONCLUSIVE"


# Class index mapping from training configuration:
# Index 0 -> not_flooded (negative class: dry pavement, wet puddles, potholes)
# Index 1 -> flooded (positive class: standing inundation, curb submersion)
FLOOD_CLASS_INDEX = 1
NOT_FLOODED_CLASS_INDEX = 0

# Established Project Inclusive Abstention Interval: [0.35, 0.65]
DEFAULT_ABSTENTION_LOWER_BOUND = 0.35
DEFAULT_ABSTENTION_UPPER_BOUND = 0.65


def evaluate_vision_abstention_boundary(
    raw_flood_probability: float,
    lower_threshold: float = DEFAULT_ABSTENTION_LOWER_BOUND,
    upper_threshold: float = DEFAULT_ABSTENTION_UPPER_BOUND,
) -> Tuple[CalibratedVisionDecision, float, bool]:
    """
    Evaluates continuous flood probability against the project's inclusive abstention band [0.35, 0.65].

    Strict Invariants:
    1. raw_prob > upper_threshold (0.65) -> FLOOD_EVIDENCE_DETECTED (confidence = raw_prob, is_ambiguous = False)
    2. raw_prob < lower_threshold (0.35) -> NO_CURRENT_FLOOD_EVIDENCE (confidence = 1.0 - raw_prob, is_ambiguous = False)
    3. lower_threshold <= raw_prob <= upper_threshold -> INCONCLUSIVE (model strictly abstains; is_ambiguous = True)
       Specifically: exactly 0.35 or 0.65 produces INCONCLUSIVE.
    4. Rejects non-finite values (NaN, +inf, -inf) with ValueError.
    5. Rejects Boolean inputs (True, False) with TypeError.
    6. Rejects values outside [0.0, 1.0] with ValueError.
    7. NO_CURRENT_FLOOD_EVIDENCE indicates only absence of visible standing water in frame;
       it NEVER guarantees that the road is safe or passable.

    Args:
        raw_flood_probability: Continuous probability in [0.0, 1.0] representing class 1 (flooded).
        lower_threshold: Non-flood decision boundary. Default 0.35.
        upper_threshold: Flood decision boundary. Default 0.65.

    Returns:
        Tuple of (CalibratedVisionDecision, confidence, is_ambiguous).
    """
    # Reject boolean inputs before numeric check (in Python bool is a subclass of int)
    if isinstance(raw_flood_probability, bool):
        raise TypeError(f"Boolean values not accepted as numeric probabilities: {raw_flood_probability}")

    if not isinstance(raw_flood_probability, (int, float)):
        raise TypeError(f"raw_flood_probability must be float or int, got {type(raw_flood_probability)}")

    if not math.isfinite(raw_flood_probability):
        raise ValueError(f"raw_flood_probability must be a finite number, got {raw_flood_probability}")

    if raw_flood_probability < 0.0 or raw_flood_probability > 1.0:
        raise ValueError(f"raw_flood_probability must be in range [0.0, 1.0], got {raw_flood_probability}")

    confidence = round(max(raw_flood_probability, 1.0 - raw_flood_probability), 4)

    if raw_flood_probability > upper_threshold:
        return CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED, confidence, False
    elif raw_flood_probability < lower_threshold:
        return CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE, confidence, False
    else:
        # Inclusive abstention interval [lower_threshold, upper_threshold] (including 0.35 and 0.65)
        return CalibratedVisionDecision.INCONCLUSIVE, confidence, True


def map_vision_probabilities_to_decision(
    score_flooded: float,
    lower_threshold: float = DEFAULT_ABSTENTION_LOWER_BOUND,
    upper_threshold: float = DEFAULT_ABSTENTION_UPPER_BOUND,
) -> Tuple[str, float, bool, bool, List[str]]:
    """
    Maps continuous flood probability into standardized API fields:
    (predicted_class, confidence, is_ambiguous, is_inconclusive, inconclusive_reasons).

    Enforces that ambiguous model outputs in [0.35, 0.65] produce an explicit 'inconclusive'
    predicted_class rather than forcing a binary classification.
    """
    decision, confidence, is_ambiguous = evaluate_vision_abstention_boundary(
        raw_flood_probability=score_flooded,
        lower_threshold=lower_threshold,
        upper_threshold=upper_threshold,
    )

    if decision == CalibratedVisionDecision.FLOOD_EVIDENCE_DETECTED:
        return "flooded", confidence, False, False, []
    elif decision == CalibratedVisionDecision.NO_CURRENT_FLOOD_EVIDENCE:
        return "not_flooded", confidence, False, False, []
    else:
        reasons = [
            f"Model flood probability ({score_flooded:.3f}) falls within [{lower_threshold:.2f}, {upper_threshold:.2f}] "
            "ambiguity abstention band. Manual review required."
        ]
        return "inconclusive", confidence, True, True, reasons
