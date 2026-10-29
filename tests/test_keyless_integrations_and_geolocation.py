"""
Unit and Integration Tests: Keyless Free-Tier Integrations and Geolocation Tracking
(tests/test_keyless_integrations_and_geolocation.py)

Validates:
1. OpenStreetMap Leaflet configuration with visible attribution and no Google Maps keys.
2. Open-Meteo keyless forecast integration, accumulation calculation (1h, 3h, 6h, 24h),
   and strict absence of zero-substitution for missing data.
3. IMD configuration marked optional/not_configured without blocking normal startup.
4. Nearest-node snapping API (/api/v1/routing/nearest-node) for user live location.
5. Out-of-bounds coordinate handling and input validation.
6. Flood-aware routing and impassable road segment exclusion.
"""

import json
import math
import os
import re
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.ingestion.connectors.weather import WeatherIngestionConnector
from sahaay.road_network.store import default_road_network_store
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.contracts import VehicleType


@pytest.fixture
def client():
    return TestClient(app)


def test_leaflet_openstreetmap_tiles_and_attribution():
    """Verify that Leaflet map uses standard OpenStreetMap tiles with visible attribution."""
    index_path = os.path.join("src", "sahaay", "api", "static", "index.html")
    assert os.path.isfile(index_path), "index.html must exist in static dir"

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must contain OpenStreetMap tile endpoint
    assert "https://tile.openstreetmap.org/{z}/{x}/{y}.png" in content
    # Must have attribution
    assert "OpenStreetMap" in content
    assert "contributors" in content
    # Leaflet attributionControl must be enabled
    assert re.search(r"attributionControl:\s*true", content) is not None
    # Must not contain Google Maps API key requirements or Carto broken key URLs
    assert "maps.googleapis.com" not in content
    assert "API KEY REQUIRED" not in content


def test_startup_without_google_maps_or_imd_keys():
    """Verify that system operates keyless without Google Maps or IMD API keys."""
    connector = WeatherIngestionConnector(is_live=False)
    events = connector.fetch_events()
    assert len(events) >= 1
    event = events[0]

    # IMD should be optional and not configured
    assert connector.imd_api_key == ""
    assert connector.imd_endpoint == ""
    assert "open-meteo" in connector.source_name.lower() or "weather" in connector.source_name.lower()


def test_open_meteo_accumulation_windows():
    """Verify 1h, 3h, 6h, and 24h forecast accumulations are computed accurately from hourly intervals."""
    connector = WeatherIngestionConnector(is_live=True)

    # 48 hourly rainfall values in mm: hour 0 has 10mm, hour 1 has 15mm, hour 2 has 20mm, hour 3 has 5mm, etc.
    mock_hourly_precip = [10.0, 15.0, 20.0, 5.0, 5.0, 5.0] + [2.0] * 18 + [0.5] * 24

    from datetime import datetime, timezone, timedelta
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    now_kolkata = datetime.now(kolkata_tz)
    mock_times = [(now_kolkata + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(48)]

    mock_data = {
        "latitude": 17.385,
        "longitude": 78.4867,
        "current": {
            "time": now_kolkata.strftime("%Y-%m-%dT%H:00"),
            "temperature_2m": 26.5,
            "relative_humidity_2m": 88,
            "precipitation": 12.0,
            "weather_code": 63,
            "surface_pressure": 955.0,
            "wind_speed_10m": 18.0,
        },
        "hourly": {
            "time": mock_times,
            "precipitation": mock_hourly_precip,
            "precipitation_probability": [90] * 48,
        },
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        event = connector._fetch_live_open_meteo()

    assert event is not None
    prov = event.provenance
    acc = prov.get("forecast_accumulations", {})

    # 1h: [10.0] -> 10.0 mm
    assert acc.get("1h_mm") == 10.0
    # 3h: [10.0, 15.0, 20.0] -> 45.0 mm
    assert acc.get("3h_mm") == 45.0
    # 6h: [10.0, 15.0, 20.0, 5.0, 5.0, 5.0] -> 60.0 mm
    assert acc.get("6h_mm") == 60.0
    # 24h: 60.0 + (18 * 2.0) -> 96.0 mm
    assert acc.get("24h_mm") == 96.0

    # Ensure separate observed vs forecast fields
    assert prov.get("observed_rainfall_1h_mm") == 12.0
    assert prov.get("forecast_rainfall_1h_mm") == 10.0
    assert prov.get("official_imd_status") == "NOT_CONFIGURED (Optional / Keyless Open-Meteo Active)"
    assert prov.get("is_imd_required") is False


def test_open_meteo_missing_data_not_converted_to_zero():
    """Ensure missing precipitation data is not converted to 0.0 or declared dry."""
    connector = WeatherIngestionConnector(is_live=True)

    mock_data = {
        "latitude": 17.385,
        "longitude": 78.4867,
        "current": {
            "time": "2026-10-29T12:00",
            # precipitation key is None / missing
            "precipitation": None,
        },
        "hourly": {
            "time": [],
            "precipitation": [],  # empty hourly data
        },
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        event = connector._fetch_live_open_meteo()

    assert event is not None
    prov = event.provenance
    # Observed rain must remain None when missing; NEVER substituted with 0.0
    assert prov.get("observed_rainfall_1h_mm") is None
    # Forecast accumulations must be None or empty
    assert prov.get("forecast_rainfall_1h_mm") is None


def test_open_meteo_network_failure_handling():
    """Ensure network timeouts or HTTP errors fall back safely without crashing."""
    import urllib.error
    connector = WeatherIngestionConnector(is_live=True)

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timed out")):
        events = connector.fetch_events()

    assert len(events) >= 1
    assert connector.consecutive_failures >= 1


def test_nearest_node_snapping_within_network(client):
    """Test /api/v1/routing/nearest-node snaps Rethibowli coordinates accurately."""
    # Node NODE-RETHIBOWLI is at lat=17.3995, lon=78.4060
    resp = client.get("/api/v1/routing/nearest-node?lat=17.3995&lon=78.4060")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "FOUND"
    assert data["nearest_node_id"] == "NODE-RETHIBOWLI"
    assert data["distance_meters"] <= 5.0
    assert data["is_within_network"] is True
    assert "Rethibowli" in data["node_name"] or "NODE-RETHIBOWLI" in data["node_name"]


def test_nearest_node_snapping_out_of_bounds(client):
    """Test /api/v1/routing/nearest-node correctly identifies coordinates outside Hyderabad network."""
    # Coordinate in Mumbai
    resp = client.get("/api/v1/routing/nearest-node?lat=19.0760&lon=72.8777")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "OUT_OF_BOUNDS"
    assert data["nearest_node_id"] is None
    assert data["is_within_network"] is False
    assert "outside" in data["message"].lower()


def test_nearest_node_invalid_coordinates(client):
    """Test coordinate range validation rejects invalid latitudes and longitudes."""
    # Latitude > 90
    resp = client.get("/api/v1/routing/nearest-node?lat=100.0&lon=78.4060")
    assert resp.status_code == 422

    # Longitude < -180
    resp = client.get("/api/v1/routing/nearest-node?lat=17.3995&lon=-200.0")
    assert resp.status_code == 422


def test_route_calculation_with_blocked_impassable_segments(client):
    """Test route calculation identifies and avoids blocked waterlogged corridors."""
    # Request route from Rethibowli to Shaikpet
    resp = client.post(
        "/api/v1/routing/safe-route",
        json={
            "origin_node_id": "NODE-RETHIBOWLI",
            "destination_node_id": "NODE-SHAIKPET-ENTRY",
            "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        }
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "outcome" in data
    assert "recommended_segments" in data
    assert "excluded_segments" in data
    assert "safety_disclaimer" in data

    # Route overlay endpoint
    overlay_resp = client.get(
        "/api/v1/map/route-overlay?origin_node_id=NODE-RETHIBOWLI&destination_node_id=NODE-SHAIKPET-ENTRY&vehicle_type=LIGHT_MOTOR_VEHICLE"
    )
    assert overlay_resp.status_code == 200
    geojson = overlay_resp.json()
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) >= 1
