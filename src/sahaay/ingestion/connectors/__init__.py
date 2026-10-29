"""
Sahaay AI - Automated Source Connectors
Adapters for weather telemetry, news RSS/API feeds, and community social/chat channels.
"""

from sahaay.ingestion.connectors.base import BaseSourceConnector
from sahaay.ingestion.connectors.weather import WeatherIngestionConnector
from sahaay.ingestion.connectors.news import NewsIngestionConnector
from sahaay.ingestion.connectors.community import CommunityIngestionConnector

__all__ = [
    "BaseSourceConnector",
    "WeatherIngestionConnector",
    "NewsIngestionConnector",
    "CommunityIngestionConnector",
]
