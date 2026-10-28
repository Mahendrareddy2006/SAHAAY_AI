"""
Sahaay AI - Phase 16 Readiness Report Generator
(scripts/generate_phase16_readiness_report.py)

Executes the comprehensive Phase 16 dataset readiness audit and evaluation protection controls.
Outputs:
- reports/phase16/phase16_readiness_report.json
- reports/phase16/evaluation_set_metadata.json
"""

import os
import sys
import json
import pandas as pd

from sahaay.data_collection_v4.operations import (
    generate_phase16_readiness_audit,
    EvaluationSetProtectionGuard,
    EvaluationSplitMetadata,
)


def main():
    print("=" * 80)
    print("SAHAAY AI — PHASE 16: ACQUISITION OPERATIONS & EVALUATION CONTROLS AUDIT")
    print("=" * 80)

    out_dir = os.path.join("reports", "phase16")
    os.makedirs(out_dir, exist_ok=True)

    # 1. Generate Evaluation Set Metadata Lockfile for Manifest V4 Test Split
    test_csv = os.path.join("data", "processed", "manifest_v4", "test_v4.csv")
    eval_meta_path = os.path.join(out_dir, "evaluation_set_metadata.json")

    if os.path.exists(test_csv):
        print(f"\n[1/3] Sealing Independent Evaluation Set Metadata Lockfile ({test_csv})...")
        df_test = pd.read_csv(test_csv)
        eval_meta = EvaluationSetProtectionGuard.create_evaluation_split_metadata(
            eval_df=df_test,
            split_id="EVAL-SPLIT-MANIFEST-V4-LOCKED",
            manifest_path=test_csv
        )
        with open(eval_meta_path, "w", encoding="utf-8") as f:
            json.dump(eval_meta.model_dump(), f, indent=2)
        print(f"  Lockfile generated: {eval_meta_path}")
        print(f"  Locked record count: {eval_meta.record_count}")
        print(f"  Manifest SHA-256: {eval_meta.manifest_sha256}")
    else:
        print(f"  Warning: {test_csv} not found. Skipping lockfile generation.")

    # 2. Execute Comprehensive Readiness Audit
    print(f"\n[2/3] Executing Dataset Readiness Audit across Registries and Manifests...")
    audit_results = generate_phase16_readiness_audit(
        permission_register_path="data/collection_v4/permission_register.csv",
        acquisition_register_path="data/collection_v4/acquisition_register.csv",
        annotation_template_path="data/collection_v4/governance_annotation_template.csv",
        manifest_v4_path="data/processed/manifest_v4/full_manifest_v4.csv",
        min_required_real_records=400
    )

    # 3. Save Machine-Readable JSON Report
    report_path = os.path.join(out_dir, "phase16_readiness_report.json")
    print(f"\n[3/3] Saving machine-readable audit report: {report_path}...")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)

    # Print Summary Table
    print("\n" + "=" * 80)
    print("PHASE 16 AUDIT RESULTS SUMMARY")
    print("=" * 80)
    print(f"Overall Status: {audit_results['overall_status']}")
    print(f"V4 Verdict:     {audit_results['v4_training_verdict']}\n")

    print("[Gate Statuses]")
    for g_name, g_info in audit_results["gates"].items():
        st = g_info.get("status", "UNKNOWN")
        print(f"  * {g_name:<35}: {st}")

    print("\n[Provenance Breakdown]")
    prov = audit_results["gates"].get("acquisition_provenance", {})
    counts = prov.get("counts_by_category", {})
    for cat, cnt in counts.items():
        print(f"  - {cat:<35}: {cnt}")

    if audit_results["blocking_reasons"]:
        print("\n[Blocking Reasons]")
        for b in audit_results["blocking_reasons"]:
            print(f"  X {b}")

    if audit_results["advisories"]:
        print("\n[Advisories]")
        for a in audit_results["advisories"]:
            print(f"  ! {a}")

    print("=" * 80)


if __name__ == "__main__":
    main()
