"""
Sahaay AI - Train Clean Baseline V2 (Phase C)
Trains a fresh baseline on the leakage-resistant, group-partitioned manifest V2.
Preserves historical checkpoint models/vision/best_model.pt untouched.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from sahaay.config import VisionModelConfig
from sahaay.vision.train import train_flood_model

def main():
    train_csv = os.path.join("data", "processed", "manifest_v2", "train_v2.csv")
    val_csv = os.path.join("data", "processed", "manifest_v2", "val_v2.csv")
    output_dir = os.path.join("models", "vision", "v2")
    os.makedirs(output_dir, exist_ok=True)
    
    config = VisionModelConfig(
        model_name="mobilenet_v3_small",
        model_version="2.0.0-clean-split",
        epochs=5,
        batch_size=32,
        learning_rate=3e-4,
        random_seed=42,
        checkpoint_dir=output_dir
    )
    
    print("=" * 60)
    print("SAHAAY AI — FLOOD VISION V2 (LEAKAGE-RESISTANT BASELINE)")
    print(f"Architecture: {config.model_name}")
    print(f"Version:      {config.model_version}")
    print(f"Train V2:     {train_csv}")
    print(f"Val V2:       {val_csv}")
    print(f"Output Dir:   {output_dir}")
    print("=" * 60)
    
    metadata = train_flood_model(
        train_csv=train_csv,
        val_csv=val_csv,
        output_dir=output_dir,
        config=config
    )
    
    # Save as model_v2.pt as requested
    old_ckpt = os.path.join(output_dir, "best_model.pt")
    new_ckpt = os.path.join(output_dir, "model_v2.pt")
    if os.path.exists(old_ckpt):
        if os.path.exists(new_ckpt):
            os.remove(new_ckpt)
        os.rename(old_ckpt, new_ckpt)
        print(f"Renamed clean checkpoint to: {new_ckpt}")
        
    meta_path = os.path.join(output_dir, "model_v2_metadata.json")
    metadata["checkpoint_file"] = new_ckpt
    import json
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to: {meta_path}")

if __name__ == "__main__":
    main()
