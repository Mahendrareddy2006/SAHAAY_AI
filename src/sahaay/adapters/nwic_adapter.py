"""
Sahaay AI - NWIC (National Water Informatics Centre) Telemetry Adapter
Boundary adapter for National Water Data Portal / Telangana Surface Water telemetry.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from sahaay.adapters.base import AdapterReading, BaseLiveAdapter, FeedAuthorizationStatus
from sahaay.hyderabad_risk.features import compute_rolling_rainfall, find_nearest_telemetry_station
from sahaay.hyderabad_risk.ingest import load_telemetry_rainfall
from sahaay.hyderabad_risk.validate import validate_telemetry_rainfall

logger = logging.getLogger(__name__)


class NWICRainfallAdapter(BaseLiveAdapter):
    """
    Adapter boundary for National Water Data Portal / Telangana Surface Water telemetry.
    Status: HISTORICAL_PLAYBACK_ONLY.
    Ingests verified open telemetry dataset with QC filtering for negative faults and accumulators.
    """

    def __init__(self, raw_csv_path: Optional[Path] = None):
        super().__init__(
            source_id="NWIC-TELEMETRY-GAUGE",
            source_name="National Water Data Portal / Telangana Surface Water Telemetry",
            auth_status=FeedAuthorizationStatus.HISTORICAL_PLAYBACK_ONLY,
        )
        self.raw_csv_path = raw_csv_path or Path("data/hyderabad_risk/raw/telangana_hourly_telemetry_rainfall_2021_2025.csv")
        self._clean_df: Optional[pd.DataFrame] = None
        self._stations_df: Optional[pd.DataFrame] = None
        self._load_data()

    def _load_data(self):
        if self.raw_csv_path.exists():
            try:
                raw_df = load_telemetry_rainfall(self.raw_csv_path)
                self._clean_df, _ = validate_telemetry_rainfall(raw_df)
                self._stations_df = self._clean_df[["Station", "District", "Latitude", "Longitude"]].drop_duplicates()
                logger.info(f"NWIC adapter initialized with {len(self._clean_df)} QC-filtered records.")
            except Exception as e:
                logger.error(f"Failed to load NWIC telemetry: {e}")
                self._clean_df = None

    def fetch_latest(
        self,
        location_id: str,
        query_time: Optional[datetime] = None,
        lat: float = 17.40,
        lon: float = 78.45,
    ) -> AdapterReading:
        now_dt = datetime.now(timezone.utc)
        retrieval_iso = now_dt.isoformat().replace("+00:00", "Z")

        if self._clean_df is None or self._stations_df is None:
            return AdapterReading(
                source_id=self.source_id,
                source_name=self.source_name,
                authorization_status=self.auth_status,
                is_live_stream=False,
                data_available=False,
                retrieval_timestamp_utc=retrieval_iso,
                units="mm",
                quality_flags=["TELEMETRY_DATA_UNAVAILABLE"],
                error_message="NWIC telemetry database offline or uninitialized.",
            )

        target_dt = query_time if query_time is not None else datetime(2023, 12, 1, 19, 0)
        station_id, station_dist_km = find_nearest_telemetry_station(lat, lon, self._stations_df)
        rolling = compute_rolling_rainfall(station_id, target_dt, self._clean_df)

        obs_iso = target_dt.isoformat() + "Z"
        fresh_h = rolling.get("freshness_hours") or 0.0
        is_stale = fresh_h > 3.0

        flags = ["QC_FILTERED_GAUGE"]
        if station_dist_km > 15.0:
            flags.append(f"REGIONAL_ATTRIBUTION_{round(station_dist_km)}KM")
        if is_stale:
            flags.append(f"STALE_TELEMETRY_{round(fresh_h, 1)}H")

        return AdapterReading(
            source_id=self.source_id,
            source_name=self.source_name,
            authorization_status=self.auth_status,
            is_live_stream=False,
            data_available=True,
            observation_timestamp_utc=obs_iso,
            retrieval_timestamp_utc=retrieval_iso,
            freshness_seconds=fresh_h * 3600.0,
            is_stale=is_stale,
            value={
                "station_id": station_id,
                "station_dist_km": station_dist_km,
                "rain_1h_mm": rolling.get("rain_1h_mm"),
                "rain_3h_mm": rolling.get("rain_3h_mm"),
                "rain_6h_mm": rolling.get("rain_6h_mm"),
                "rain_24h_mm": rolling.get("rain_24h_mm"),
            },
            units="mm",
            quality_flags=flags,
            fallback_applied=False,
        )

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "authorization_status": self.auth_status.value,
            "is_live_connected": False,
            "operational_mode": "Automated Historical Playback & QC Filtered Telemetry",
            "coverage": "38 stations across Telangana (2021-2025)",
            "known_limitations": [
                "Nearest station to Hyderabad is 50.6 km (Kondapochamma Reservoir).",
                "Regional basin precipitation only; does not provide street-level resolution.",
                "Cumulative bucket accumulator spikes (>250mm) filtered automatically."
            ],
        }
