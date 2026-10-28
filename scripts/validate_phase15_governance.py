"""
Phase 15: Vision Data Acquisition & Label Governance Verification Runner
(scripts/validate_phase15_governance.py)

Executes offline validation checks for:
1. Metadata integrity and geographic bounding box (Hyderabad Metropolitan Area).
2. Annotation field decoupling (visible evidence vs wet road vs physical depth vs passability).
3. Rejection of model-inferred depth and model-inferred passability.
4. Source-class balance and Cramér's V on Manifest V4.
5. Reproducible session/cluster-grouped partitioning with zero cross-partition leakage.
6. Verification of partition isolation across IDs, MD5s, sessions, clusters, and dhashes.

Writes summary output strictly to reports/phase15/phase15_governance_validation_results.json
"""

import os
import sys
import json
import hashlib
import pandas as pd

from sahaay.data_collection_v4.governance import (
    validate_metadata_integrity,
    validate_annotation_governance,
    audit_source_class_balance,
    partition_dataset_with_session_grouping,
    verify_partition_isolation,
    HYDERABAD_BOUNDS,
)


def run_phase15_validation() -> dict:
    print("=" * 80)
    print("SAHAAY AI — PHASE 15: VISION DATA ACQUISITION & GOVERNANCE VALIDATION")
    print("=" * 80)

    os.makedirs("reports/phase15", exist_ok=True)
    results = {
        "audit_phase": "Phase 15",
        "title": "Vision Acquisition and Label Governance Verification",
        "checks": {}
    }

    # 1. Validate Acquisition Register Metadata
    acq_path = "data/collection_v4/acquisition_register.csv"
    print("\n[1/5] Validating Acquisition Register Metadata Integrity...")
    if os.path.exists(acq_path):
        acq_df = pd.read_csv(acq_path)
        meta_res = validate_metadata_integrity(acq_df, require_hyderabad_bounds=True)
        results["checks"]["metadata_integrity"] = meta_res
        print(f"  Total records audited: {meta_res['total_records']}")
        print(f"  Valid records: {meta_res['valid_records']} | Excluded: {meta_res['excluded_records']}")
        print(f"  Issues identified: {meta_res['issues_summary']}")
    else:
        results["checks"]["metadata_integrity"] = {"error": f"File not found: {acq_path}"}
        print(f"  Error: {acq_path} not found")

    # 2. Validate Annotation Decoupling & Governance
    ann_path = "data/collection_v4/governance_annotation_template.csv"
    print("\n[2/5] Validating Annotation Field Decoupling & Governance...")
    if os.path.exists(ann_path):
        ann_df = pd.read_csv(ann_path)
        ann_res = validate_annotation_governance(ann_df)
        results["checks"]["annotation_governance"] = ann_res
        print(f"  Total annotations audited: {ann_res['total_records']}")
        print(f"  Valid annotations: {ann_res['valid_records']} | Violations: {ann_res['violation_count']}")
        print(f"  Issues identified: {ann_res['issues_summary']}")
    else:
        results["checks"]["annotation_governance"] = {"error": f"File not found: {ann_path}"}
        print(f"  Error: {ann_path} not found")

    # 3. Source-Class Balance & Confounding Audit on Manifest V4
    manifest_v4_path = "data/processed/manifest_v4/full_manifest_v4.csv"
    print("\n[3/5] Auditing Source-Class Balance & Confounding on Manifest V4...")
    if os.path.exists(manifest_v4_path):
        m4_df = pd.read_csv(manifest_v4_path)
        sc_res = audit_source_class_balance(m4_df)
        results["checks"]["source_class_balance_manifest_v4"] = sc_res
        print(f"  Total samples: {sc_res['total_samples']}")
        print(f"  Cramér's V: {sc_res['cramers_v']} (Gate: <= 0.30)")
        print(f"  Mutual Information: {sc_res['mutual_information_bits']} bits (Gate: <= 0.20 bits)")
        print(f"  Sources with both classes (>= 100): {sc_res['sources_with_both_classes_count']} (Gate: >= 2)")
        print(f"  Status: {'CONFOUNDED (Gate Failed)' if sc_res['is_confounded'] else 'BALANCED'}")
    else:
        results["checks"]["source_class_balance_manifest_v4"] = {"error": f"File not found: {manifest_v4_path}"}

    # 4. Session-Grouped Partitioning Demonstration
    print("\n[4/5] Executing Session-Grouped Partitioning Demonstration...")
    # Construct a synthetic multi-session dataset with correlated frames within session
    demo_records = []
    for s_idx in range(1, 11):
        sess_id = f"SES-2026-07-DEMO-{s_idx:02d}"
        # Base 16-hex-char hash unique to each session (differing by ~32 bits across sessions)
        base_h = hashlib.sha256(f"session_entropy_seed_{s_idx}".encode()).hexdigest()[:16]
        for f_idx in range(1, 6):
            img_id = f"IMG-{s_idx:02d}-{f_idx:02d}"
            # Within session, frames have identical or near-identical dhash (distance 0)
            demo_records.append({
                "image_id": img_id,
                "capture_session_id": sess_id,
                "cluster_id": f"cluster_{s_idx:03d}",
                "location_id": f"HYD-LOC-{((s_idx - 1) % 4) + 1:03d}",
                "md5": hashlib.md5(f"content_{img_id}".encode()).hexdigest(),
                "dhash": base_h,
                "label": 1 if s_idx <= 5 else 0
            })
    demo_df = pd.DataFrame(demo_records)

    tr_df, va_df, ev_df = partition_dataset_with_session_grouping(
        demo_df,
        cluster_col="cluster_id",
        session_col="capture_session_id",
        location_col="location_id",
        train_ratio=0.70,
        val_ratio=0.15,
        eval_ratio=0.15,
        random_seed=42
    )

    print(f"  Demo partition sizes: Train={len(tr_df)}, Val={len(va_df)}, Eval={len(ev_df)}")
    print(f"  Independent evaluation set locked: {bool(ev_df['is_locked_for_tuning'].all())}")

    # 5. Verify Partition Isolation
    print("\n[5/5] Verifying Partition Isolation Across Splits...")
    iso_res = verify_partition_isolation(
        tr_df, va_df, ev_df,
        id_col="image_id",
        md5_col="md5",
        dhash_col="dhash",
        session_col="capture_session_id",
        cluster_col="cluster_id"
    )
    results["checks"]["partition_isolation"] = iso_res
    print(f"  Is partition isolated: {iso_res['is_isolated']}")
    print(f"  Violations count: {iso_res['violations_count']}")
    if iso_res["violations"]:
        print(f"  Violations: {iso_res['violations']}")

    out_json = "reports/phase15/phase15_governance_validation_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nPhase 15 validation results saved strictly to: {out_json}")
    print("=" * 80)
    return results


if __name__ == "__main__":
    run_phase15_validation()
