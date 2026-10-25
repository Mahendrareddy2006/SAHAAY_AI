"""
Sahaay AI - Train Controlled Model Baselines V3 (Phase 3)
Trains two models on the shortcut-resistant, hard-negative balanced dataset V3:
1. Model V3 Clean: Standard augmentation on balanced V3 split.
2. Model V3 Monsoon: Realistic degradation (blur, rain spray, contrast attenuation).

Preserves historical artifacts:
- models/vision/best_model.pt (V1)
- models/vision/v2/model_v2.pt (V2)
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath("src"))

from sahaay.config import VisionModelConfig
from sahaay.vision.train import train_flood_model
from sahaay.vision.transforms import get_train_transforms, get_monsoon_train_transforms

def run_training():
    train_csv = os.path.join("data", "processed", "manifest_v3", "train_v3.csv")
    val_csv = os.path.join("data", "processed", "manifest_v3", "val_v3.csv")
    v3_dir = os.path.join("models", "vision", "v3")
    os.makedirs(v3_dir, exist_ok=True)

    # 1. Train Model V3 Clean
    print("\n" + "=" * 65)
    print("TRAINING MODEL V3 CLEAN (Consistently Preprocessed Baseline)")
    print("=" * 65)
    config_clean = VisionModelConfig(
        model_name="mobilenet_v3_small",
        model_version="3.0.0-clean-balanced",
        epochs=5,
        batch_size=32,
        learning_rate=3e-4,
        random_seed=42,
        checkpoint_dir=v3_dir
    )

    clean_meta = train_flood_model(
        train_csv=train_csv,
        val_csv=val_csv,
        output_dir=v3_dir,
        config=config_clean,
        train_transforms=get_train_transforms(224)
    )

    clean_raw_ckpt = os.path.join(v3_dir, "best_model.pt")
    clean_target_ckpt = os.path.join(v3_dir, "model_v3_clean.pt")
    if os.path.exists(clean_raw_ckpt):
        if os.path.exists(clean_target_ckpt):
            os.remove(clean_target_ckpt)
        os.rename(clean_raw_ckpt, clean_target_ckpt)
    clean_meta["checkpoint_file"] = clean_target_ckpt

    clean_meta_path = os.path.join(v3_dir, "model_v3_clean_metadata.json")
    with open(clean_meta_path, "w", encoding="utf-8") as f:
        json.dump(clean_meta, f, indent=2)
    print(f"Model V3 Clean saved to: {clean_target_ckpt}")

    # 2. Train Model V3 Monsoon-Augmented
    print("\n" + "=" * 65)
    print("TRAINING MODEL V3 MONSOON (Monsoon Degradation & Blur Augmented)")
    print("=" * 65)
    config_monsoon = VisionModelConfig(
        model_name="mobilenet_v3_small",
        model_version="3.0.0-monsoon-robust",
        epochs=5,
        batch_size=32,
        learning_rate=3e-4,
        random_seed=42,
        checkpoint_dir=v3_dir
    )

    monsoon_meta = train_flood_model(
        train_csv=train_csv,
        val_csv=val_csv,
        output_dir=v3_dir,
        config=config_monsoon,
        train_transforms=get_monsoon_train_transforms(224)
    )

    monsoon_raw_ckpt = os.path.join(v3_dir, "best_model.pt")
    monsoon_target_ckpt = os.path.join(v3_dir, "model_v3_monsoon.pt")
    if os.path.exists(monsoon_raw_ckpt):
        if os.path.exists(monsoon_target_ckpt):
            os.remove(monsoon_target_ckpt)
        os.rename(monsoon_raw_ckpt, monsoon_target_ckpt)
    monsoon_meta["checkpoint_file"] = monsoon_target_ckpt

    monsoon_meta_path = os.path.join(v3_dir, "model_v3_monsoon_metadata.json")
    with open(monsoon_meta_path, "w", encoding="utf-8") as f:
        json.dump(monsoon_meta, f, indent=2)
    print(f"Model V3 Monsoon saved to: {monsoon_target_ckpt}")

if __name__ == "__main__":
    run_training()
