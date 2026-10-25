"""
Sahaay AI - Forensic Provenance and Duplicate Audit Script
Performs complete forensic verification of dataset splits, image paths, MD5 checksums,
duplicate detection across splits, and evaluation consistency.
"""

import os
import hashlib
import json
import pandas as pd
from PIL import Image
from collections import Counter, defaultdict

def compute_md5(file_path: str) -> str:
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def compute_dhash(image_path: str, hash_size: int = 8) -> str:
    """Computes difference hash (perceptual hash) to detect near-duplicates."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            
        difference = []
        for row in range(hash_size):
            for col in range(hash_size):
                pixel_left = pixels[row * (hash_size + 1) + col]
                pixel_right = pixels[row * (hash_size + 1) + col + 1]
                difference.append(pixel_left > pixel_right)
                
        decimal_value = 0
        hex_string = []
        for index, value in enumerate(difference):
            if value:
                decimal_value += 2 ** (index % 8)
            if (index % 8) == 7:
                hex_string.append(hex(decimal_value)[2:].rjust(2, '0'))
                decimal_value = 0
        return "".join(hex_string)
    except Exception:
        return "error"

def main():
    train_path = os.path.join("data", "processed", "train.csv")
    val_path = os.path.join("data", "processed", "val.csv")
    test_path = os.path.join("data", "processed", "test.csv")
    
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)
    test_df = pd.read_csv(test_path)
    
    print("=== 1. SPLIT SUMMARY & PROVENANCE ===")
    for name, df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        print(f"\n{name} Split:")
        print(f"  Row count: {len(df)}")
        print(f"  Source datasets: {df['source_dataset'].value_counts().to_dict()}")
        print(f"  Labels: {df['label_str'].value_counts().to_dict()}")
        # Check path roots
        roots = set(os.path.dirname(os.path.dirname(p)) for p in df["file_path"])
        print(f"  Path root: {roots}")

    all_paths = pd.concat([train_df["file_path"], val_df["file_path"], test_df["file_path"]]).tolist()
    total_images = len(all_paths)
    
    print("\n=== 2. DATASET INCLUSION AUDIT ===")
    has_clemson = any("hhrclemson" in p for p in all_paths)
    has_floodnet = any("FloodNet" in p for p in all_paths)
    has_eu = any("eu-flood" in p for p in all_paths)
    all_roham1 = all("roham1" in p for p in all_paths)
    print(f"Total images across all splits: {total_images}")
    print(f"Images originating from roham1/flood-classification-dataset: {sum('roham1' in p for p in all_paths)} / {total_images}")
    print(f"Images originating from hhrclemson/flooding-image-dataset: {sum('hhrclemson' in p for p in all_paths)} / {total_images}")
    print(f"Images originating from FloodNet: {sum('FloodNet' in p for p in all_paths)} / {total_images}")
    print(f"Images originating from eu-flood-dataset: {sum('eu-flood' in p for p in all_paths)} / {total_images}")
    
    print("\n=== 3. EXACT DUPLICATE (MD5) AUDIT ===")
    md5_by_split = {"train": {}, "val": {}, "test": {}}
    all_md5_map = defaultdict(list)
    
    for split_name, df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        print(f"Computing MD5 hashes for {split_name} ({len(df)} images)...")
        for idx, row in df.iterrows():
            fpath = row["file_path"]
            h = compute_md5(fpath)
            md5_by_split[split_name][fpath] = h
            all_md5_map[h].append((split_name, row["image_id"], row["label_str"], fpath))
            
    unique_md5s = len(all_md5_map)
    print(f"\nTotal image instances: {total_images}")
    print(f"Total unique MD5 hashes: {unique_md5s}")
    
    # Check within-split and cross-split duplicates
    exact_duplicates = {h: items for h, items in all_md5_map.items() if len(items) > 1}
    print(f"Exact duplicate clusters found: {len(exact_duplicates)}")
    
    cross_split_duplicates = []
    within_split_duplicates = []
    
    for h, items in exact_duplicates.items():
        splits_involved = set(item[0] for item in items)
        if len(splits_involved) > 1:
            cross_split_duplicates.append((h, items))
        else:
            within_split_duplicates.append((h, items))
            
    print(f"  - Cross-split exact duplicates: {len(cross_split_duplicates)}")
    print(f"  - Within-split exact duplicates: {len(within_split_duplicates)}")
    if cross_split_duplicates:
        print("  Sample cross-split duplicate:", cross_split_duplicates[0])

    print("\n=== 4. NEAR-DUPLICATE (PERCEPTUAL DHASH) AUDIT ===")
    dhash_map = defaultdict(list)
    for split_name, df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        for idx, row in df.iterrows():
            dh = compute_dhash(row["file_path"])
            dhash_map[dh].append((split_name, row["image_id"], row["label_str"], row["file_path"]))
            
    near_dupe_clusters = {dh: items for dh, items in dhash_map.items() if len(items) > 1 and dh != "error"}
    cross_split_near_dupes = []
    for dh, items in near_dupe_clusters.items():
        splits = set(item[0] for item in items)
        if len(splits) > 1:
            cross_split_near_dupes.append((dh, items))
            
    print(f"Total perceptual hash clusters (>1 image with identical dhash): {len(near_dupe_clusters)}")
    print(f"Cross-split near-duplicate clusters: {len(cross_split_near_dupes)}")
    if cross_split_near_dupes:
        print("Sample cross-split near duplicate cluster:", cross_split_near_dupes[0])

    print("\n=== 5. CHECKPOINT METADATA VERIFICATION ===")
    meta_path = os.path.join("models", "vision", "model_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print("Saved Model Metadata:")
        print(f"  Model Name: {meta.get('model_name')}")
        print(f"  Model Version: {meta.get('model_version')}")
        print(f"  Best Epoch: {meta.get('best_epoch')}")
        print(f"  Best Val Macro-F1: {meta.get('best_val_macro_f1')}")
        print(f"  Total Params: {meta.get('total_parameters')}")
        print(f"  Checkpoint File: {meta.get('checkpoint_file')}")

    print("\n=== 6. IMAGE PROPERTIES & CLASS SHORTCUT AUDIT ===")
    # Analyze image dimensions and aspect ratios between classes
    train_flood = train_df[train_df["label_str"] == "flooded"]
    train_non_flood = train_df[train_df["label_str"] == "not_flooded"]
    
    print("Train Flooded Dimensions (Top 5):")
    flood_dims = Counter(zip(train_flood["width"], train_flood["height"]))
    for d, c in flood_dims.most_common(5):
        print(f"  {d}: {c}")
        
    print("Train Non-Flooded Dimensions (Top 5):")
    non_flood_dims = Counter(zip(train_non_flood["width"], train_non_flood["height"]))
    for d, c in non_flood_dims.most_common(5):
        print(f"  {d}: {c}")

    # Inspect filenames
    print("Sample Flooded Filenames:", train_flood["image_id"].head(5).tolist())
    print("Sample Non-Flooded Filenames:", train_non_flood["image_id"].head(5).tolist())

if __name__ == "__main__":
    main()
