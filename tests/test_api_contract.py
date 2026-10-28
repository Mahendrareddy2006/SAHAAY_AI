"""API contract and route integration tests."""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sahaay.api.main import app

client = TestClient(app)

def test_api_health_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"

def test_vision_health_endpoint():
    resp = client.get("/api/v1/vision/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checkpoint_loaded"] is True

def test_vision_predict_valid_image():
    # Create test JPEG in-memory
    im = Image.new("RGB", (128, 128), color=(20, 80, 140))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    buf.seek(0)
    
    files = {"file": ("test.jpg", buf, "image/jpeg")}
    data = {"latitude": "17.3850", "longitude": "78.4867", "report_id": "rep_test_001"}
    
    resp = client.post("/api/v1/vision/predict", files=files, data=data)
    assert resp.status_code == 200
    res = resp.json()
    assert "prediction_id" in res
    assert res["predicted_class"] in ["flooded", "not_flooded", "inconclusive"]
    assert "class_scores" in res
    assert res["location"]["latitude"] == 17.3850
    assert len(res["warnings"]) >= 2


def test_vision_predict_inconclusive_serialization(monkeypatch):
    """Verify that an inconclusive prediction result is serialized as 'inconclusive' without forcing binary classification."""
    from unittest.mock import MagicMock
    import sahaay.api.routes as routes

    mock_service = MagicMock()
    mock_service.predict.return_value = {
        "prediction_id": "pred_inconclusive_001",
        "predicted_class": "inconclusive",
        "confidence": 0.65,
        "class_scores": {"not_flooded": 0.50, "flooded": 0.50},
        "is_ambiguous": True,
        "is_inconclusive": True,
        "inconclusive_reasons": ["Score falls within [0.35, 0.65] ambiguity band"],
        "quality_metrics": None,
        "model_name": "mobilenetv3_large_baseline",
        "model_version": "v3.0.0",
        "device": "cpu",
        "inference_latency_ms": 12.5,
        "created_at": "2026-10-26T12:00:00Z",
        "report_id": "rep_test_inconcl",
        "location": {"latitude": 17.3850, "longitude": 78.4867},
        "warnings": ["Model evaluation is inconclusive. Manual field verification recommended."]
    }
    monkeypatch.setattr(routes, "get_inference_service", lambda: mock_service)

    fake_file = io.BytesIO(b"fake_jpeg_payload")
    files = {"file": ("test.jpg", fake_file, "image/jpeg")}
    resp = client.post("/api/v1/vision/predict", files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["predicted_class"] == "inconclusive"
    assert res["is_inconclusive"] is True
    assert res["is_ambiguous"] is True
    assert "inconclusive" in res["warnings"][0].lower()


def test_vision_predict_unsupported_mimetype():
    files = {"file": ("test.txt", io.BytesIO(b"Hello world text"), "text/plain")}
    resp = client.post("/api/v1/vision/predict", files=files)
    assert resp.status_code == 415

def test_decision_evaluate_endpoint():
    payload = {
        "location_id": "HYD-RD-042",
        "road_name": "Begumpet Flyover Underpass",
        "vision_predicted_class": "flooded",
        "vision_confidence": 0.94,
        "vision_is_ambiguous": False,
        "rainfall_risk_category": "HIGH",
        "rainfall_risk_score": 0.85,
        "vulnerability_category": "SEVERE",
        "vulnerability_index": 0.80,
        "report_age_minutes": 15.0,
        "is_field_verified": True
    }
    resp = client.post("/api/v1/decision/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["alert_level"] in ["EMERGENCY", "WARNING"]
    assert data["is_actionable_for_crews"] is True
