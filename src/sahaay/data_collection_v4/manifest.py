"""
Sahaay AI - Manifest Generation & Split Isolation Engine (data_collection_v4)

Constructs eligible training and evaluation manifests, isolates non-semantic metadata from model inputs,
preserves ambiguous/out-of-scope instances for abstention evaluation, and performs grouped splitting.
"""

import os
import json
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd


def isolate_semantic_model_inputs(
    manifest_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separates the manifest into:
    1. clean_model_manifest: Contains strictly semantic fields (image_id, file_path, label, cluster_id, group_id).
       Prevents models from accidentally reading camera_id, source_owner, resolution, or file size.
    2. provenance_audit_manifest: Retains full acquisition metadata for compliance, audit, and post-hoc stratification.
    """
    clean_columns = ["image_id", "file_path", "label", "class_name", "cluster_id", "group_id"]
    available_clean_cols = [c for c in clean_columns if c in manifest_df.columns]

    clean_manifest = manifest_df[available_clean_cols].copy()
    provenance_manifest = manifest_df.copy()

    return clean_manifest, provenance_manifest


def group_aware_split(
    manifest_df: pd.DataFrame,
    group_col: str = "cluster_id",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Splits manifest into Train, Val, and Test ensuring that no atomic group
    (e.g., cluster_id, capture_event_id, or location_id) is divided across splits.
    """
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-4:
        raise ValueError("Split ratios must sum to 1.0")

    rng = np.random.RandomState(random_seed)
    unique_groups = sorted(list(manifest_df[group_col].unique()))
    rng.shuffle(unique_groups)

    n_groups = len(unique_groups)
    n_train = int(n_groups * train_ratio)
    n_val = int(n_groups * val_ratio)

    train_groups = set(unique_groups[:n_train])
    val_groups = set(unique_groups[n_train:n_train + n_val])
    test_groups = set(unique_groups[n_train + n_val:])

    train_df = manifest_df[manifest_df[group_col].isin(train_groups)].copy()
    val_df = manifest_df[manifest_df[group_col].isin(val_groups)].copy()
    test_df = manifest_df[manifest_df[group_col].isin(test_groups)].copy()

    train_df["split"] = "train"
    val_df["split"] = "val"
    test_df["split"] = "test"

    return train_df, val_df, test_df


def handle_ambiguous_and_out_of_scope(
    annotations_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separates standard binary classification examples (flooded_road vs non-flooded road)
    from ambiguous and out-of-scope instances.
    
    Ensures ambiguous and out-of-scope examples are NEVER silently forced into positive/negative
    classes, but are preserved for abstention and image-quality safety evaluation.
    """
    binary_mask = annotations_df["label"].isin(["flooded_road", "dry_road", "wet_no_visible_inundation"])
    abstention_mask = annotations_df["label"].isin(["ambiguous", "out_of_scope"])

    binary_cohort = annotations_df[binary_mask].copy()
    abstention_cohort = annotations_df[abstention_mask].copy()

    return binary_cohort, abstention_cohort
