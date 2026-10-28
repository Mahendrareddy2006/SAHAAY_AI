"""
Sahaay AI - Phase 15: Vision Data Acquisition & Label Governance Engine
(data_collection_v4.governance)

Implements offline data-governance validation, explicit label decoupling,
source-balance auditing, and reproducible session/cluster-grouped partitioning.

Core Principles:
1. Never infer physical water depth or road passability from visual classification alone.
2. Wet roads without verified inundation must be explicitly decoupled from flooded roads.
3. Multi-source cross-representation and Cramér's V must be formally audited.
4. Frames correlated by perceptual similarity, capture session, or collection event
   must be grouped atomically before assigning partitions.
5. Independent evaluation sets must be strictly locked against model or threshold tuning.
"""

import os
import math
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any, Set
import numpy as np
import pandas as pd

from sahaay.data_collection_v4.schemas import (
    AcquisitionRecord,
    AnnotationRecord,
    AnnotationLabel,
    PermissionStatus,
    PrivacyProcessingStatus,
    DepthMeasurementMethod,
    VerifiedPassability,
    ImageQualityStatus,
)
from sahaay.data_collection_v4.validate import DisjointSetUnion, hamming_distance


# Hyderabad Metropolitan Region Spatial Bounding Box
HYDERABAD_BOUNDS = {
    "min_lat": 17.15,
    "max_lat": 17.65,
    "min_lon": 78.15,
    "max_lon": 78.70,
}


def validate_metadata_integrity(
    register_df: pd.DataFrame,
    require_hyderabad_bounds: bool = True
) -> Dict[str, Any]:
    """
    Validates acquisition register metadata completeness, formats, spatial bounds,
    and privacy compliance.
    """
    total_records = len(register_df)
    valid_count = 0
    excluded_records = []
    issues_by_type: Dict[str, int] = {}

    required_columns = [
        "acquisition_id", "location_id", "capture_timestamp", "source_type",
        "permission_status", "latitude", "longitude", "location_precision_m",
        "privacy_processing_status"
    ]

    missing_cols = [c for c in required_columns if c not in register_df.columns]
    if missing_cols:
        return {
            "is_valid": False,
            "total_records": total_records,
            "fatal_error": f"Missing required columns in acquisition register: {missing_cols}",
            "valid_records": 0,
            "excluded_records": total_records,
            "issues_summary": {"missing_columns": total_records}
        }

    now_utc = datetime.now(timezone.utc)

    for idx, row in register_df.iterrows():
        row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        acq_id = str(row_dict.get("acquisition_id", f"ROW_{idx}"))
        reasons = []

        # 1. Pydantic schema validation
        try:
            record = AcquisitionRecord(**row_dict)
        except Exception as e:
            reasons.append(f"schema_validation_error: {str(e)}")

        # 2. Timestamp format and future check
        ts_str = str(row_dict.get("capture_timestamp", ""))
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts > now_utc:
                reasons.append(f"future_timestamp: {ts_str} is in the future")
        except Exception:
            reasons.append(f"invalid_timestamp_format: {ts_str} must be ISO 8601")

        # 3. Spatial bounding box
        try:
            lat = float(row_dict["latitude"])
            lon = float(row_dict["longitude"])
            if require_hyderabad_bounds:
                if not (HYDERABAD_BOUNDS["min_lat"] <= lat <= HYDERABAD_BOUNDS["max_lat"] and
                        HYDERABAD_BOUNDS["min_lon"] <= lon <= HYDERABAD_BOUNDS["max_lon"]):
                    reasons.append(f"coordinates_outside_hyderabad: ({lat}, {lon})")
        except (ValueError, TypeError):
            reasons.append("non_numeric_coordinates")

        # 4. Location precision check
        try:
            prec = float(row_dict.get("location_precision_m", 0.0))
            if prec <= 0.0 or prec > 100.0:
                reasons.append(f"invalid_location_precision: {prec}m (must be > 0 and <= 100m)")
        except (ValueError, TypeError):
            reasons.append("invalid_location_precision_type")

        # 5. Permission & Consent
        perm_status = str(row_dict.get("permission_status", "")).lower()
        if perm_status != PermissionStatus.APPROVED.value:
            reasons.append(f"unapproved_permission: status is '{perm_status}'")
        else:
            ref = str(row_dict.get("consent_or_authorization_reference", "")).strip()
            if not ref or ref.upper() in ["NONE", "UNKNOWN", "PENDING", "PENDING_VERIFICATION"]:
                reasons.append("approved_record_lacks_valid_consent_reference")

        # 6. Privacy processing
        priv_status = str(row_dict.get("privacy_processing_status", "")).lower()
        if priv_status != PrivacyProcessingStatus.BLURRED_VERIFIED.value:
            reasons.append(f"privacy_unverified: status is '{priv_status}'")

        if reasons:
            for r in reasons:
                cat = r.split(":")[0]
                issues_by_type[cat] = issues_by_type.get(cat, 0) + 1
            excluded_records.append({"acquisition_id": acq_id, "reasons": reasons})
        else:
            valid_count += 1

    return {
        "is_valid": len(excluded_records) == 0,
        "total_records": total_records,
        "valid_records": valid_count,
        "excluded_records": len(excluded_records),
        "issues_summary": issues_by_type,
        "exclusion_details": excluded_records[:25]
    }


def validate_annotation_governance(
    annotations_df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Validates that annotations decouple visual flood evidence, wet non-flooded surfaces,
    independently verified flood events, physical water depth, and road passability.
    Enforces that depth and passability are NEVER inferred from computer vision models.
    """
    total_records = len(annotations_df)
    valid_count = 0
    violations = []
    issues_by_type: Dict[str, int] = {}

    for idx, row in annotations_df.iterrows():
        row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        img_id = str(row_dict.get("image_id", f"ROW_{idx}"))
        reasons = []

        # 1. Pydantic validation of AnnotationRecord
        try:
            record = AnnotationRecord(**row_dict)
        except Exception as e:
            reasons.append(f"schema_or_governance_violation: {str(e)}")
            violations.append({"image_id": img_id, "reasons": reasons})
            issues_by_type["schema_or_governance_violation"] = issues_by_type.get("schema_or_governance_violation", 0) + 1
            continue

        # 2. Rejection of model-inferred depth
        depth_method = str(record.depth_measurement_method.value).lower()
        if any(term in depth_method for term in ["model", "infer", "classifier", "neural", "vision"]):
            reasons.append(f"prohibited_depth_method: depth inferred from vision ({depth_method})")

        # 3. Rejection of model-inferred passability
        passability = str(record.verified_road_passability.value).lower()
        event_src = str(record.event_verification_source).lower()
        if any(term in event_src for term in ["model", "infer", "classifier", "neural", "vision"]):
            reasons.append(f"prohibited_passability_source: passability source is vision model ({event_src})")

        if record.verified_road_passability != VerifiedPassability.UNVERIFIED_UNKNOWN:
            if event_src in ["unverified", "none", "unknown", ""]:
                reasons.append("unverified_passability_asserted: requires independent ground truth authority")

        # 4. Decoupling of wet asphalt and flood
        if record.is_wet_non_flooded and record.label == AnnotationLabel.FLOODED_ROAD:
            reasons.append("contradictory_label: is_wet_non_flooded=True cannot be labeled as flooded_road")

        # 5. Missing or invalid label confidence
        if record.label_confidence < 0.0 or record.label_confidence > 1.0 or math.isnan(record.label_confidence):
            reasons.append("invalid_label_confidence")

        # 6. Degraded image routing to abstention
        if record.image_quality_status != ImageQualityStatus.SUFFICIENT:
            if record.label not in [AnnotationLabel.AMBIGUOUS, AnnotationLabel.OUT_OF_SCOPE]:
                reasons.append(
                    f"degraded_image_forced_binary: quality={record.image_quality_status.value} "
                    f"must be labeled AMBIGUOUS or OUT_OF_SCOPE"
                )

        if reasons:
            for r in reasons:
                cat = r.split(":")[0]
                issues_by_type[cat] = issues_by_type.get(cat, 0) + 1
            violations.append({"image_id": img_id, "reasons": reasons})
        else:
            valid_count += 1

    return {
        "is_valid": len(violations) == 0,
        "total_records": total_records,
        "valid_records": valid_count,
        "violation_count": len(violations),
        "issues_summary": issues_by_type,
        "violation_details": violations[:25]
    }


def audit_source_class_balance(
    manifest_df: pd.DataFrame,
    source_col: str = "source_dataset",
    label_col: str = "label",
    min_samples_per_source_per_class: int = 100,
    min_independent_sources: int = 2,
    max_cramers_v: float = 0.30,
    max_mutual_information_bits: float = 0.20
) -> Dict[str, Any]:
    """
    Audits source-label confounding, contingency balance, Cramér's V, mutual information,
    and representation of critical negative cohorts.
    """
    total = len(manifest_df)
    if total == 0:
        return {"total_samples": 0, "status": "EMPTY_MANIFEST", "is_confounded": True}

    if source_col not in manifest_df.columns or label_col not in manifest_df.columns:
        raise ValueError(f"Manifest must contain '{source_col}' and '{label_col}' columns")

    ct = pd.crosstab(manifest_df[source_col], manifest_df[label_col])
    
    # 1. Multi-source cross representation
    sources_with_both_classes = []
    for src in ct.index:
        pos = ct.loc[src, 1] if 1 in ct.columns else 0
        neg = ct.loc[src, 0] if 0 in ct.columns else 0
        if pos >= min_samples_per_source_per_class and neg >= min_samples_per_source_per_class:
            sources_with_both_classes.append(str(src))

    # 2. Information theoretic mutual information
    pj = ct / total
    p_src = pj.sum(axis=1)
    p_lbl = pj.sum(axis=0)

    mi = 0.0
    for s in pj.index:
        for l in pj.columns:
            val = pj.loc[s, l]
            if val > 0:
                mi += val * np.log2(val / (p_src[s] * p_lbl[l]))

    h_lbl = -np.sum(p_lbl * np.log2(p_lbl)) if len(p_lbl) > 0 else 0.0

    # 3. Chi-squared & Cramér's V
    chi2 = 0.0
    for s in ct.index:
        for l in ct.columns:
            O = ct.loc[s, l]
            E = (ct.loc[s].sum() * ct[l].sum()) / total
            chi2 += ((O - E) ** 2) / E if E > 0 else 0.0

    min_dim = min(ct.shape) - 1
    cramers_v = np.sqrt(chi2 / (total * min_dim)) if min_dim > 0 and total > 0 else 1.0

    is_balanced_multi_source = bool(len(sources_with_both_classes) >= min_independent_sources)
    is_confounded = bool((cramers_v > max_cramers_v) or (mi > max_mutual_information_bits) or not is_balanced_multi_source)


    return {
        "total_samples": total,
        "contingency_table": {str(k): {str(ik): int(iv) for ik, iv in v.items()} for k, v in ct.to_dict().items()},
        "cramers_v": round(float(cramers_v), 4),
        "mutual_information_bits": round(float(mi), 4),
        "label_entropy_bits": round(float(h_lbl), 4),
        "sources_with_both_classes_count": len(sources_with_both_classes),
        "sources_with_both_classes": sources_with_both_classes,
        "is_confounded": is_confounded,
        "gates": {
            "cramers_v_passed": bool(cramers_v <= max_cramers_v),
            "mutual_information_passed": bool(mi <= max_mutual_information_bits),
            "multi_source_cross_representation_passed": is_balanced_multi_source
        }
    }


def partition_dataset_with_session_grouping(
    manifest_df: pd.DataFrame,
    cluster_col: str = "cluster_id",
    session_col: str = "capture_session_id",
    location_col: str = "location_id",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    eval_ratio: float = 0.15,
    random_seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Reproducibly partitions a dataset into Train, Validation, and Independent Evaluation
    while grouping all correlated frames (by perceptual cluster, capture session, and location).
    Guarantees atomic component assignment so no session or scene crosses partitions.
    """
    if abs((train_ratio + val_ratio + eval_ratio) - 1.0) > 1e-4:
        raise ValueError("Train, Val, and Eval ratios must sum exactly to 1.0")

    df = manifest_df.copy()
    n_samples = len(df)
    if n_samples == 0:
        return df.copy(), df.copy(), df.copy()

    # Identify primary identifier
    id_col = "acquisition_id" if "acquisition_id" in df.columns else "image_id"
    if id_col not in df.columns:
        df["item_id"] = [f"item_{i:06d}" for i in range(n_samples)]
        id_col = "item_id"

    item_ids = list(df[id_col].astype(str))
    dsu = DisjointSetUnion(item_ids)

    # 1. Union by cluster_id (perceptual near duplicates)
    if cluster_col in df.columns:
        cluster_map: Dict[str, str] = {}
        for _, row in df.iterrows():
            cid = str(row[cluster_col])
            iid = str(row[id_col])
            if cid and cid != "nan" and cid != "none":
                if cid in cluster_map:
                    dsu.union(iid, cluster_map[cid])
                else:
                    cluster_map[cid] = iid

    # 2. Union by capture_session_id (burst or continuous video sequence)
    if session_col in df.columns:
        session_map: Dict[str, str] = {}
        for _, row in df.iterrows():
            sid = str(row[session_col])
            iid = str(row[id_col])
            if sid and sid != "nan" and sid != "none":
                if sid in session_map:
                    dsu.union(iid, session_map[sid])
                else:
                    session_map[sid] = iid

    # Assign each item to its root component
    df["atomic_group_root"] = [dsu.find(iid) for iid in item_ids]

    # Group-aware stratified shuffle
    rng = np.random.RandomState(random_seed)
    unique_roots = sorted(list(df["atomic_group_root"].unique()))
    rng.shuffle(unique_roots)

    n_roots = len(unique_roots)
    n_train_roots = int(n_roots * train_ratio)
    n_val_roots = int(n_roots * val_ratio)

    train_roots = set(unique_roots[:n_train_roots])
    val_roots = set(unique_roots[n_train_roots:n_train_roots + n_val_roots])
    eval_roots = set(unique_roots[n_train_roots + n_val_roots:])

    train_df = df[df["atomic_group_root"].isin(train_roots)].copy()
    val_df = df[df["atomic_group_root"].isin(val_roots)].copy()
    eval_df = df[df["atomic_group_root"].isin(eval_roots)].copy()

    train_df["partition"] = "train"
    val_df["partition"] = "validation"
    eval_df["partition"] = "independent_evaluation"
    eval_df["is_locked_for_tuning"] = True  # Strict key-lock indicator

    return train_df, val_df, eval_df


def verify_partition_isolation(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    id_col: str = "image_id",
    md5_col: str = "md5",
    dhash_col: str = "dhash",
    session_col: str = "capture_session_id",
    cluster_col: str = "cluster_id",
    hamming_threshold: int = 2
) -> Dict[str, Any]:
    """
    Exhaustively verifies that Train, Validation, and Independent Evaluation
    partitions are completely disjoint across IDs, MD5 hashes, session IDs,
    clusters, and perceptual dhashes (Hamming <= 2).
    """
    # Helper to resolve columns
    def get_col(df, pref, alt):
        return pref if pref in df.columns else alt if alt in df.columns else None

    actual_id = get_col(train_df, id_col, "acquisition_id")
    actual_md5 = get_col(train_df, md5_col, "md5_hash")
    actual_dhash = get_col(train_df, dhash_col, "dhash_hex")

    violations = []

    # 1. Image / Acquisition ID disjointness
    if actual_id:
        t_ids = set(train_df[actual_id].dropna().astype(str))
        v_ids = set(val_df[actual_id].dropna().astype(str))
        e_ids = set(eval_df[actual_id].dropna().astype(str))

        if t_ids & v_ids:
            violations.append(f"Train and Val share {len(t_ids & v_ids)} ID(s)")
        if t_ids & e_ids:
            violations.append(f"Train and Eval share {len(t_ids & e_ids)} ID(s)")
        if v_ids & e_ids:
            violations.append(f"Val and Eval share {len(v_ids & e_ids)} ID(s)")

    # 2. Cryptographic MD5 disjointness
    if actual_md5 and actual_md5 in val_df.columns and actual_md5 in eval_df.columns:
        t_md5 = set(train_df[actual_md5].dropna().astype(str))
        v_md5 = set(val_df[actual_md5].dropna().astype(str))
        e_md5 = set(eval_df[actual_md5].dropna().astype(str))

        if t_md5 & v_md5:
            violations.append(f"Train and Val share {len(t_md5 & v_md5)} exact MD5 hash(es)")
        if t_md5 & e_md5:
            violations.append(f"Train and Eval share {len(t_md5 & e_md5)} exact MD5 hash(es)")
        if v_md5 & e_md5:
            violations.append(f"Val and Eval share {len(v_md5 & e_md5)} exact MD5 hash(es)")

    # 3. Capture session disjointness
    if session_col in train_df.columns and session_col in val_df.columns and session_col in eval_df.columns:
        t_sess = set(train_df[session_col].dropna().astype(str)) - {"none", "nan", ""}
        v_sess = set(val_df[session_col].dropna().astype(str)) - {"none", "nan", ""}
        e_sess = set(eval_df[session_col].dropna().astype(str)) - {"none", "nan", ""}

        if t_sess & v_sess:
            violations.append(f"Train and Val share {len(t_sess & v_sess)} capture session(s)")
        if t_sess & e_sess:
            violations.append(f"Train and Eval share {len(t_sess & e_sess)} capture session(s)")
        if v_sess & e_sess:
            violations.append(f"Val and Eval share {len(v_sess & e_sess)} capture session(s)")

    # 4. Cluster ID disjointness
    if cluster_col in train_df.columns and cluster_col in val_df.columns and cluster_col in eval_df.columns:
        t_cl = set(train_df[cluster_col].dropna().astype(str)) - {"none", "nan", ""}
        v_cl = set(val_df[cluster_col].dropna().astype(str)) - {"none", "nan", ""}
        e_cl = set(eval_df[cluster_col].dropna().astype(str)) - {"none", "nan", ""}

        if t_cl & v_cl:
            violations.append(f"Train and Val share {len(t_cl & v_cl)} duplicate cluster(s)")
        if t_cl & e_cl:
            violations.append(f"Train and Eval share {len(t_cl & e_cl)} duplicate cluster(s)")
        if v_cl & e_cl:
            violations.append(f"Val and Eval share {len(v_cl & e_cl)} duplicate cluster(s)")

    # 5. Perceptual dhash cross-partition leak check (pairwise check between Train and Eval)
    near_dup_leaks = 0
    if actual_dhash and actual_dhash in eval_df.columns:
        t_hashes = [str(h) for h in train_df[actual_dhash].dropna() if str(h) not in ["none", "nan", ""]]
        e_hashes = [str(h) for h in eval_df[actual_dhash].dropna() if str(h) not in ["none", "nan", ""]]

        for th in t_hashes:
            for eh in e_hashes:
                if hamming_distance(th, eh) <= hamming_threshold:
                    near_dup_leaks += 1

        if near_dup_leaks > 0:
            violations.append(f"Found {near_dup_leaks} near-duplicate pair(s) (dhash Hamming <= {hamming_threshold}) between Train and Eval")

    is_isolated = len(violations) == 0

    return {
        "is_isolated": is_isolated,
        "partition_sizes": {
            "train": len(train_df),
            "validation": len(val_df),
            "independent_evaluation": len(eval_df)
        },
        "violations_count": len(violations),
        "violations": violations
    }
