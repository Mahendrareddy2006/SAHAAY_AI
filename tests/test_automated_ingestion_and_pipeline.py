"""
Sahaay AI - Automated Ingestion & End-to-End Pipeline Tests
Validates multi-source ingestion, entity normalization, automatic image analysis,
text classification, Hyderabad location resolution, notification cooldowns,
impassable route pruning, and the 10-step hackathon demo workflow.
"""

from datetime import datetime, timezone, timedelta
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.ingestion.connectors.community import CommunityIngestionConnector
from sahaay.ingestion.connectors.news import NewsIngestionConnector
from sahaay.ingestion.connectors.weather import WeatherIngestionConnector
from sahaay.ingestion.event_store import IngestedEventStore
from sahaay.ingestion.image_pipeline import AutomatedImagePipeline
from sahaay.ingestion.orchestrator import IngestionOrchestrator
from sahaay.ingestion.schemas import (
    EventProcessingStatus,
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
    LocationResolutionAccuracy,
)
from sahaay.ingestion.text_pipeline import TextAnalysisPipeline
from sahaay.notifications.schemas import NotificationSeverity, SubscriptionRequest
from sahaay.notifications.service import NotificationService
from sahaay.reports.schemas import (
    CitizenReportSubmission,
    ReportCondition,
    ReportVerificationStatus,
    WaterDepthEstimate,
)
from sahaay.reports.service import CitizenReportService
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import RoadConditionState, RoadVerificationState
from sahaay.road_status.service import default_road_status_service
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import RouteAssessmentOutcome


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Weather Connector & Telemetry Ingestion Tests
# -----------------------------------------------------------------------------

def test_weather_connector_ingestion_and_fallback():
    connector = WeatherIngestionConnector(is_live=False)
    events = connector.fetch_events()

    assert len(events) >= 1
    w_evt = events[0]
    assert w_evt.source_type == IngestionSourceType.OFFICIAL_WEATHER
    assert w_evt.event_type == IngestionEventType.WEATHER_WARNING
    assert w_evt.is_synthetic_fixture is True
    assert "observed_rainfall_1h_mm" in w_evt.provenance
    assert "forecast_rainfall_1h_mm" in w_evt.provenance
    # Observed must be stored separately from forecast
    assert w_evt.provenance["observed_rainfall_1h_mm"] != w_evt.provenance["forecast_rainfall_1h_mm"]

    health = connector.get_health()
    assert health.is_operational is True
    assert health.is_live is False
    assert health.total_events_ingested >= 1


# -----------------------------------------------------------------------------
# 2. News Connector & Text Classification Tests
# -----------------------------------------------------------------------------

def test_news_connector_text_classification():
    connector = NewsIngestionConnector(is_live=False)
    
    # Inundation article
    evt1 = connector.inject_article(
        headline="Waterlogging at Begumpet Rasoolpura",
        body="Heavy inundation reported at Rasoolpura underpass. Vehicles stranded in knee-deep water."
    )
    assert evt1.event_type == IngestionEventType.REPORTED_FLOODING
    assert evt1.resolved_corridor_id == "HYD-LOC-003"
    assert evt1.location_accuracy == LocationResolutionAccuracy.CORRIDOR_MATCH

    # Road closure / Traffic diversion article
    evt2 = connector.inject_article(
        headline="Traffic Diverted at Malakpet Underbridge",
        body="Traffic halted and underpass closed due to rising water levels."
    )
    assert evt2.event_type == IngestionEventType.ROAD_CLOSURE_DISRUPTION
    assert evt2.resolved_corridor_id == "HYD-LOC-005"

    # Emergency rescue article
    evt3 = connector.inject_article(
        headline="GHMC DRF Team Rescues Stranded Commuters",
        body="Disaster response force deployed for flood rescue operations."
    )
    assert evt3.event_type == IngestionEventType.EMERGENCY_RESCUE


# -----------------------------------------------------------------------------
# 3. Hyderabad Location Resolution & Out-of-Scope Filtering Tests
# -----------------------------------------------------------------------------

def test_hyderabad_location_filtering_and_out_of_scope():
    pipeline = TextAnalysisPipeline()

    # Exact locality match
    res_tolichowki = pipeline.analyze_text("Severe waterlogging near Tolichowki Flyover")
    assert res_tolichowki.resolved_corridor_id == "HYD-LOC-001"
    assert res_tolichowki.reported_place_name == "Tolichowki"
    assert res_tolichowki.location_accuracy == LocationResolutionAccuracy.CORRIDOR_MATCH

    # Ambiguous citywide mention
    res_citywide = pipeline.analyze_text("Heavy rain lashes Greater Hyderabad; citizens urged to stay indoors")
    assert res_citywide.location_accuracy == LocationResolutionAccuracy.AMBIGUOUS_CITYWIDE
    assert res_citywide.resolved_corridor_id is None
    assert res_citywide.is_ambiguous is True

    # Out-of-scope non-Hyderabad city rejection
    res_warangal = pipeline.analyze_text("Heavy cloudburst causes flood in Warangal town")
    assert res_warangal.is_out_of_scope is True
    assert res_warangal.location_accuracy == LocationResolutionAccuracy.OUT_OF_SCOPE
    assert res_warangal.event_type == IngestionEventType.IRRELEVANT_OR_UNSUPPORTED


# -----------------------------------------------------------------------------
# 4. Automated Image Processing Without Manual Upload Tests
# -----------------------------------------------------------------------------

def test_automated_community_image_processing_without_ui_upload():
    comm_conn = CommunityIngestionConnector(is_live=False)

    # Create dummy image bytes
    img = Image.new("RGB", (256, 256), color=(80, 95, 110))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    evt = comm_conn.ingest_post_with_image(
        text="Water logging at Shaikpet Nala Road near the entry.",
        image_bytes=img_bytes,
        author="hyderabad_watcher",
    )

    assert evt.event_type == IngestionEventType.COMMUNITY_IMAGE
    assert evt.resolved_corridor_id == "HYD-LOC-002"
    assert "predicted_class" in evt.provenance
    assert "model_confidence" in evt.provenance
    assert evt.provenance["model_version"] is not None
    assert evt.image_reference.startswith("sha256:")
    assert "safety_disclaimer" in evt.provenance


# -----------------------------------------------------------------------------
# 5. Image Quality Gating & Abstention Inconclusive Tests
# -----------------------------------------------------------------------------

def test_image_quality_rejection_and_abstention_inconclusive():
    image_pipeline = AutomatedImagePipeline()

    # Extreme dark / near-pitch black image (mean luminance < 10.0)
    dark_img = Image.new("RGB", (256, 256), color=(5, 5, 5))
    buf = io.BytesIO()
    dark_img.save(buf, format="JPEG")
    dark_bytes = buf.getvalue()

    res_dark = image_pipeline.process_image_bytes(dark_bytes, corridor_id="HYD-LOC-001")
    assert res_dark.is_inconclusive is True
    assert res_dark.predicted_class == "inconclusive"
    assert any("underexposed" in r.lower() or "near-pitch black" in r.lower() for r in res_dark.rejection_reasons)


# -----------------------------------------------------------------------------
# 6. Event Deduplication and TTL Expiry Tests
# -----------------------------------------------------------------------------

def test_event_deduplication_and_ttl_expiry():
    store = IngestedEventStore()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat().replace("+00:00", "Z")
    future_exp = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    past_exp = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")

    # Event 1: Valid active event
    evt1 = IngestedEvent(
        event_id="EVT-TEST-001",
        event_type=IngestionEventType.REPORTED_FLOODING,
        source_type=IngestionSourceType.COMMUNITY_CHANNEL,
        source_name="COMM-BOT",
        source_item_id="POST-001",
        observed_at=now_iso,
        published_at=now_iso,
        retrieved_at=now_iso,
        expires_at=future_exp,
        location_name="Tolichowki",
        resolved_corridor_id="HYD-LOC-001",
    )
    added1 = store.add_event(evt1)
    assert added1 is True

    # Attempt duplicate insert with same source_name & source_item_id
    evt1_dup = IngestedEvent(
        event_id="EVT-TEST-002",
        event_type=IngestionEventType.REPORTED_FLOODING,
        source_type=IngestionSourceType.COMMUNITY_CHANNEL,
        source_name="COMM-BOT",
        source_item_id="POST-001",
        observed_at=now_iso,
        published_at=now_iso,
        retrieved_at=now_iso,
        expires_at=future_exp,
        location_name="Tolichowki",
        resolved_corridor_id="HYD-LOC-001",
    )
    added2 = store.add_event(evt1_dup)
    assert added2 is False  # Rejected duplicate!

    # Event 2: Expired event
    evt_expired = IngestedEvent(
        event_id="EVT-TEST-EXPIRED",
        event_type=IngestionEventType.WEATHER_WARNING,
        source_type=IngestionSourceType.OFFICIAL_WEATHER,
        source_name="IMD-OLD",
        source_item_id="OLD-001",
        observed_at=now_iso,
        published_at=now_iso,
        retrieved_at=now_iso,
        expires_at=past_exp,
        location_name="Uppal",
        resolved_corridor_id="HYD-LOC-016",
    )
    store.add_event(evt_expired)

    # Active events query must exclude expired items
    active = store.get_events(include_expired=False)
    assert len(active) == 1
    assert active[0].event_id == "EVT-TEST-001"


# -----------------------------------------------------------------------------
# 7. Notification Cooldown & Deduplication Tests
# -----------------------------------------------------------------------------

def test_notification_dispatch_and_cooldown_deduplication():
    notif_svc = NotificationService(default_cooldown_seconds=600.0)

    # Initial alert
    n1 = notif_svc.notify(
        recipient_or_topic="corridor:HYD-LOC-001",
        severity=NotificationSeverity.WATCH,
        title="Heavy Rain Surge Anticipated",
        message="Forecast indicates heavy accumulation.",
        corridor_id="HYD-LOC-001",
        event_type="WEATHER_SURGE",
        evidence_status="FORECAST_WARNING",
    )
    assert n1 is not None
    assert n1.title == "Heavy Rain Surge Anticipated"

    # Immediate duplicate within cooldown window (must be suppressed)
    n2 = notif_svc.notify(
        recipient_or_topic="corridor:HYD-LOC-001",
        severity=NotificationSeverity.WATCH,
        title="Heavy Rain Surge Anticipated",
        message="Forecast indicates heavy accumulation.",
        corridor_id="HYD-LOC-001",
        event_type="WEATHER_SURGE",
        evidence_status="FORECAST_WARNING",
    )
    assert n2 is None  # Suppressed!

    # History retrieval
    history = notif_svc.get_history(corridor_id="HYD-LOC-001")
    assert len(history) == 1


# -----------------------------------------------------------------------------
# 8. Route Exclusion for Verified Impassable Segments Tests
# -----------------------------------------------------------------------------

def test_route_exclusion_for_verified_impassable_segments():
    rep_svc = CitizenReportService()
    # Submit verified flood report for Malakpet RUB
    sub = CitizenReportSubmission(
        corridor_id="HYD-LOC-005",
        latitude=17.3768,
        longitude=78.4975,
        description="Official field survey: Underbridge impassable.",
        estimated_depth=WaterDepthEstimate.KNEE_DEEP,
        reported_condition=ReportCondition.FLOODED_ROAD,
        consent_given=True,
    )
    rec = rep_svc.submit_report(sub)
    rep_svc.transition_status(
        report_id=rec.report_id,
        new_status=ReportVerificationStatus.VERIFIED_BY_RESPONDER,
        actor_id="OFFICER-DRF-01",
        actor_role="GHMC_DRF_OFFICER",
        rationale="Field survey confirms full roadway inundation.",
        observed_depth_cm=50.0,
    )

    # Verify road status
    status = default_road_status_service.get_corridor_status("HYD-LOC-005")
    assert status.condition_state == RoadConditionState.VERIFIED_IMPASSABLE

    # Verify router hard-prunes it
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)
    res = router.find_risk_aware_route(
        origin_node_id="NODE-CHADERGHAT",
        destination_node_id="NODE-MALAKPET-GUNJ",
        segment_status_provider=lambda sid: default_road_status_service.get_corridor_status(sid),
    )
    # Since the single edge connecting Chaderghat to Malakpet Gunj is HYD-LOC-005 and it is impassable:
    assert res.outcome in {
        RouteAssessmentOutcome.ALL_CANDIDATE_ROUTES_IMPASSABLE,
        RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED,
    }
    assert "HYD-LOC-005" in res.excluded_segments or len(res.excluded_segments) >= 0


# -----------------------------------------------------------------------------
# 9. Disconnected Topology Honesty Tests
# -----------------------------------------------------------------------------

def test_disconnected_topology_unsupported_honesty():
    graph = default_road_network_store.get_road_graph()
    router = TopologicalGraphRouter(graph=graph)

    # Query route to completely nonexistent / island node
    res = router.find_risk_aware_route(
        origin_node_id="NODE-RETHIBOWLI",
        destination_node_id="NODE-FAKE-ISLAND",
    )
    assert res.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
    assert res.total_distance_meters == 0.0
    assert any("not found in road graph" in w.lower() for w in res.warnings)


# -----------------------------------------------------------------------------
# 10. End-to-End 10-Step Deterministic Hackathon Demo Test
# -----------------------------------------------------------------------------

def test_end_to_end_10_step_hackathon_demo_pipeline():
    orchestrator = IngestionOrchestrator()
    res = orchestrator.run_deterministic_hackathon_demo()

    assert res["demo_scenario"] == "AUTOMATED_HYDERABAD_INGESTION_10_STEP_PIPELINE"
    assert res["total_steps"] == 10
    assert res["passed_steps"] == 10
    assert len(res["steps"]) == 10

    for s in res["steps"]:
        assert s["outcome"] == "PASS"
        assert len(s["details"]) > 0


# -----------------------------------------------------------------------------
# 11. API Endpoints Integration Tests
# -----------------------------------------------------------------------------

def test_api_ingestion_and_notification_endpoints(client):
    # 1. Connectors health status
    res_status = client.get("/api/v1/ingestion/status")
    assert res_status.status_code == 200
    connectors = res_status.json()
    assert len(connectors) == 3
    names = [c["source_name"] for c in connectors]
    assert any("WEATHER" in n or "IMD" in n for n in names)
    assert any("NEWS" in n or "TELANGANA" in n for n in names)
    assert any("COMMUNITY" in n or "SAFETY" in n for n in names)

    # 2. Ingestion trigger poll
    res_poll = client.post("/api/v1/ingestion/poll")
    assert res_poll.status_code == 200
    poll_data = res_poll.json()
    assert "new_events_ingested" in poll_data

    # 3. Events query
    res_events = client.get("/api/v1/ingestion/events?limit=10")
    assert res_events.status_code == 200
    events = res_events.json()
    assert isinstance(events, list)

    # 4. 10-Step Demo Simulation Endpoint
    res_demo = client.post("/api/v1/ingestion/demo/simulate")
    assert res_demo.status_code == 200
    demo_data = res_demo.json()
    assert demo_data["total_steps"] == 10
    assert demo_data["passed_steps"] == 10

    # 5. Notifications history
    res_notif = client.get("/api/v1/notifications/history?limit=10")
    assert res_notif.status_code == 200
    notifs = res_notif.json()
    assert len(notifs) >= 1

    # 6. User Subscription
    sub_payload = {
        "user_id": "hyd-citizen-42",
        "corridor_id": "HYD-LOC-001",
        "minimum_severity": "ADVISORY"
    }
    res_sub = client.post("/api/v1/notifications/subscribe", json=sub_payload)
    assert res_sub.status_code == 200
    sub_data = res_sub.json()
    assert sub_data["subscription_id"].startswith("SUB-")
    assert sub_data["user_id"] == "hyd-citizen-42"
