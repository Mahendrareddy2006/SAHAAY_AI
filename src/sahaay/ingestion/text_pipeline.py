"""
Sahaay AI - Text & News Analysis Pipeline
Classifies textual reports and news articles into flood risk categories
and resolves Hyderabad localities without hallucinating coordinates.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple

from sahaay.ingestion.schemas import (
    IngestionEventType,
    LocationResolutionAccuracy,
)

# Known Hyderabad localities mapped to representative coordinates and candidate seed corridors
HYDERABAD_LOCALITY_MAP: Dict[str, Dict[str, Any]] = {
    "tolichowki": {
        "canonical_name": "Tolichowki",
        "lat": 17.4010,
        "lon": 78.4110,
        "corridor_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
    },
    "shaikpet": {
        "canonical_name": "Shaikpet",
        "lat": 17.4095,
        "lon": 78.3986,
        "corridor_id": "HYD-LOC-002",
        "road_name": "Shaikpet Nala Road",
    },
    "begumpet": {
        "canonical_name": "Begumpet",
        "lat": 17.4419,
        "lon": 78.4728,
        "corridor_id": "HYD-LOC-003",
        "road_name": "Begumpet Rasoolpura Underpass",
    },
    "rasoolpura": {
        "canonical_name": "Rasoolpura",
        "lat": 17.4419,
        "lon": 78.4728,
        "corridor_id": "HYD-LOC-003",
        "road_name": "Begumpet Rasoolpura Underpass",
    },
    "khairatabad": {
        "canonical_name": "Khairatabad",
        "lat": 17.4116,
        "lon": 78.4611,
        "corridor_id": "HYD-LOC-004",
        "road_name": "Khairatabad Flyover Junction",
    },
    "raj bhavan": {
        "canonical_name": "Raj Bhavan Road",
        "lat": 17.4116,
        "lon": 78.4611,
        "corridor_id": "HYD-LOC-004",
        "road_name": "Khairatabad Flyover Junction",
    },
    "malakpet": {
        "canonical_name": "Malakpet",
        "lat": 17.3768,
        "lon": 78.4975,
        "corridor_id": "HYD-LOC-005",
        "road_name": "Malakpet Railway Underbridge",
    },
    "chaderghat": {
        "canonical_name": "Chaderghat",
        "lat": 17.3768,
        "lon": 78.4975,
        "corridor_id": "HYD-LOC-005",
        "road_name": "Malakpet Railway Underbridge",
    },
    "panjagutta": {
        "canonical_name": "Panjagutta",
        "lat": 17.4262,
        "lon": 78.4518,
        "corridor_id": "HYD-LOC-006",
        "road_name": "Panjagutta Underpass & Nagarjuna Circle",
    },
    "nagarjuna circle": {
        "canonical_name": "Nagarjuna Circle",
        "lat": 17.4262,
        "lon": 78.4518,
        "corridor_id": "HYD-LOC-006",
        "road_name": "Panjagutta Underpass & Nagarjuna Circle",
    },
    "ameerpet": {
        "canonical_name": "Ameerpet",
        "lat": 17.4350,
        "lon": 78.4480,
        "corridor_id": "HYD-LOC-006",
        "road_name": "Panjagutta Underpass & Nagarjuna Circle",
    },
    "gachibowli": {
        "canonical_name": "Gachibowli",
        "lat": 17.4428,
        "lon": 78.3654,
        "corridor_id": "HYD-LOC-007",
        "road_name": "Gachibowli Bio-Diversity Flyover Underpass",
    },
    "biodiversity": {
        "canonical_name": "Bio-Diversity Junction",
        "lat": 17.4428,
        "lon": 78.3654,
        "corridor_id": "HYD-LOC-007",
        "road_name": "Gachibowli Bio-Diversity Flyover Underpass",
    },
    "lakdikapul": {
        "canonical_name": "Lakdikapul",
        "lat": 17.4048,
        "lon": 78.4645,
        "corridor_id": "HYD-LOC-008",
        "road_name": "Lakdikapul Junction & Railway Bridge",
    },
    "uppal": {
        "canonical_name": "Uppal",
        "lat": 17.4035,
        "lon": 78.5605,
        "corridor_id": "HYD-LOC-016",
        "road_name": "Uppal Ring Road Junction",
    },
    "mehdipatnam": {
        "canonical_name": "Mehdipatnam",
        "lat": 17.3950,
        "lon": 78.4380,
        "corridor_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
    },
    "rethibowli": {
        "canonical_name": "Rethibowli",
        "lat": 17.3980,
        "lon": 78.4320,
        "corridor_id": "HYD-LOC-001",
        "road_name": "Tolichowki Flyover Underpass",
    },
    "moosarambagh": {
        "canonical_name": "Moosarambagh",
        "lat": 17.3750,
        "lon": 78.5120,
        "corridor_id": "HYD-LOC-005",
        "road_name": "Malakpet Railway Underbridge",
    },
    "amberpet": {
        "canonical_name": "Amberpet",
        "lat": 17.3880,
        "lon": 78.5150,
        "corridor_id": "HYD-LOC-016",
        "road_name": "Uppal Ring Road Junction",
    },
}

# Out-of-scope non-Hyderabad locations that must be rejected
OUT_OF_SCOPE_LOCATIONS = [
    "warangal", "vijayawada", "visakhapatnam", "vizag", "guntur",
    "bengaluru", "bangalore", "chennai", "mumbai", "delhi", "pune"
]

# Classification keywords
FLOOD_KEYWORDS = [
    "waterlogg", "flooded", "flooding", "submerged", "inundat",
    "knee-deep", "waist-deep", "waterlogged", "water logging",
    "overflowing", "deluge", "standing water", "sheets of water"
]

WEATHER_KEYWORDS = [
    "heavy rain", "cloudburst", "red alert", "orange alert", "yellow alert",
    "downpour", "thunderstorm", "imd alert", "imd warning", "heavy rainfall",
    "rainfall forecast", "monsoon surge", "squall"
]

DISRUPTION_KEYWORDS = [
    "traffic diverted", "traffic diversion", "underpass closed", "rub closed",
    "road blocked", "impassable", "stranded vehicles", "gridlock",
    "flyover closed", "traffic halted"
]

RESCUE_KEYWORDS = [
    "rescue", "evacuat", "drf team", "ndrf", "ghmc disaster",
    "relief camp", "shelter opened", "emergency team"
]


@dataclass
class TextAnalysisResult:
    event_type: IngestionEventType
    confidence: float
    reported_place_name: Optional[str]
    resolved_corridor_id: Optional[str]
    resolved_road_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_accuracy: LocationResolutionAccuracy
    matched_keywords: List[str]
    is_out_of_scope: bool
    is_ambiguous: bool
    summary: str


class TextAnalysisPipeline:
    """
    Deterministic rule and keyword analysis engine for Hyderabad flood intelligence.
    Performs event categorization and location extraction without external paid APIs.
    """

    def analyze_text(self, text: str) -> TextAnalysisResult:
        if not text:
            return TextAnalysisResult(
                event_type=IngestionEventType.IRRELEVANT_OR_UNSUPPORTED,
                confidence=0.0,
                reported_place_name=None,
                resolved_corridor_id=None,
                resolved_road_name=None,
                latitude=None,
                longitude=None,
                location_accuracy=LocationResolutionAccuracy.UNRESOLVED,
                matched_keywords=[],
                is_out_of_scope=False,
                is_ambiguous=True,
                summary="Empty text payload"
            )

        lower_text = text.lower()

        # 1. Out-of-Scope Check
        for oos in OUT_OF_SCOPE_LOCATIONS:
            if re.search(r"\b" + re.escape(oos) + r"\b", lower_text):
                # If an out of scope city is found, check if Hyderabad is also explicitly mentioned
                if "hyderabad" not in lower_text:
                    return TextAnalysisResult(
                        event_type=IngestionEventType.IRRELEVANT_OR_UNSUPPORTED,
                        confidence=0.85,
                        reported_place_name=oos.title(),
                        resolved_corridor_id=None,
                        resolved_road_name=None,
                        latitude=None,
                        longitude=None,
                        location_accuracy=LocationResolutionAccuracy.OUT_OF_SCOPE,
                        matched_keywords=[oos],
                        is_out_of_scope=True,
                        is_ambiguous=False,
                        summary=f"Event pertains to out-of-scope non-Hyderabad region ({oos.title()})"
                    )

        # 2. Location Resolution
        reported_place: Optional[str] = None
        corridor_id: Optional[str] = None
        road_name: Optional[str] = None
        lat: Optional[float] = None
        lon: Optional[float] = None
        accuracy = LocationResolutionAccuracy.UNRESOLVED
        is_ambiguous = False

        for loc_key, loc_meta in HYDERABAD_LOCALITY_MAP.items():
            if re.search(r"\b" + re.escape(loc_key) + r"\b", lower_text):
                reported_place = loc_meta["canonical_name"]
                corridor_id = loc_meta["corridor_id"]
                road_name = loc_meta["road_name"]
                lat = loc_meta["lat"]
                lon = loc_meta["lon"]
                accuracy = LocationResolutionAccuracy.CORRIDOR_MATCH
                break

        if not reported_place:
            if "hyderabad" in lower_text or "ghmc" in lower_text:
                reported_place = "Greater Hyderabad (Citywide)"
                accuracy = LocationResolutionAccuracy.AMBIGUOUS_CITYWIDE
                is_ambiguous = True

        # 3. Categorization
        matched_kw: List[str] = []
        event_type = IngestionEventType.IRRELEVANT_OR_UNSUPPORTED
        confidence = 0.5

        # Check in priority order: Rescue -> Disruption -> Inundation -> Weather
        for kw in RESCUE_KEYWORDS:
            if kw in lower_text:
                matched_kw.append(kw)
        if matched_kw:
            event_type = IngestionEventType.EMERGENCY_RESCUE
            confidence = 0.85
        else:
            for kw in DISRUPTION_KEYWORDS:
                if kw in lower_text:
                    matched_kw.append(kw)
            if matched_kw:
                event_type = IngestionEventType.ROAD_CLOSURE_DISRUPTION
                confidence = 0.80
            else:
                for kw in FLOOD_KEYWORDS:
                    if kw in lower_text:
                        matched_kw.append(kw)
                if matched_kw:
                    event_type = IngestionEventType.REPORTED_FLOODING
                    confidence = 0.80
                else:
                    for kw in WEATHER_KEYWORDS:
                        if kw in lower_text:
                            matched_kw.append(kw)
                    if matched_kw:
                        event_type = IngestionEventType.WEATHER_WARNING
                        confidence = 0.75

        summary_parts = []
        if event_type != IngestionEventType.IRRELEVANT_OR_UNSUPPORTED:
            summary_parts.append(f"Classified as {event_type.value}")
        if reported_place:
            summary_parts.append(f"at {reported_place}")
        if corridor_id:
            summary_parts.append(f"(associated corridor: {corridor_id})")
        summary = " ".join(summary_parts) if summary_parts else "Unclassified generic text"

        return TextAnalysisResult(
            event_type=event_type,
            confidence=confidence,
            reported_place_name=reported_place,
            resolved_corridor_id=corridor_id,
            resolved_road_name=road_name,
            latitude=lat,
            longitude=lon,
            location_accuracy=accuracy,
            matched_keywords=matched_kw,
            is_out_of_scope=False,
            is_ambiguous=is_ambiguous,
            summary=summary,
        )


# Singleton instance
default_text_pipeline = TextAnalysisPipeline()
