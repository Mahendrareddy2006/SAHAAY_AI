"""
Sahaay AI - Phase E: Destination-Aware Safe Routing Service
(src/sahaay/emergency_destinations/service.py)

Implements transparent destination evaluation, feasibility ranking, and emergency
workflow integration over the topological road graph.
Enforces:
1. Separation of straight-line proximity from graph route feasibility and facility operational status.
2. Non-recommendation of facilities with unknown essential status as operationally suitable.
3. Explicit unsupported results for disconnected components or unmapped nodes (no synthetic edges).
4. Connection to human-reviewed emergency workflows without autonomous external actions.
"""

from datetime import datetime, timezone
import math
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from sahaay.emergency_destinations.registry import (
    EmergencyDestinationRegistry,
    default_destination_registry,
)
from sahaay.emergency_destinations.schemas import (
    CandidateDestinationAssessment,
    DestinationFeasibilityTier,
    DestinationSuitabilityRequest,
    DestinationSuitabilityResponse,
    DestinationSuitabilityTier,
    EmergencyDestinationRecord,
    EmergencyDestinationType,
    FacilityOperationalStatus,
)
from sahaay.emergency.schemas import (
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
    EmergencyPriority,
    EmergencyState,
)
from sahaay.emergency.workflow import EmergencyWorkflowEngine
from sahaay.road_network.graph import RoadGraph
from sahaay.road_network.store import RoadNetworkStore, default_road_network_store
from sahaay.road_status.schemas import RoadConditionState, RoadStatusSnapshot
from sahaay.routing.contracts import VehicleType
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import (
    RouteAssessmentOutcome,
    RiskAwareRouteAssessment,
)

logger = logging.getLogger(__name__)


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates geodesic distance between two coordinate pairs in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class DestinationAwareRoutingService:
    """
    Evaluates, ranks, and navigates to emergency destinations.
    Fuses topological road graph feasibility with destination operational status evidence.
    """

    def __init__(
        self,
        registry: Optional[EmergencyDestinationRegistry] = None,
        road_store: Optional[RoadNetworkStore] = None,
        router: Optional[TopologicalGraphRouter] = None,
        emergency_engine: Optional[EmergencyWorkflowEngine] = None,
    ):
        self.registry = registry or default_destination_registry
        self.road_store = road_store or default_road_network_store
        self.graph = self.road_store.get_road_graph()
        self.router = router or TopologicalGraphRouter(graph=self.graph)
        self.emergency_engine = emergency_engine or EmergencyWorkflowEngine()

    def assess_destinations(
        self,
        request: DestinationSuitabilityRequest,
        segment_status_provider: Optional[Callable[[str], Optional[RoadStatusSnapshot]]] = None,
    ) -> DestinationSuitabilityResponse:
        """
        Assesses and ranks candidate emergency destinations from the specified origin.
        Separates geographic proximity from topological route feasibility.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 1. Determine origin node ID and coordinates
        origin_node_id = request.origin_node_id
        origin_lat = request.origin_latitude
        origin_lon = request.origin_longitude

        if origin_node_id:
            origin_node = self.graph.get_node(origin_node_id)
            if origin_node:
                origin_lat = origin_node.latitude
                origin_lon = origin_node.longitude
        elif origin_lat is not None and origin_lon is not None:
            # Match to nearest graph node
            origin_node_id = self._find_nearest_graph_node(origin_lat, origin_lon)
            if origin_node_id:
                origin_node = self.graph.get_node(origin_node_id)
                if origin_node:
                    origin_lat = origin_node.latitude
                    origin_lon = origin_node.longitude
            else:
                origin_node = None
        else:
            origin_node = None

        origin_coords = {"latitude": origin_lat, "longitude": origin_lon} if (origin_lat and origin_lon) else None

        # 2. Filter candidates by destination_type
        all_destinations = self.registry.filter_destinations(
            destination_type=request.destination_type,
        )

        candidate_evaluations: List[CandidateDestinationAssessment] = []
        connected_count = 0
        suitable_count = 0

        for facility in all_destinations:
            eval_result = self._evaluate_single_candidate(
                origin_node_id=origin_node_id,
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                facility=facility,
                vehicle_type=request.vehicle_type,
                require_verified_operational=request.require_verified_operational,
                segment_status_provider=segment_status_provider,
            )
            if eval_result.is_topologically_connected:
                connected_count += 1
            if eval_result.is_operationally_suitable:
                suitable_count += 1

            candidate_evaluations.append(eval_result)

        # 3. Sort candidates by ranking score descending
        candidate_evaluations.sort(key=lambda c: c.ranking_score, reverse=True)

        # Trim to max_candidates
        top_candidates = candidate_evaluations[: request.max_candidates]

        return DestinationSuitabilityResponse(
            assessment_timestamp_utc=now_iso,
            origin_node_id=origin_node_id,
            origin_coordinates=origin_coords,
            vehicle_type=request.vehicle_type,
            candidates_ranked=top_candidates,
            total_registered_facilities=len(all_destinations),
            connected_facilities_count=connected_count,
            suitable_facilities_count=suitable_count,
        )

    def _evaluate_single_candidate(
        self,
        origin_node_id: Optional[str],
        origin_lat: Optional[float],
        origin_lon: Optional[float],
        facility: EmergencyDestinationRecord,
        vehicle_type: VehicleType,
        require_verified_operational: bool,
        segment_status_provider: Optional[Callable[[str], Optional[RoadStatusSnapshot]]] = None,
    ) -> CandidateDestinationAssessment:
        """Evaluates a single destination facility with respect to the origin."""
        warnings: List[str] = []
        unknown_fields = list(facility.unknown_fields)

        # Straight-line distance calculation
        if origin_lat is not None and origin_lon is not None:
            straight_line_dist = round(
                haversine_distance_meters(origin_lat, origin_lon, facility.latitude, facility.longitude),
                1,
            )
        else:
            straight_line_dist = 0.0

        dest_node_id = facility.nearest_graph_node_id
        route_assessment: Optional[RiskAwareRouteAssessment] = None
        route_dist: Optional[float] = None
        route_dur: Optional[float] = None

        # ----------------------------------------------------------------------
        # Feasibility Analysis
        # ----------------------------------------------------------------------
        if not origin_node_id or not self.graph.get_node(origin_node_id):
            feasibility = DestinationFeasibilityTier.UNSUPPORTED_LOCATION
            rejection_reason = (
                f"Origin node '{origin_node_id}' is not in the directed road graph. "
                "Routing outside monitored network topology is unsupported."
            )
            warnings.append("Origin outside road graph coverage; route calculation impossible.")

        elif not dest_node_id or not self.graph.get_node(dest_node_id):
            feasibility = DestinationFeasibilityTier.UNSUPPORTED_LOCATION
            rejection_reason = (
                f"Facility '{facility.name}' has no registered road graph node ({dest_node_id}). "
                "Cannot compute topological connection."
            )
            warnings.append(f"Destination facility {facility.facility_id} is unmapped in road graph.")

        else:
            # Both nodes exist; check connected components
            components = self.graph.find_connected_components()
            origin_comp = next((c for c in components if origin_node_id in c), set())
            dest_comp = next((c for c in components if dest_node_id in c), set())

            if origin_comp != dest_comp or not origin_comp:
                feasibility = DestinationFeasibilityTier.DISCONNECTED_TOPOLOGY
                rejection_reason = (
                    f"Origin '{origin_node_id}' and destination node '{dest_node_id}' belong to "
                    "disconnected topological components. No continuous road network path exists."
                )
                warnings.append(
                    f"Facility is {straight_line_dist/1000.0:.2f}km away straight-line, but DISCONNECTED "
                    "in topological network. Proximity does not imply road reachability."
                )
            else:
                # Compute route using TopologicalGraphRouter
                route_assessment = self.router.find_risk_aware_route(
                    origin_node_id=origin_node_id,
                    destination_node_id=dest_node_id,
                    vehicle_type=vehicle_type,
                    segment_status_provider=segment_status_provider,
                    target_facility=facility,
                    is_demonstration=True,
                )

                if route_assessment.outcome == RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE:
                    feasibility = DestinationFeasibilityTier.BLOCKED_IMPASSABLE_ACCESS
                    rejection_reason = (
                        "All topological road paths to facility are blocked by verified flood inundation. "
                        f"Pruned impassable segments: {len(route_assessment.excluded_segments)}."
                    )
                    warnings.append("Access corridors verified impassable; route cannot be traversed.")
                elif route_assessment.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED:
                    feasibility = DestinationFeasibilityTier.DISCONNECTED_TOPOLOGY
                    rejection_reason = "Topological pathfinding failed; graph path unsupported."
                    warnings.append("Path unsupported in current graph topology.")
                else:
                    feasibility = DestinationFeasibilityTier.CONNECTED_AND_TRAVERSABLE
                    route_dist = route_assessment.total_distance_meters
                    route_dur = route_assessment.estimated_duration_seconds
                    rejection_reason = "Traversable topological path verified."

        is_connected = (feasibility == DestinationFeasibilityTier.CONNECTED_AND_TRAVERSABLE)
        is_passable = is_connected

        # ----------------------------------------------------------------------
        # Suitability Analysis
        # ----------------------------------------------------------------------
        op_status = facility.operational_status

        if not is_connected:
            suitability = DestinationSuitabilityTier.UNSUITABLE_UNREACHABLE
            is_suitable = False
            base_score = 0.0
            rationale = f"Unreachable: {rejection_reason}"
            explanation = (
                f"REJECTED: Facility '{facility.name}' is physically located {straight_line_dist/1000.0:.2f}km away, "
                f"but cannot be reached topologically ({feasibility.value}). Straight-line proximity does not guarantee road access."
            )

        elif op_status == FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED:
            suitability = DestinationSuitabilityTier.RESTRICTED_ACCESS_INUNDATED
            is_suitable = False
            base_score = 0.05
            rationale = "Facility grounds or vehicular access bay is actively inundated."
            explanation = (
                f"REJECTED: Facility '{facility.name}' access bay is INUNDATED_ACCESS_RESTRICTED. "
                "Even though road connection exists, facility cannot safely admit incoming vehicles."
            )
            warnings.append("Facility access bay inundated; redirection to alternative facility required.")

        elif op_status == FacilityOperationalStatus.UNVERIFIED:
            suitability = DestinationSuitabilityTier.DEGRADED_UNVERIFIED_STATUS
            is_suitable = (not require_verified_operational)
            base_score = 0.40
            rationale = "Road path traversable, but facility operational status is UNVERIFIED."
            explanation = (
                f"DEGRADED ADVISORY: Facility '{facility.name}' is topologically reachable "
                f"({route_dist/1000.0:.2f}km route), but current operating status is UNVERIFIED. "
                "Do NOT assume facility is operational without verbal/responder confirmation."
            )
            warnings.append("Facility operating status unverified; admission is NOT guaranteed.")

        elif op_status == FacilityOperationalStatus.OPERATIONAL_CAPACITY_CONSTRAINED:
            suitability = DestinationSuitabilityTier.CONSTRAINED_CAPACITY
            is_suitable = True
            base_score = 0.70
            rationale = "Traversable route and verified operational, but capacity constrained."
            explanation = (
                f"RECOMMENDED WITH CAUTION: Facility '{facility.name}' is open and reachable "
                f"({route_dist/1000.0:.2f}km route), but reports constrained bed/intake capacity."
            )

        elif op_status == FacilityOperationalStatus.OPERATIONAL_VERIFIED:
            suitability = DestinationSuitabilityTier.SUITABLE_VERIFIED_OPERATIONAL
            is_suitable = True
            base_score = 0.95
            rationale = "Traversable route and verified operational facility."
            explanation = (
                f"RECOMMENDED: Facility '{facility.name}' is verified operational and topologically reachable "
                f"({route_dist/1000.0:.2f}km route distance vs {straight_line_dist/1000.0:.2f}km straight-line)."
            )
        else:
            suitability = DestinationSuitabilityTier.UNSUITABLE_UNREACHABLE
            is_suitable = False
            base_score = 0.0
            rationale = "Unknown or unsupported operational status."
            explanation = f"REJECTED: Facility status {op_status} unsupported."

        # Compute transparent composite score
        # Base score modulated by route distance efficiency: shorter route gives slight edge within tier
        if is_connected and route_dist is not None and route_dist > 0.0:
            distance_factor = 1.0 / (1.0 + (route_dist / 8000.0))  # Scales from ~1.0 down to ~0.5 for long routes
            ranking_score = round(max(0.0, min(1.0, base_score * (0.8 + 0.2 * distance_factor))), 3)
        else:
            ranking_score = base_score

        # If synthetic fixture, append explicit disclosure
        if facility.is_synthetic_fixture:
            warnings.append(facility.fixture_warning or "DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY")

        return CandidateDestinationAssessment(
            facility=facility,
            feasibility_tier=feasibility,
            suitability_tier=suitability,
            straight_line_distance_meters=straight_line_dist,
            route_distance_meters=route_dist,
            route_duration_seconds=route_dur,
            is_topologically_connected=is_connected,
            is_access_passable=is_passable,
            is_operationally_suitable=is_suitable,
            ranking_score=ranking_score,
            ranking_rationale=rationale,
            selection_or_rejection_explanation=explanation,
            route_assessment=route_assessment,
            warnings=warnings,
            unknown_suitability_fields=unknown_fields,
        )

    def evaluate_emergency_destination_workflow(
        self,
        origin_node_id: str,
        target_facility_id: str,
        road_status_snapshot: Optional[RoadStatusSnapshot] = None,
        vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
    ) -> EmergencyModeAssessment:
        """
        Connects destination-aware route evaluation to the Phase 20 emergency workflow.
        Enforces human review boundaries and ensures autonomous dispatch remains disarmed.
        """
        facility = self.registry.get_destination(target_facility_id)
        if not facility:
            raise ValueError(f"Facility '{target_facility_id}' not found in destination registry.")

        # Evaluate route to target destination
        route_assessment = self.router.find_risk_aware_route(
            origin_node_id=origin_node_id,
            destination_node_id=facility.nearest_graph_node_id or origin_node_id,
            vehicle_type=vehicle_type,
            target_facility=facility,
            is_demonstration=True,
        )

        input_data = EmergencyAssessmentInput(
            location_id=origin_node_id,
            road_name=f"Access Route to {facility.name}",
            road_status_snapshot=road_status_snapshot,
            route_assessment_output=route_assessment,
        )

        emergency_assessment = self.emergency_engine.evaluate_emergency_assessment(input_data=input_data)

        # Explicitly verify software audit disclaimer
        emergency_assessment.audit_hash_disclaimer = (
            "AUDIT HASH DISCLAIMER: Software SHA-256 audit hash records evaluation state snapshot only; "
            "does NOT constitute legal/cryptographic proof of signer identity or tamper-proof external storage."
        )

        return emergency_assessment

    def _find_nearest_graph_node(self, lat: float, lon: float) -> Optional[str]:
        """Finds the closest node in the road network graph using Euclidean/geodesic distance."""
        nodes = getattr(self.graph, "nodes", {})
        if not nodes:
            return None

        best_node_id = None
        min_dist = float("inf")

        for node_id, node in nodes.items():
            dist = haversine_distance_meters(lat, lon, node.latitude, node.longitude)
            if dist < min_dist:
                min_dist = dist
                best_node_id = node_id

        # Only associate if within reasonable urban distance (e.g., 5.0 km)
        if min_dist <= 5000.0:
            return best_node_id
        return None


# Global default service instance
default_destination_routing_service = DestinationAwareRoutingService()
