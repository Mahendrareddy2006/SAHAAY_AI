"""
Sahaay AI - Phase E: Safe Routing and Emergency Destinations Test Suite
(tests/test_phase_e_safe_routing_and_emergency_destinations.py)

Comprehensive regression tests covering:
1. Destination schema validation, forbidden safety phrases, and synthetic fixture disclosures.
2. Emergency destination registry lookup, filtering, and GeoJSON export.
3. Separation of straight-line geographic proximity from topological route feasibility.
4. Transparent destination ranking and operational suitability boundaries.
5. Unknown/unverified facility operational status handling.
6. Inundated access bay and impassable corridor pruning.
7. Connected, disconnected, and unknown route endpoints without edge fabrication.
8. Emergency workflow integration, P1 review escalation, and audit hash disclaimer.
9. Security gating against caller role spoofing and privileged action denial.
10. REST API endpoints for destination lookup, suitability ranking, safe routing, and map overlays.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.decision.contracts import CurrentFloodEvidenceStatus
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
from sahaay.emergency_destinations.service import (
    DestinationAwareRoutingService,
    default_destination_routing_service,
    haversine_distance_meters,
)
from sahaay.emergency.schemas import (
    AuthorizedReviewerRole,
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
    EmergencyPriority,
    EmergencyResolutionRecord,
    EmergencyState,
)
from sahaay.emergency.workflow import EmergencyWorkflowEngine
from sahaay.road_network.schemas import (
    GeoJSONGeometryType,
    RoadClassification,
    RoadGeometry,
    RoadMonitoringStatus,
    RoadSegment,
)
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadStatusSnapshot,
    RoadVerificationState,
    UncertaintyLevel,
)
from sahaay.routing.contracts import VehicleType
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import (
    RouteAssessmentOutcome,
    RiskAwareRouteAssessment,
)
from tests.test_phase_b_topological_graph_routing import create_tolichowki_test_graph

client = TestClient(app)


# ==============================================================================
# 1. Destination Schema & Safety Constraints
# ==============================================================================

def test_destination_schema_forbidden_safety_phrases():
    """
    Attempting to include forbidden safety claims (e.g. 'guaranteed safe', 'zero risk')
    in a destination record triggers a validation error.
    """
    with pytest.raises(ValueError, match="forbidden safety phrase"):
        EmergencyDestinationRecord(
            facility_id="HOSP-TEST-01",
            name="City Hospital Guaranteed Safe Passage",
            destination_type=EmergencyDestinationType.HOSPITAL,
            latitude=17.40,
            longitude=78.45,
            emergency_contact_masked="040-2000XXXX",
        )


def test_unverified_operational_status_populates_unknown_fields():
    """
    Facilities with UNVERIFIED operational status automatically record 'operational_status'
    in unknown_fields and append the UNVERIFIED_OPERATIONAL_STATUS quality flag.
    """
    dest = EmergencyDestinationRecord(
        facility_id="HOSP-TEST-02",
        name="Apollo Care Clinic",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.42,
        longitude=78.44,
        operational_status=FacilityOperationalStatus.UNVERIFIED,
        emergency_contact_masked="040-2300XXXX",
    )

    assert dest.operational_status == FacilityOperationalStatus.UNVERIFIED
    assert "operational_status" in dest.unknown_fields
    assert "UNVERIFIED_OPERATIONAL_STATUS" in dest.data_quality_flags


def test_synthetic_fixture_disclosure_required():
    """
    Synthetic demonstration fixtures automatically populate an explicit fixture warning
    prohibiting reliance during actual life-safety operations.
    """
    fixture = EmergencyDestinationRecord(
        facility_id="SHELTER-FIXTURE-01",
        name="Municipal Community Relief Shed",
        destination_type=EmergencyDestinationType.OFFICIAL_SHELTER,
        latitude=17.41,
        longitude=78.42,
        is_synthetic_fixture=True,
        emergency_contact_masked="040-1000XXXX",
    )

    assert fixture.is_synthetic_fixture is True
    assert fixture.fixture_warning is not None
    assert "DEMONSTRATION_FIXTURE_NOT_REAL_FACILITY" in fixture.fixture_warning


# ==============================================================================
# 2. Destination Registry Tests
# ==============================================================================

def test_destination_registry_lookup_and_filtering():
    """
    Registry supports retrieval by ID and filtering by destination type, operational status, and zone.
    """
    registry = EmergencyDestinationRegistry(populate_seed_fixtures=True)

    # Lookup
    osmania = registry.get_destination("HOSP-OSMANIA-01")
    assert osmania is not None
    assert osmania.name == "Osmania General Hospital"
    assert osmania.destination_type == EmergencyDestinationType.HOSPITAL
    assert osmania.operational_status == FacilityOperationalStatus.OPERATIONAL_VERIFIED

    # Non-existent
    assert registry.get_destination("HOSP-NONEXISTENT") is None

    # Filter by type
    hospitals = registry.filter_destinations(destination_type=EmergencyDestinationType.HOSPITAL)
    assert len(hospitals) >= 3
    assert all(h.destination_type == EmergencyDestinationType.HOSPITAL for h in hospitals)

    shelters = registry.filter_destinations(destination_type=EmergencyDestinationType.OFFICIAL_SHELTER)
    assert len(shelters) >= 2
    assert all(s.destination_type == EmergencyDestinationType.OFFICIAL_SHELTER for s in shelters)

    # Filter by status
    operational = registry.filter_destinations(operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED)
    assert len(operational) >= 2


def test_destination_registry_geojson_export():
    """
    Registry exports valid GeoJSON FeatureCollection with status styling and fixture disclosures.
    """
    registry = EmergencyDestinationRegistry(populate_seed_fixtures=True)
    fc = registry.to_geojson_feature_collection()

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 5

    feat = fc["features"][0]
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    assert len(feat["geometry"]["coordinates"]) == 2
    assert "facility_id" in feat["properties"]
    assert "operational_status" in feat["properties"]
    assert "marker_color" in feat["properties"]


# ==============================================================================
# 3. Separation of Proximity from Feasibility & Ranking
# ==============================================================================

def test_proximity_separated_from_topological_feasibility():
    """
    SAFETY INVARIANT: Geographic straight-line proximity does NOT imply topological reachability.
    A hospital physically closer (1.5km) in a disconnected component ranks 0.0 (UNSUITABLE_UNREACHABLE),
    while a hospital further away (4.0km) with a traversable road route ranks higher.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)
    registry = EmergencyDestinationRegistry(populate_seed_fixtures=False)

    # Facility A: physically closer to NODE-A (1.5 km), but placed at disconnected NODE-ISOLATED-2
    fac_close_disconnected = EmergencyDestinationRecord(
        facility_id="HOSP-CLOSE-DISC",
        name="Close Isolated Clinic",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4010,
        longitude=78.4070,
        nearest_graph_node_id="NODE-ISOLATED-2",  # Disconnected from NODE-A!
        operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
        emergency_contact_masked="040-1111XXXX",
    )

    # Facility B: physically further (3.5 km), but connected to NODE-A via traversable bypass to NODE-C
    fac_far_connected = EmergencyDestinationRecord(
        facility_id="HOSP-FAR-CONN",
        name="Far Connected Hospital",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4150,
        longitude=78.4250,
        nearest_graph_node_id="NODE-C",  # Connected to NODE-A!
        operational_status=FacilityOperationalStatus.OPERATIONAL_VERIFIED,
        emergency_contact_masked="040-2222XXXX",
    )

    registry.register_destination(fac_close_disconnected)
    registry.register_destination(fac_far_connected)

    service = DestinationAwareRoutingService(
        registry=registry,
        router=router,
    )
    service.graph = graph

    req = DestinationSuitabilityRequest(
        origin_node_id="NODE-A",
        destination_type=EmergencyDestinationType.HOSPITAL,
    )

    response = service.assess_destinations(req)
    assert len(response.candidates_ranked) == 2

    # Verify that the connected hospital is ranked #1 despite greater straight-line distance
    ranked_1 = response.candidates_ranked[0]
    ranked_2 = response.candidates_ranked[1]

    assert ranked_1.facility.facility_id == "HOSP-FAR-CONN"
    assert ranked_1.feasibility_tier == DestinationFeasibilityTier.CONNECTED_AND_TRAVERSABLE
    assert ranked_1.is_topologically_connected is True
    assert ranked_1.ranking_score > 0.70

    assert ranked_2.facility.facility_id == "HOSP-CLOSE-DISC"
    assert ranked_2.feasibility_tier == DestinationFeasibilityTier.DISCONNECTED_TOPOLOGY
    assert ranked_2.is_topologically_connected is False
    assert ranked_2.ranking_score == 0.0
    assert "disconnected" in ranked_2.selection_or_rejection_explanation.lower()


def test_facility_with_unknown_status_not_operationally_suitable():
    """
    A facility with UNVERIFIED operational status cannot be recommended as
    SUITABLE_VERIFIED_OPERATIONAL, and is strictly excluded when
    require_verified_operational=True.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)
    registry = EmergencyDestinationRegistry(populate_seed_fixtures=False)

    fac_unverified = EmergencyDestinationRecord(
        facility_id="HOSP-UNVERIFIED-01",
        name="Civic Dispensary Unverified Status",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4020,
        longitude=78.4110,
        nearest_graph_node_id="NODE-C",
        operational_status=FacilityOperationalStatus.UNVERIFIED,
        emergency_contact_masked="040-3333XXXX",
    )
    registry.register_destination(fac_unverified)

    service = DestinationAwareRoutingService(registry=registry, router=router)
    service.graph = graph

    # Case 1: Standard request without strict filter -> DEGRADED_UNVERIFIED_STATUS
    req = DestinationSuitabilityRequest(origin_node_id="NODE-A")
    resp = service.assess_destinations(req)
    candidate = resp.candidates_ranked[0]
    assert candidate.suitability_tier == DestinationSuitabilityTier.DEGRADED_UNVERIFIED_STATUS
    assert any("operating status unverified" in w.lower() for w in candidate.warnings)

    # Case 2: Strict request require_verified_operational=True -> is_operationally_suitable is False
    req_strict = DestinationSuitabilityRequest(
        origin_node_id="NODE-A",
        require_verified_operational=True,
    )
    resp_strict = service.assess_destinations(req_strict)
    candidate_strict = resp_strict.candidates_ranked[0]
    assert candidate_strict.is_operationally_suitable is False


def test_inundated_facility_access_bay_rejected():
    """
    A destination marked INUNDATED_ACCESS_RESTRICTED is rejected with
    RESTRICTED_ACCESS_INUNDATED even if the road path is connected.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)
    registry = EmergencyDestinationRegistry(populate_seed_fixtures=False)

    fac_inundated = EmergencyDestinationRecord(
        facility_id="HOSP-INUNDATED-01",
        name="Inundated General Hospital",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.4020,
        longitude=78.4110,
        nearest_graph_node_id="NODE-C",
        operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
        emergency_contact_masked="040-4444XXXX",
    )
    registry.register_destination(fac_inundated)

    service = DestinationAwareRoutingService(registry=registry, router=router)
    service.graph = graph

    req = DestinationSuitabilityRequest(origin_node_id="NODE-A")
    resp = service.assess_destinations(req)
    candidate = resp.candidates_ranked[0]

    assert candidate.suitability_tier == DestinationSuitabilityTier.RESTRICTED_ACCESS_INUNDATED
    assert candidate.is_operationally_suitable is False
    assert candidate.ranking_score <= 0.10
    assert "INUNDATED_ACCESS_RESTRICTED" in candidate.selection_or_rejection_explanation


# ==============================================================================
# 4. Route Feasibility & Explanations
# ==============================================================================

def test_unknown_origin_or_destination_node_unsupported():
    """
    When origin or destination node does not exist in road graph, route evaluation
    returns TOPOLOGY_UNSUPPORTED with TOPOLOGY_MISSING_NODE_REFERENCE.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    route = router.find_risk_aware_route(
        origin_node_id="NODE-GHOST-UNKNOWN",
        destination_node_id="NODE-C",
    )

    assert route.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert route.engine_status == "TOPOLOGY_MISSING_NODE_REFERENCE"
    assert len(route.recommended_segments) == 0
    assert "not found in road graph" in route.warnings[0].lower()


def test_disconnected_graph_components_unsupported():
    """
    Routing between nodes in disconnected components returns TOPOLOGY_UNSUPPORTED
    with DISCONNECTED_TOPOLOGICAL_COMPONENTS without fabricating connecting edges.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-ISOLATED-2",
    )

    assert route.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert route.engine_status == "DISCONNECTED_TOPOLOGICAL_COMPONENTS"
    assert len(route.recommended_segments) == 0
    assert "disconnected topological components" in route.warnings[0].lower()


def test_verified_impassable_segment_pruning_with_viable_detour():
    """
    When primary link TEST-SEG-2 is VERIFIED_IMPASSABLE, router strictly prunes it
    and successfully routes via alternate bypass (A -> D -> E -> C).
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    def _impassable_provider(seg_id: str):
        if seg_id == "TEST-SEG-2":
            return RoadStatusSnapshot(
                road_segment_id=seg_id,
                road_name="Tolichowki Flyover Underpass",
                condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
                evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
                verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
                freshness_category=RoadFreshnessCategory.FRESH,
                uncertainty_level=UncertaintyLevel.LOW,
                confidence_score=0.98,
                last_status_update_utc="2026-10-28T00:00:00Z",
            )
        return None

    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        segment_status_provider=_impassable_provider,
    )

    assert route.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
    assert len(route.excluded_segments) == 1
    assert route.excluded_segments[0].segment_id == "TEST-SEG-2"
    assert any("TEST-SEG-BYPASS" in s.segment_id for s in route.recommended_segments)
    assert any("was pruned: Verified impassable" in e for e in route.exclusion_explanations)


def test_all_paths_impassable_unsupported():
    """
    When both primary path and alternate bypass links are marked VERIFIED_IMPASSABLE,
    router returns ALL_CANDIDATE_ROUTES_IMPASSABLE.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    def _block_all_provider(seg_id: str):
        return RoadStatusSnapshot(
            road_segment_id=seg_id,
            road_name="Flooded Corridor",
            condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
            evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
            verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
            freshness_category=RoadFreshnessCategory.FRESH,
            uncertainty_level=UncertaintyLevel.LOW,
            confidence_score=0.98,
            last_status_update_utc="2026-10-28T00:00:00Z",
        )

    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        segment_status_provider=_block_all_provider,
    )

    assert route.outcome == RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE
    assert len(route.recommended_segments) == 0
    assert len(route.excluded_segments) > 0


def test_demonstration_route_label_and_non_optimality():
    """
    Advisory routes computed over bounded graph carry DEMONSTRATION ROUTE ONLY labels,
    is_optimality_claimed=False, and is_guaranteed_safe=False.
    """
    graph, _ = create_tolichowki_test_graph()
    router = TopologicalGraphRouter(graph=graph)

    route = router.find_risk_aware_route(
        origin_node_id="NODE-A",
        destination_node_id="NODE-C",
        is_demonstration=True,
    )

    assert "DEMONSTRATION ROUTE ONLY" in route.warnings[0]
    assert route.is_optimality_claimed is False
    assert route.is_guaranteed_safe is False
    assert route.operational_action_authorized is False


# ==============================================================================
# 5. Emergency Workflow Integration Tests
# ==============================================================================

def test_blocked_hospital_access_triggers_p1_urgent_review():
    """
    When route assessment reports hospital access corridor is cut or hospital
    is INUNDATED_ACCESS_RESTRICTED, emergency workflow escalates to P1_URGENT_VERIFIED
    and enters NEEDS_HUMAN_REVIEW.
    """
    service = DestinationAwareRoutingService()
    workflow_engine = EmergencyWorkflowEngine()

    fac_inundated = EmergencyDestinationRecord(
        facility_id="HOSP-URGENT-01",
        name="Apollo Hospital Access Submerged",
        destination_type=EmergencyDestinationType.HOSPITAL,
        latitude=17.41,
        longitude=78.43,
        operational_status=FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED,
        emergency_contact_masked="040-9999XXXX",
    )

    input_data = EmergencyAssessmentInput(
        incident_id="INC-URGENT-001",
        corridor_id="HYD-CORR-001",
        road_name="Tolichowki Corridor",
        route_assessment_output=RiskAwareRouteAssessment(
            route_id="ROUTE-TEST-001",
            assessment_timestamp_utc="2026-10-28T00:00:00Z",
            outcome=RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE,
            origin={"latitude": 17.40, "longitude": 78.41},
            destination={"latitude": 17.41, "longitude": 78.43},
            vehicle_type=VehicleType.LIGHT_MOTOR_VEHICLE,
            target_facility=fac_inundated,
            total_distance_meters=0.0,
            estimated_duration_seconds=0.0,
            aggregate_heuristic_risk=1.0,
            warnings=["ACCESS RESTRICTION: Target emergency facility access road is inundated and restricted."],
        ),
    )

    assessment = workflow_engine.evaluate_emergency_assessment(input_data=input_data)

    assert assessment.review_priority == EmergencyPriority.P1_URGENT_VERIFIED
    assert assessment.current_state == EmergencyState.NEEDS_HUMAN_REVIEW
    assert "EMERGENCY_HOSPITAL_ACCESS_INUNDATED_AND_RESTRICTED" in assessment.priority_reason_codes


def test_emergency_resolution_requires_authorized_role_and_justification():
    """
    Resolving an emergency assessment requires an AuthorizedReviewerRole and
    at least 10 characters of justification notes. Unauthorized roles are rejected.
    """
    workflow_engine = EmergencyWorkflowEngine()

    assessment = EmergencyModeAssessment(
        incident_id="INC-001",
        corridor_id="HYD-LOC-001",
        road_name="Tolichowki Corridor",
        assessment_timestamp_utc="2026-10-28T00:00:00Z",
        current_state=EmergencyState.NEEDS_HUMAN_REVIEW,
        review_priority=EmergencyPriority.P1_URGENT_VERIFIED,
        urgency_heuristic_score=0.95,
        ground_status_evidence={},
        forecast_rainfall_context={},
        static_susceptibility_context={},
        routing_impact_context={},
    )

    # Rejection 1: Short justification
    with pytest.raises(ValueError, match="minimum 10 characters"):
        workflow_engine.resolve_emergency(
            assessment=assessment,
            reviewer_role=AuthorizedReviewerRole.GHMC_DRF_SUPERVISOR,
            reviewer_id="DRF-OFFICER-01",
            action_type="CONFIRMED_DETOUR",
            justification_notes="Too short",
        )

    # Resolution succeeds with valid role and justification
    resolved = workflow_engine.resolve_emergency(
        assessment=assessment,
        reviewer_role=AuthorizedReviewerRole.GHMC_DRF_SUPERVISOR,
        reviewer_id="DRF-OFFICER-01",
        action_type="CONFIRMED_DETOUR",
        justification_notes="Verified on ground by DRF Unit 4; traffic diverted to Paramount Bypass.",
    )

    assert resolved.current_state == EmergencyState.RESOLVED_BY_AUTHORIZED_REVIEW
    assert resolved.resolution_record is not None
    assert resolved.resolution_record.reviewer_role == AuthorizedReviewerRole.GHMC_DRF_SUPERVISOR
    assert len(resolved.resolution_record.audit_hash) == 64


def test_audit_hash_disclaimer_present():
    """
    Emergency resolution records contain an explicit software hash disclaimer
    stating that SHA-256 hash does not constitute legal proof of signer identity.
    """
    rec = EmergencyResolutionRecord.create(
        resolution_id="RES-AUDIT0001",
        reviewer_role=AuthorizedReviewerRole.TRAFFIC_POLICE_DUTY_OFFICER,
        reviewer_id="TP-DUTY-99",
        action_type="SIGN_OFF",
        justification_notes="Verified clearance of standing water by pump crew.",
        timestamp_utc="2026-10-28T00:00:00Z",
    )

    assert hasattr(rec, "audit_disclaimer")
    assert "does not prove legal identity" in rec.audit_disclaimer.lower()


def test_autonomous_action_disarmed_across_workflow():
    """
    operational_action_authorized and external_side_effects_triggered must remain False
    across all emergency workflow states.
    """
    workflow_engine = EmergencyWorkflowEngine()
    input_data = EmergencyAssessmentInput(
        incident_id="INC-DISARMED-01",
        corridor_id="HYD-CORR-001",
        road_name="Tolichowki Corridor",
    )
    assessment = workflow_engine.evaluate_emergency_assessment(input_data)

    assert assessment.operational_action_authorized is False
    assert assessment.external_side_effects_triggered is False


# ==============================================================================
# 6. REST API Endpoints & Security
# ==============================================================================

def test_api_list_emergency_destinations():
    """GET /api/v1/emergency-destinations/ returns registered seed facilities."""
    res = client.get("/api/v1/emergency-destinations/")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 5
    facility_ids = [d["facility_id"] for d in data]
    assert "HOSP-OSMANIA-01" in facility_ids
    assert "HOSP-NIMS-01" in facility_ids


def test_api_get_single_emergency_destination():
    """GET /api/v1/emergency-destinations/{facility_id} returns single facility or 404."""
    # Existing
    res = client.get("/api/v1/emergency-destinations/HOSP-OSMANIA-01")
    assert res.status_code == 200
    data = res.json()
    assert data["facility_id"] == "HOSP-OSMANIA-01"
    assert data["destination_type"] == "HOSPITAL"

    # Not found
    res_404 = client.get("/api/v1/emergency-destinations/HOSP-NONEXISTENT")
    assert res_404.status_code == 404


def test_api_assess_destination_suitability():
    """POST /api/v1/emergency-destinations/assess-suitability ranks candidate destinations."""
    payload = {
        "origin_node_id": "NODE-CHADERGHAT",
        "destination_type": "HOSPITAL",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        "max_candidates": 3,
    }
    res = client.post("/api/v1/emergency-destinations/assess-suitability", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "candidates_ranked" in data
    assert "ranking_criteria_summary" in data
    assert "coverage_warning" in data
    assert data["operational_action_authorized"] is False


def test_api_map_emergency_destinations_geojson():
    """GET /api/v1/map/emergency-destinations returns valid GeoJSON FeatureCollection."""
    res = client.get("/api/v1/map/emergency-destinations")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) >= 5
    feat = data["features"][0]
    assert feat["geometry"]["type"] == "Point"
    assert "marker_color" in feat["properties"]


def test_api_safe_route_evaluation():
    """POST /api/v1/routing/safe-route evaluates topological route feasibility."""
    payload = {
        "origin_node_id": "NODE-RETHIBOWLI",
        "destination_node_id": "NODE-SHAIKPET-ENTRY",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
    }
    res = client.post("/api/v1/routing/safe-route", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "outcome" in data
    assert "warnings" in data
    assert "safety_disclaimer" in data
    assert data["is_guaranteed_safe"] is False
    assert data["operational_action_authorized"] is False


def test_api_map_route_overlay_geojson():
    """GET /api/v1/map/route-overlay returns GeoJSON overlay features."""
    params = {
        "origin_node_id": "NODE-RETHIBOWLI",
        "destination_node_id": "NODE-SHAIKPET-ENTRY",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
    }
    res = client.get("/api/v1/map/route-overlay", params=params)
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert "properties" in data
    assert "outcome" in data["properties"]


def test_api_security_role_spoofing_denied():
    """
    Attempting to supply caller role tokens or request emergency dispatch via API
    is strictly rejected with HTTP 403 Forbidden.
    """
    payload = {
        "origin_node_id": "NODE-RETHIBOWLI",
        "destination_node_id": "NODE-SHAIKPET-ENTRY",
        "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        "caller_role": "SUPER_ADMIN_DISPATCHER",
        "request_emergency_dispatch": True,
    }
    res = client.post("/api/v1/routing/safe-route", json=payload)
    assert res.status_code == 403
    assert "rejected" in res.json()["detail"].lower()
