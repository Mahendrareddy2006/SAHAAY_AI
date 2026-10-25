"""
Sahaay AI - Live Data Adapters Package
"""

from sahaay.adapters.base import AdapterReading, BaseLiveAdapter, FeedAuthorizationStatus
from sahaay.adapters.cctv_adapter import MunicipalCCTVAdapter
from sahaay.adapters.ghmc_drf_adapter import GHMCDRFIncidentAdapter
from sahaay.adapters.nwic_adapter import NWICRainfallAdapter
from sahaay.adapters.registry import LiveDataAdapterRegistry, default_adapter_registry
from sahaay.adapters.tsdps_adapter import TSDPSWeatherAdapter

__all__ = [
    "AdapterReading",
    "BaseLiveAdapter",
    "FeedAuthorizationStatus",
    "TSDPSWeatherAdapter",
    "NWICRainfallAdapter",
    "GHMCDRFIncidentAdapter",
    "MunicipalCCTVAdapter",
    "LiveDataAdapterRegistry",
    "default_adapter_registry",
]
