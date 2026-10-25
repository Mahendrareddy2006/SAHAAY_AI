"""
Regression tests for Image Quality Gate:
- Native resolution verification
- Borderline input handling (resolution, darkness, whiteout)
- Severe optical and motion blur rejection
- Non-silent rejection guarantee (never silently defaulted to non-flood)
"""

import pytest
import numpy as np
from PIL import Image, ImageFilter
from sahaay.vision.inference import FloodVisionInference

@pytest.fixture(scope="module")
def inference_service():
    return FloodVisionInference(device_name="cpu")

def test_native_resolution_metrics_preservation(inference_service):
    # Verify quality metrics are measured on original image size, not resized 224x224
    img = Image.new("RGB", (1024, 768), color=(100, 110, 120))
    res = inference_service.predict(img)
    assert res["quality_metrics"]["dimensions"] == [1024, 768]

def test_borderline_resolution_rejection(inference_service):
    # 63x64 must fail (< 64 threshold)
    img_fail = Image.new("RGB", (63, 64), color=(100, 110, 120))
    res_fail = inference_service.predict(img_fail)
    assert res_fail["is_inconclusive"] is True
    assert res_fail["predicted_class"] == "inconclusive"

    # 64x64 must pass
    img_pass = Image.new("RGB", (64, 64), color=(100, 110, 120))
    res_pass = inference_service.predict(img_pass)
    assert res_pass["is_inconclusive"] is False

def test_borderline_darkness_rejection(inference_service):
    # Mean luminance 8.0 must fail (< 10.0 threshold)
    img_dark_fail = Image.new("RGB", (256, 256), color=(8, 8, 8))
    res_fail = inference_service.predict(img_dark_fail)
    assert res_fail["is_inconclusive"] is True
    assert res_fail["predicted_class"] == "inconclusive"

    # Mean luminance 15.0 must pass
    img_dark_pass = Image.new("RGB", (256, 256), color=(15, 15, 15))
    res_pass = inference_service.predict(img_dark_pass)
    assert res_pass["is_inconclusive"] is False

def test_borderline_whiteout_rejection(inference_service):
    # Mean luminance 252.0 must fail (> 248.0 threshold with low std)
    img_white_fail = Image.new("RGB", (256, 256), color=(252, 252, 252))
    res_fail = inference_service.predict(img_white_fail)
    assert res_fail["is_inconclusive"] is True
    assert res_fail["predicted_class"] == "inconclusive"

    # Mean luminance 240.0 must pass
    img_white_pass = Image.new("RGB", (256, 256), color=(240, 240, 240))
    res_pass = inference_service.predict(img_white_pass)
    assert res_pass["is_inconclusive"] is False

def test_non_silent_rejection_guarantee(inference_service):
    # Severe blur on scene must never be silently converted to 'not_flooded' or 'flooded'
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:128, :] = [230, 230, 230]
    arr[128:, :] = [30, 30, 30]
    scene = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(radius=30))
    
    res = inference_service.predict(scene)
    assert res["is_inconclusive"] is True
    assert res["predicted_class"] == "inconclusive"
    assert res["confidence"] == 0.0
    assert res["class_scores"] == {"not_flooded": 0.5, "flooded": 0.5}
    assert res["is_ambiguous"] is True
    assert any("inconclusive" in w.lower() for w in res["warnings"])
