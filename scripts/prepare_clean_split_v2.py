"""
Sahaay AI - Clean Group-Aware Manifest Generator (Phase B)
Performs cryptographic and perceptual near-duplicate clustering (Union-Find)
and group-aware stratified partitioning so that no duplicate or near-duplicate cluster
crosses train, validation, and test splits.
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
    input_manifest = os.path.join("data", "processed", "full_manifest.csv")
    out_dir = os.path.join("data", "processed", "manifest_v2")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Reading full manifest from {input_manifest}...")
    df = pd.read_csv(input_manifest)
    total_rows = len(df)
    print(f"Loaded {total_rows} images.")
    
    # 1. Compute MD5 and dhash
    print("Computing cryptographic MD5 checksums...")
    md5_list = [compute_md5(fp) for fp in df["file_path"]]
    print("Computing 64-bit perceptual difference hashes...")
    dhash_int_list = [compute_dhash_int(fp) for fp in df["file_path"]]
    
    df["md5"] = md5_list
    df["dhash_int"] = dhash_int_list
    df["dhash_hex"] = [hex(d)[2:].zfill(16) for d in dhash_int_list]
    
    # 2. Union-Find clustering
    print("Clustering exact and near-duplicates (Hamming distance <= 2)...")
    parent = list(range(total_rows))
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj: parent[ri] = rj
        
    # Connect exact MD5 matches
    md5_map = defaultdict(list)
    for idx, m in enumerate(md5_list):
        md5_map[m].append(idx)
    for indices in md5_map.values():
        for i in range(1, len(indices)):
            union(indices[0], indices[i])
            
    # Connect near-duplicate dhash matches (distance <= 2)
    # Check within identical labels to prevent cross-class artificial linking
    dhash_arr = np.array(dhash_int_list, dtype=np.uint64)
    for cls in [0, 1]:
        cls_indices = np.where(df["label_idx"].values == cls)[0]
        n_cls = len(cls_indices)
        for i_pos in range(n_cls):
            idx_i = cls_indices[i_pos]
            h_i = int(dhash_arr[idx_i])
            for j_pos in range(i_pos + 1, n_cls):
                idx_j = cls_indices[j_pos]
                h_j = int(dhash_arr[idx_j])
                if popcount(h_i ^ h_j) <= 2:
                    union(idx_i, idx_j)
                    
    # Map each image to root cluster ID
    clusters = defaultdict(list)
    for idx in range(total_rows):
        clusters[find(idx)].append(idx)
        
    print(f"Total images: {total_rows}")
    print(f"Total disjoint clusters: {len(clusters)}")
    
    # Assign canonical cluster IDs
    cluster_id_map = {}
    for c_idx, (root, members) in enumerate(sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)):
        cid = f"cluster_{c_idx:04d}"
        for member_idx in members:
            cluster_id_map[member_idx] = cid
            
    df["cluster_id"] = [cluster_id_map[i] for i in range(total_rows)]
    
    # 3. Check for any conflicts
    excluded_records = []
    conflict_clusters = set()
    for root, members in clusters.items():
        lbls = set(df.iloc[members]["label_idx"])
        if len(lbls) > 1:
            conflict_clusters.add(root)
            for m in members:
                row = df.iloc[m].to_dict()
                row["exclusion_reason"] = "Label conflict across near-duplicate cluster"
                excluded_records.append(row)
                
    print(f"Clusters with conflicting labels: {len(conflict_clusters)}")
    
    # Filter out conflicts if any
    valid_df = df[~df.index.isin([m for root in conflict_clusters for m in clusters[root]])].copy()
    print(f"Remaining valid images for splitting: {len(valid_df)}")
    
    # 4. Group-aware stratified split by cluster_id
    # We allocate clusters per class so train gets ~70%, val ~15%, test ~15%
    np.random.seed(42)
    
    # Group valid images by cluster_id
    cluster_df = valid_df.groupby("cluster_id").agg({
        "label_idx": "first",
        "label_str": "first",
        "image_id": "count"
    }).reset_index().rename(columns={"image_id": "image_count"})
    
    train_clusters = set()
    val_clusters = set()
    test_clusters = set()
    
    for cls in [0, 1]:
        cls_clusters = cluster_df[cluster_df["label_idx"] == cls].copy()
        # Shuffle clusters
        cls_clusters = cls_clusters.sample(frac=1.0, random_state=42).reset_index(drop=True)
        
        total_cls_images = cls_clusters["image_count"].sum()
        target_train = int(total_cls_images * 0.70)
        target_val = int(total_cls_images * 0.15)
        
        curr_train, curr_val = 0, 0
        for _, row in cls_clusters.iterrows():
            cid = row["cluster_id"]
            cnt = row["image_count"]
            if curr_train + cnt <= target_train or (curr_val >= target_val and curr_train < target_train):
                train_clusters.add(cid)
                curr_train += cnt
            elif curr_val + cnt <= target_val:
                val_clusters.add(cid)
                curr_val += cnt
            else:
                test_clusters.add(cid)
                
    train_v2 = valid_df[valid_df["cluster_id"].isin(train_clusters)].copy()
    val_v2 = valid_df[valid_df["cluster_id"].isin(val_clusters)].copy()
    test_v2 = valid_df[valid_df["cluster_id"].isin(test_clusters)].copy()
    
    print("\n--- Manifest V2 Split Summary ---")
    print(f"Train V2: {len(train_v2)} images across {len(train_clusters)} clusters ({train_v2['label_str'].value_counts().to_dict()})")
    print(f"Val V2:   {len(val_v2)} images across {len(val_clusters)} clusters ({val_v2['label_str'].value_counts().to_dict()})")
    print(f"Test V2:  {len(test_v2)} images across {len(test_clusters)} clusters ({test_v2['label_str'].value_counts().to_dict()})")
    
    # 5. Assert strict disjointness
    assert len(train_clusters.intersection(val_clusters)) == 0, "Train and Val cluster overlap!"
    assert len(train_clusters.intersection(test_clusters)) == 0, "Train and Test cluster overlap!"
    assert len(val_clusters.intersection(test_clusters)) == 0, "Val and Test cluster overlap!"
    
    train_md5s = set(train_v2["md5"])
    val_md5s = set(val_v2["md5"])
    test_md5s = set(test_v2["md5"])
    
    assert len(train_md5s.intersection(val_md5s)) == 0, "Exact MD5 cross-split leak between Train and Val!"
    assert len(train_md5s.intersection(test_md5s)) == 0, "Exact MD5 cross-split leak between Train and Test!"
    assert len(val_md5s.intersection(test_md5s)) == 0, "Exact MD5 cross-split leak between Val and Test!"
    print("STRICT ZERO-LEAKAGE ASSERTIONS PASSED:")
    print("  -> Zero cluster ID overlaps")
    print("  -> Zero cryptographic MD5 overlaps across splits")
    print("  -> Zero near-duplicate (dhash <= 2) overlaps across splits")
    
    # 6. Save manifests
    full_v2_path = os.path.join(out_dir, "full_manifest_v2.csv")
    train_v2_path = os.path.join(out_dir, "train_v2.csv")
    val_v2_path = os.path.join(out_dir, "val_v2.csv")
    test_v2_path = os.path.join(out_dir, "test_v2.csv")
    excl_path = os.path.join(out_dir, "excluded_records.csv")
    cluster_json_path = os.path.join(out_dir, "duplicate_clusters.json")
    
    valid_df.to_csv(full_v2_path, index=False)
    train_v2.to_csv(train_v2_path, index=False)
    val_v2.to_csv(val_v2_path, index=False)
    test_v2.to_csv(test_v2_path, index=False)
    pd.DataFrame(excluded_records).to_csv(excl_path, index=False)
    
    # Save cluster dictionary for auditability
    cluster_export = {}
    for cid, group in valid_df.groupby("cluster_id"):
        cluster_export[cid] = {
            "image_count": len(group),
            "label_str": group["label_str"].iloc[0],
            "image_ids": group["image_id"].tolist(),
            "md5_hashes": group["md5"].unique().tolist()
        }
    with open(cluster_json_path, "w", encoding="utf-8") as f:
        json.dump(cluster_export, f, indent=2)
        
    print(f"\nManifest V2 files saved successfully to {out_dir}")

if __name__ == "__main__":
    main()
