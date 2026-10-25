"""
Regression and Integrity Test Suite for Vision V3:
- Split disjointness and historical non-overlap
- Provenance and metadata completeness
- Hard-negative handling
- Image-quality gate rejection of blurred/black/overexposed imagery
- Advisory policy compliance in Decision Engine
"""

import os
import io
import pytest
import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from sahaay.vision.inference import FloodVisionInference
from sahaay.decision.contracts import DecisionInput, evaluate_decision, AlertLevel

@pytest.fixture(scope="module")
def v3_manifests():
    train_p = os.path.join("data", "processed", "manifest_v3", "train_v3.csv")
    val_p = os.path.join("data", "processed", "manifest_v3", "val_v3.csv")
    test_p = os.path.join("data", "processed", "manifest_v3", "test_v3.csv")
    
    if not (os.path.exists(train_p) and os.path.exists(val_p) and os.path.exists(test_p)):
        pytest.skip("Manifest V3 files not generated yet")
        
    df_train = pd.read_csv(train_p)
    df_val = pd.read_csv(val_p)
    df_test = pd.read_csv(test_p)
    return df_train, df_val, df_test

@pytest.fixture(scope="module")
def inference_service():
    v3_monsoon = os.path.join("models", "vision", "v3", "model_v3_monsoon.pt")
    if not os.path.exists(v3_monsoon):
        pytest.skip("Model V3 Monsoon checkpoint not found")
    return FloodVisionInference(checkpoint_path=v3_monsoon, device_name="cpu")

# --- 1. Split & Leakage Integrity ---

def test_v3_split_disjointness(v3_manifests):
    df_train, df_val, df_test = v3_manifests
    train_ids = set(df_train['image_id'])
    val_ids = set(df_val['image_id'])
    test_ids = set(df_test['image_id'])
    
    assert len(train_ids & val_ids) == 0, "Train-Val image ID leakage!"
    assert len(train_ids & test_ids) == 0, "Train-Test image ID leakage!"
    assert len(val_ids & test_ids) == 0, "Val-Test image ID leakage!"

def test_v3_md5_disjointness(v3_manifests):
    df_train, df_val, df_test = v3_manifests
    train_md5 = set(df_train['md5'])
    val_md5 = set(df_val['md5'])
    test_md5 = set(df_test['md5'])
    
    assert len(train_md5 & val_md5) == 0, "Train-Val MD5 leakage!"
    assert len(train_md5 & test_md5) == 0, "Train-Test MD5 leakage!"
    assert len(val_md5 & test_md5) == 0, "Val-Test MD5 leakage!"

def test_v3_cluster_disjointness(v3_manifests):
    df_train, df_val, df_test = v3_manifests
    train_c = set(df_train['cluster_id'])
    val_c = set(df_val['cluster_id'])
    test_c = set(df_test['cluster_id'])
    
    assert len(train_c & val_c) == 0, "Train-Val cluster leakage!"
    assert len(train_c & test_c) == 0, "Train-Test cluster leakage!"
    assert len(val_c & test_c) == 0, "Val-Test cluster leakage!"

def test_v3_independence_from_v1_and_v2(v3_manifests):
    """Manifest V3 flood images must not leak any images from historical V1/V2 sets."""
    df_train, df_val, df_test = v3_manifests
    v3_md5s = set(df_train['md5']).union(set(df_val['md5'])).union(set(df_test['md5']))
    
    historical_csvs = [
        os.path.join("data", "processed", "train.csv"),
        os.path.join("data", "processed", "manifest_v2", "train_v2.csv"),
    ]
    for hist_csv in historical_csvs:
        if os.path.exists(hist_csv):
            h_df = pd.read_csv(hist_csv)
            if 'md5' in h_df.columns:
                h_md5s = set(h_df['md5'].dropna())
                overlap = v3_md5s & h_md5s
                assert len(overlap) == 0, f"Found {len(overlap)} hash overlaps between V3 and {hist_csv}!"

def test_v3_class_and_hard_negative_balance(v3_manifests):
    df_train, df_val, df_test = v3_manifests
    for split_name, df in [("Train", df_train), ("Val", df_val), ("Test", df_test)]:
        lbl_counts = df['label'].value_counts()
        assert lbl_counts[0] == lbl_counts[1], f"{split_name} split is not exactly class-balanced!"
        
        # Verify hard negatives presence
        hard_neg_count = len(df[df['subcondition'] == 'wet_road_pothole_hard_negative'])
        assert hard_neg_count > 0, f"{split_name} split has no hard negatives!"

# --- 2. Image-Quality Safety Gate ---

def test_quality_gate_rejects_pitch_black(inference_service):
    black_img = Image.new("RGB", (256, 256), color=(2, 2, 2))
    res = inference_service.predict(black_img)
    
    assert res["is_inconclusive"] is True
    assert res["predicted_class"] == "inconclusive"
    assert res["confidence"] == 0.0
    assert any("underexposed" in r.lower() or "darkness" in r.lower() for r in res["inconclusive_reasons"])
    assert any("inconclusive" in w.lower() for w in res["warnings"])

def test_quality_gate_rejects_severe_blur(inference_service):
    # Create structured scene (sky and road) then blur it heavily
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:128, :] = [220, 220, 220]
    arr[128:, :] = [40, 40, 40]
    base_img = Image.fromarray(arr)
    blurred_img = base_img.filter(ImageFilter.GaussianBlur(radius=25))
    
    res = inference_service.predict(blurred_img)
    assert res["is_inconclusive"] is True
    assert res["predicted_class"] == "inconclusive"
    assert any("blur" in r.lower() or "motion" in r.lower() for r in res["inconclusive_reasons"])

def test_quality_gate_rejects_low_resolution(inference_service):
    tiny_img = Image.new("RGB", (48, 48), color=(100, 150, 200))
    res = inference_service.predict(tiny_img)
    assert res["is_inconclusive"] is True
    assert res["predicted_class"] == "inconclusive"
    assert any("resolution" in r.lower() for r in res["inconclusive_reasons"])

def test_quality_gate_accepts_clear_image(inference_service):
    # Natural road-like pattern with sharp edges
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:128, :] = [80, 80, 80]     # asphalt
    arr[128:, :] = [200, 200, 200]  # concrete/curb
    arr[120:136, 60:80] = [255, 255, 0] # road stripe
    img = Image.fromarray(arr)
    
    res = inference_service.predict(img)
    assert res["is_inconclusive"] is False
    assert res["predicted_class"] in ["flooded", "not_flooded"]

# --- 3. Decision Engine Integration Safeguards ---

def test_decision_engine_inconclusive_safety():
    # If vision is inconclusive and no high rainfall, alert level cannot escalate to WARNING or EMERGENCY
    inp = DecisionInput(
        location_id="HYD-RD-099",
        road_name="Panjagutta Main Junction",
        vision_predicted_class="inconclusive",
        vision_confidence=0.0,
        vision_is_ambiguous=True,
        rainfall_risk_category="LOW",
        rainfall_risk_score=0.1,
        vulnerability_category="LOW",
        vulnerability_index=0.2,
        report_age_minutes=5.0,
        is_field_verified=False
    )
    decision = evaluate_decision(inp)
    assert decision.alert_level != AlertLevel.EMERGENCY
    assert decision.alert_level != AlertLevel.WARNING
    assert decision.is_actionable_for_crews is False
    assert any("inconclusive" in w.lower() for w in decision.warnings)
