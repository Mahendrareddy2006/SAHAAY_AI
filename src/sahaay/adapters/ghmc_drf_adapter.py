"""
Sahaay AI - GHMC DRF (Disaster Response Force) Incident Adapter
Boundary adapter for municipal disaster response force waterlogging dispatch logs.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sahaay.adapters.base import AdapterReading, BaseLiveAdapter, FeedAuthorizationStatus

logger = logging.getLogger(__name__)


class GHMCDRFIncidentAdapter(BaseLiveAdapter):
    """
    Adapter boundary for GHMC Disaster Response Force dispatch and pump deployment logs.
    Status: PENDING_APPROVAL.
    Access to live internal municipal emergency dispatch queues is restricted.
    Safeguard: Operates in disabled/mockable standby mode until formal government clearance.
    """

    def __init__(self, enable_standby_feed: bool = True):
        super().__init__(
            source_id="GHMC-DRF-DISPATCH",
            source_name="GHMC Disaster Response Force Emergency Incident Dispatch Stream",
            auth_status=FeedAuthorizationStatus.PENDING_APPROVAL,
        )
        self.enable_standby_feed = enable_standby_feed
        # In-memory incident buffer for authorized drill scenarios
        self._mock_incidents: Dict[str, List[Dict[str, Any]]] = {}

    def inject_drill_incident(self, corridor_id: str, incident: Dict[str, Any]):
        """Injects verified incident into drill buffer for authorized evaluation scenarios."""
        if corridor_id not in self._mock_incidents:
            self._mock_incidents[corridor_id] = []
        self._mock_incidents[corridor_id].append(incident)

    def fetch_latest(
        self,
        location_id: str,
        query_time: Optional[datetime] = None
    ) -> AdapterReading:
        now_dt = datetime.now(timezone.utc)
        retrieval_iso = now_dt.isoformat().replace("+00:00", "Z")

        # Check for drill incident
        if location_id in self._mock_incidents and self._mock_incidents[location_id]:
            inc = self._mock_incidents[location_id][-1]
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=True,
                observation_timestamp_utc=inc.get("timestamp_utc", retrieval_iso),
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=inc.get("age_seconds", 300.0),
                is_stale=False,
                value=inc,
                units="incident_record",
                quality_flags=["AUTHORIZED_DRILL_FIXTURE", "VERIFIED_DRF_DISPATCH"],
                fallback_applied=False,
            )

        # Default fallback: No active live incident feed authorized
        return AdapterReading(
            source_id=self.source_id,
            source_name=self.source_name,
            authorization_status=self.auth_status,
            is_live_stream=False,
            data_available=False,
            retrieval_timestamp_utc=retrieval_iso,
            units="incident_record",
            quality_flags=["MUNICIPAL_FEED_PENDING_APPROVAL"],
            error_message="GHMC DRF live dispatch feed is awaiting inter-departmental MOU. Zero live logs currently ingested.",
            fallback_applied=True,
            fallback_mode="SAFE_OFFLINE_STANDBY",
        )

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "authorization_status": self.auth_status.value,
            "is_live_connected": False,
            "primary_access_method": "GHMC Disaster Management Cell Enterprise API",
            "access_blocker": "Municipal data sharing agreement under review with GHMC Directorate of Enforcement, Vigilance and Disaster Management (EVDM).",
            "operational_impact": "System does not receive automated municipal crew dispatch records in production without manual responder verification."
        }
