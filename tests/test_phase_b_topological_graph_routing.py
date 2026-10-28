"""
Sahaay AI - Phase B: Topological Graph & Routing Integration Test Suite
(tests/test_phase_b_topological_graph_routing.py)

Comprehensive automated tests for:
1. Directed graph construction, stable node IDs, and stable edge IDs.
2. One-way vs. bidirectional edge traversal.
3. Node junction connectivity and disconnected components detection.
4. Duplicate edge detection, invalid vertex counts, and out-of-bounds rejection.
5. Risk-aware Dijkstra route computation on a small, multi-path connected test graph.
6. Strict exclusion of verified impassable segments with alternate detour navigation.
7. Unreachable destinations when all candidate paths are flooded (ALL_CANDIDATE_ROUTES_IMPASSABLE).
8. Uncertainty preservation for unmonitored and stale segments (never claiming guaranteed safe).
9. Disconnected component origin-destination queries returning TOPOLOGY_UNSUPPORTED without fabrication.
10. REST API endpoints for graph metrics and demonstration routing evaluation.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.road_network.schemas import (
    RoadClassification,
    RoadMonitoringStatus,
    GeoJSONGeometryType,
    RoadGeometry,
    RoadSegment,
    HYDERABAD_MIN_LAT,
    HYDERABAD_MAX_LAT,
    HYDERABAD_MIN_LON,
    HYDERABAD_MAX_LON,
)
from sahaay.road_network.graph import (
    GraphNode,
    DirectedEdge,
    RoadGraph,
    RoadGraphBuilder,
    GraphValidationIssue,
    GraphTopologyMetrics,
)
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadStatusSnapshot,
    RoadVerificationState,
    RoadFreshnessCategory,
    RoadEvidenceType,
    UncertaintyLevel,
)
from sahaay.routing.contracts import VehicleType
from sahaay.routing.schemas import (
    PassabilityAssessment,
    RouteAssessmentOutcome,
    SegmentRoutingAssessment,
    RiskAwareRouteAssessment,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_ROUTING_DISCLAIMER,
)
from sahaay.routing.service import RiskAwareRoutingService
from sahaay.routing.graph_router import TopologicalGraphRouter

client = TestClient(app)


# ==============================================================================
# Test Graph Fixtures
# ==============================================================================

def create_tolichowki_test_graph() -> Tuple[RoadGraph, Dict[str, RoadSegment]]:
    r"""
    Creates a small, bounded, fully controlled test graph representing the
    Tolichowki corridor and its alternate northern bypass network:

        (NODE-A: West Junction)
          |                \  [TEST-SEG-BYPASS-1 (One-Way)]
          | [TEST-SEG-1]    v
          v              (NODE-D: Paramount Bypass North)
        (NODE-B: Underpass)   |
          |                   | [TEST-SEG-BYPASS-2 (Bidi)]
          | [TEST-SEG-2]      v
          v              (NODE-E: Shaikpet Collector)
        (NODE-C: East Junc)  /  [TEST-SEG-BYPASS-3 (Bidi)]
          ^                v
          |---------------/

    - Primary Path: A -> B -> C (900 meters, speed 50 km/h)
    - Bypass Detour: A -> D -> E -> C (1700 meters, speed 40 km/h)
    - Isolated Node: NODE-ISOLATED (separate disconnected component)
    """
    builder = RoadGraphBuilder()

    seg1 = RoadSegment(
        segment_id="TEST-SEG-1",
        road_name="Tolichowki West Approach",
        road_class=RoadClassification.PRIMARY,
        is_one_way=False,
        from_node_id="NODE-A",
        to_node_id="NODE-B",
        length_meters=400.0,
        speed_limit_kph=50,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4060, 17.3995], [78.4085, 17.4010]],
        ),
    )

    seg2 = RoadSegment(
        segment_id="TEST-SEG-2",
        road_name="Tolichowki Flyover Underpass",
        road_class=RoadClassification.PRIMARY,
        is_one_way=False,
        from_node_id="NODE-B",
        to_node_id="NODE-C",
        length_meters=500.0,
        speed_limit_kph=50,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4085, 17.4010], [78.4112, 17.4023]],
        ),
    )

    seg_bypass1 = RoadSegment(
        segment_id="TEST-SEG-BYPASS-1",
        road_name="Paramount North Bypass Entry",
        road_class=RoadClassification.SECONDARY,
        is_one_way=True,  # Strictly one-way A -> D
        from_node_id="NODE-A",
        to_node_id="NODE-D",
        length_meters=600.0,
        speed_limit_kph=40,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4060, 17.3995], [78.4070, 17.4040]],
        ),
    )

    seg_bypass2 = RoadSegment(
        segment_id="TEST-SEG-BYPASS-2",
        road_name="Paramount Internal Link",
        road_class=RoadClassification.SECONDARY,
        is_one_way=False,
        from_node_id="NODE-D",
        to_node_id="NODE-E",
        length_meters=500.0,
        speed_limit_kph=40,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4070, 17.4040], [78.4095, 17.4050]],
        ),
    )

    seg_bypass3 = RoadSegment(
        segment_id="TEST-SEG-BYPASS-3",
        road_name="Shaikpet Collector East Connector",
        road_class=RoadClassification.SECONDARY,
        is_one_way=False,
        from_node_id="NODE-E",
        to_node_id="NODE-C",
        length_meters=600.0,
        speed_limit_kph=40,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.4095, 17.4050], [78.4112, 17.4023]],
        ),
    )

    seg_isolated = RoadSegment(
        segment_id="TEST-SEG-ISOLATED",
        road_name="Isolated Gachibowli Dead End Link",
        road_class=RoadClassification.RESIDENTIAL,
        is_one_way=False,
        from_node_id="NODE-ISOLATED-1",
        to_node_id="NODE-ISOLATED-2",
        length_meters=350.0,
        speed_limit_kph=30,
        geometry=RoadGeometry(
            type=GeoJSONGeometryType.LINESTRING,
            coordinates=[[78.3600, 17.4395], [78.3630, 17.4410]],
        ),
    )

    segments_map = {
        s.segment_id: s for s in [seg1, seg2, seg_bypass1, seg_bypass2, seg_bypass3, seg_isolated]
    }
    graph, _ = builder.build_from_segments(list(segments_map.values()))
    return graph, segments_map


# ==============================================================================
# 1. Topological Graph Construction & Invariant Tests
# ==============================================================================

def test_graph_builder_seed_catalog_metrics():
    """
    Building graph from default store seed catalog produces exact, non-fabricated metrics:
    - 22 segments
    - 40 unique nodes
    - 44 directed edges (22 fwd + 22 rev)
    - 20 weakly connected components (NOT artificially connected)
    - 2 junction nodes where links meet
    """
    graph = default_road_network_store.get_road_graph()
    metrics = graph.get_metrics()

    assert metrics.total_segments_represented == 22
    assert metrics.total_nodes == 40
    assert metrics.total_directed_edges == 44
    assert metrics.forward_edges_count == 22
    assert metrics.reverse_edges_count == 22
    assert metrics.connected_components_count == 18
    assert metrics.is_fully_connected is False
    assert metrics.junction_nodes_count == 3

    # Check stable edge IDs
    fwd_edge = graph.get_edge("EDGE-HYD-LOC-001-FWD")
    assert fwd_edge is not None
    assert fwd_edge.from_node_id == "NODE-RETHIBOWLI"
    assert fwd_edge.to_node_id == "NODE-SHAIKPET-ENTRY"
    assert fwd_edge.direction == "FORWARD"

    rev_edge = graph.get_edge("EDGE-HYD-LOC-001-REV")
    assert rev_edge is not None
    assert rev_edge.from_node_id == "NODE-SHAIKPET-ENTRY"
    assert rev_edge.to_node_id == "NODE-RETHIBOWLI"
    assert rev_edge.direction == "REVERSE"


def test_one_way_and_bidirectional_traversal_rules():
    """
    One-way road segments strictly create ONE directed edge (FORWARD).
    Bidirectional road segments create TWO directed edges (FORWARD and REVERSE).
    """
    graph, seg_map = create_tolichowki_test_graph()

    # TEST-SEG-BYPASS-1 is one-way A -> D
    bypass_edges = graph.get_edges_for_segment("TEST-SEG-BYPASS-1")
    assert len(bypass_edges) == 1
    assert bypass_edges[0].edge_id == "EDGE-TEST-SEG-BYPASS-1-FWD"
    assert bypass_edges[0].is_one_way is True
    assert graph.get_edge("EDGE-TEST-SEG-BYPASS-1-REV") is None

    # TEST-SEG-1 is bidirectional A <-> B
    bidi_edges = graph.get_edges_for_segment("TEST-SEG-1")
    assert len(bidi_edges) == 2
    edge_ids = {e.edge_id for e in bidi_edges}
    assert edge_ids == {"EDGE-TEST-SEG-1-FWD", "EDGE-TEST-SEG-1-REV"}


def test_duplicate_edges_and_invalid_geometries_detected():
    """Builder detects duplicate segment IDs and logs issues without crashing."""
    builder = RoadGraphBuilder()
    seg_valid = RoadSegment(
        segment_id="TEST-DUP-1",
        road_name="Shaikpet Road",
        geometry=RoadGeometry(type=GeoJSONGeometryType.LINESTRING, coordinates=[[78.40, 17.40], [78.41, 17.41]]),
        from_node_id="NODE-1",
        to_node_id="NODE-2",
    )

    # Build with duplicate
    graph, issues = builder.build_from_segments([seg_valid, seg_valid])
    issue_codes = [i.code for i in issues]
    assert "DUPLICATE_EDGE" in issue_codes
    assert len(graph.edges) == 2  # 1 fwd, 1 rev (duplicate skipped)


def test_disconnected_components_detected_accurately():
    """Graph accurately calculates disconnected components without snapping."""
    graph, _ = create_tolichowki_test_graph()
    components = graph.find_connected_components()

    # Tolichowki cluster (NODE-A, B, C, D, E) + Isolated cluster (NODE-ISOLATED-1, 2)
    assert len(components) == 2
    comp_sizes = sorted([len(c) for c in components], reverse=True)
    assert comp_sizes == [5, 2]


# ==============================================================================
# 2. Risk-Aware Dijkstra Routing on Test Graph
# ==============================================================================

def test_router_finds_direct_path_under_baseline_conditions():
    """
    Baseline (dry/unknown): Direct underpass path A -> B -> C (900m) is selected
    over the longer bypass A -> D -> E -> C (1700m).
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
    )

    assert assessment.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
    assert len(assessment.recommended_segments) == 2
    recommended_ids = [s.segment_id for s in assessment.recommended_segments]
    assert recommended_ids == ["TEST-SEG-1", "TEST-SEG-2"]
    assert assessment.total_distance_meters == 900.0
    assert assessment.impassable_segments_count == 0
    assert assessment.is_guaranteed_safe is False
    assert "DEMONSTRATION ROUTE ONLY" in assessment.warnings[0]


def test_router_strictly_excludes_verified_impassable_and_routes_via_detour():
    """
    SAFETY INVARIANT: When primary underpass TEST-SEG-2 is marked VERIFIED_IMPASSABLE,
    the router strictly avoids it and selects the alternate bypass A -> D -> E -> C (1700m).
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Provider marking TEST-SEG-2 as officially verified flooded/impassable
    def _status_provider(seg_id: str):
        if seg_id == "TEST-SEG-2":
            return RoadStatusSnapshot(
                road_segment_id="TEST-SEG-2",
                road_name="Tolichowki Flyover Underpass",
                condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
                evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                last_status_update_utc="2026-10-27T12:00:00Z",
                freshness_category=RoadFreshnessCategory.FRESH,
                verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
                uncertainty_level=UncertaintyLevel.LOW,
                confidence_score=0.98,
                measured_water_depth_cm=55.0,
                verified_passability="impassable_all_vehicles",
            )
        return None

    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
        segment_status_provider=_status_provider,
    )

    # Verified impassable segment was avoided
    recommended_ids = [s.segment_id for s in assessment.recommended_segments]
    assert "TEST-SEG-2" not in recommended_ids
    assert recommended_ids == ["TEST-SEG-BYPASS-1", "TEST-SEG-BYPASS-2", "TEST-SEG-BYPASS-3"]
    assert assessment.total_distance_meters == 1700.0

    # Excluded segments tracked
    assert assessment.impassable_segments_count == 1
    assert assessment.excluded_segments[0].segment_id == "TEST-SEG-2"
    assert "was pruned: Verified impassable" in assessment.exclusion_explanations[0]


def test_router_returns_all_impassable_when_all_alternate_paths_flooded():
    """
    SAFETY INVARIANT: When both primary underpass AND bypass connector are
    verified impassable, router returns ALL_CANDIDATE_ROUTES_IMPASSABLE.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    def _status_provider(seg_id: str):
        if seg_id in ["TEST-SEG-2", "TEST-SEG-BYPASS-2"]:
            return RoadStatusSnapshot(
                road_segment_id=seg_id,
                road_name=f"Flooded road {seg_id}",
                condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
                evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                last_status_update_utc="2026-10-27T12:00:00Z",
                freshness_category=RoadFreshnessCategory.FRESH,
                verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
                uncertainty_level=UncertaintyLevel.LOW,
                confidence_score=0.95,
                measured_water_depth_cm=60.0,
                verified_passability="impassable_all_vehicles",
            )
        return None

    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        segment_status_provider=_status_provider,
    )

    assert assessment.outcome == RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE
    assert len(assessment.recommended_segments) == 0
    assert assessment.impassable_segments_count == 2
    assert assessment.total_distance_meters == 0.0


def test_router_fails_gracefully_when_origin_destination_disconnected():
    """
    Connecting nodes from different components returns TOPOLOGY_UNSUPPORTED
    without fabricating an impossible jump.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Route from Tolichowki cluster (NODE-A) to Isolated cluster (NODE-ISOLATED-2)
    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-ISOLATED-2",
    )

    assert assessment.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert len(assessment.recommended_segments) == 0
    assert "disconnected topological components" in assessment.warnings[0]


def test_router_enforces_one_way_directionality():
    """
    Attempting to navigate backwards against one-way bypass link D -> A fails
    if no return path exists.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    # TEST-SEG-BYPASS-1 is strictly one-way A -> D.
    # Routing D -> A via bypass is illegal; router must traverse D -> E -> C -> B -> A.
    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-D",
        destination_node_id="NODE-A",
    )

    assert assessment.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
    recommended_ids = [s.segment_id for s in assessment.recommended_segments]
    # Traverses legal path D -> E -> C -> B -> A
    assert recommended_ids == ["TEST-SEG-BYPASS-2", "TEST-SEG-BYPASS-3", "TEST-SEG-2", "TEST-SEG-1"]
    assert "TEST-SEG-BYPASS-1" not in recommended_ids


def test_uncertainty_preservation_and_forbidden_safety_phrases():
    """
    Route traversing unmonitored roads surfaces uncertainty warnings.
    Forbidden safety phrases are strictly absent.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    assessment = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
    )

    # Check uncertainty warnings
    assert assessment.has_unmonitored_segments is True
    assert any("unmonitored segments" in w.lower() for w in assessment.warnings)
    assert any("does not indicate dry or safe" in w.lower() for w in assessment.warnings)
    assert assessment.is_guaranteed_safe is False
    assert assessment.operational_action_authorized is False

    # Check forbidden phrases across all string fields
    all_text = " ".join([
        assessment.engine_status,
        assessment.safety_disclaimer,
        " ".join(assessment.warnings),
        " ".join(assessment.exclusion_explanations),
    ]).lower()

    for phrase in FORBIDDEN_SAFETY_PHRASES:
        assert phrase not in all_text, f"Forbidden safety phrase '{phrase}' found in assessment output!"


# ==============================================================================
# 3. REST API Endpoint Tests
# ==============================================================================

def test_api_get_routing_graph_metrics():
    """GET /api/v1/routing/graph/metrics returns real metrics for default road network."""
    res = client.get("/api/v1/routing/graph/metrics")
    assert res.status_code == 200
    data = res.json()

    assert data["total_segments_represented"] == 22
    assert data["total_nodes"] == 40
    assert data["total_directed_edges"] == 44
    assert data["connected_components_count"] == 18
    assert data["is_fully_connected"] is False
    assert data["junction_nodes_count"] == 3


def test_api_post_routing_demonstration_evaluate_disconnected():
    """POST /api/v1/routing/demonstration/evaluate between disconnected corridors returns TOPOLOGY_UNSUPPORTED."""
    payload = {
        "origin_node_id": "NODE-OU-COLONY",
        "destination_node_id": "NODE-PATNY-CIRCLE",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
    }
    res = client.post("/api/v1/routing/demonstration/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["outcome"] == "TOPOLOGY_UNSUPPORTED"
    assert data["total_distance_meters"] == 0.0
    assert "disconnected" in data["warnings"][0].lower()


def test_api_post_routing_demonstration_evaluate_connected_pair():
    """POST /api/v1/routing/demonstration/evaluate across connected corridor pair returns valid route."""
    # HYD-LOC-002 (NODE-OU-COLONY -> NODE-SHAIKPET-ENTRY) connects to HYD-LOC-001 (NODE-SHAIKPET-ENTRY -> NODE-RETHIBOWLI)
    payload = {
        "origin_node_id": "NODE-OU-COLONY",
        "destination_node_id": "NODE-RETHIBOWLI",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
    }
    res = client.post("/api/v1/routing/demonstration/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["outcome"] == "ADVISORY_TRAVERSABLE_WITH_CAUTION"
    assert len(data["recommended_segments"]) == 2
    seg_ids = [s["segment_id"] for s in data["recommended_segments"]]
    assert seg_ids == ["HYD-LOC-002", "HYD-LOC-001"]
    assert data["total_distance_meters"] == 2430.0
    assert data["is_guaranteed_safe"] is False
    assert "DEMONSTRATION ROUTE ONLY" in data["warnings"][0]
