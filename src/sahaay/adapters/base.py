"""
Sahaay AI - Live Data Adapter Base Contracts
Abstract interfaces for live telemetry, municipal incident logs, and CCTV camera adapters.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FeedAuthorizationStatus(str, Enum):
    AUTHORIZED_LIVE = "AUTHORIZED_LIVE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    HISTORICAL_PLAYBACK_ONLY = "HISTORICAL_PLAYBACK_ONLY"
    QUARANTINED_DISABLED = "QUARANTINED_DISABLED"


class AdapterReading(BaseModel):
    """
    Standardized reading returned by an adapter boundary.
    """
    source_id: str
    source_name: str
    authorization_status: FeedAuthorizationStatus
    is_live_stream: bool = False
    data_available: bool = True
    
    # Provenance & Temporal
    observation_timestamp_utc: Optional[str] = None
    retrieval_timestamp_utc: str
    freshness_seconds: Optional[float] = None
    is_stale: bool = False
    
    # Values & Units
    value: Optional[Any] = None
    units: str
    quality_flags: List[str] = Field(default_factory=list)
    
    # Resilience & Fallback
    fallback_applied: bool = False
    fallback_mode: Optional[str] = None
    error_message: Optional[str] = None


class BaseLiveAdapter(ABC):
    """
    Abstract base class enforcing adapter boundary contracts.
    """

    def __init__(self, source_id: str, source_name: str, auth_status: FeedAuthorizationStatus):
        self.source_id = source_id
        self.source_name = source_name
        self.auth_status = auth_status

    @abstractmethod
    def fetch_latest(
        self,
        location_id: str,
        query_time: Optional[datetime] = None
    ) -> AdapterReading:
        """
        Fetches the latest reading or cleanly triggers fallback behavior.
        """
        pass

    @abstractmethod
    def get_source_status(self) -> Dict[str, Any]:
        """
        Reports operational health, authentication state, and known limitations.
        """
        pass
