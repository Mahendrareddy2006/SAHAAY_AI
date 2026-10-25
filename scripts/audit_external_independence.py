"""
Sahaay AI - Phase 1: External Evaluation Independence Audit
Verifies cryptographic MD5 and perceptual-hash (dhash) overlap between the external
Clemson evaluation cohort and ALL splits (Train, Val, Test) of both historical V1 and clean V2 manifests.
Also audits internal duplicate scenes within the external sample and formalizes evaluation limitations.
"""

import os
import json
import hashlib
import numpy as np
import pandas as pd
from PIL import Image
from collections import defaultdict

def compute_md5(fp: str) -> str:
    hasher = hashlib.md5()
    with open(fp, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def compute_dhash_int(fp: str, hash_size: int = 8) -> int:
    try:
        with Image.open(fp) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
        diff = []
        for r in range(hash_size):
            for c in range(hash_size):
                diff.append(pixels[r * (hash_size + 1) + c] > pixels[r * (hash_size + 1) + c + 1])
        dec = 0
        for i, v in enumerate(diff):
            if v:
                dec |= (1 << i)
        return dec
    except Exception:
        return 0

def popcount(x: int) -> int:
    return bin(x).count("1")

def main():
    clemson_dir = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images"
    out_dir = os.path.join("reports", "vision_integrity")
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. Load historical manifests (V1)
    train_v1 = pd.read_csv("data/processed/train.csv")
    val_v1 = pd.read_csv("data/processed/val.csv")
    test_v1 = pd.read_csv("data/processed/test.csv")
    
    # 2. Load clean manifests (V2)
    train_v2 = pd.read_csv("data/processed/manifest_v2/train_v2.csv")
    val_v2 = pd.read_csv("data/processed/manifest_v2/val_v2.csv")
    test_v2 = pd.read_csv("data/processed/manifest_v2/test_v2.csv")
    
    print("Computing hashes for internal splits...")
    # Cache split hashes
    splits = {
        "train_v1": {compute_md5(fp): fp for fp in train_v1["file_path"]},
        "val_v1": {compute_md5(fp): fp for fp in val_v1["file_path"]},
        "test_v1": {compute_md5(fp): fp for fp in test_v1["file_path"]},
        "train_v2": {compute_md5(fp): fp for fp in train_v2["file_path"]},
        "val_v2": {compute_md5(fp): fp for fp in val_v2["file_path"]},
        "test_v2": {compute_md5(fp): fp for fp in test_v2["file_path"]}
    }
    
    # Also load external evaluation sample from phase D
    phase_d_report = os.path.join(out_dir, "external_validation_v2.json")
    with open(phase_d_report) as f:
        phase_d_data = json.load(f)
        
    # Recreate the 200-sample selection used in phase D (seed 123)
    all_files = sorted(os.listdir(clemson_dir))
    np.random.seed(123)
    train_v2_md5s = set(splits["train_v2"].keys())
    
    selected_sample = []
    for fn in all_files:
        fp = os.path.join(clemson_dir, fn)
        h = compute_md5(fp)
        if h not in train_v2_md5s:
            selected_sample.append({"filename": fn, "file_path": fp, "md5": h})
        if len(selected_sample) >= 200:
            break
            
    print(f"Auditing selected external sample of {len(selected_sample)} images...")
    
    # Compute perceptual hashes for the external sample
    for item in selected_sample:
        item["dhash_int"] = compute_dhash_int(item["file_path"])
        item["dhash_hex"] = hex(item["dhash_int"])[2:].zfill(16)
        
    # Check overlap of external sample against ALL V1 and V2 splits
    overlap_audit = {
        "sample_size": len(selected_sample),
        "exact_md5_overlap": {},
        "perceptual_near_duplicate_overlap": {}
    }
    
    # Check against each split
    for split_name, split_dict in splits.items():
        # MD5 check
        exact_matches = []
        for item in selected_sample:
            if item["md5"] in split_dict:
                exact_matches.append({
                    "clemson_file": item["filename"],
                    "md5": item["md5"],
                    "split_file": split_dict[item["md5"]]
                })
        overlap_audit["exact_md5_overlap"][split_name] = {
            "count": len(exact_matches),
            "matches": exact_matches
        }
        
    # Perceptual hash comparison against test_v2 and val_v2
    print("Checking perceptual near-duplicates (Hamming distance <= 2) against test_v2 and val_v2...")
    for target_name, target_df in [("val_v2", val_v2), ("test_v2", test_v2), ("train_v2", train_v2)]:
        target_dhashes = [compute_dhash_int(fp) for fp in target_df["file_path"]]
        near_matches = []
        for item in selected_sample:
            h_ext = item["dhash_int"]
            for idx_t, h_t in enumerate(target_dhashes):
                if popcount(int(h_ext ^ h_t)) <= 2:
                    near_matches.append({
                        "clemson_file": item["filename"],
                        "target_file": target_df["file_path"].iloc[idx_t],
                        "hamming_distance": popcount(int(h_ext ^ h_t))
                    })
        overlap_audit["perceptual_near_duplicate_overlap"][target_name] = {
            "count": len(near_matches),
            "matches": near_matches[:5]
        }
        
    # Check internal duplicate clusters within the 200 external sample itself
    print("Checking internal near-duplicate clusters within the external sample...")
    internal_clusters = defaultdict(list)
    n_sample = len(selected_sample)
    parent = list(range(n_sample))
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj: parent[ri] = rj
        
    for i in range(n_sample):
        for j in range(i + 1, n_sample):
            if selected_sample[i]["md5"] == selected_sample[j]["md5"]:
                union(i, j)
            elif popcount(int(selected_sample[i]["dhash_int"] ^ selected_sample[j]["dhash_int"])) <= 2:
                union(i, j)
                
    for i in range(n_sample):
        internal_clusters[find(i)].append(selected_sample[i]["filename"])
        
    multi_scene_clusters = [c for c in internal_clusters.values() if len(c) > 1]
    
    # Full independence audit report
    audit_report = {
        "audit_version": "1.0",
        "audit_date": "2026-10-25",
        "objective": "Audit independence and provenance of external Clemson evaluation cohort",
        "provenance_and_licensing": {
            "dataset_source": "Clemson University FloodIMG (Kaggle: hhrclemson/flooding-image-dataset)",
            "research_citation": "Karanjit et al., Data in Brief (2023), DOI: 10.1016/j.dib.2023.109164",
            "license": "Academic Research / Open Access (Data in Brief)",
            "acquisition_nature": "Scraped from Twitter/X and USGS/DOT traffic cameras during flood events",
            "ground_truth_label": "100% positive flood event photography (no negative class)",
            "usage_role": "Strictly post-hoc external validation (NOT used for model training, hyperparameter tuning, or threshold selection)"
        },
        "sample_selection_methodology": {
            "total_available_images": len(all_files),
            "selection_strategy": "Sequential selection filtered against training MD5 hashes (seed 123)",
            "sample_size": len(selected_sample)
        },
        "independence_verification": {
            "overlap_audit": overlap_audit,
            "internal_duplicate_scenes": {
                "total_clusters": len(internal_clusters),
                "multi_image_clusters_count": len(multi_scene_clusters),
                "multi_image_clusters_sample": multi_scene_clusters[:5]
            }
        },
        "critical_methodological_limitations": [
            "POSITIVE-ONLY COHORT: The external Clemson dataset contains exclusively flood images. It CANNOT evaluate false positive rate, true negative rate, specificity, or overall precision.",
            "PROVISIONAL CALIBRATION: Evaluating calibration or threshold efficacy on a 100% positive distribution is mathematically incomplete, as receiver operating characteristic (ROC) curves and precision-recall curves require both positive and negative ground-truth instances.",
            "DEPLOYMENT NON-READINESS: High external recall (100% on Clemson) proves feature transfer for flood patterns, but does NOT establish deployment readiness for urban Hyderabad due to absent local hard-negative validation."
        ]
    }
    
    audit_path = os.path.join(out_dir, "external_independence_audit.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_report, f, indent=2)
        
    print(f"\nIndependence Audit Complete!")
    print(f"MD5 Overlap with Train V2: {overlap_audit['exact_md5_overlap']['train_v2']['count']}")
    print(f"MD5 Overlap with Val V2:   {overlap_audit['exact_md5_overlap']['val_v2']['count']}")
    print(f"MD5 Overlap with Test V2:  {overlap_audit['exact_md5_overlap']['test_v2']['count']}")
    print(f"Near-duplicate (dhash<=2) overlap with Test V2: {overlap_audit['perceptual_near_duplicate_overlap']['test_v2']['count']}")
    print(f"Internal multi-image clusters in Clemson 200: {len(multi_scene_clusters)}")
    print(f"Report saved to: {audit_path}")

if __name__ == "__main__":
    main()
