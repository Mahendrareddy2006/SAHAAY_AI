"""
Sahaay AI - Phase 19: Risk-Aware Routing Module
Exports routing contracts, evidence schemas, readiness auditing, and assessment service.
"""

from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestinationType,
    FacilityOperationalStatus,
    EmergencyDestination,
    RouteRequest,
    RouteSegmentRisk,
    RouteResponse,
    MANDATORY_SAFETY_DISCLAIMER,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    SegmentRoutingAssessment,
    RiskAwareRouteAssessment,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_ROUTING_DISCLAIMER,
)
from sahaay.routing.readiness import (
    audit_road_network_readiness,
    RoadNetworkAuditRecord,
    RoutingReadinessReport,
)
from sahaay.routing.service import (
    RiskAwareRoutingService,
)
from sahaay.routing.graph_router import (
    TopologicalGraphRouter,
)

__all__ = [
    # Contracts
    "VehicleType",
    "EmergencyDestinationType",
    "FacilityOperationalStatus",
    "EmergencyDestination",
    "RouteRequest",
    "RouteSegmentRisk",
    "RouteResponse",
    "MANDATORY_SAFETY_DISCLAIMER",
    # Schemas
    "PassabilityAssessment",
    "RouteAssessmentOutcome",
    "SegmentRoutingAssessment",
    "RiskAwareRouteAssessment",
    "FORBIDDEN_SAFETY_PHRASES",
    "MANDATORY_ROUTING_DISCLAIMER",
    # Readiness
    "audit_road_network_readiness",
    "RoadNetworkAuditRecord",
    "RoutingReadinessReport",
    # Service & Graph Router
    "RiskAwareRoutingService",
    "TopologicalGraphRouter",
]
