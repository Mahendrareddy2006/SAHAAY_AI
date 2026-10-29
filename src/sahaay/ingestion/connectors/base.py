"""
Sahaay AI - Base Ingestion Connector Interface
Enforces reliability tracking, timeouts, error bounding, and provenance semantics.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional

from sahaay.ingestion.schemas import (
    ConnectorHealthStatus,
    IngestedEvent,
    IngestionSourceType,
)

logger = logging.getLogger(__name__)


class BaseSourceConnector(ABC):
    """
    Abstract interface for automated source connectors.
    Tracks health, last error, polling intervals, and handles degraded connectivity.
    """

    def __init__(
        self,
        connector_id: str,
        source_name: str,
        source_type: IngestionSourceType,
        is_live: bool = False,
        polling_interval_seconds: int = 300,
    ):
        self.connector_id = connector_id
        self.source_name = source_name
        self.source_type = source_type
        self.is_live = is_live
        self.is_configured = True
        self.polling_interval_seconds = polling_interval_seconds
        
        self.is_operational = True
        self.last_successful_fetch_utc: Optional[str] = None
        self.last_attempted_fetch_utc: Optional[str] = None
        self.next_scheduled_fetch_utc: Optional[str] = None
        self.last_error_message: Optional[str] = None
        self.total_events_ingested: int = 0
        self.total_events_processed: int = 0
        self.consecutive_failures: int = 0
        self.provenance_metadata: Dict[str, Any] = {}

    @property
    def connectivity_mode(self) -> str:
        if not getattr(self, "is_configured", True):
            return "NOT_CONFIGURED"
        if not self.is_operational:
            return "DEGRADED"
        if self.is_live:
            return "LIVE"
        return "FIXTURE"

    @abstractmethod
    def fetch_events(self) -> List[IngestedEvent]:
        """
        Polls the source gateway or returns synthetic demonstration fixtures.
        Must handle errors gracefully and update internal health metrics.
        """
        pass

    def record_attempt(self) -> None:
        """Records an attempted fetch cycle and calculates next scheduled poll."""
        now = datetime.now(timezone.utc)
        self.last_attempted_fetch_utc = now.isoformat().replace("+00:00", "Z")
        self.next_scheduled_fetch_utc = (now + timedelta(seconds=self.polling_interval_seconds)).isoformat().replace("+00:00", "Z")

    def get_health(self) -> ConnectorHealthStatus:
        """Returns the current operational health of the connector."""
        return ConnectorHealthStatus(
            connector_id=self.connector_id,
            source_name=self.source_name,
            source_type=self.source_type,
            is_live=self.is_live,
            is_operational=self.is_operational,
            connectivity_mode=self.connectivity_mode,
            polling_interval_seconds=self.polling_interval_seconds,
            last_successful_fetch_utc=self.last_successful_fetch_utc,
            last_attempted_fetch_utc=self.last_attempted_fetch_utc,
            next_scheduled_fetch_utc=self.next_scheduled_fetch_utc,
            last_error_message=self.last_error_message,
            total_events_ingested=self.total_events_ingested,
            total_events_processed=self.total_events_processed,
            consecutive_failures=self.consecutive_failures,
            provenance_metadata=self.provenance_metadata,
        )

    def record_success(self, count: int) -> None:
        """Marks successful fetch cycle."""
        self.is_operational = True
        self.consecutive_failures = 0
        self.last_error_message = None
        self.last_successful_fetch_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.total_events_ingested += count
        self.total_events_processed += count

    def record_failure(self, error_message: str) -> None:
        """Records error and tracks failure count."""
        self.consecutive_failures += 1
        self.last_error_message = error_message
        if self.consecutive_failures >= 3:
            self.is_operational = False
        logger.warning(f"Connector {self.connector_id} failed: {error_message}")
