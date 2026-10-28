"""
Sahaay AI - Deterministic Mock IMD Weather Adapter
Provides deterministic, in-memory replay of synthetic or benchmark rainfall observations
for testing and local experimentation. Does NOT perform network I/O or fabricate dry baselines.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sahaay.adapters.base import AdapterReading, BaseLiveAdapter, FeedAuthorizationStatus
from sahaay.hyderabad_risk.schemas import (
    IMDRainfallObservation,
    ObservationQCFlag,
)


class MockIMDRainfallAdapter(BaseLiveAdapter):
    """
    Deterministic mock adapter for rainfall telemetry.
    Replays strictly supplied in-memory fixtures or synthetic observation records.
    Never falls back to fabricated dry weather (0.0 mm).
    """

    def __init__(
        self,
        source_id: str = "MOCK-IMD-WEATHER",
        source_name: str = "Mock IMD Weather Telemetry Provider (Deterministic Synthetic Benchmark)",
        stale_threshold_hours: float = 3.0,
    ):
        super().__init__(
            source_id=source_id,
            source_name=source_name,
            auth_status=FeedAuthorizationStatus.HISTORICAL_PLAYBACK_ONLY,
        )
        self.stale_threshold_seconds = stale_threshold_hours * 3600.0
        self._records_by_location: Dict[str, List[IMDRainfallObservation]] = {}
        self._simulated_outage: bool = False

    def load_observations(self, location_id: str, observations: List[IMDRainfallObservation]) -> None:
        """Loads a sequence of observations for a specific location corridor, sorted chronologically."""
        if location_id not in self._records_by_location:
            self._records_by_location[location_id] = []
        self._records_by_location[location_id].extend(observations)
        # Deduplicate identical station + timestamp records (preserving last ingested)
        deduped: Dict[str, IMDRainfallObservation] = {}
        for obs in self._records_by_location[location_id]:
            key = f"{obs.station_id}_{obs.observation_time_utc.isoformat()}"
            deduped[key] = obs
        self._records_by_location[location_id] = sorted(
            deduped.values(), key=lambda o: o.observation_time_utc
        )

    def set_simulated_outage(self, is_outage: bool) -> None:
        """Simulates provider feed outage or connection failure."""
        self._simulated_outage = is_outage

    def clear(self) -> None:
        """Clears all loaded observations and resets outage state."""
        self._records_by_location.clear()
        self._simulated_outage = False

    def fetch_latest(
        self,
        location_id: str,
        query_time: Optional[datetime] = None,
    ) -> AdapterReading:
        if query_time is None:
            query_time = datetime.now(timezone.utc)
        elif query_time.tzinfo is None:
            query_time = query_time.replace(tzinfo=timezone.utc)

        retrieval_iso = query_time.isoformat().replace("+00:00", "Z")

        # 1. Outage Check: Provider unavailable (NEVER emit 0.0mm dry fallback)
        if self._simulated_outage:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,  # Explicit None: never manufacture dry baseline
                units="mm/hr",
                quality_flags=["PROVIDER_OUTAGE_SIMULATED"],
                fallback_applied=False,
                error_message="Mock provider simulated outage: telemetry feed unavailable.",
            )

        # 2. Missing Data Check: No records for corridor
        records = self._records_by_location.get(location_id, [])
        if not records:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,  # Explicit None: never manufacture dry baseline
                units="mm/hr",
                quality_flags=["NO_TELEMETRY_AVAILABLE"],
                fallback_applied=False,
                error_message=f"No telemetry observations available for corridor '{location_id}'.",
            )

        # Filter observations up to query_time
        eligible = [r for r in records if r.observation_time_utc <= query_time]
        if not eligible:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=None,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=None,
                is_stale=False,
                value=None,
                units="mm/hr",
                quality_flags=["NO_PRIOR_TELEMETRY"],
                fallback_applied=False,
                error_message=f"No observations prior to query time {retrieval_iso}.",
            )

        latest = eligible[-1]
        freshness_sec = max(0.0, (query_time - latest.observation_time_utc).total_seconds())
        is_stale = freshness_sec > self.stale_threshold_seconds
        obs_iso = latest.observation_time_utc.isoformat().replace("+00:00", "Z")

        # 3. Invalid Observation Check (QC failed or is_valid is False)
        if not latest.is_valid or latest.qc_flag != ObservationQCFlag.VALID:
            quality_flags = [latest.qc_flag.value, "INVALID_OBSERVATION"]
            if is_stale:
                quality_flags.append("TELEMETRY_STALE")
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                observation_timestamp_utc=obs_iso,
                retrieval_timestamp_utc=retrieval_iso,
                freshness_seconds=round(freshness_sec, 1),
                is_stale=is_stale,
                value=None,  # Never treat invalid telemetry as 0.0mm
                units="mm/hr",
                quality_flags=quality_flags,
                fallback_applied=False,
                error_message=f"Observation failed QC check: {latest.qc_flag.value}",
            )

        # 4. Valid Observation (clearly distinguishing valid zero from missing/stale)
        val_mm = latest.interval_rainfall_mm
        quality_flags = ["VALID_OBSERVATION"]
        if is_stale:
            quality_flags.append("TELEMETRY_STALE")
        if val_mm == 0.0:
            quality_flags.append("VALID_MEASURED_ZERO")

        return AdapterReading(
            source_id=self.source_id,
            source_name=self.source_name,
            authorization_status=self.auth_status,
            is_live_stream=False,
            data_available=True,
            observation_timestamp_utc=obs_iso,
            retrieval_timestamp_utc=retrieval_iso,
            freshness_seconds=round(freshness_sec, 1),
            is_stale=is_stale,
            value={
                "rainfall_1h_mm": val_mm,
                "station_id": latest.station_id,
                "station_name": latest.station_name,
                "provider": latest.provider,
                "station_type": latest.station_type.value,
                "latitude": latest.latitude,
                "longitude": latest.longitude,
                "interval_minutes": latest.interval_minutes,
                "qc_flag": latest.qc_flag.value,
            },
            units="mm/hr",
            quality_flags=quality_flags,
            fallback_applied=False,
        )

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "authorization_status": self.auth_status.value,
            "is_live_connected": False,
            "primary_access_method": "In-Memory Deterministic Synthetic Fixture Replay",
            "access_blocker": "None (Testing Adapter). Real IMD live access remains blocked pending authorized credentials.",
            "data_handling_safeguards": [
                "Zero network access or scraping.",
                "Zero fabricated dry baselines during outages or missing data.",
                "Explicit distinction between valid zero rainfall, stale data, and missing data.",
                "Full provenance tracking preserved."
            ],
            "fallback_strategy": "Explicit UNKNOWN / data_available=False; dry weather is never imputed."
        }
