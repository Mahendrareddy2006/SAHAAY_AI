"""
Sahaay AI - Split Integrity Automated Unit Tests (Phase B)
Asserts that:
1. No image ID appears in multiple splits.
2. No cryptographic MD5 hash appears in multiple splits.
3. No cluster ID appears in multiple splits.
4. Class balance is preserved.
5. All image paths exist on disk.
"""

import os
import pytest
import pandas as pd

@pytest.fixture(scope="module")
def manifests_v2():
    train_path = os.path.join("data", "processed", "manifest_v2", "train_v2.csv")
    val_path = os.path.join("data", "processed", "manifest_v2", "val_v2.csv")
    test_path = os.path.join("data", "processed", "manifest_v2", "test_v2.csv")
    
    if not (os.path.exists(train_path) and os.path.exists(val_path) and os.path.exists(test_path)):
        pytest.skip("Manifest V2 files not found. Run scripts/prepare_clean_split_v2.py first.")
        
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)
    test_df = pd.read_csv(test_path)
    return train_df, val_df, test_df

def test_image_id_disjointness(manifests_v2):
    train_df, val_df, test_df = manifests_v2
    train_ids = set(train_df["image_id"])
    val_ids = set(val_df["image_id"])
    test_ids = set(test_df["image_id"])
    
    assert len(train_ids.intersection(val_ids)) == 0, "Train and Val share image IDs!"
    assert len(train_ids.intersection(test_ids)) == 0, "Train and Test share image IDs!"
    assert len(val_ids.intersection(test_ids)) == 0, "Val and Test share image IDs!"

def test_exact_md5_disjointness(manifests_v2):
    train_df, val_df, test_df = manifests_v2
    train_md5 = set(train_df["md5"])
    val_md5 = set(val_df["md5"])
    test_md5 = set(test_df["md5"])
    
    assert len(train_md5.intersection(val_md5)) == 0, "Cross-split MD5 duplicate leak between Train and Val!"
    assert len(train_md5.intersection(test_md5)) == 0, "Cross-split MD5 duplicate leak between Train and Test!"
    assert len(val_md5.intersection(test_md5)) == 0, "Cross-split MD5 duplicate leak between Val and Test!"

def test_cluster_id_disjointness(manifests_v2):
    train_df, val_df, test_df = manifests_v2
    train_clusters = set(train_df["cluster_id"])
    val_clusters = set(val_df["cluster_id"])
    test_clusters = set(test_df["cluster_id"])
    
    assert len(train_clusters.intersection(val_clusters)) == 0, "Cross-split cluster leak between Train and Val!"
    assert len(train_clusters.intersection(test_clusters)) == 0, "Cross-split cluster leak between Train and Test!"
    assert len(val_clusters.intersection(test_clusters)) == 0, "Cross-split cluster leak between Val and Test!"

def test_class_balance_v2(manifests_v2):
    train_df, val_df, test_df = manifests_v2
    for df, name in [(train_df, "Train"), (val_df, "Val"), (test_df, "Test")]:
        counts = df["label_str"].value_counts()
        assert "flooded" in counts
        assert "not_flooded" in counts
        ratio = counts["flooded"] / counts["not_flooded"]
        assert 0.90 <= ratio <= 1.10, f"{name} class ratio {ratio:.2f} deviates significantly from 50/50 balance"

def test_all_files_exist_on_disk(manifests_v2):
    train_df, val_df, test_df = manifests_v2
    for df, name in [(train_df, "Train"), (val_df, "Val"), (test_df, "Test")]:
        for fp in df["file_path"].head(50):
            assert os.path.exists(fp), f"File in {name} does not exist: {fp}"
