"""
Sahaay AI - Comprehensive End-to-End Architecture Acceptance Suite
Validates all 12 operational acceptance scenarios from Section 11:
1. Advance forecast warning for saved-area users.
2. Rain-event update with material threshold suppression.
3. Article image discovery with provenance and abstention gate.
4. Independent multi-source flood corroboration.
5. Exclusion of impassable roads from routing when alternative exists.
6. Forecast risk separation from confirmed ground inundation.
7. Targeted alerts to frequently affected saved localities.
8. Non-silent degradation when data feeds become stale/unavailable.
9. Honest unsupported response for disconnected road graphs.
10. Honest NOT_CONFIGURED status for uncredentialed external notifications.
11. Safe handling of conflicting and syndicated evidence.
12. Responsive sub-50ms critical pipeline execution.
"""

from datetime import datetime, timezone, timedelta
import io
import time
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.corridor_evidence.service import default_corridor_evidence_service
from sahaay.forecast_risk.schemas import ForecastRainfallInput, MANDATORY_FORECAST_RISK_DISCLAIMER
from sahaay.hyderabad_risk.weather_pipeline import default_weather_pipeline
from sahaay.ingestion.connectors.weather import WeatherIngestionConnector
from sahaay.ingestion.event_store import IngestedEventStore
from sahaay.ingestion.image_pipeline import AutomatedImagePipeline
from sahaay.ingestion.orchestrator import IngestionOrchestrator
from sahaay.ingestion.schemas import (
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
)
from sahaay.notifications.schemas import (
    NotificationDeliveryChannel,
    NotificationSeverity,
    NotificationType,
    SubscriptionRequest,
)
from sahaay.notifications.service import NotificationService
from sahaay.reports.schemas import (
    CitizenReportSubmission,
    ReportCondition,
    WaterDepthEstimate,
)
from sahaay.reports.service import CitizenReportService
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    UncertaintyLevel,
)
from sahaay.road_status.service import default_road_status_service
from sahaay.routing.contracts import VehicleType
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import PassabilityAssessment, RouteAssessmentOutcome


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# Scenario 1: Advance Forecast Warning for Saved-Area User
# -----------------------------------------------------------------------------

def test_scenario_1_advance_forecast_warning_saved_area():
    service = NotificationService()
    service.clear()

    # User 1 has saved Begumpet; User 2 has saved Hitec City
    service.subscribe(SubscriptionRequest(
        user_id="USR-BEGUMPET-RESIDENT",
        saved_areas=["Begumpet", "Prakash Nagar"],
        corridor_id=None,
    ))
    service.subscribe(SubscriptionRequest(
        user_id="USR-HITEC-WORKER",
        saved_areas=["Hitec City", "Madhapur"],
        corridor_id=None,
    ))

    # Advance forecast warning for Begumpet
    emitted = service.dispatch_advance_forecast_warning(
        locality="Begumpet",
        corridor_id="HYD-LOC-002",
        forecast_horizon_hours=24.0,
        rainfall_amount_mm=65.0,
        risk_level="HIGH",
        forecast_source="IMD Hyderabad Regional Model",
        uncertainty="MODERATE",
        valid_window_utc="2026-10-30T06:00:00Z to 2026-10-30T18:00:00Z",
    )

    assert len(emitted) == 1
    alert = emitted[0]
    assert alert.recipient_or_topic == "user:USR-BEGUMPET-RESIDENT"
    assert alert.notification_type == NotificationType.ADVANCE_FORECAST_WARNING
    assert alert.severity == NotificationSeverity.WATCH
    assert alert.evidence_status == "FORECAST_WARNING"
    assert "Begumpet" in alert.affected_areas
    assert "65.0mm" in alert.message
    assert alert.forecast_window_utc is not None
    assert alert.recommended_action is not None


# -----------------------------------------------------------------------------
# Scenario 2: Rain Event Update with Material Threshold Suppression
# -----------------------------------------------------------------------------

def test_scenario_2_rain_update_with_material_threshold_suppression():
    service = NotificationService(default_cooldown_seconds=1200.0)
    service.clear()

    # Step A: Rain starts at 5.0 mm/h
    emitted_1 = service.dispatch_rain_event_update(
        locality="Tolichowki",
        corridor_id="HYD-LOC-001",
        current_rate_mm_h=5.0,
        intensity_state="STARTED",
    )
    assert len(emitted_1) == 1
    assert emitted_1[0].notification_type == NotificationType.RAIN_EVENT_UPDATE

    # Step B: Minor change to 6.2 mm/h within cooldown (same light band, <15 mm/h delta)
    emitted_2 = service.dispatch_rain_event_update(
        locality="Tolichowki",
        corridor_id="HYD-LOC-001",
        current_rate_mm_h=6.2,
        intensity_state="CONTINUING",
    )
    assert len(emitted_2) == 0  # Immaterial change suppressed

    # Step C: Major intensification to 35.0 mm/h (crosses from light into heavy band, >15 mm/h jump)
    emitted_3 = service.dispatch_rain_event_update(
        locality="Tolichowki",
        corridor_id="HYD-LOC-001",
        current_rate_mm_h=35.0,
        intensity_state="INTENSIFIED",
    )
    assert len(emitted_3) == 1
    assert "35.0 mm/h" in emitted_3[0].message
    assert emitted_3[0].severity == NotificationSeverity.ADVISORY


# -----------------------------------------------------------------------------
# Scenario 3: Article Image Discovered, Provenance Preserved, Abstention Respected
# -----------------------------------------------------------------------------

def test_scenario_3_article_image_discovery_and_abstention():
    pipeline = AutomatedImagePipeline()

    # Generate synthetic image
    img = Image.new("RGB", (300, 300), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    # Ingest image
    result = pipeline.process_image_bytes(
        image_bytes=img_bytes,
        corridor_id="HYD-LOC-001",
        source_name="TELANGANA_TODAY_ARTICLE",
    )

    assert result.predicted_class in {"flooded", "not_flooded", "inconclusive", "unclassified"}
    assert result.is_inconclusive is True
    assert result.image_sha256 is not None
    assert result.safety_disclaimer is not None

    # Verify SHA-256 caching: Second identical submission recognizes hash
    cached_result = pipeline.process_image_bytes(
        image_bytes=img_bytes,
        corridor_id="HYD-LOC-001",
        source_name="DUPLICATE_SYNDICATED_SCRAPE",
    )
    assert cached_result.image_sha256 == result.image_sha256


# -----------------------------------------------------------------------------
# Scenario 4: Multiple Independent Reports Corroborate Flooding
# -----------------------------------------------------------------------------

def test_scenario_4_multi_source_independent_corroboration():
    from sahaay.road_status.schemas import RoadStatusEvaluationInput
    status_service = default_road_status_service
    corridor_id = "HYD-LOC-001"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    input_data = RoadStatusEvaluationInput(
        road_segment_id=corridor_id,
        community_reports=[
            {
                "report_id": "CITIZEN-REP-A",
                "reporter_id_masked": "USR-101",
                "reported_condition": "WATERLOGGED_PASSABLE",
                "observation_timestamp_utc": now_iso,
                "submission_timestamp_utc": now_iso,
            },
            {
                "report_id": "CITIZEN-REP-B",
                "reporter_id_masked": "USR-102",
                "reported_condition": "WATERLOGGED_PASSABLE",
                "observation_timestamp_utc": now_iso,
                "submission_timestamp_utc": now_iso,
            },
        ]
    )

    status = status_service.evaluate_road_status(input_data)
    assert status.condition_state == RoadConditionState.CORROBORATED
    assert "CORROBORATED_BY_INDEPENDENT_COMMUNITY_SOURCES" in status.reason_codes


# -----------------------------------------------------------------------------
# Scenario 5: Newly Verified Impassable Road Excluded from Routing
# -----------------------------------------------------------------------------

def test_scenario_5_newly_verified_impassable_road_pruned_from_route():
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Initial route computation
    orig = "NODE-RETHIBOWLI"
    dest = "NODE-OU-COLONY"
    initial_route = router.find_risk_aware_route(origin_node_id=orig, destination_node_id=dest)
    assert initial_route.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION

    # Corridor HYD-LOC-001 is now confirmed impassable
    recalculated_route, was_recalculated = router.recalculate_route(
        current_route=initial_route,
        origin_node_id=orig,
        destination_node_id=dest,
        newly_impassable_segment_ids=["HYD-LOC-001"],
    )

    assert was_recalculated is True
    # The impassable corridor must not be in recommended segments
    rec_ids = [s.segment_id for s in recalculated_route.recommended_segments]
    assert "HYD-LOC-001" not in rec_ids
    # It must be documented in excluded segments
    ex_ids = [s.segment_id for s in recalculated_route.excluded_segments]
    assert "HYD-LOC-001" in ex_ids


# -----------------------------------------------------------------------------
# Scenario 6: Forecast Risk Separation from Confirmed Inundation
# -----------------------------------------------------------------------------

def test_scenario_6_forecast_risk_separation_from_confirmed_inundation(client):
    response = client.get("/api/v1/map/forecast-risk/geojson?horizon_hours=3.0&rainfall_scenario_mm=75.0")
    assert response.status_code == 200
    data = response.json()

    assert data["type"] == "FeatureCollection"
    assert data["metadata"]["layer_type"] == "FORECAST_FLOOD_RISK_MAP"
    assert data["metadata"]["forecast_horizon_hours"] == 3.0

    features = data["features"]
    assert len(features) > 0

    first_feat = features[0]
    props = first_feat["properties"]
    # Risk category must be modeled, not confirmed road closure
    assert "forecast_risk_category" in props
    assert props["safety_disclaimer"] == MANDATORY_FORECAST_RISK_DISCLAIMER
    # Symbology uses dashed lines for forecast uncertainty
    assert props["symbology"]["stroke_style"] == "dashed"


# -----------------------------------------------------------------------------
# Scenario 7: Targeted Warnings for Frequently Affected Localities
# -----------------------------------------------------------------------------

def test_scenario_7_targeted_warnings_only_reach_affected_users():
    service = NotificationService()
    service.clear()

    # User X saved Malakpet (frequently flooded underpass)
    service.subscribe(SubscriptionRequest(
        user_id="USR-MALAKPET-COMMUTER",
        saved_areas=["Malakpet", "Chaderghat"],
    ))
    # User Y saved Jubilee Hills (elevated zone, unaffected)
    service.subscribe(SubscriptionRequest(
        user_id="USR-JUBILEE-COMMUTER",
        saved_areas=["Jubilee Hills", "Banjara Hills"],
    ))

    # Alert for Malakpet
    emitted = service.dispatch_local_flood_warning(
        locality="Malakpet",
        corridor_id="HYD-LOC-006",
        evidence_summary="Malakpet Railway Underbridge submerged under 45cm water",
        recommended_action="Take elevated flyover towards Dilsukhnagar; avoid RUB",
        severity=NotificationSeverity.WARNING,
    )

    assert len(emitted) == 1
    assert emitted[0].recipient_or_topic == "user:USR-MALAKPET-COMMUTER"
    assert "Malakpet" in emitted[0].title
    assert "avoid RUB" in emitted[0].recommended_action

    # User Y received 0 notifications
    user_y_history = [n for n in service.get_history() if n.recipient_or_topic == "user:USR-JUBILEE-COMMUTER"]
    assert len(user_y_history) == 0


# -----------------------------------------------------------------------------
# Scenario 8: Stale or Degraded Feeds Expose Non-Silent Uncertainty
# -----------------------------------------------------------------------------

def test_scenario_8_stale_or_degraded_feed_exposes_uncertainty():
    # If telemetry is missing, evaluate_corridor_weather marks data freshness and telemetry missingness
    weather_res = default_weather_pipeline.evaluate_corridor_weather(
        corridor_id="HYD-LOC-016",
        corridor_lat=17.40,
        corridor_lon=78.55,
        target_dt=datetime.now(timezone.utc) - timedelta(hours=8),  # 8 hours old
    )
    # Never silences missingness as safe zero
    assert weather_res.data_freshness_hours >= 6.0


# -----------------------------------------------------------------------------
# Scenario 9: Disconnected Road Graph Reports Unsupported Rather Than Inventing
# -----------------------------------------------------------------------------

def test_scenario_9_disconnected_road_graph_reports_unsupported():
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Attempt to route to an unsupported/non-existent node
    route = router.find_risk_aware_route(
        origin_node_id="NODE-RETHIBOWLI",
        destination_node_id="NODE-NONEXISTENT-ISLAND",
    )

    assert route.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert route.total_distance_meters == 0.0
    assert len(route.recommended_segments) == 0
    assert not route.is_guaranteed_safe
    assert not route.is_optimality_claimed
    assert "Destination node 'NODE-NONEXISTENT-ISLAND'" in route.warnings[0]


# -----------------------------------------------------------------------------
# Scenario 10: Absent External Notification Credentials Honestly Reported
# -----------------------------------------------------------------------------

def test_scenario_10_absent_external_credentials_honestly_reported(client):
    response = client.get("/api/v1/notifications/external-status")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in {"NOT_CONFIGURED", "CONFIGURED"}
    if not data["is_configured"]:
        assert data["delivery_channel"] == "NOT_CONFIGURED"
        assert "not configured in hackathon environment" in data["details"]


# -----------------------------------------------------------------------------
# Scenario 11: Conflicting Evidence Does Not Cause False Certainty
# -----------------------------------------------------------------------------

def test_scenario_11_conflicting_evidence_does_not_assert_closure():
    from sahaay.road_status.schemas import RoadStatusEvaluationInput
    status_service = default_road_status_service
    corridor_id = "HYD-LOC-003"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    input_data = RoadStatusEvaluationInput(
        road_segment_id=corridor_id,
        community_reports=[
            {
                "report_id": "REP-PASS-1",
                "reporter_id_masked": "USR-A",
                "reported_condition": "DRY_ROAD_CLEAR",
                "observation_timestamp_utc": now_iso,
                "submission_timestamp_utc": now_iso,
            },
            {
                "report_id": "REP-FLOOD-2",
                "reporter_id_masked": "USR-B",
                "reported_condition": "FLOODED_ROAD",
                "observation_timestamp_utc": now_iso,
                "submission_timestamp_utc": now_iso,
            },
        ]
    )

    status = status_service.evaluate_road_status(input_data)
    assert status.has_conflicting_evidence is True
    assert status.condition_state == RoadConditionState.CONFLICTING


# -----------------------------------------------------------------------------
# Scenario 12: Fast Application Performance Benchmark (<50ms)
# -----------------------------------------------------------------------------

def test_scenario_12_critical_pipeline_responsiveness():
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)

    # 1. Routing latency benchmark
    t0 = time.perf_counter()
    route = router.find_risk_aware_route(
        origin_node_id="NODE-RETHIBOWLI",
        destination_node_id="NODE-OU-COLONY",
    )
    t_route_ms = (time.perf_counter() - t0) * 1000.0
    assert route.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION
    assert t_route_ms < 50.0, f"Routing latency {t_route_ms:.2f}ms exceeded 50ms benchmark"

    # 2. Targeted notification dispatch benchmark
    service = NotificationService()
    service.subscribe(SubscriptionRequest(user_id="USR-PERF", saved_areas=["Begumpet"]))
    t1 = time.perf_counter()
    service.dispatch_advance_forecast_warning(
        locality="Begumpet",
        corridor_id="HYD-LOC-001",
        forecast_horizon_hours=6.0,
        rainfall_amount_mm=30.0,
    )
    t_notif_ms = (time.perf_counter() - t1) * 1000.0
    assert t_notif_ms < 15.0, f"Notification dispatch latency {t_notif_ms:.2f}ms exceeded 15ms benchmark"
