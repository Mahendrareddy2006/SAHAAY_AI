"""
Sahaay AI - Phase B: Topological Road Graph Engine
(src/sahaay/road_network/graph.py)

Constructs, validates, and manages a formal directed topological road graph:
- Stable node and directed edge identifiers.
- Directed traversal support for one-way roads.
- Bidirectional traversal strictly when justified by source data (is_one_way == False).
- Explicit connectivity and edge provenance tracking.
- Geometry and coordinate validation against Hyderabad bounding box.
- Detection of duplicate edges, disconnected components, and invalid references.
- Separation of missing network topology from verified impassable road conditions.
- Strict anti-fabrication policy: Does NOT snap or connect roads merely because
  they are geographically close unless an explicit shared junction node exists.
"""

from collections import deque
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

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
    validate_wgs84_coordinate,
)


class GraphNode(BaseModel):
    """
    Physical vertex in the topological road network representing an intersection,
    junction, or terminal endpoint of a road centerline.
    """
    node_id: str = Field(..., min_length=3, max_length=64, description="Stable unique node identifier e.g. NODE-TOLICHOWKI-W")
    longitude: float = Field(..., ge=HYDERABAD_MIN_LON, le=HYDERABAD_MAX_LON)
    latitude: float = Field(..., ge=HYDERABAD_MIN_LAT, le=HYDERABAD_MAX_LAT)
    elevation_m: Optional[float] = None
    is_junction: bool = Field(False, description="True if connected to multiple distinct road corridors")
    connected_segment_ids: List[str] = Field(default_factory=list)
    outgoing_edge_ids: List[str] = Field(default_factory=list)
    incoming_edge_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DirectedEdge(BaseModel):
    """
    Directed, navigable edge representing permissible vehicular travel in one direction
    along a physical road segment between two graph nodes.
    """
    edge_id: str = Field(..., min_length=5, max_length=80, description="Stable unique edge ID e.g. EDGE-HYD-LOC-001-FWD")
    segment_id: str = Field(..., min_length=3, max_length=64)
    road_name: str
    from_node_id: str
    to_node_id: str
    direction: str = Field("FORWARD", description="'FORWARD' or 'REVERSE'")
    is_one_way: bool = False
    length_meters: float = Field(..., gt=0.0)
    speed_limit_kph: int = Field(..., ge=10, le=140)
    free_flow_travel_time_seconds: float = Field(..., gt=0.0)
    road_class: RoadClassification = RoadClassification.PRIMARY
    source_provider: str = Field("SAHAAY_BASE_CORRIDOR_CATALOG")
    source_license: str = Field("ODbL-1.0")
    source_attribution: str = Field("© OpenStreetMap contributors, ODbL 1.0; Sahaay AI Project")
    geometry_coordinates: List[List[float]] = Field(..., min_length=2)


class GraphValidationIssue(BaseModel):
    """Auditable log of validation errors or warnings during graph construction."""
    issue_type: str = Field(..., description="'ERROR' or 'WARNING'")
    code: str = Field(..., description="Machine-readable code e.g. DUPLICATE_EDGE, INVALID_NODE_REFERENCE")
    entity_id: str
    message: str


class GraphTopologyMetrics(BaseModel):
    """Quantitative topology and connectivity metrics for a built road graph."""
    total_nodes: int
    total_directed_edges: int
    forward_edges_count: int
    reverse_edges_count: int
    total_segments_represented: int
    one_way_segments_count: int
    bidirectional_segments_count: int
    junction_nodes_count: int
    dead_end_nodes_count: int
    connected_components_count: int
    largest_component_node_count: int
    is_fully_connected: bool
    validation_errors_count: int
    validation_warnings_count: int


class RoadGraph:
    """
    Directed topological graph representation of a road network.
    Maintains adjacency lists, node registers, and graph traversal indexes.
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, DirectedEdge] = {}
        self.outgoing_edges: Dict[str, List[DirectedEdge]] = {}
        self.incoming_edges: Dict[str, List[DirectedEdge]] = {}
        self.segment_to_edges: Dict[str, List[DirectedEdge]] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self.outgoing_edges:
            self.outgoing_edges[node.node_id] = []
        if node.node_id not in self.incoming_edges:
            self.incoming_edges[node.node_id] = []

    def add_edge(self, edge: DirectedEdge) -> None:
        self.edges[edge.edge_id] = edge
        self.outgoing_edges.setdefault(edge.from_node_id, []).append(edge)
        self.incoming_edges.setdefault(edge.to_node_id, []).append(edge)
        self.segment_to_edges.setdefault(edge.segment_id, []).append(edge)

        # Update node edge lists
        if edge.from_node_id in self.nodes:
            if edge.edge_id not in self.nodes[edge.from_node_id].outgoing_edge_ids:
                self.nodes[edge.from_node_id].outgoing_edge_ids.append(edge.edge_id)
        if edge.to_node_id in self.nodes:
            if edge.edge_id not in self.nodes[edge.to_node_id].incoming_edge_ids:
                self.nodes[edge.to_node_id].incoming_edge_ids.append(edge.edge_id)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Optional[DirectedEdge]:
        return self.edges.get(edge_id)

    def get_outgoing_edges(self, node_id: str) -> List[DirectedEdge]:
        return self.outgoing_edges.get(node_id, [])

    def get_incoming_edges(self, node_id: str) -> List[DirectedEdge]:
        return self.incoming_edges.get(node_id, [])

    def get_edges_for_segment(self, segment_id: str) -> List[DirectedEdge]:
        return self.segment_to_edges.get(segment_id, [])

    def find_connected_components(self) -> List[Set[str]]:
        """
        Computes weakly connected components (treating directed edges as undirected)
        across the entire node set using Breadth-First Search (BFS).
        """
        visited: Set[str] = set()
        components: List[Set[str]] = []

        # Build undirected adjacency list for weak connectivity analysis
        undirected_adj: Dict[str, Set[str]] = {nid: set() for nid in self.nodes}
        for edge in self.edges.values():
            if edge.from_node_id in undirected_adj and edge.to_node_id in undirected_adj:
                undirected_adj[edge.from_node_id].add(edge.to_node_id)
                undirected_adj[edge.to_node_id].add(edge.from_node_id)

        for node_id in self.nodes:
            if node_id not in visited:
                component: Set[str] = set()
                queue = deque([node_id])
                visited.add(node_id)

                while queue:
                    curr = queue.popleft()
                    component.add(curr)
                    for neighbor in undirected_adj.get(curr, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                components.append(component)

        # Sort largest components first
        components.sort(key=lambda c: len(c), reverse=True)
        return components

    def get_metrics(
        self,
        validation_errors: int = 0,
        validation_warnings: int = 0
    ) -> GraphTopologyMetrics:
        """Computes comprehensive topological connectivity metrics for the graph."""
        components = self.find_connected_components()
        largest_comp_size = len(components[0]) if components else 0
        total_nodes = len(self.nodes)

        forward_count = sum(1 for e in self.edges.values() if e.direction == "FORWARD")
        reverse_count = sum(1 for e in self.edges.values() if e.direction == "REVERSE")

        unique_segments = set(e.segment_id for e in self.edges.values())
        oneway_count = sum(1 for sid, edgs in self.segment_to_edges.items() if len(edgs) == 1 and edgs[0].is_one_way)
        bidi_count = len(unique_segments) - oneway_count

        junction_nodes = sum(1 for n in self.nodes.values() if len(n.connected_segment_ids) > 1 or (len(n.outgoing_edge_ids) + len(n.incoming_edge_ids)) > 2)
        dead_end_nodes = sum(1 for n in self.nodes.values() if len(n.outgoing_edge_ids) == 0 or len(n.incoming_edge_ids) == 0)

        is_connected = (len(components) == 1 and total_nodes > 0)

        return GraphTopologyMetrics(
            total_nodes=total_nodes,
            total_directed_edges=len(self.edges),
            forward_edges_count=forward_count,
            reverse_edges_count=reverse_count,
            total_segments_represented=len(unique_segments),
            one_way_segments_count=oneway_count,
            bidirectional_segments_count=bidi_count,
            junction_nodes_count=junction_nodes,
            dead_end_nodes_count=dead_end_nodes,
            connected_components_count=len(components),
            largest_component_node_count=largest_comp_size,
            is_fully_connected=is_connected,
            validation_errors_count=validation_errors,
            validation_warnings_count=validation_warnings,
        )


class RoadGraphBuilder:
    """
    Converts a collection of canonical RoadSegment objects into a formal directed RoadGraph.
    Enforces strict topological and geometric invariants:
    - Never fabricates connections between disjoint segments based on proximity alone.
    - Accurately respects one-way directionality from source tags.
    - Produces stable node and edge identifiers.
    """

    DEFAULT_SPEED_LIMITS = {
        RoadClassification.MOTORWAY: 80,
        RoadClassification.TRUNK: 60,
        RoadClassification.PRIMARY: 50,
        RoadClassification.SECONDARY: 40,
        RoadClassification.TERTIARY: 30,
        RoadClassification.RESIDENTIAL: 25,
        RoadClassification.SERVICE: 20,
        RoadClassification.UNCLASSIFIED: 30,
    }

    def __init__(self, coordinate_precision: int = 5):
        self.coordinate_precision = coordinate_precision

    def _generate_node_id(self, lon: float, lat: float, prefix: str = "NODE") -> str:
        """Generates a stable deterministic node identifier from coordinates if no explicit ID is given."""
        lat_str = f"{lat:.{self.coordinate_precision}f}".replace(".", "P")
        lon_str = f"{lon:.{self.coordinate_precision}f}".replace(".", "P")
        return f"{prefix}-{lat_str}-{lon_str}"

    def build_from_segments(
        self,
        segments: List[RoadSegment],
        enforce_explicit_nodes: bool = False
    ) -> Tuple[RoadGraph, List[GraphValidationIssue]]:
        """
        Builds a directed RoadGraph from validated RoadSegment objects.
        Returns the constructed graph and a list of auditable validation issues.
        """
        graph = RoadGraph()
        issues: List[GraphValidationIssue] = []
        seen_edge_ids: Set[str] = set()

        for seg in segments:
            # 1. Geometry validation
            geom = seg.geometry
            if geom.type != GeoJSONGeometryType.LINESTRING:
                issues.append(
                    GraphValidationIssue(
                        issue_type="WARNING",
                        code="NON_LINESTRING_GEOMETRY",
                        entity_id=seg.segment_id,
                        message=f"Segment {seg.segment_id} geometry type is '{geom.type}'; graph routing expects LineString",
                    )
                )

            coords = geom.coordinates
            if not isinstance(coords, list) or len(coords) < 2:
                issues.append(
                    GraphValidationIssue(
                        issue_type="ERROR",
                        code="INVALID_VERTEX_COUNT",
                        entity_id=seg.segment_id,
                        message=f"Segment {seg.segment_id} does not have at least 2 coordinate vertices",
                    )
                )
                continue

            start_pt = coords[0]
            end_pt = coords[-1]

            # 2. Node Identification (Explicit or Deterministic)
            from_node_id = seg.from_node_id
            to_node_id = seg.to_node_id

            if not from_node_id:
                if enforce_explicit_nodes:
                    issues.append(
                        GraphValidationIssue(
                            issue_type="ERROR",
                            code="MISSING_NODE_REFERENCE",
                            entity_id=seg.segment_id,
                            message=f"Segment {seg.segment_id} is missing explicit 'from_node_id'",
                        )
                    )
                    continue
                from_node_id = self._generate_node_id(float(start_pt[0]), float(start_pt[1]), prefix="NODE-DERIVED")

            if not to_node_id:
                if enforce_explicit_nodes:
                    issues.append(
                        GraphValidationIssue(
                            issue_type="ERROR",
                            code="MISSING_NODE_REFERENCE",
                            entity_id=seg.segment_id,
                            message=f"Segment {seg.segment_id} is missing explicit 'to_node_id'",
                        )
                    )
                    continue
                to_node_id = self._generate_node_id(float(end_pt[0]), float(end_pt[1]), prefix="NODE-DERIVED")

            if from_node_id == to_node_id:
                issues.append(
                    GraphValidationIssue(
                        issue_type="WARNING",
                        code="SELF_LOOP_DETECTED",
                        entity_id=seg.segment_id,
                        message=f"Segment {seg.segment_id} forms a self-loop (from_node == to_node == '{from_node_id}')",
                    )
                )

            # 3. Add or update terminal nodes
            for nid, pt in [(from_node_id, start_pt), (to_node_id, end_pt)]:
                lon = float(pt[0])
                lat = float(pt[1])
                try:
                    validate_wgs84_coordinate(lon, lat)
                except ValueError as ve:
                    issues.append(
                        GraphValidationIssue(
                            issue_type="ERROR",
                            code="OUT_OF_BOUNDS_NODE_COORDINATE",
                            entity_id=nid,
                            message=f"Node {nid} coordinates [{lon}, {lat}] outside Hyderabad bounds: {str(ve)}",
                        )
                    )
                    continue

                existing_node = graph.get_node(nid)
                if existing_node is None:
                    node = GraphNode(
                        node_id=nid,
                        longitude=lon,
                        latitude=lat,
                        connected_segment_ids=[seg.segment_id],
                    )
                    graph.add_node(node)
                else:
                    if seg.segment_id not in existing_node.connected_segment_ids:
                        existing_node.connected_segment_ids.append(seg.segment_id)
                    # Node is a junction if multiple segments meet here
                    if len(existing_node.connected_segment_ids) > 1:
                        existing_node.is_junction = True

            # 4. Length and speed parameters
            speed_kph = seg.speed_limit_kph or self.DEFAULT_SPEED_LIMITS.get(seg.road_class, 40)
            length_m = seg.length_meters
            if not length_m or length_m <= 0.0:
                # Fallback calculation from vertex coordinates
                calc_len = 0.0
                for i in range(len(coords) - 1):
                    p1 = coords[i]
                    p2 = coords[i + 1]
                    lat1_r, lat2_r = math.radians(p1[1]), math.radians(p2[1])
                    d_lat = math.radians(p2[1] - p1[1])
                    d_lon = math.radians(p2[0] - p1[0])
                    x = d_lon * math.cos((lat1_r + lat2_r) / 2.0)
                    y = d_lat
                    calc_len += 6371000.0 * math.sqrt(x * x + y * y)
                length_m = max(50.0, round(calc_len, 1))

            speed_ms = max(2.0, (speed_kph * 1000.0) / 3600.0)
            travel_time_sec = round(length_m / speed_ms, 2)

            # 5. Build Forward Directed Edge
            fwd_edge_id = f"EDGE-{seg.segment_id}-FWD"
            if fwd_edge_id in seen_edge_ids:
                issues.append(
                    GraphValidationIssue(
                        issue_type="ERROR",
                        code="DUPLICATE_EDGE",
                        entity_id=fwd_edge_id,
                        message=f"Duplicate forward edge '{fwd_edge_id}' detected; skipping",
                    )
                )
            else:
                seen_edge_ids.add(fwd_edge_id)
                fwd_edge = DirectedEdge(
                    edge_id=fwd_edge_id,
                    segment_id=seg.segment_id,
                    road_name=seg.road_name,
                    from_node_id=from_node_id,
                    to_node_id=to_node_id,
                    direction="FORWARD",
                    is_one_way=seg.is_one_way,
                    length_meters=length_m,
                    speed_limit_kph=speed_kph,
                    free_flow_travel_time_seconds=travel_time_sec,
                    road_class=seg.road_class,
                    source_provider=seg.source_provider,
                    source_license=seg.source_license,
                    source_attribution=seg.source_attribution,
                    geometry_coordinates=[[float(p[0]), float(p[1])] for p in coords],
                )
                graph.add_edge(fwd_edge)

            # 6. Build Reverse Directed Edge ONLY IF NOT ONE-WAY
            if not seg.is_one_way:
                rev_edge_id = f"EDGE-{seg.segment_id}-REV"
                if rev_edge_id in seen_edge_ids:
                    issues.append(
                        GraphValidationIssue(
                            issue_type="ERROR",
                            code="DUPLICATE_EDGE",
                            entity_id=rev_edge_id,
                            message=f"Duplicate reverse edge '{rev_edge_id}' detected; skipping",
                        )
                    )
                else:
                    seen_edge_ids.add(rev_edge_id)
                    # Coordinates reversed for opposing direction
                    rev_coords = [[float(p[0]), float(p[1])] for p in reversed(coords)]
                    rev_edge = DirectedEdge(
                        edge_id=rev_edge_id,
                        segment_id=seg.segment_id,
                        road_name=seg.road_name,
                        from_node_id=to_node_id,
                        to_node_id=from_node_id,
                        direction="REVERSE",
                        is_one_way=False,
                        length_meters=length_m,
                        speed_limit_kph=speed_kph,
                        free_flow_travel_time_seconds=travel_time_sec,
                        road_class=seg.road_class,
                        source_provider=seg.source_provider,
                        source_license=seg.source_license,
                        source_attribution=seg.source_attribution,
                        geometry_coordinates=rev_coords,
                    )
                    graph.add_edge(rev_edge)

        # 7. Post-construction topological validation
        error_count = sum(1 for i in issues if i.issue_type == "ERROR")
        warning_count = sum(1 for i in issues if i.issue_type == "WARNING")

        components = graph.find_connected_components()
        if len(components) > 1:
            issues.append(
                GraphValidationIssue(
                    issue_type="WARNING",
                    code="DISCONNECTED_COMPONENTS_DETECTED",
                    entity_id="ROAD_GRAPH",
                    message=(
                        f"Road graph contains {len(components)} disconnected components across "
                        f"{len(graph.nodes)} nodes. Urban routing across disjoint components will fail "
                        "unless additional connecting road corridors are ingested."
                    ),
                )
            )
            warning_count += 1

        return graph, issues
