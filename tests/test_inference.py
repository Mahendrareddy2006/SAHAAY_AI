"""Unit tests for Flood Vision inference service."""
import os
import io
import pytest
from PIL import Image
from sahaay.vision.inference import FloodVisionInference

@pytest.fixture(scope="module")
def inference_service():
    checkpoint = os.path.join("models", "vision", "best_model.pt")
    if not os.path.exists(checkpoint):
        pytest.skip("Model checkpoint not available")
    return FloodVisionInference(checkpoint_path=checkpoint, device_name="cpu")

def test_inference_valid_image(inference_service):
    img = Image.new("RGB", (256, 256), color=(50, 100, 150))
    result = inference_service.predict(img)
    
    assert "prediction_id" in result
    assert result["predicted_class"] in ["not_flooded", "flooded"]
    assert 0.0 <= result["confidence"] <= 1.0
    assert "not_flooded" in result["class_scores"]
    assert "flooded" in result["class_scores"]
    assert len(result["warnings"]) >= 2
    assert result["model_name"] == "mobilenet_v3_small"

def test_inference_empty_bytes_rejection(inference_service):
    with pytest.raises(ValueError, match="empty"):
        inference_service.predict(b"")

def test_inference_corrupt_bytes_rejection(inference_service):
    with pytest.raises(ValueError, match="Failed to decode|Corrupt"):
        inference_service.predict(b"NOT_A_VALID_IMAGE_PAYLOAD_12345")
