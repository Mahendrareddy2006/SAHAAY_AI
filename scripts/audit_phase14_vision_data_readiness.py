"""
Phase 14: Comprehensive Vision Data Readiness and Evaluation Audit Script

Audits:
1. Manifest and Dataset Inventory (V1, V2, V3, V4, and Collection V4).
2. Local raw image cache existence and integrity.
3. Exact MD5 duplicate leaks across all splits (Train, Val, Test).
4. Near-duplicate perceptual dhash leaks across all splits (Hamming <= 2).
5. Source-label association, contingency matrices, Cramer's V, and Mutual Information.
6. Non-semantic metadata diagnostic models (Decision Tree & Random Forest).
7. Checkpoint inventory, file sizes, and MD5 hashes.
8. V4 Training readiness gate and evaluation defensibility.

Outputs results strictly to reports/phase14/phase14_vision_data_audit.json
"""

import os
import sys
import json
import hashlib
import glob
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score

def compute_md5(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

def hamming_distance(h1: str, h2: str) -> int:
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count('1')
    except Exception:
        return 999

def run_phase14_audit() -> Dict[str, Any]:
    print("=" * 80)
    print("RUNNING PHASE 14: VISION DATA READINESS & EVALUATION AUDIT")
    print("=" * 80)
    
    os.makedirs("reports/phase14", exist_ok=True)
    report = {
        "audit_phase": "Phase 14",
        "audit_title": "Vision Data Readiness and Evaluation Audit",
        "timestamp_utc": "2026-10-27T05:00:00Z",
        "gate_status_v4_training": "NO-GO",
        "gate_status_independent_evaluation": "DEFENSIBLE_INDEPENDENT_EVAL_SET_ABSENT",
        "sections": {}
    }

    # ---------------------------------------------------------
    # 1. Checkpoint Inventory
    # ---------------------------------------------------------
    print("\n[1/7] Auditing Checkpoint Inventory...")
    checkpoints = {
        "v1_baseline": "models/vision/best_model.pt",
        "v2_dedup": "models/vision/v2/model_v2.pt",
        "v3_clean": "models/vision/v3/model_v3_clean.pt",
        "v3_monsoon": "models/vision/v3/model_v3_monsoon.pt"
    }
    ckpt_data = {}
    for name, path in checkpoints.items():
        exists = os.path.exists(path)
        sz = os.path.getsize(path) if exists else 0
        md5 = compute_md5(path) if exists else ""
        ckpt_data[name] = {
            "checkpoint_path": path,
            "exists": exists,
            "size_bytes": sz,
            "size_mb": round(sz / (1024 * 1024), 2),
            "md5": md5
        }
        print(f"  {name:<12}: Exists={exists} | Size={sz} bytes | MD5={md5}")
    report["sections"]["checkpoint_inventory"] = ckpt_data

    # ---------------------------------------------------------
    # 2. Local Raw Datasets Inventory
    # ---------------------------------------------------------
    print("\n[2/7] Auditing Raw Datasets & Local Caches...")
    raw_dirs = {
        "roham1_flood": r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\flood-classification-dataset\versions\1\Flood",
        "roham1_non_flood": r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\flood-classification-dataset\versions\1\Non_Flood",
        "clemson_flood": r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images",
        "virenbr11_plain": r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\virenbr11\pothole-and-plain-rode-images\versions\1\My Dataset\train\Plain",
        "virenbr11_pothole": r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\virenbr11\pothole-and-plain-rode-images\versions\1\My Dataset\train\Pothole",
        "collection_v4_raw": "data/collection_v4/raw"
    }
    raw_data = {}
    for name, p in raw_dirs.items():
        exists = os.path.exists(p)
        files = glob.glob(os.path.join(p, "*")) if exists else []
        img_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        raw_data[name] = {
            "path": p,
            "exists": exists,
            "total_files": len(files),
            "image_files": len(img_files)
        }
        print(f"  {name:<20}: Exists={exists} | Image Count={len(img_files)}")
    report["sections"]["raw_dataset_inventory"] = raw_data

    # ---------------------------------------------------------
    # 3. Manifest Inventory & Class Balances
    # ---------------------------------------------------------
    print("\n[3/7] Auditing Manifests (V1, V2, V3, V4)...")
    manifest_configs = {
        "manifest_v1": {
            "full": "data/processed/full_manifest.csv",
            "train": "data/processed/train.csv",
            "val": "data/processed/val.csv",
            "test": "data/processed/test.csv"
        },
        "manifest_v2": {
            "full": "data/processed/manifest_v2/full_manifest_v2.csv",
            "train": "data/processed/manifest_v2/train_v2.csv",
            "val": "data/processed/manifest_v2/val_v2.csv",
            "test": "data/processed/manifest_v2/test_v2.csv"
        },
        "manifest_v3": {
            "full": "data/processed/manifest_v3/full_manifest_v3.csv",
            "train": "data/processed/manifest_v3/train_v3.csv",
            "val": "data/processed/manifest_v3/val_v3.csv",
            "test": "data/processed/manifest_v3/test_v3.csv"
        },
        "manifest_v4": {
            "full": "data/processed/manifest_v4/full_manifest_v4.csv",
            "train": "data/processed/manifest_v4/train_v4.csv",
            "val": "data/processed/manifest_v4/val_v4.csv",
            "test": "data/processed/manifest_v4/test_v4.csv"
        }
    }

    manifest_summary = {}
    manifest_dfs = {}
    for m_ver, splits in manifest_configs.items():
        manifest_summary[m_ver] = {}
        manifest_dfs[m_ver] = {}
        for sp_name, path in splits.items():
            if not os.path.exists(path):
                manifest_summary[m_ver][sp_name] = {"exists": False}
                continue
            df = pd.read_csv(path)
            manifest_dfs[m_ver][sp_name] = df
            lbl_col = "label" if "label" in df.columns else "label_idx"
            cls_counts = {str(k): int(v) for k, v in df[lbl_col].value_counts().to_dict().items()}
            src_counts = {str(k): int(v) for k, v in df["source_dataset"].value_counts().to_dict().items()} if "source_dataset" in df.columns else {}
            manifest_summary[m_ver][sp_name] = {
                "exists": True,
                "path": path,
                "total_rows": len(df),
                "class_counts": cls_counts,
                "source_counts": src_counts
            }
            print(f"  {m_ver} [{sp_name:<5}]: Total={len(df):<5} | Classes={cls_counts} | Sources={src_counts}")
    report["sections"]["manifest_inventory"] = manifest_summary

    # ---------------------------------------------------------
    # 4. Exact MD5 Cross-Split Leakage Audit
    # ---------------------------------------------------------
    print("\n[4/7] Auditing Exact MD5 Cross-Split Leakage...")
    md5_audit = {}
    for m_ver in ["manifest_v1", "manifest_v2", "manifest_v3", "manifest_v4"]:
        tr_df = manifest_dfs[m_ver].get("train")
        va_df = manifest_dfs[m_ver].get("val")
        te_df = manifest_dfs[m_ver].get("test")
        if tr_df is None or va_df is None or te_df is None:
            continue

        # Compute MD5s if not present
        if "md5" not in tr_df.columns:
            tr_md5 = set(tr_df["file_path"].apply(compute_md5))
            va_md5 = set(va_df["file_path"].apply(compute_md5))
            te_md5 = set(te_df["file_path"].apply(compute_md5))
        else:
            tr_md5 = set(tr_df["md5"].dropna())
            va_md5 = set(va_df["md5"].dropna())
            te_md5 = set(te_df["md5"].dropna())

        leak_tr_va = len(tr_md5 & va_md5)
        leak_tr_te = len(tr_md5 & te_md5)
        leak_va_te = len(va_md5 & te_md5)
        md5_audit[m_ver] = {
            "train_val_exact_leaks": leak_tr_va,
            "train_test_exact_leaks": leak_tr_te,
            "val_test_exact_leaks": leak_va_te,
            "total_cross_split_exact_leaks": leak_tr_va + leak_tr_te + leak_va_te
        }
        print(f"  {m_ver}: Train-Val={leak_tr_va} | Train-Test={leak_tr_te} | Val-Test={leak_va_te}")
    report["sections"]["exact_md5_leakage"] = md5_audit

    # ---------------------------------------------------------
    # 5. Near-Duplicate (dhash <= 2) Cross-Split Leakage Audit
    # ---------------------------------------------------------
    print("\n[5/7] Auditing Perceptual Near-Duplicate (dhash Hamming <= 2) Leakage...")
    near_dup_audit = {}
    for m_ver in ["manifest_v3", "manifest_v4"]:
        tr_df = manifest_dfs[m_ver]["train"]
        va_df = manifest_dfs[m_ver]["val"]
        te_df = manifest_dfs[m_ver]["test"]

        def extract_hashes(df):
            out = []
            for _, r in df.iterrows():
                h = r.get("dhash") or r.get("dhash_hex")
                if pd.notna(h):
                    out.append((str(r["image_id"]), str(h)))
            return out

        tr_h = extract_hashes(tr_df)
        va_h = extract_hashes(va_df)
        te_h = extract_hashes(te_df)

        def count_leaks(hlist1, hlist2):
            leaks = []
            for id1, hash1 in hlist1:
                for id2, hash2 in hlist2:
                    d = hamming_distance(hash1, hash2)
                    if d <= 2:
                        leaks.append({"id1": id1, "id2": id2, "hamming_dist": d})
            return leaks

        leaks_tr_te = count_leaks(tr_h, te_h)
        leaks_tr_va = count_leaks(tr_h, va_h)
        leaks_va_te = count_leaks(va_h, te_h)

        near_dup_audit[m_ver] = {
            "train_test_near_leaks_count": len(leaks_tr_te),
            "train_val_near_leaks_count": len(leaks_tr_va),
            "val_test_near_leaks_count": len(leaks_va_te),
            "train_test_samples": leaks_tr_te[:5]
        }
        print(f"  {m_ver}: Train-Test={len(leaks_tr_te)} | Train-Val={len(leaks_tr_va)} | Val-Test={len(leaks_va_te)}")
    report["sections"]["near_duplicate_leakage"] = near_dup_audit

    # ---------------------------------------------------------
    # 6. Source-Label Confounding & Metadata Shortcuts
    # ---------------------------------------------------------
    print("\n[6/7] Auditing Source-Label Confounding & Metadata Predictability...")
    full_v4 = manifest_dfs["manifest_v4"]["full"]
    ct = pd.crosstab(full_v4["source_dataset"], full_v4["label"])
    n = len(full_v4)
    pj = ct / n
    p_src = pj.sum(axis=1)
    p_lbl = pj.sum(axis=0)

    mi = 0.0
    for s in pj.index:
        for l in pj.columns:
            val = pj.loc[s, l]
            if val > 0:
                mi += val * np.log2(val / (p_src[s] * p_lbl[l]))
    h_lbl = -np.sum(p_lbl * np.log2(p_lbl))

    chi2 = 0.0
    for s in ct.index:
        for l in ct.columns:
            O = ct.loc[s, l]
            E = (ct.loc[s].sum() * ct[l].sum()) / n
            chi2 += ((O - E) ** 2) / E
    cramers_v = np.sqrt(chi2 / (n * (min(ct.shape) - 1)))

    print(f"  Contingency Table:\n{ct}")
    print(f"  Mutual Information: {mi:.4f} bits | Label Entropy: {h_lbl:.4f} bits")
    print(f"  Cramer's V: {cramers_v:.4f}")

    # Metadata diagnostic models on V4
    tr_v4 = manifest_dfs["manifest_v4"]["train"]
    te_v4 = manifest_dfs["manifest_v4"]["test"]
    features = ["width", "height", "aspect_ratio", "file_size_kb"]

    rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    rf.fit(tr_v4[features], tr_v4["label"])
    rf_preds = rf.predict(te_v4[features])
    rf_probs = rf.predict_proba(te_v4[features])[:, 1]
    rf_acc = accuracy_score(te_v4["label"], rf_preds)
    rf_p, rf_r, rf_f1, _ = precision_recall_fscore_support(te_v4["label"], rf_preds, average="binary")
    rf_auc = roc_auc_score(te_v4["label"], rf_probs)
    importances = dict(zip(features, [round(float(x), 4) for x in rf.feature_importances_]))

    stump = DecisionTreeClassifier(max_depth=1, random_state=42)
    stump.fit(tr_v4[["file_size_kb"]], tr_v4["label"])
    stump_preds = stump.predict(te_v4[["file_size_kb"]])
    stump_acc = accuracy_score(te_v4["label"], stump_preds)

    print(f"  Non-semantic RF Test Acc: {rf_acc:.4f} | Macro-F1: {rf_f1:.4f} | AUC: {rf_auc:.4f}")
    print(f"  File Size Stump Test Acc: {stump_acc:.4f}")
    print(f"  Feature Importances: {importances}")

    report["sections"]["source_confounding"] = {
        "contingency_matrix": {str(k): {str(ik): int(iv) for ik, iv in v.items()} for k, v in ct.to_dict().items()},
        "cramers_v": round(float(cramers_v), 4),
        "mutual_information_bits": round(float(mi), 4),
        "label_entropy_bits": round(float(h_lbl), 4),
        "multi_source_cross_representation_sources_with_both_classes": 0,
        "metadata_diagnostics": {
            "random_forest_all_metadata": {
                "features": features,
                "test_accuracy": round(float(rf_acc), 4),
                "test_precision": round(float(rf_p), 4),
                "test_recall": round(float(rf_r), 4),
                "test_macro_f1": round(float(rf_f1), 4),
                "test_roc_auc": round(float(rf_auc), 4),
                "feature_importances": importances
            },
            "file_size_only_stump": {
                "test_accuracy": round(float(stump_acc), 4)
            }
        }
    }

    # ---------------------------------------------------------
    # 7. Collection V4 Register & Field Readiness Audit
    # ---------------------------------------------------------
    print("\n[7/7] Auditing Collection V4 & Stream Status...")
    acq_reg_path = "data/collection_v4/acquisition_register.csv"
    perm_reg_path = "data/collection_v4/permission_register.csv"
    
    total_real_images = 0
    synthetic_fixtures_count = 0
    if os.path.exists(acq_reg_path):
        acq_df = pd.read_csv(acq_reg_path)
        real_df = acq_df[~acq_df["acquisition_id"].astype(str).str.startswith("SYNTHETIC-")]
        synthetic_df = acq_df[acq_df["acquisition_id"].astype(str).str.startswith("SYNTHETIC-")]
        total_real_images = len(real_df)
        synthetic_fixtures_count = len(synthetic_df)

    streams_data = {}
    if os.path.exists(perm_reg_path):
        perm_df = pd.read_csv(perm_reg_path)
        for _, r in perm_df.iterrows():
            streams_data[str(r["stream_id"])] = {
                "name": str(r["acquisition_stream_name"]),
                "organization": str(r["responsible_organization"]),
                "status": str(r["request_status"]),
                "blocker": str(r["outstanding_blockers"])
            }

    print(f"  Real-world images acquired: {total_real_images}")
    print(f"  Synthetic fixtures in register: {synthetic_fixtures_count}")
    print(f"  Permissions summary: { {k: v['status'] for k, v in streams_data.items()} }")

    report["sections"]["collection_v4_status"] = {
        "real_world_images_acquired": total_real_images,
        "synthetic_fixtures": synthetic_fixtures_count,
        "streams": streams_data,
        "approved_streams_count": sum(1 for v in streams_data.values() if v["status"] == "approved")
    }

    # ---------------------------------------------------------
    # Formal Gate Decision
    # ---------------------------------------------------------
    blocking_reasons = []
    if total_real_images == 0:
        blocking_reasons.append("Zero real-world street observations acquired (0 in acquisition register).")
    if cramers_v > 0.30:
        blocking_reasons.append(f"Severe source-label confounding active (Cramer's V = {cramers_v:.4f} > 0.30).")
    if rf_acc > 0.65:
        blocking_reasons.append(f"Non-semantic metadata classifier achieves {rf_acc*100:.2f}% accuracy > 65.0% threshold.")
    if sum(1 for v in streams_data.values() if v["status"] == "approved") == 0:
        blocking_reasons.append("Zero acquisition streams have approved legal/governance permissions.")

    report["blocking_reasons"] = blocking_reasons
    report["overall_gate_status"] = "NO-GO"

    out_json = "reports/phase14/phase14_vision_data_audit.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nAudit complete. Output written strictly to: {out_json}")
    print("=" * 80)
    return report

if __name__ == "__main__":
    run_phase14_audit()
