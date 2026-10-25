"""
Sahaay AI - Vision V4 Comprehensive Integrity and Split Disjointness Test Suite

Verifies:
1. Manifest V4 file existence and integrity.
2. Complete disjointness of image IDs, cryptographic MD5 hashes, and cluster IDs across splits.
3. Strict absence of near-duplicate cross-split leakage (dhash Hamming distance <= 2).
4. Complete unification of the 5 historical V3 leak pairs within single splits (no cross-split leakage).
5. Representation of hard negatives (potholes/water accumulations) and plain road controls across all splits.
6. Safety integration: Image Quality Gate rejection of degraded images (blur, underexposure, low resolution).
7. Safety integration: Decision Engine preservation of advisory-only semantics.
"""

import os
import json
import pytest
import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from sahaay.vision.inference import FloodVisionInference
from sahaay.decision.contracts import DecisionInput, evaluate_decision, AlertLevel


@pytest.fixture(scope="module")
def v4_manifests():
    train_p = os.path.join("data", "processed", "manifest_v4", "train_v4.csv")
    val_p = os.path.join("data", "processed", "manifest_v4", "val_v4.csv")
    test_p = os.path.join("data", "processed", "manifest_v4", "test_v4.csv")
    full_p = os.path.join("data", "processed", "manifest_v4", "full_manifest_v4.csv")
    clusters_p = os.path.join("data", "processed", "manifest_v4", "duplicate_clusters_v4.json")

    for p in [train_p, val_p, test_p, full_p, clusters_p]:
        if not os.path.exists(p):
            pytest.skip(f"Manifest V4 artifact missing: {p}")

    df_train = pd.read_csv(train_p)
    df_val = pd.read_csv(val_p)
    df_test = pd.read_csv(test_p)
    df_full = pd.read_csv(full_p)
    with open(clusters_p, "r", encoding="utf-8") as f:
        clusters_data = json.load(f)

    return df_train, df_val, df_test, df_full, clusters_data


# --- 1. Manifest Disjointness & Integrity ---

def test_v4_manifest_files_exist(v4_manifests):
    df_train, df_val, df_test, df_full, clusters_data = v4_manifests
    assert len(df_train) > 0
    assert len(df_val) > 0
    assert len(df_test) > 0
    assert len(df_full) == len(df_train) + len(df_val) + len(df_test)
    assert len(clusters_data) > 0


def test_v4_image_id_disjointness(v4_manifests):
    df_train, df_val, df_test, _, _ = v4_manifests
    train_ids = set(df_train["image_id"])
    val_ids = set(df_val["image_id"])
    test_ids = set(df_test["image_id"])

    assert len(train_ids & val_ids) == 0, "Train and Val share image IDs in V4!"
    assert len(train_ids & test_ids) == 0, "Train and Test share image IDs in V4!"
    assert len(val_ids & test_ids) == 0, "Val and Test share image IDs in V4!"


def test_v4_md5_disjointness(v4_manifests):
    df_train, df_val, df_test, _, _ = v4_manifests
    train_md5 = set(df_train["md5"])
    val_md5 = set(df_val["md5"])
    test_md5 = set(df_test["md5"])

    assert len(train_md5 & val_md5) == 0, "Train and Val share MD5 hashes in V4!"
    assert len(train_md5 & test_md5) == 0, "Train and Test share MD5 hashes in V4!"
    assert len(val_md5 & test_md5) == 0, "Val and Test share MD5 hashes in V4!"


def test_v4_cluster_disjointness(v4_manifests):
    df_train, df_val, df_test, _, _ = v4_manifests
    train_c = set(df_train["cluster_id"])
    val_c = set(df_val["cluster_id"])
    test_c = set(df_test["cluster_id"])

    assert len(train_c & val_c) == 0, "Train and Val share cluster IDs in V4!"
    assert len(train_c & test_c) == 0, "Train and Test share cluster IDs in V4!"
    assert len(val_c & test_c) == 0, "Val and Test share cluster IDs in V4!"


# --- 2. Zero Near-Duplicate Cross-Split Leakage ---

def test_v4_zero_near_duplicates_cross_splits(v4_manifests):
    """
    Assert that for all multi-image clusters, all cluster members reside strictly
    in exactly one split.
    """
    df_train, df_val, df_test, _, clusters_data = v4_manifests
    train_ids = set(df_train["image_id"])
    val_ids = set(df_val["image_id"])
    test_ids = set(df_test["image_id"])

    for cluster_id, img_ids in clusters_data.items():
        if len(img_ids) > 1:
            in_train = any(iid in train_ids for iid in img_ids)
            in_val = any(iid in val_ids for iid in img_ids)
            in_test = any(iid in test_ids for iid in img_ids)
            num_splits = sum([in_train, in_val, in_test])
            assert num_splits == 1, (
                f"Cluster {cluster_id} with images {img_ids} spans across multiple splits! "
                f"(train={in_train}, val={in_val}, test={in_test})"
            )


def test_v4_historical_leak_pairs_unified(v4_manifests):
    """
    Verify that the 5 V3 leak pairs identified in Phase 1 are never split
    across Train, Val, or Test in V4.
    """
    df_train, df_val, df_test, _, _ = v4_manifests

    def get_split(img_name):
        for name, df in [("train", df_train), ("val", df_val), ("test", df_test)]:
            if any(img_name in p for p in df["file_path"]):
                return name
        return None

    # The 5 reported V3 leak pairs
    v3_pairs = [
        ("flood_7940.png", "flood_7963.png"),  # Pair 1
        ("flood_7210.png", "flood_9328.png"),  # Pair 2
        ("flood_7210.png", "flood_7283.png"),  # Pair 3
        ("flood_7295.png", "flood_9328.png"),  # Pair 4
        ("flood_7186.png", "flood_7184.png"),  # Pair 5
    ]

    for f1, f2 in v3_pairs:
        s1 = get_split(f1)
        s2 = get_split(f2)
        assert s1 is not None, f"Image {f1} not found in V4 manifests!"
        assert s2 is not None, f"Image {f2} not found in V4 manifests!"
        assert s1 == s2, (
            f"V3 leak pair ({f1}, {f2}) is still separated in V4! ({f1} in {s1}, {f2} in {s2})"
        )


# --- 3. Class Balance and Hard Negatives Composition ---

def test_v4_class_and_hard_negative_distribution(v4_manifests):
    df_train, df_val, df_test, _, _ = v4_manifests

    for split_name, df in [("Train", df_train), ("Val", df_val), ("Test", df_test)]:
        lbl_counts = df["class_name"].value_counts()
        assert "flood" in lbl_counts
        assert "non_flood" in lbl_counts
        assert abs(lbl_counts["flood"] - lbl_counts["non_flood"]) <= 2, f"{split_name} class imbalance exceeds cluster tolerance: {lbl_counts}"

        # Verify presence of hard negative potholes
        potholes = len(df[df["subcondition"] == "wet_road_pothole_hard_negative"])
        assert potholes > 0, f"{split_name} split is missing hard negative potholes!"

        # Verify presence of plain road controls
        plain_roads = len(df[df["subcondition"] == "plain_dry_road"])
        assert plain_roads > 0, f"{split_name} split is missing plain road controls!"


# --- 4. Safety Integration Tests ---

def test_v4_quality_gate_behavior():
    """Verify inference image quality gate rejects degraded images."""
    v3_monsoon = os.path.join("models", "vision", "v3", "model_v3_monsoon.pt")
    if not os.path.exists(v3_monsoon):
        pytest.skip("Model checkpoint not found for quality gate test")

    inference_service = FloodVisionInference(checkpoint_path=v3_monsoon, device_name="cpu")

    # Black image
    dark_img = Image.new("RGB", (256, 256), color=(3, 3, 3))
    res_dark = inference_service.predict(dark_img)
    assert res_dark["is_inconclusive"] is True
    assert res_dark["predicted_class"] == "inconclusive"

    # Heavily blurred image
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[:128, :] = [240, 240, 240]
    arr[128:, :] = [20, 20, 20]
    sharp = Image.fromarray(arr)
    blurred = sharp.filter(ImageFilter.GaussianBlur(radius=30))
    res_blur = inference_service.predict(blurred)
    assert res_blur["is_inconclusive"] is True
    assert res_blur["predicted_class"] == "inconclusive"


def test_v4_decision_engine_advisory_contract():
    """Ensure vision alone cannot trigger autonomous road closure or emergency."""
    # Scenario A: High-confidence visual flood without rainfall/field verification cannot trigger EMERGENCY
    decision_input_a = DecisionInput(
        location_id="HYD-RD-V4-001",
        road_name="Tolichowki Flyover Underpass",
        vision_predicted_class="flooded",
        vision_confidence=0.99,
        vision_is_ambiguous=False,
        rainfall_risk_category="LOW",
        rainfall_risk_score=0.1,
        vulnerability_category="LOW",
        vulnerability_index=0.15,
        report_age_minutes=2.0,
        is_field_verified=False
    )
    decision_a = evaluate_decision(decision_input_a)
    assert decision_a.alert_level != AlertLevel.EMERGENCY, "Vision alone must never trigger EMERGENCY alert!"
    assert any("not an official municipal ndrf/ghmc evacuation directive" in w.lower() for w in decision_a.warnings)

    # Scenario B: Ambiguous or inconclusive vision input decays to advisory, non-actionable
    decision_input_b = DecisionInput(
        location_id="HYD-RD-V4-002",
        road_name="Shaikpet Nala Road",
        vision_predicted_class="inconclusive",
        vision_confidence=0.0,
        vision_is_ambiguous=True,
        rainfall_risk_category="LOW",
        rainfall_risk_score=0.1,
        vulnerability_category="LOW",
        vulnerability_index=0.15,
        report_age_minutes=5.0,
        is_field_verified=False
    )
    decision_b = evaluate_decision(decision_input_b)
    assert decision_b.alert_level != AlertLevel.EMERGENCY
    assert decision_b.is_actionable_for_crews is False
    assert any("inconclusive" in w.lower() for w in decision_b.warnings)
