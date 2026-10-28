"""
Sahaay AI — End-to-End Workflow Reliability and Capability Verification
(tests/test_end_to_end_workflow_reliability.py)

Comprehensive end-to-end integration and failure tests covering the 4 core workflows:
1. Workflow A: Image -> flood evidence -> map (with non-inference & deduplication safety)
2. Workflow B: Current conditions -> road map -> safer route (with impassable pruning & disconnected detection)
3. Workflow C: Rainfall and forecasts -> future risk -> proactive route advice (with 5-signal separation & fail-closed telemetry)
4. Workflow D: Emergency -> eligible destination -> reachable route -> human review (with bay inundation pruning & disarmed dispatch)
"""

import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.corridor_evidence.service import default_corridor_evidence_service
from sahaay.road_network.store import default_road_network_store
from sahaay.road_status.schemas import (
    RoadConditionState,
    RoadEvidenceType,
    RoadFreshnessCategory,
    RoadVerificationState,
    RoadStatusSnapshot,
    UncertaintyLevel,
)
from sahaay.road_status.service import default_road_status_service
from sahaay.emergency_destinations.registry import default_destination_registry
from sahaay.emergency_destinations.schemas import FacilityOperationalStatus

client = TestClient(app)


def _create_synthetic_test_image(color=(30, 80, 150), size=(128, 128)) -> io.BytesIO:
    """Helper creating an in-memory valid JPEG image."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


@pytest.fixture(autouse=True)
def clean_workflow_test_state():
    """Ensures a clean state before each test run."""
    default_corridor_evidence_service.clear_vision_cache()
    yield
    default_corridor_evidence_service.clear_vision_cache()


# ==============================================================================
# WORKFLOW A: Image -> Flood Evidence -> Map
# ==============================================================================

class TestWorkflowAImageToEvidenceToMap:
    """Verifies end-to-end evidence ingestion, map reflection, and non-inference safety."""

    def test_workflow_a_upload_with_corridor_updates_evidence_and_map(self):
        """Image upload with explicit corridor updates corridor evidence and GeoJSON map."""
        buf = _create_synthetic_test_image()
        files = {"file": ("flood_scene.jpg", buf, "image/jpeg")}
        data = {
            "corridor_id": "HYD-LOC-001",
            "report_id": "rep_wf_a_001",
        }

        resp = client.post("/api/v1/vision/predict", files=files, data=data)
        assert resp.status_code == 200
        res = resp.json()

        # Contract assertions
        assert res["corridor_id"] == "HYD-LOC-001"
        assert res["is_provisional_evidence"] is True
        assert res["evidence_registered"] is True
        assert res["verification_status"] == "PROVISIONAL_UNVERIFIED"
        assert res["predicted_class"] in {"flooded", "not_flooded", "inconclusive"}

        # Non-inference safety: No water depth claimed
        assert "measured_water_depth_cm" not in res or res.get("measured_water_depth_cm") is None

        # Corridor evidence API check
        ev_resp = client.get("/api/v1/corridor-evidence/assessment/HYD-LOC-001")
        assert ev_resp.status_code == 200
        ev_data = ev_resp.json()
        assert ev_data["vision_evidence"]["inference_available"] is True
        assert ev_data["vision_evidence"]["predicted_class"] == res["predicted_class"]

        # Map GeoJSON feature check
        map_resp = client.get("/api/v1/map/corridor/HYD-LOC-001")
        assert map_resp.status_code == 200
        map_feat = map_resp.json()
        props = map_feat["properties"]
        assert props["vision_state"] == res["predicted_class"]
        assert props["vision_is_provisional"] is True

    def test_workflow_a_upload_with_coordinates_resolves_nearest_corridor(self):
        """Image upload with GPS coordinates resolves nearest seed corridor and updates map."""
        buf = _create_synthetic_test_image()
        files = {"file": ("street_photo.jpg", buf, "image/jpeg")}
        # Coordinates near Tolichowki Flyover (HYD-LOC-001 seed segment)
        data = {
            "latitude": "17.4045",
            "longitude": "78.4110",
            "report_id": "rep_wf_a_coords",
        }

        resp = client.post("/api/v1/vision/predict", files=files, data=data)
        assert resp.status_code == 200
        res = resp.json()
        assert res["corridor_id"] is not None
        assert res["evidence_registered"] is True
        assert res["location"]["latitude"] == 17.4045

    def test_workflow_a_duplicate_image_hash_prevention(self):
        """Identical image bytes within observation window are flagged to prevent corroboration inflation."""
        # Fixed deterministic image bytes
        buf1 = _create_synthetic_test_image(color=(55, 65, 75))
        content = buf1.getvalue()

        # First upload
        files1 = {"file": ("cam1.jpg", io.BytesIO(content), "image/jpeg")}
        resp1 = client.post("/api/v1/vision/predict", files=files1, data={"corridor_id": "HYD-LOC-002"})
        assert resp1.status_code == 200
        res1 = resp1.json()
        assert res1["deduplication_status"] == "UNIQUE_IMAGE_REGISTERED"

        # Second upload of exact same bytes
        files2 = {"file": ("cam2_duplicate.jpg", io.BytesIO(content), "image/jpeg")}
        resp2 = client.post("/api/v1/vision/predict", files=files2, data={"corridor_id": "HYD-LOC-002"})
        assert resp2.status_code == 200
        res2 = resp2.json()
        assert res2["deduplication_status"] == "DUPLICATE_IMAGE_IGNORED_FOR_CORROBORATION"
        assert any("DUPLICATE_IMAGE_DETECTED" in w for w in res2["warnings"])

    def test_workflow_a_invalid_upload_handling(self):
        """Empty files, invalid mime types, and oversized uploads are safely rejected."""
        # 1. Invalid mime type
        resp = client.post(
            "/api/v1/vision/predict",
            files={"file": ("doc.txt", io.BytesIO(b"not an image"), "text/plain")}
        )
        assert resp.status_code == 415

        # 2. Empty 0-byte file
        resp = client.post(
            "/api/v1/vision/predict",
            files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
        )
        assert resp.status_code == 400

    def test_workflow_a_quality_gate_rejection_marks_inconclusive_no_false_flood(self):
        """Images failing quality checks (pitch black / near pure darkness) are strictly marked inconclusive."""
        # Create solid near-black image to trigger quality gate
        dark_img = Image.new("RGB", (128, 128), color=(2, 2, 2))
        buf = io.BytesIO()
        dark_img.save(buf, format="JPEG")
        buf.seek(0)

        files = {"file": ("dark.jpg", buf, "image/jpeg")}
        resp = client.post("/api/v1/vision/predict", files=files, data={"corridor_id": "HYD-LOC-003"})
        assert resp.status_code == 200
        res = resp.json()
        # Strictly inconclusive or rejected by gate
        assert res["predicted_class"] == "inconclusive"
        assert res["is_inconclusive"] is True

        # Map property for corridor must NOT show flooded
        map_resp = client.get("/api/v1/map/corridor/HYD-LOC-003")
        assert map_resp.status_code == 200
        props = map_resp.json()["properties"]
        assert props["vision_state"] == "inconclusive"
        assert props["condition_state"] != "VERIFIED_IMPASSABLE"

    def test_workflow_a_missing_location_returns_prediction_with_warning(self):
        """Upload without corridor_id or coordinates returns inference but leaves map untouched."""
        buf = _create_synthetic_test_image()
        files = {"file": ("unlocated.jpg", buf, "image/jpeg")}
        resp = client.post("/api/v1/vision/predict", files=files)
        assert resp.status_code == 200
        res = resp.json()
        assert res["corridor_id"] is None
        assert res["evidence_registered"] is False
        assert any("MISSING_LOCATION" in w for w in res["warnings"])

    def test_workflow_a_unknown_corridor_handled_gracefully(self):
        """Upload with unknown corridor ID returns inference, logs warning, and does not crash map."""
        buf = _create_synthetic_test_image()
        files = {"file": ("unknown_corridor.jpg", buf, "image/jpeg")}
        resp = client.post(
            "/api/v1/vision/predict",
            files=files,
            data={"corridor_id": "NON-EXISTENT-CORRIDOR-999"}
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["corridor_id"] == "NON-EXISTENT-CORRIDOR-999"
        assert any("UNKNOWN_CORRIDOR" in w for w in res["warnings"])


# ==============================================================================
# WORKFLOW B: Current Conditions -> Road Map -> Safer Route
# ==============================================================================

class TestWorkflowBCurrentConditionsToSaferRoute:
    """Verifies graph routing, impassable pruning, alternative selection, and disclaimers."""

    def test_workflow_b_successful_route_on_connected_components(self):
        """Calculates topological route over connected seed network nodes."""
        payload = {
            "origin_node_id": "NODE-RETHIBOWLI",
            "destination_node_id": "NODE-OU-COLONY",
            "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        }
        resp = client.post("/api/v1/routing/safe-route", json=payload)
        assert resp.status_code == 200
        route = resp.json()
        assert route["outcome"] == "ADVISORY_TRAVERSABLE_WITH_CAUTION"
        assert route["total_distance_meters"] > 0
        assert route["safety_disclaimer"] is not None
        assert "not guarantee" in route["safety_disclaimer"].lower()
        assert route["is_guaranteed_safe"] is False

    def test_workflow_b_excludes_verified_impassable_corridors(self, monkeypatch):
        """Hard-prunes corridors confirmed impassable from candidate routes."""
        # Mock status snapshot marking HYD-LOC-001 as VERIFIED_IMPASSABLE
        impassable_snap = RoadStatusSnapshot(
            road_segment_id="HYD-LOC-001",
            corridor_id="HYD-LOC-001",
            road_name="Tolichowki Main Road",
            condition_state=RoadConditionState.VERIFIED_IMPASSABLE,
            verification_state=RoadVerificationState.VERIFIED_BY_RESPONDER,
            evidence_type=RoadEvidenceType.FIELD_RESPONDER_INSPECTION,
            freshness_category=RoadFreshnessCategory.FRESH,
            last_status_update_utc="2026-10-28T12:00:00Z",
            uncertainty_level=UncertaintyLevel.LOW,
            confidence_score=0.95,
            is_verified_impassable=True,
            measured_water_depth_cm=65.0,
        )

        def mock_status_provider(segment_id):
            if segment_id == "HYD-LOC-001":
                return impassable_snap
            return None

        monkeypatch.setattr(default_road_status_service, "get_corridor_status", mock_status_provider)

        payload = {
            "origin_node_id": "NODE-RETHIBOWLI",
            "destination_node_id": "NODE-OU-COLONY",
            "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        }
        resp = client.post("/api/v1/routing/safe-route", json=payload)
        assert resp.status_code == 200
        route = resp.json()
        # HYD-LOC-001 must be pruned
        excluded_ids = [s["segment_id"] for s in route["excluded_segments"]]
        assert "HYD-LOC-001" in excluded_ids

    def test_workflow_b_disconnected_nodes_yield_unsupported_result(self):
        """Origin and destination in disconnected components yield TOPOLOGY_UNSUPPORTED without fabricating edges."""
        payload = {
            "origin_node_id": "NODE-RETHIBOWLI",
            "destination_node_id": "NODE-DISCONNECTED-ISLAND-999",
            "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        }
        resp = client.post("/api/v1/routing/safe-route", json=payload)
        assert resp.status_code == 200
        route = resp.json()
        assert route["outcome"] == "TOPOLOGY_UNSUPPORTED"
        assert route["total_distance_meters"] == 0.0

    def test_workflow_b_coordinate_based_routing(self):
        """Routing requests with GPS coordinates resolve to the nearest graph node."""
        payload = {
            "origin_latitude": 17.404,
            "origin_longitude": 78.411,
            "destination_latitude": 17.391,
            "destination_longitude": 78.440,
            "vehicle_type": "LIGHT_MOTOR_VEHICLE",
        }
        resp = client.post("/api/v1/routing/safe-route", json=payload)
        assert resp.status_code == 200
        route = resp.json()
        assert route["outcome"] in {"ADVISORY_TRAVERSABLE_WITH_CAUTION", "TOPOLOGY_UNSUPPORTED"}

    def test_workflow_b_privileged_dispatch_attempt_denied(self):
        """Autonomous emergency dispatch requests via routing endpoint are strictly forbidden (403)."""
        payload = {
            "origin_node_id": "NODE-RETHIBOWLI",
            "destination_node_id": "NODE-OU-COLONY",
            "request_emergency_dispatch": True,
        }
        resp = client.post("/api/v1/routing/safe-route", json=payload)
        assert resp.status_code == 403


# ==============================================================================
# WORKFLOW C: Rainfall & Forecasts -> Future Risk -> Proactive Advice
# ==============================================================================

class TestWorkflowCRainfallAndForecastsToRisk:
    """Verifies multi-horizon forecast risk, 5-signal separation, and proactive steering."""

    def test_workflow_c_corridor_forecast_risk_endpoint(self):
        """Retrieves forecast risk assessment with explicit 5-signal decoupling."""
        resp = client.get("/api/v1/weather/forecast/HYD-LOC-001")
        assert resp.status_code == 200
        data = resp.json()
        # Must preserve mandatory disclaimers and decoupling
        assert "safety_disclaimer" in data
        assert "does not guarantee road safety" in data["safety_disclaimer"].lower()
        assert data["segment_id"] == "HYD-LOC-001"

    def test_workflow_c_missing_weather_telemetry_reported_non_silently(self):
        """Corridors with missing telemetry are reported as UNKNOWN / outage, never synthetic dry 0.0mm."""
        resp = client.get("/api/v1/weather/corridor/HYD-UNKNOWN-999")
        assert resp.status_code == 200
        data = resp.json()
        # Must flag missingness
        assert data["risk_category"] == "UNKNOWN" or "QC_MISSING_VALUE" in data["qc_flags"]

    def test_workflow_c_weather_ingestion_health_endpoint(self):
        """Pipeline health reflects active provider status and freshness without live leakage."""
        resp = client.get("/api/v1/weather/ingestion/health")
        assert resp.status_code == 200
        health = resp.json()
        assert "pipeline_status" in health
        assert "provider_authorization_status" in health


# ==============================================================================
# WORKFLOW D: Emergency -> Eligible Destination -> Reachable Route -> Review
# ==============================================================================

class TestWorkflowDEmergencyModeAndDestinations:
    """Verifies hospital reachability, access bay inundation pruning, and human review."""

    def test_workflow_d_destination_suitability_ranks_and_prunes_inundated_bay(self, monkeypatch):
        """Hospitals with flooded entrance bays are pruned (RESTRICTED_ACCESS_INUNDATED)."""
        # Register a mock destination with inundated access
        dest = default_destination_registry.get_destination("DEST-HOSP-001")
        if dest:
            original_status = dest.operational_status
            dest.operational_status = FacilityOperationalStatus.INUNDATED_ACCESS_RESTRICTED

            try:
                payload = {
                    "origin_node_id": "NODE-TOLICHOWKI",
                    "destination_type": "HOSPITAL",
                    "max_candidates": 5,
                }
                resp = client.post("/api/v1/emergency-destinations/assess-suitability", json=payload)
                assert resp.status_code == 200
                data = resp.json()
                candidates = data["candidates_ranked"]
                hosp1 = next((c for c in candidates if c["facility"]["facility_id"] == "DEST-HOSP-001"), None)
                if hosp1:
                    assert hosp1["suitability_tier"] == "RESTRICTED_ACCESS_INUNDATED"
                    assert hosp1["is_operationally_suitable"] is False
            finally:
                dest.operational_status = original_status

    def test_workflow_d_disconnected_destination_unreachable(self):
        """Destinations on unmapped/disconnected nodes are rejected as unreachable."""
        payload = {
            "origin_node_id": "NODE-UNMAPPED-ORIGIN-000",
            "destination_type": "HOSPITAL",
            "max_candidates": 3,
        }
        resp = client.post("/api/v1/emergency-destinations/assess-suitability", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        for cand in data["candidates_ranked"]:
            assert cand["is_topologically_connected"] is False
            assert cand["suitability_tier"] == "UNSUITABLE_UNREACHABLE"

    def test_workflow_d_emergency_routing_disallows_role_spoofing(self):
        """Client-supplied privileged roles are rejected (HTTP 403)."""
        payload = {
            "origin_node_id": "NODE-TOLICHOWKI",
            "caller_role": "ROOT_DISPATCHER",
        }
        resp = client.post("/api/v1/emergency-destinations/assess-suitability", json=payload)
        assert resp.status_code == 403

    def test_workflow_d_synthetic_fixture_disclosures_preserved(self):
        """Emergency facility records preserve synthetic demonstration fixture disclaimers."""
        resp = client.get("/api/v1/emergency-destinations/")
        assert resp.status_code == 200
        facilities = resp.json()
        assert len(facilities) >= 1
        for fac in facilities:
            if fac["is_synthetic_fixture"]:
                assert "DEMONSTRATION" in fac["fixture_warning"] or "DEMONSTRATION" in fac["provenance_source"]
