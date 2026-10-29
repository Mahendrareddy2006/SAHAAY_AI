"""
Sahaay AI - Automated Ingestion Schemas & Canonical Event Contract
Implements normalized contracts for multi-source weather, news, and community events.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IngestionSourceType(str, Enum):
    OFFICIAL_WEATHER = "OFFICIAL_WEATHER"
    NEWS_FEED = "NEWS_FEED"
    COMMUNITY_CHANNEL = "COMMUNITY_CHANNEL"
    MUNICIPAL_DISPATCH = "MUNICIPAL_DISPATCH"
    MOCK_FIXTURE = "MOCK_FIXTURE"


class IngestionEventType(str, Enum):
    WEATHER_WARNING = "WEATHER_WARNING"
    TELEMETRY_OBSERVATION = "TELEMETRY_OBSERVATION"
    REPORTED_FLOODING = "REPORTED_FLOODING"
    ROAD_CLOSURE_DISRUPTION = "ROAD_CLOSURE_DISRUPTION"
    EMERGENCY_RESCUE = "EMERGENCY_RESCUE"
    COMMUNITY_IMAGE = "COMMUNITY_IMAGE"
    IRRELEVANT_OR_UNSUPPORTED = "IRRELEVANT_OR_UNSUPPORTED"


class LocationResolutionAccuracy(str, Enum):
    EXACT_GPS = "EXACT_GPS"
    NAMED_LOCALITY = "NAMED_LOCALITY"
    CORRIDOR_MATCH = "CORRIDOR_MATCH"
    AMBIGUOUS_CITYWIDE = "AMBIGUOUS_CITYWIDE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNRESOLVED = "UNRESOLVED"


class EventProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    INCONCLUSIVE = "INCONCLUSIVE"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class EventVerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    CORROBORATED = "CORROBORATED"
    VERIFIED_RESPONDER = "VERIFIED_RESPONDER"
    REJECTED = "REJECTED"


class IngestedEvent(BaseModel):
    """
    Canonical normalized event schema shared across all ingest connectors and analysis engines.
    Ensures strict provenance, location distinction, and expiry semantics.
    """
    event_id: str = Field(..., description="Unique deterministic or random event ID")
    event_type: IngestionEventType
    source_type: IngestionSourceType
    source_name: str = Field(..., description="Identifies source provider (e.g. IMD-HYD, TELANGANA-TODAY, CIVIC-TELEGRAM)")
    source_item_id: str = Field(..., description="Original item/article ID in source system")
    source_url: Optional[str] = None
    
    # Timestamps (ISO 8601 UTC)
    observed_at: str
    published_at: str
    retrieved_at: str
    expires_at: str

    # Geospatial Location Resolution
    latitude: Optional[float] = Field(None, ge=17.0, le=17.8)
    longitude: Optional[float] = Field(None, ge=78.1, le=78.8)
    location_name: Optional[str] = Field(None, description="Reported place name from text/post")
    location_accuracy: LocationResolutionAccuracy = LocationResolutionAccuracy.UNRESOLVED
    resolved_corridor_id: Optional[str] = Field(None, description="Matched road segment ID (distinct from reported place)")

    # Payloads & Evidence References
    raw_text: Optional[str] = None
    raw_evidence_reference: Optional[str] = None
    image_reference: Optional[str] = None

    # Processing & Assessment State
    processing_status: EventProcessingStatus = EventProcessingStatus.PENDING
    verification_status: EventVerificationStatus = EventVerificationStatus.UNVERIFIED
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    
    # Traceability & Provenance
    provenance: Dict[str, Any] = Field(default_factory=dict)
    is_synthetic_fixture: bool = Field(True, description="Strictly distinguishes demonstration fixtures from live feeds")


class ConnectorHealthStatus(BaseModel):
    """
    Health and reliability metrics for an external or fixture connector.
    """
    connector_id: str
    source_name: str
    source_type: IngestionSourceType
    is_live: bool = False
    is_operational: bool = True
    connectivity_mode: str = "FIXTURE"  # LIVE | DEGRADED | NOT_CONFIGURED | FIXTURE
    polling_interval_seconds: int = 300
    last_successful_fetch_utc: Optional[str] = None
    last_attempted_fetch_utc: Optional[str] = None
    next_scheduled_fetch_utc: Optional[str] = None
    last_error_message: Optional[str] = None
    total_events_ingested: int = 0
    total_events_processed: int = 0
    consecutive_failures: int = 0
    provenance_metadata: Dict[str, Any] = Field(default_factory=dict)
