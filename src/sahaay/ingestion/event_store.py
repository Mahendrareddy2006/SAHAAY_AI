"""
Sahaay AI - Ingested Event Repository & Expiry Store
Provides thread-safe persistence, deduplication, and TTL expiration for all normalized events.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Dict, List, Optional, Set

from sahaay.ingestion.schemas import (
    EventProcessingStatus,
    IngestedEvent,
    IngestionEventType,
)

logger = logging.getLogger(__name__)


class IngestedEventStore:
    """
    In-memory, thread-safe store for normalized flood intelligence events.
    Enforces deduplication by (source_name, source_item_id) and automatically prunes expired items.
    """

    def __init__(self, max_capacity: int = 500):
        self._lock = threading.Lock()
        self._max_capacity = max_capacity
        self._events: Dict[str, IngestedEvent] = {}
        self._dedup_keys: Set[str] = set()

    def add_event(self, event: IngestedEvent) -> bool:
        """
        Inserts event if not already present.
        Returns True if newly added, False if duplicate.
        """
        dedup_key = f"{event.source_name}::{event.source_item_id}"
        with self._lock:
            if dedup_key in self._dedup_keys or event.event_id in self._events:
                logger.debug(f"Rejected duplicate event: {dedup_key}")
                return False

            self._events[event.event_id] = event
            self._dedup_keys.add(dedup_key)

            # Enforce capacity
            if len(self._events) > self._max_capacity:
                # Remove oldest event
                oldest_id = next(iter(self._events))
                old_evt = self._events.pop(oldest_id)
                self._dedup_keys.discard(f"{old_evt.source_name}::{old_evt.source_item_id}")

            return True

    def get_event(self, event_id: str) -> Optional[IngestedEvent]:
        """Retrieves a single event by ID."""
        with self._lock:
            return self._events.get(event_id)

    def get_events(
        self,
        corridor_id: Optional[str] = None,
        event_type: Optional[IngestionEventType] = None,
        include_expired: bool = False,
        limit: int = 50,
    ) -> List[IngestedEvent]:
        """
        Retrieves matching events sorted by published_at descending.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            results = list(self._events.values())

            if not include_expired:
                results = [e for e in results if e.expires_at >= now_iso]

            if corridor_id:
                results = [e for e in results if e.resolved_corridor_id == corridor_id]

            if event_type:
                results = [e for e in results if e.event_type == event_type]

            # Sort descending by published_at
            results.sort(key=lambda x: x.published_at, reverse=True)
            return results[:limit]

    def clear(self) -> None:
        """Clears all events (used for test isolation)."""
        with self._lock:
            self._events.clear()
            self._dedup_keys.clear()


# Global singleton store
default_event_store = IngestedEventStore()
