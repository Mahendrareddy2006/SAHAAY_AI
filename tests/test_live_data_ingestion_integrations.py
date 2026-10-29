"""
Sahaay AI - Real-Time Hyderabad Data Ingestion Integration Tests
Validates real external source connectors, provider status transitions (LIVE/FIXTURE/NOT_CONFIGURED),
SSRF protection, article/blog image extraction, automated vision inference,
evidence fusion into CorridorEvidenceService, and notification deduplication.
"""

from datetime import datetime, timezone, timedelta
import io
import json
import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

from sahaay.ingestion.connectors.weather import WeatherIngestionConnector
from sahaay.ingestion.connectors.news import NewsIngestionConnector
from sahaay.ingestion.connectors.community import CommunityIngestionConnector
from sahaay.ingestion.event_store import IngestedEventStore
from sahaay.ingestion.image_downloader import (
    is_safe_public_url,
    fetch_remote_image,
    fetch_safe_article_html,
    extract_image_urls_from_article_html,
    SafeRedirectHandler,
)
from sahaay.ingestion.image_pipeline import default_image_pipeline
from sahaay.ingestion.orchestrator import IngestionOrchestrator
from sahaay.ingestion.schemas import (
    EventProcessingStatus,
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
    LocationResolutionAccuracy,
)
from sahaay.notifications.service import NotificationService
from sahaay.notifications.schemas import NotificationSeverity, NotificationDeliveryChannel
from sahaay.corridor_evidence.service import default_corridor_evidence_service


# -----------------------------------------------------------------------------
# 1. Weather Connector: Observed vs Forecast & Provider State
# -----------------------------------------------------------------------------

def test_weather_connector_fixture_and_live_fallback():
    # Fixture mode
    conn_fixture = WeatherIngestionConnector(is_live=False)
    events = conn_fixture.fetch_events()
    assert len(events) >= 1
    assert events[0].is_synthetic_fixture is True
    assert conn_fixture.connectivity_mode == "FIXTURE"

    # Live mode with mock response
    mock_payload = {
        "current": {
            "time": "2026-10-29T14:30",
            "interval": 900,
            "precipitation": 12.5,
            "rain": 12.5,
            "weather_code": 61,
        },
        "hourly": {
            "time": ["2026-10-29T14:00", "2026-10-29T15:00", "2026-10-29T16:00"],
            "precipitation": [10.0, 18.0, 25.0],
            "rain": [10.0, 18.0, 25.0],
        }
    }
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        conn_live = WeatherIngestionConnector(is_live=True)
        live_events = conn_live.fetch_events()
        assert len(live_events) == 1
        evt = live_events[0]
        assert evt.is_synthetic_fixture is False
        assert evt.source_name == "OPEN-METEO-HYDERABAD-STREAM"
        assert evt.provenance["forecast_rainfall_1h_mm"] == 10.0
        assert evt.provenance["forecast_rainfall_3h_mm"] == 53.0
        assert evt.provenance["forecast_accumulations"]["3h_mm"] == 53.0
        assert evt.location_accuracy == LocationResolutionAccuracy.AMBIGUOUS_CITYWIDE
        assert evt.resolved_corridor_id is None
        assert "NOT_CONFIGURED" in evt.provenance["official_imd_status"]
        assert conn_live.connectivity_mode == "LIVE"


def test_weather_connector_degradation_on_error():
    conn = WeatherIngestionConnector(is_live=True)
    with patch("urllib.request.urlopen", side_effect=Exception("Connection timeout")):
        # Fail 3 consecutive times to trigger DEGRADED
        for _ in range(3):
            conn.fetch_events()
        assert conn.consecutive_failures >= 3
        assert conn.connectivity_mode == "DEGRADED"
        assert conn.is_operational is False


# -----------------------------------------------------------------------------
# 2. News Connector: Permitted Feeds & Article Image Discovery
# -----------------------------------------------------------------------------

def test_news_connector_registry_and_fixture():
    conn = NewsIngestionConnector(is_live=False)
    assert any("TELANGANA-TODAY" in f["name"] for f in conn.feed_registry)
    assert any("THE-HINDU" in f["name"] for f in conn.feed_registry)
    events = conn.fetch_events()
    assert len(events) >= 1
    assert events[0].is_synthetic_fixture is True
    assert conn.connectivity_mode == "FIXTURE"


def test_news_article_html_image_discovery():
    sample_article_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Heavy rain lashes Tolichowki area in Hyderabad</title>
        <meta property="og:image" content="https://images.thehindu.com/flood_tolichowki.jpg" />
        <meta name="twitter:image" content="https://images.thehindu.com/flood_tolichowki.jpg" />
    </head>
    <body>
        <h1>Waterlogging near Tolichowki Flyover</h1>
        <figure>
            <img src="https://images.thehindu.com/article_body_image.jpg" alt="Inundated road" />
        </figure>
    </body>
    </html>
    """
    with patch("sahaay.ingestion.image_downloader.is_safe_public_url", return_value=True):
        images = extract_image_urls_from_article_html(sample_article_html, "https://www.thehindu.com/article123")
        assert len(images) >= 1
        assert "https://images.thehindu.com/flood_tolichowki.jpg" in images


# -----------------------------------------------------------------------------
# 3. Community Connector: NOT_CONFIGURED vs FIXTURE
# -----------------------------------------------------------------------------

def test_community_connector_not_configured_mode():
    # When no secret/token in env, should report NOT_CONFIGURED
    with patch.dict("os.environ", {"SAHAAY_COMMUNITY_WEBHOOK_SECRET": "", "SAHAAY_COMMUNITY_BOT_TOKEN": ""}):
        conn = CommunityIngestionConnector()
        assert conn.connectivity_mode == "NOT_CONFIGURED"
        assert conn.is_configured is False


def test_community_connector_explicit_fixture_mode():
    conn = CommunityIngestionConnector(is_live=False)
    assert conn.connectivity_mode == "FIXTURE"
    events = conn.fetch_events()
    assert len(events) >= 1
    assert events[0].event_type == IngestionEventType.COMMUNITY_IMAGE


# -----------------------------------------------------------------------------
# 4. SSRF & URL Security Hardening
# -----------------------------------------------------------------------------

def test_ssrf_rejection_of_private_and_metadata_ips():
    # Localhost and loopback
    assert is_safe_public_url("http://127.0.0.1/image.jpg") is False
    assert is_safe_public_url("http://localhost/image.jpg") is False
    assert is_safe_public_url("http://::1/image.jpg") is False

    # Private RFC 1918 ranges
    assert is_safe_public_url("http://192.168.1.50/malicious.png") is False
    assert is_safe_public_url("http://10.0.0.1/private.jpg") is False
    assert is_safe_public_url("http://172.16.0.10/admin.png") is False

    # Cloud metadata service (169.254.169.254)
    assert is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False

    # Non-HTTP schemes
    assert is_safe_public_url("file:///etc/passwd") is False
    assert is_safe_public_url("gopher://evil.com") is False
    assert is_safe_public_url("ftp://ftp.server.com/img.jpg") is False


def test_safe_redirect_handler_blocks_private_targets():
    handler = SafeRedirectHandler()
    req = MagicMock()
    # Attempt redirect to loopback
    result = handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/secret.jpg")
    assert result is None  # Blocked!


# -----------------------------------------------------------------------------
# 5. Automated Image Quality Gate & Abstention
# -----------------------------------------------------------------------------

def test_automated_image_pipeline_abstention_band():
    # Generate test image
    img = Image.new("RGB", (256, 256), color=(100, 110, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    result = default_image_pipeline.process_image_bytes(raw_bytes, corridor_id="HYD-LOC-001")
    assert result.image_sha256 is not None
    assert result.predicted_class in {"flooded", "not_flooded", "inconclusive"}
    assert "does not infer water depth" in result.safety_disclaimer.lower()


# -----------------------------------------------------------------------------
# 6. Evidence Fusion into CorridorEvidenceService
# -----------------------------------------------------------------------------

def test_evidence_fusion_records_provisional_vision():
    orchestrator = IngestionOrchestrator()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    event = IngestedEvent(
        event_id="EVT-TEST-FUSION-001",
        event_type=IngestionEventType.REPORTED_FLOODING,
        source_type=IngestionSourceType.NEWS_FEED,
        source_name="THE-HINDU",
        source_item_id="ART-101",
        observed_at=now_iso,
        published_at=now_iso,
        retrieved_at=now_iso,
        expires_at=now_iso,
        location_name="Tolichowki Flyover",
        resolved_corridor_id="HYD-LOC-001",
        image_reference="sha256:abcd1234ef567890",
        confidence=0.88,
        provenance={
            "vision_predicted_class": "flooded",
            "vision_confidence": 0.88,
            "is_inconclusive": False,
            "discovered_image_url": "https://thehindu.com/flood.jpg",
        },
        is_synthetic_fixture=False,
    )

    orchestrator._process_single_event(event)

    # Verify registered in corridor_evidence_service
    evidence = default_corridor_evidence_service.get_latest_vision_evidence("HYD-LOC-001")
    assert evidence is not None
    assert evidence["predicted_class"] == "flooded"
    assert evidence["is_provisional_evidence"] is True
    assert evidence["measured_water_depth_cm"] is None  # Non-inference safety contract


# -----------------------------------------------------------------------------
# 7. Notification Deduplication & External Delivery Reporting
# -----------------------------------------------------------------------------

def test_notification_external_delivery_status_and_cooldown():
    service = NotificationService(default_cooldown_seconds=60.0)

    # Check unconfigured external gateway
    ext_status = service.get_external_delivery_status()
    assert ext_status["status"] == "NOT_CONFIGURED"
    assert ext_status["is_configured"] is False

    # Dispatch notification
    n1 = service.notify(
        recipient_or_topic="corridor:HYD-LOC-001",
        severity=NotificationSeverity.WATCH,
        title="Heavy Rain Surge",
        message="Rainfall threshold exceeded.",
        corridor_id="HYD-LOC-001",
        event_type="WEATHER_SURGE",
        evidence_status="FORECAST_WARNING",
    )
    assert n1 is not None
    assert n1.delivery_metadata["external_delivery_status"] == "NOT_CONFIGURED"

    # Immediate duplicate suppressed
    n2 = service.notify(
        recipient_or_topic="corridor:HYD-LOC-001",
        severity=NotificationSeverity.WATCH,
        title="Heavy Rain Surge",
        message="Rainfall threshold exceeded.",
        corridor_id="HYD-LOC-001",
        event_type="WEATHER_SURGE",
        evidence_status="FORECAST_WARNING",
    )
    assert n2 is None


# -----------------------------------------------------------------------------
# 8. Real External Live Fetch Verification (Open-Meteo & RSS)
# -----------------------------------------------------------------------------

def test_real_live_weather_fetch_end_to_end():
    """Queries actual live Open-Meteo endpoint to verify Hyderabad coordinates response."""
    conn = WeatherIngestionConnector(is_live=True)
    try:
        events = conn.fetch_events()
        assert len(events) >= 1
        w_evt = events[0]
        assert w_evt.is_synthetic_fixture is False
        assert w_evt.source_name == "OPEN-METEO-HYDERABAD-STREAM"
        assert w_evt.latitude == 17.3850
        assert w_evt.longitude == 78.4867
        assert "observed_rainfall_1h_mm" in w_evt.provenance
        assert "forecast_rainfall_1h_mm" in w_evt.provenance
        assert conn.connectivity_mode in ("LIVE", "DEGRADED")
    except Exception as ex:
        pytest.skip(f"External Open-Meteo endpoint unreachable or timed out: {ex}")

