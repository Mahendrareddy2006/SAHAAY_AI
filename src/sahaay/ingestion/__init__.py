"""
Sahaay AI - Automated Source Ingestion Subsystem
Orchestrates online source monitoring (weather, civic news, community posts),
text and vision analysis, event normalization, deduplication, and risk alerts.
"""

from sahaay.ingestion.schemas import (
    ConnectorHealthStatus,
    EventProcessingStatus,
    EventVerificationStatus,
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
    LocationResolutionAccuracy,
)
from sahaay.ingestion.text_pipeline import (
    TextAnalysisPipeline,
    TextAnalysisResult,
    default_text_pipeline,
)
from sahaay.ingestion.image_pipeline import (
    AutomatedImageAnalysisResult,
    AutomatedImagePipeline,
    default_image_pipeline,
)
from sahaay.ingestion.event_store import (
    IngestedEventStore,
    default_event_store,
)
from sahaay.ingestion.orchestrator import (
    IngestionOrchestrator,
    default_orchestrator,
)

__all__ = [
    "ConnectorHealthStatus",
    "EventProcessingStatus",
    "EventVerificationStatus",
    "IngestedEvent",
    "IngestionEventType",
    "IngestionSourceType",
    "LocationResolutionAccuracy",
    "TextAnalysisPipeline",
    "TextAnalysisResult",
    "default_text_pipeline",
    "AutomatedImageAnalysisResult",
    "AutomatedImagePipeline",
    "default_image_pipeline",
    "IngestedEventStore",
    "default_event_store",
    "IngestionOrchestrator",
    "default_orchestrator",
]
