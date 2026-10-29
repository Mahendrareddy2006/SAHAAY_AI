"""
Sahaay AI - Phase B: Topological Graph Router
(src/sahaay/routing/graph_router.py)

Implements risk-aware shortest-path navigation over a validated directed RoadGraph.
Strictly adheres to safety invariants:
1. Verified impassable road segments are strictly excluded from candidate paths (infinite traversal cost).
2. Waterlogged corridors incur severe heuristic penalty multipliers.
3. Unmonitored segments with absent telemetry are traversed with baseline costs but explicitly
   surfaced with uncertainty warnings — NEVER marked as safe or clear.
4. Completely disconnected components yield TOPOLOGY_UNSUPPORTED without fabricating connections.
5. Operational dispatch triggers remain disabled; optimality and safe passage are never claimed.
"""

from datetime import datetime, timezone
import heapq
import logging
from typing import Callable, Dict, List, Optional, Set, Tuple

from sahaay.road_network.graph import RoadGraph, DirectedEdge, GraphNode
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadStatusSnapshot,
    RoadVerificationState,
    RoadFreshnessCategory,
)
from sahaay.forecast_risk.schemas import ForecastRiskAssessmentOutput
from sahaay.routing.contracts import (
    VehicleType,
    EmergencyDestination,
    FacilityOperationalStatus,
)
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    SegmentRoutingAssessment,
    RiskAwareRouteAssessment,
    MANDATORY_ROUTING_DISCLAIMER,
)
from sahaay.routing.service import RiskAwareRoutingService

logger = logging.getLogger(__name__)


class TopologicalGraphRouter:
    """
    Risk-aware graph pathfinder executing Dijkstra traversal over a directed RoadGraph.
    Integrates with RiskAwareRoutingService (Phase 19) to dynamically evaluate
    segment passability, forecast precipitation context, and static vulnerability.
    """

    def __init__(
        self,
        graph: RoadGraph,
        routing_service: Optional[RiskAwareRoutingService] = None,
    ):
        self.graph = graph
        self.routing_service = routing_service or RiskAwareRoutingService()

    def find_risk_aware_route(
        self,
        origin_node_id: str,
        destination_node_id: str,
        vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
        segment_status_provider: Optional[Callable[[str], Optional[RoadStatusSnapshot]]] = None,
        forecast_risk_provider: Optional[Callable[[str], Optional[ForecastRiskAssessmentOutput]]] = None,
        target_facility: Optional[EmergencyDestination] = None,
        route_id_prefix: str = "ROUTE-TOPOLOGY",
        is_demonstration: bool = True,
    ) -> RiskAwareRouteAssessment:
        """
        Calculates the risk-penalized optimal path from origin_node_id to destination_node_id.
        Excludes verified impassable segments and accounts for unmonitored uncertainty.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        route_id = f"{route_id_prefix}-{int(datetime.now(timezone.utc).timestamp())}"

        origin_node = self.graph.get_node(origin_node_id)
        destination_node = self.graph.get_node(destination_node_id)

        # 1. Node existence validation
        if not origin_node or not destination_node:
            missing = []
            if not origin_node:
                missing.append(f"Origin node '{origin_node_id}'")
            if not destination_node:
                missing.append(f"Destination node '{destination_node_id}'")
            return RiskAwareRouteAssessment(
                route_id=route_id,
                assessment_timestamp_utc=now_iso,
                outcome=RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED,
                origin={"latitude": origin_node.latitude if origin_node else 17.40, "longitude": origin_node.longitude if origin_node else 78.45},
                destination={"latitude": destination_node.latitude if destination_node else 17.40, "longitude": destination_node.longitude if destination_node else 78.45},
                vehicle_type=vehicle_type,
                target_facility=target_facility,
                total_distance_meters=0.0,
                estimated_duration_seconds=0.0,
                aggregate_heuristic_risk=1.0,
                recommended_segments=[],
                excluded_segments=[],
                impassable_segments_count=0,
                unmonitored_segments_count=0,
                stale_or_conflicting_segments_count=0,
                has_unmonitored_segments=False,
                is_optimality_claimed=False,
                is_guaranteed_safe=False,
                operational_action_authorized=False,
                warnings=[f"Topological routing failed: {', '.join(missing)} not found in road graph."],
                exclusion_explanations=[],
                safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
                engine_status="TOPOLOGY_MISSING_NODE_REFERENCE",
            )

        origin_coords = {"latitude": origin_node.latitude, "longitude": origin_node.longitude}
        dest_coords = {"latitude": destination_node.latitude, "longitude": destination_node.longitude}

        # 2. Check if origin and destination belong to the same connected component
        components = self.graph.find_connected_components()
        origin_comp = next((c for c in components if origin_node_id in c), set())
        dest_comp = next((c for c in components if destination_node_id in c), set())

        if origin_comp != dest_comp or not origin_comp:
            return RiskAwareRouteAssessment(
                route_id=route_id,
                assessment_timestamp_utc=now_iso,
                outcome=RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED,
                origin=origin_coords,
                destination=dest_coords,
                vehicle_type=vehicle_type,
                target_facility=target_facility,
                total_distance_meters=0.0,
                estimated_duration_seconds=0.0,
                aggregate_heuristic_risk=1.0,
                recommended_segments=[],
                excluded_segments=[],
                impassable_segments_count=0,
                unmonitored_segments_count=0,
                stale_or_conflicting_segments_count=0,
                has_unmonitored_segments=False,
                is_optimality_claimed=False,
                is_guaranteed_safe=False,
                operational_action_authorized=False,
                warnings=[
                    f"Origin node '{origin_node_id}' and destination node '{destination_node_id}' belong to "
                    "disconnected topological components. No continuous road network path exists between them."
                ],
                exclusion_explanations=[],
                safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
                engine_status="DISCONNECTED_TOPOLOGICAL_COMPONENTS",
            )

        # 3. Dijkstra pathfinding with flood-hazard penalty weights
        # Priority queue stores tuples: (cumulative_cost, current_node_id, path_edges)
        pq: List[Tuple[float, str, List[DirectedEdge]]] = [(0.0, origin_node_id, [])]
        min_cost: Dict[str, float] = {origin_node_id: 0.0}
        visited: Set[str] = set()

        all_excluded_segments: Dict[str, SegmentRoutingAssessment] = {}

        best_path_edges: Optional[List[DirectedEdge]] = None

        while pq:
            curr_cost, curr_node_id, path = heapq.heappop(pq)

            if curr_node_id == destination_node_id:
                best_path_edges = path
                break

            if curr_node_id in visited and curr_cost > min_cost.get(curr_node_id, float("inf")):
                continue
            visited.add(curr_node_id)

            for edge in self.graph.get_outgoing_edges(curr_node_id):
                # Query road status for this segment
                status_snapshot = None
                if segment_status_provider:
                    status_snapshot = segment_status_provider(edge.segment_id)

                forecast_risk = None
                if forecast_risk_provider:
                    forecast_risk = forecast_risk_provider(edge.segment_id)

                # Assess segment passability
                seg_assessment = self.routing_service.assess_segment(
                    segment_id=edge.segment_id,
                    road_name=edge.road_name,
                    road_status=status_snapshot,
                    forecast_risk=forecast_risk,
                    length_meters=edge.length_meters,
                    vehicle_type=vehicle_type,
                )

                # SAFETY RULE 1: Hard exclusion of verified impassable segments
                if not seg_assessment.is_traversable or seg_assessment.passability_state == PassabilityAssessment.VERIFIED_IMPASSABLE:
                    all_excluded_segments[edge.segment_id] = seg_assessment
                    continue  # Strict pruning: cannot traverse flooded/impassable road

                # Cost Calculation with risk multipliers
                base_time = edge.free_flow_travel_time_seconds
                state = seg_assessment.passability_state

                # SAFETY RULE 2: Penalty weights based on flood uncertainty and verification
                if seg_assessment.condition_state == RoadConditionState.VERIFIED_WATERLOGGED:
                    # Verified waterlogged: massive deterrence penalty (15x base time + 1800s delay)
                    penalty = base_time * 15.0 + 1800.0
                elif state == PassabilityAssessment.CORROBORATED_HAZARD:
                    penalty = base_time * 5.0 + 300.0
                elif state == PassabilityAssessment.UNVERIFIED_REPORT:
                    penalty = base_time * 3.0 + 120.0
                elif state == PassabilityAssessment.CONFLICTING_EVIDENCE:
                    penalty = base_time * 4.0 + 200.0
                elif state == PassabilityAssessment.STALE_OR_EXPIRED:
                    penalty = base_time * 2.0 + 60.0
                else:
                    # UNMONITORED_NO_EVIDENCE / INSUFFICIENT_DATA / VERIFIED_PASSABLE
                    penalty = base_time * 1.0

                next_cost = curr_cost + penalty
                next_node_id = edge.to_node_id

                if next_cost < min_cost.get(next_node_id, float("inf")):
                    min_cost[next_node_id] = next_cost
                    heapq.heappush(pq, (next_cost, next_node_id, path + [edge]))

        # 4. Handle unreachable destination (e.g. all alternate paths impassable)
        if best_path_edges is None:
            return RiskAwareRouteAssessment(
                route_id=route_id,
                assessment_timestamp_utc=now_iso,
                outcome=RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE if all_excluded_segments else RouteAssessmentOutcome.UNCERTAIN_INSUFFICIENT_DATA,
                origin=origin_coords,
                destination=dest_coords,
                vehicle_type=vehicle_type,
                target_facility=target_facility,
                total_distance_meters=0.0,
                estimated_duration_seconds=0.0,
                aggregate_heuristic_risk=1.0,
                recommended_segments=[],
                excluded_segments=list(all_excluded_segments.values()),
                impassable_segments_count=len(all_excluded_segments),
                unmonitored_segments_count=0,
                stale_or_conflicting_segments_count=0,
                has_unmonitored_segments=False,
                is_optimality_claimed=False,
                is_guaranteed_safe=False,
                operational_action_authorized=False,
                warnings=[
                    "No viable topological route found. All candidate paths are blocked by verified flood inundation."
                    if all_excluded_segments else
                    "No topological path connects the requested origin and destination."
                ],
                exclusion_explanations=[
                    f"Segment {s.segment_id} ({s.road_name}) was pruned: Verified impassable flood inundation."
                    for s in all_excluded_segments.values()
                ],
                safety_disclaimer=MANDATORY_ROUTING_DISCLAIMER,
                engine_status="ALL_CANDIDATE_ROUTES_IMPASSABLE",
            )

        # 5. Build recommended segment assessments along chosen path
        recommended_segments: List[SegmentRoutingAssessment] = []
        for edge in best_path_edges:
            status_snapshot = segment_status_provider(edge.segment_id) if segment_status_provider else None
            forecast_risk = forecast_risk_provider(edge.segment_id) if forecast_risk_provider else None
            seg_assessment = self.routing_service.assess_segment(
                segment_id=edge.segment_id,
                road_name=edge.road_name,
                road_status=status_snapshot,
                forecast_risk=forecast_risk,
                length_meters=edge.length_meters,
                vehicle_type=vehicle_type,
            )
            recommended_segments.append(seg_assessment)

        # 6. Evaluate route using Phase 19 service
        assessment = self.routing_service.evaluate_route(
            route_id=route_id,
            candidate_segments=recommended_segments,
            origin=origin_coords,
            destination=dest_coords,
            vehicle_type=vehicle_type,
            target_facility=target_facility,
            reference_time_utc=datetime.now(timezone.utc),
        )

        # Attach excluded impassable segments from graph exploration
        assessment.excluded_segments = list(all_excluded_segments.values())
        assessment.impassable_segments_count = len(all_excluded_segments)
        for s in all_excluded_segments.values():
            assessment.exclusion_explanations.append(
                f"Segment {s.segment_id} ({s.road_name}) was pruned: Verified impassable flood inundation."
            )

        # Append demonstration / bounded graph caution notices
        if is_demonstration:
            assessment.warnings.insert(
                0,
                "DEMONSTRATION ROUTE ONLY: Path computed over bounded test road graph. "
                "Not certified for live operational navigation or evacuation dispatch."
            )
            assessment.engine_status = "PHASE_B_TOPOLOGICAL_DEMONSTRATION_ROUTER"
        else:
            assessment.engine_status = "PHASE_B_TOPOLOGICAL_GRAPH_ROUTER"

        return assessment

    def recalculate_route(
        self,
        current_route: RiskAwareRouteAssessment,
        origin_node_id: str,
        destination_node_id: str,
        newly_impassable_segment_ids: Optional[List[str]] = None,
        segment_status_provider: Optional[Callable[[str], Optional[RoadStatusSnapshot]]] = None,
        vehicle_type: VehicleType = VehicleType.LIGHT_MOTOR_VEHICLE,
    ) -> Tuple[RiskAwareRouteAssessment, bool]:
        """
        Evaluates whether an active route is intercepted by newly reported hazards,
        and triggers a topological recalculation avoiding the impassable corridors.
        Returns:
            (new_assessment, is_recalculated)
        """
        impassable_set = set(newly_impassable_segment_ids or [])
        affected = False

        for seg in current_route.recommended_segments:
            if seg.segment_id in impassable_set:
                affected = True
                break
            if segment_status_provider:
                st = segment_status_provider(seg.segment_id)
                if st and st.condition_state == RoadConditionState.VERIFIED_IMPASSABLE:
                    affected = True
                    break

        if not affected:
            return current_route, False

        def _merged_provider(sid: str) -> Optional[RoadStatusSnapshot]:
            if sid in impassable_set:
                from sahaay.road_status.schemas import RoadEvidenceType, RoadFreshnessCategory, UncertaintyLevel
                now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                return RoadStatusSnapshot(
                    road_segment_id=sid,
                    road_name=f"Corridor {sid}",
                    condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
                    evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                    verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
                    freshness_category=RoadFreshnessCategory.FRESH,
                    uncertainty_level=UncertaintyLevel.LOW,
                    confidence_score=0.95,
                    evidence_age_minutes=5.0,
                    source_authority="GHMC_FIELD_REPORT",
                    source_provenance="LIVE_INCIDENT_INGESTION",
                    snapshot_timestamp_utc=now_iso,
                    last_status_update_utc=now_iso,
                    evidence_timestamp_utc=now_iso,
                )
            if segment_status_provider:
                return segment_status_provider(sid)
            return None

        new_route = self.find_risk_aware_route(
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            vehicle_type=vehicle_type,
            segment_status_provider=_merged_provider,
        )
        return new_route, True

