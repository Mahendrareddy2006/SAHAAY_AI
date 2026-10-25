"""
Unit and integration test suite for Sahaay AI Phase 9:
Split Integrity, Transitive Duplicate Clustering, Row-Reorder Invariance,
Metadata Shortcut Diagnostics, and Gated Vision Model Semantics.
"""

import os
import json
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from sahaay.data_collection_v4.validate import (
    DisjointSetUnion,
    cluster_perceptual_duplicates_exhaustive,
    hamming_distance,
)
from sahaay.data_collection_v4.manifest import (
    group_aware_split,
    isolate_semantic_model_inputs,
    handle_ambiguous_and_out_of_scope,
)


# ==============================================================================
# 1. Adversarial Duplicate Clustering & Transitive Chain Tests
# ==============================================================================

def test_exhaustive_clustering_transitive_chains():
    """
    Adversarial test for transitive duplicate chains:
    Image A is near-duplicate to B (h=1), B is near-duplicate to C (h=2).
    Direct distance between A and C is h=3 (> threshold of 2).
    Union-Find must transitively unify A, B, and C into the exact same cluster.
    """
    # 64-bit hex difference hashes
    hash_a = "0000000000000000"
    hash_b = "0000000000000001"  # dist(A, B) = 1 (bit 0 diff)
    hash_c = "0000000000000007"  # dist(B, C) = 2 (bits 1,2 diff), dist(A, C) = 3 (bits 0,1,2 diff)

    assert hamming_distance(hash_a, hash_b) == 1
    assert hamming_distance(hash_b, hash_c) == 2
    assert hamming_distance(hash_a, hash_c) == 3  # > threshold 2

    records = [
        {"acquisition_id": "CHAIN_A", "dhash": hash_a, "md5": "md5_a"},
        {"acquisition_id": "CHAIN_B", "dhash": hash_b, "md5": "md5_b"},
        {"acquisition_id": "CHAIN_C", "dhash": hash_c, "md5": "md5_c"},
    ]

    clusters = cluster_perceptual_duplicates_exhaustive(records, hamming_threshold=2)

    assert clusters["CHAIN_A"] == clusters["CHAIN_B"]
    assert clusters["CHAIN_B"] == clusters["CHAIN_C"]
    assert clusters["CHAIN_A"] == clusters["CHAIN_C"], (
        "Transitive duplicate clustering failed to group chain A-B-C into the same cluster!"
    )


def test_clustering_distant_duplicate_pairs_defeats_windowing():
    """
    Verifies that duplicate pairs separated by 1,000 distinct items in the manifest
    are unified into the same cluster without any sliding window boundary limitation.
    """
    records = []
    target_hash = "abcdef0123456789"

    records.append({"acquisition_id": "DISTANT_FIRST", "dhash": target_hash, "md5": "md5_first"})

    # 1,000 intervening distinct items
    for i in range(1, 1001):
        # Generate hash with large distance
        diff_hash = f"{i:016x}"
        records.append({"acquisition_id": f"INTERVENING_{i:04d}", "dhash": diff_hash, "md5": f"md5_{i}"})

    records.append({"acquisition_id": "DISTANT_LAST", "dhash": target_hash, "md5": "md5_last"})

    clusters = cluster_perceptual_duplicates_exhaustive(records, hamming_threshold=2)

    assert clusters["DISTANT_FIRST"] == clusters["DISTANT_LAST"], (
        "Exhaustive clustering failed to group distant duplicates across 1,000 intervening records!"
    )


# ==============================================================================
# 2. Split Invariance & Determinism Tests
# ==============================================================================

def test_group_aware_split_row_reorder_invariance():
    """
    Verifies that group_aware_split produces strictly identical partition allocations
    even if the input DataFrame rows are randomly shuffled prior to splitting.
    """
    # 50 clusters of 4 images each = 200 rows
    rows = []
    for c_idx in range(50):
        c_id = f"CLUSTER_{c_idx:03d}"
        for i_idx in range(4):
            rows.append({
                "image_id": f"IMG_{c_idx:03d}_{i_idx}",
                "cluster_id": c_id,
                "label": c_idx % 2
            })

    df_original = pd.DataFrame(rows)

    # Shuffled version
    df_shuffled = df_original.sample(frac=1.0, random_state=777).reset_index(drop=True)

    tr1, val1, te1 = group_aware_split(df_original, group_col="cluster_id", random_seed=42)
    tr2, val2, te2 = group_aware_split(df_shuffled, group_col="cluster_id", random_seed=42)

    assert set(tr1["cluster_id"]) == set(tr2["cluster_id"]), "Train clusters differ after row shuffle!"
    assert set(val1["cluster_id"]) == set(val2["cluster_id"]), "Val clusters differ after row shuffle!"
    assert set(te1["cluster_id"]) == set(te2["cluster_id"]), "Test clusters differ after row shuffle!"


def test_group_aware_split_cluster_atomicity():
    """Verifies that no cluster spans across multiple split partitions."""
    df = pd.DataFrame({
        "image_id": [f"img_{i}" for i in range(120)],
        "cluster_id": [f"cluster_{i // 6}" for i in range(120)],  # 20 clusters of 6 images
        "label": [i % 2 for i in range(120)],
    })

    tr, val, te = group_aware_split(df, group_col="cluster_id", random_seed=42)

    tr_clusters = set(tr["cluster_id"])
    val_clusters = set(val["cluster_id"])
    te_clusters = set(te["cluster_id"])

    assert len(tr_clusters & val_clusters) == 0, "Cluster leak between Train and Val!"
    assert len(tr_clusters & te_clusters) == 0, "Cluster leak between Train and Test!"
    assert len(val_clusters & te_clusters) == 0, "Cluster leak between Val and Test!"


# ==============================================================================
# 3. Manifest V4 Forensic Disjointness Tests
# ==============================================================================

def test_manifest_v4_zero_leakage_and_cross_split_hamming_ceiling():
    """Asserts that Manifest V4 has zero ID/MD5/cluster leakage and min cross-split Hamming dist >= 3."""
    report_p = Path("reports/phase9/split_integrity_report.json")
    assert report_p.exists(), "split_integrity_report.json must exist"

    with open(report_p, "r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["disjointness_audit"]["exact_overlap_detected"] is False
    assert rep["perceptual_hash_audit"]["cross_split_near_duplicate_pairs_h_le_2"] == 0
    assert rep["perceptual_hash_audit"]["minimum_cross_split_hamming_distances"]["test_vs_train"] >= 3
    assert rep["perceptual_hash_audit"]["minimum_cross_split_hamming_distances"]["test_vs_val"] >= 3
    assert rep["cluster_atomicity"]["all_clusters_strictly_partitioned"] is True
    assert rep["historical_v3_leak_resolution"]["all_historical_leaks_cured"] is True


# ==============================================================================
# 4. Source-Label Confounding & Metadata Shortcut Tests
# ==============================================================================

def test_metadata_shortcut_results_and_contingency_audit():
    """Asserts that source confounding is quantified and metadata baseline predicts label with >80% accuracy."""
    report_p = Path("reports/phase9/metadata_shortcut_results.json")
    assert report_p.exists(), "metadata_shortcut_results.json must exist"

    with open(report_p, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Contingency table checks
    assert data["contingency_analysis"]["source_dataset_collinear_with_label"] is True
    assert data["contingency_analysis"]["cramers_v"] == 1.0
    assert data["contingency_analysis"]["mutual_information_bits"] == 1.0
    assert data["contingency_analysis"]["contingency_gate_status"] == "FAILED_EXTREME_CONFOUNDING"

    # Non-semantic metadata diagnostic performance
    rf_acc = data["models"]["random_forest_metadata"]["test_accuracy"]
    rf_auc = data["models"]["random_forest_metadata"]["test_roc_auc"]
    assert rf_acc >= 0.80, f"Expected metadata accuracy >= 0.80, got {rf_acc}"
    assert rf_auc >= 0.85, f"Expected metadata AUC >= 0.85, got {rf_auc}"


def test_source_class_matrix_collinearity():
    """Asserts that source_class_matrix.csv reflects zero multi-class sources in V4."""
    matrix_p = Path("reports/phase9/source_class_matrix.csv")
    assert matrix_p.exists(), "source_class_matrix.csv must exist"

    df = pd.read_csv(matrix_p)
    for _, row in df.iterrows():
        source = row["source_dataset"]
        ratio = row["flood_ratio"]
        if source == "clemson_flood":
            assert ratio == 1.0, "Clemson flood must be 100% positive"
        elif "virenbr11" in source:
            assert ratio == 0.0, "Virenbr11 must be 100% negative"


# ==============================================================================
# 5. Model Safety Semantics & Gated Production Training Status
# ==============================================================================

def test_vision_v4_production_training_remains_not_run():
    """Asserts that production Vision V4 training is marked NOT_RUN with explicit blocking reasons."""
    results_p = Path("reports/phase9/experiment_results.json")
    assert results_p.exists(), "experiment_results.json must exist"

    with open(results_p, "r", encoding="utf-8") as f:
        exp = json.load(f)

    track_c = exp["tracks"]["track_c_production_training_readiness"]
    assert track_c["experiment_status"] == "NOT_RUN"
    assert track_c["decision_verdict"] == "NO-GO FOR PRODUCTION VISION V4 TRAINING"
    assert len(track_c["blocking_gates"]) == 4

    # Verify safety contracts
    safety = exp["model_safety_contract_adherence"]
    assert safety["advisory_only_classification"] is True
    assert safety["autonomous_road_closure_prohibited"] is True
    assert safety["autonomous_emergency_dispatch_prohibited"] is True

    expected_states = [
        "FLOOD_EVIDENCE_DETECTED",
        "NO_CURRENT_FLOOD_EVIDENCE",
        "INCONCLUSIVE",
        "INSUFFICIENT_OR_STALE_DATA",
        "HUMAN_VERIFICATION_REQUIRED",
    ]
    assert safety["vision_abstention_states"] == expected_states
