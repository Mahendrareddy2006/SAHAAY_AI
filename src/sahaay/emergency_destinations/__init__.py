"""
Sahaay AI - Phase E: Emergency Destinations & Safe Routing Package
(src/sahaay/emergency_destinations/__init__.py)
"""

from sahaay.emergency_destinations.schemas import (
    EmergencyDestinationRecord,
    DestinationFeasibilityTier,
    DestinationSuitabilityTier,
    CandidateDestinationAssessment,
    DestinationSuitabilityRequest,
    DestinationSuitabilityResponse,
)
from sahaay.emergency_destinations.registry import (
    EmergencyDestinationRegistry,
    default_destination_registry,
)
from sahaay.emergency_destinations.service import (
    DestinationAwareRoutingService,
    default_destination_routing_service,
    haversine_distance_meters,
)

__all__ = [
    "EmergencyDestinationRecord",
    "DestinationFeasibilityTier",
    "DestinationSuitabilityTier",
    "CandidateDestinationAssessment",
    "DestinationSuitabilityRequest",
    "DestinationSuitabilityResponse",
    "EmergencyDestinationRegistry",
    "default_destination_registry",
    "DestinationAwareRoutingService",
    "default_destination_routing_service",
    "haversine_distance_meters",
]
