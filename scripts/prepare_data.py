"""
Sahaay AI - Data Preparation & Stratified Manifest Generator
Validates images, extracts metadata, and generates clean train/val/test CSV manifests.
"""

import os
import glob
import pandas as pd
from PIL import Image
from sklearn.model_selection import train_test_split

DATASET_ROOT = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\flood-classification-dataset\versions\1"
OUTPUT_DIR = r"data\processed"

def inspect_and_collect_images(dataset_root: str):
    print(f"Scanning dataset at: {dataset_root}")
    records = []
    classes = [("Non_Flood", 0, "not_flooded"), ("Flood", 1, "flooded")]
    
    corrupt_count = 0
    for folder_name, label_idx, label_str in classes:
        folder_path = os.path.join(dataset_root, folder_name)
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")
            
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        print(f"Found {len(files)} candidate images in {folder_name}")
        
        for fname in files:
            fpath = os.path.join(folder_path, fname)
            try:
                with Image.open(fpath) as img:
                    w, h = img.size
                    mode = img.mode
                records.append({
                    "image_id": fname,
                    "file_path": fpath,
                    "label_str": label_str,
                    "label_idx": label_idx,
                    "source_dataset": "roham1_binary_ground",
                    "perspective": "ground_level",
                    "width": w,
                    "height": h,
                    "mode": mode
                })
            except Exception as e:
                corrupt_count += 1
                print(f"Skipping corrupt image {fname}: {e}")
                
    print(f"Validation complete: {len(records)} usable images, {corrupt_count} corrupt images.")
    return pd.DataFrame(records)

def create_stratified_splits(df: pd.DataFrame, output_dir: str, seed: int = 42):
    os.makedirs(output_dir, exist_ok=True)
    
    # 70% train, 30% temp (which will be split into 15% val, 15% test)
    train_df, temp_df = train_test_split(
        df,
        test_size=0.30,
        random_state=seed,
        stratify=df["label_idx"]
    )
    
    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.50,
        random_state=seed,
        stratify=temp_df["label_idx"]
    )
    
    print("\n--- Split Summary ---")
    print(f"Train Set: {len(train_df)} rows ({train_df['label_str'].value_counts().to_dict()})")
    print(f"Val Set:   {len(val_df)} rows ({val_df['label_str'].value_counts().to_dict()})")
    print(f"Test Set:  {len(test_df)} rows ({test_df['label_str'].value_counts().to_dict()})")
    
    # Verify zero overlap
    train_ids = set(train_df["image_id"])
    val_ids = set(val_df["image_id"])
    test_ids = set(test_df["image_id"])
    
    assert len(train_ids.intersection(val_ids)) == 0, "Train and Val overlap detected!"
    assert len(train_ids.intersection(test_ids)) == 0, "Train and Test overlap detected!"
    assert len(val_ids.intersection(test_ids)) == 0, "Val and Test overlap detected!"
    print("Zero overlap verification passed: Train, Val, and Test are strictly disjoint.")
    
    train_path = os.path.join(output_dir, "train.csv")
    val_path = os.path.join(output_dir, "val.csv")
    test_path = os.path.join(output_dir, "test.csv")
    full_manifest_path = os.path.join(output_dir, "full_manifest.csv")
    
    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)
    df.to_csv(full_manifest_path, index=False)
    
    print(f"\nManifests saved to:")
    print(f" - {train_path}")
    print(f" - {val_path}")
    print(f" - {test_path}")
    print(f" - {full_manifest_path}")

def main():
    df = inspect_and_collect_images(DATASETSET_ROOT if 'DATASETSET_ROOT' in locals() else DATASET_ROOT)
    create_stratified_splits(df, OUTPUT_DIR)

if __name__ == "__main__":
    main()
